import os

import faiss
import numpy as np
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from network import (
    DESCRIPTOR_SETTINGS, FEATURE_SETTINGS, GPS_PATH, INDEX_PATH, PATHS_PATH, PCA_DIM, PCA_PATH,
    PCA_WHITEN, RAW_PATH, ImageDataset, check_meta, finalize_descriptors, fit_pca,
    load_database_df, load_vpr_model, save_meta,
)

BATCH_SIZE = 32
NUM_WORKERS = 4


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    df = load_database_df()  # only the annotated images
    paths = df["path"].tolist()
    print(f"{len(paths)} annotated database images")

    check_meta("features", FEATURE_SETTINGS)
    model = load_vpr_model(device)

    loader = DataLoader(ImageDataset(paths), batch_size=BATCH_SIZE, shuffle=False,
                        num_workers=NUM_WORKERS, pin_memory=device.type == "cuda")
    chunks = []
    print("Extracting global VLAD descriptors...")
    with torch.inference_mode(), torch.autocast(device_type=device.type, enabled=device.type == "cuda"):
        for imgs in tqdm(loader):
            chunks.append(model(imgs.to(device, non_blocking=True)).float().cpu().numpy().astype(np.float32))
    raw = np.concatenate(chunks)
    print(f"Raw descriptors: {raw.shape}")

    del model
    if device.type == "cuda":
        torch.cuda.empty_cache()

    gps = df[["lat", "lon"]].to_numpy(dtype=np.float64)  # from annotations.json

    if PCA_DIM is not None:
        print(f"Fitting PCA{'+whitening' if PCA_WHITEN else ''} -> {PCA_DIM} dims...")
        mean, proj = fit_pca(raw, PCA_DIM, PCA_WHITEN, device)
        np.savez(PCA_PATH, mean=mean, proj=proj)
        pca = (mean, proj)
        print(f"Projection: {proj.shape}")
    else:
        if os.path.exists(PCA_PATH):
            os.remove(PCA_PATH)
        pca = None

    desc = finalize_descriptors(raw, pca)
    index = faiss.IndexFlatIP(desc.shape[1])
    index.add(desc)

    np.save(PATHS_PATH, np.array(paths))
    np.save(GPS_PATH, gps)
    np.save(RAW_PATH, raw)
    faiss.write_index(index, INDEX_PATH)
    save_meta("descriptor", DESCRIPTOR_SETTINGS)
    print(f"Done. {index.ntotal} images indexed, descriptor dim {desc.shape[1]}.")


if __name__ == "__main__":
    main()