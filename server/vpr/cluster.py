import math

import faiss
import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from tqdm import tqdm

from network import (
    CENTROIDS_PATH, FEATURE_SETTINGS, MAX_CLUSTER_VECTORS, NORMALIZE_PATCHES, NUM_CLUSTERS, SEED,
    DINOv2Backbone, ImageDataset, load_database_df, save_meta,
)

BATCH_SIZE = 32
NUM_WORKERS = 4


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    df = load_database_df()
    paths = df["path"].tolist()
    print(f"{len(paths)} database images")

    loader = DataLoader(ImageDataset(paths), batch_size=BATCH_SIZE, shuffle=False,
                        num_workers=NUM_WORKERS, pin_memory=device.type == "cuda")
    model = DINOv2Backbone().to(device).eval()

    rng = np.random.default_rng(SEED)
    per_image = None
    samples = []

    print("Sampling patch features...")
    with torch.inference_mode(), torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
        for imgs in tqdm(loader):
            feats = model(imgs.to(device, non_blocking=True)).float()  # B, N, D
            if NORMALIZE_PATCHES:
                feats = F.normalize(feats, dim=-1)
            B, N, D = feats.shape
            if per_image is None:
                per_image = min(N, max(8, math.ceil(MAX_CLUSTER_VECTORS / len(paths))))
                print(f"Patches per image: {per_image} (of {N}), dim {D}")
            for b in range(B):
                idx = torch.from_numpy(rng.choice(N, per_image, replace=False)).to(feats.device)
                samples.append(feats[b, idx].cpu().numpy())

    X = np.ascontiguousarray(np.concatenate(samples), dtype=np.float32)
    print(f"Clustering {X.shape[0]} vectors into {NUM_CLUSTERS} clusters...")
    kmeans = faiss.Kmeans(
        X.shape[1], NUM_CLUSTERS, niter=25, verbose=True, seed=SEED,
        max_points_per_centroid=X.shape[0] // NUM_CLUSTERS + 1,  # use all sampled vectors
    )
    kmeans.train(X)

    np.save(CENTROIDS_PATH, kmeans.centroids.astype(np.float32))
    # reset=True: any previously built database is now stale and will be rejected
    save_meta("features", FEATURE_SETTINGS, reset=True)
    print(f"Saved {CENTROIDS_PATH} {kmeans.centroids.shape}. Now run database.py")


if __name__ == "__main__":
    main()

