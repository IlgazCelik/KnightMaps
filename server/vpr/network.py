import json
import os

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps
from torch import nn
from sklearn.decomposition import PCA

# Settings
MODEL_TYPE = "dinov2_vitb14"
LAYER = 9
IMAGE_SIZE = (322, 434)          # (H, W), multiples of 14. Use (224, 224) for the old behaviour.
MEAN = (0.485, 0.456, 0.406)     # ImageNet stats, which DINOv2 was trained with
STD = (0.229, 0.224, 0.225)

NUM_CLUSTERS = 64
NORMALIZE_PATCHES = True
ASSIGNMENT = "hard"              # "hard" (AnyLoc default) or "soft"
SOFT_TEMPERATURE = 20.0          # only used when ASSIGNMENT == "soft"
MAX_CLUSTER_VECTORS = 200_000
SEED = 9

PCA_DIM = 2048                   # None disables PCA. Must be < number of database images.
PCA_WHITEN = True

LABELS_CSV = "/home/celik/scripts/knightmaps/scripts/ucfCampusDataset/coords_v2.csv"
IMAGE_DIR = "/home/celik/scripts/knightmaps/scripts/ucfCampusDataset/ucf_streetview_images_v2/"

CENTROIDS_PATH = "cluster_centroids.npy"
PATHS_PATH = "database_paths.npy"
GPS_PATH = "database_gps.npy"
RAW_PATH = "database_raw.npy"
PCA_PATH = "pca.npz"
INDEX_PATH = "vlad_database.index"
META_PATH = "vpr_meta.json"

FEATURE_SETTINGS = {
    "model_type": MODEL_TYPE, "layer": LAYER, "image_size": list(IMAGE_SIZE),
    "mean": list(MEAN), "std": list(STD), "normalize_patches": NORMALIZE_PATCHES,
}
DESCRIPTOR_SETTINGS = {
    **FEATURE_SETTINGS,
    "num_clusters": NUM_CLUSTERS, "assignment": ASSIGNMENT,
    "temperature": SOFT_TEMPERATURE if ASSIGNMENT == "soft" else None,
    "pca_dim": PCA_DIM, "pca_whiten": PCA_WHITEN,
}


# Settings consistency check
def _read_meta():
    if os.path.exists(META_PATH):
        with open(META_PATH) as f:
            return json.load(f)
    return {}


def save_meta(name, settings, reset=False):
    meta = {} if reset else _read_meta()
    meta[name] = json.loads(json.dumps(settings))
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)


def check_meta(name, settings):
    saved = _read_meta().get(name)
    if saved is None:
        raise RuntimeError(f"No saved '{name}' settings in {META_PATH}. Re-run the earlier pipeline steps.")
    current = json.loads(json.dumps(settings))
    if saved != current:
        diff = {k: (saved.get(k), current.get(k)) for k in set(saved) | set(current)
                if saved.get(k) != current.get(k)}
        raise RuntimeError(f"Settings for '{name}' changed since it was built (saved, now): {diff}. "
                           "Rebuild centroids and database.")


# Data helpers
def parse_gps_from_name(path):
    """'<lat>_<lon>_....jpg' -> (lat, lon), or None if it doesn't parse or is out of range."""
    try:
        parts = os.path.splitext(os.path.basename(str(path)))[0].split("_")
        lat, lon = float(parts[0]), float(parts[1])
        if 25.0 <= lat <= 32.0 and -85.0 <= lon <= -75.0:
            return lat, lon
    except Exception:
        pass
    return None


def load_database_df():
    df = pd.read_csv(LABELS_CSV)
    df["path"] = df["path"].astype(str).str.strip()
    ok = df["path"].apply(lambda p: os.path.exists(os.path.join(IMAGE_DIR, p)))
    if (~ok).any():
        print(f"Warning: dropping {(~ok).sum()} rows whose image files are missing.")
        df = df[ok]
    return df.sort_values("path").reset_index(drop=True)


_MEAN_T = torch.tensor(MEAN).view(3, 1, 1)
_STD_T = torch.tensor(STD).view(3, 1, 1)


def preprocess(pil_image):
    """The ONE preprocessing path: database, centroids and server queries must all use this."""
    img = ImageOps.exif_transpose(pil_image).convert("RGB")
    img = img.resize((IMAGE_SIZE[1], IMAGE_SIZE[0]), Image.BICUBIC)
    t = torch.from_numpy(np.asarray(img).copy()).permute(2, 0, 1).float() / 255.0
    return (t - _MEAN_T) / _STD_T


class ImageDataset(torch.utils.data.Dataset):
    def __init__(self, paths, image_dir=IMAGE_DIR):
        self.paths = list(paths)
        self.image_dir = image_dir

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, i):
        return preprocess(Image.open(os.path.join(self.image_dir, self.paths[i])))


# PCA / final descriptor
def fit_pca(raw, dim, whiten, device):
    """Computes PCA in seconds using a randomized solver on the CPU."""
    if hasattr(raw, "cpu"):
        raw = raw.cpu().numpy()
        
    print("Fitting Randomized PCA (fast)...")
    pca = PCA(n_components=dim, whiten=whiten, svd_solver='randomized')
    pca.fit(raw)
    
    mean = pca.mean_.astype(np.float32)
    if whiten:
        proj = (pca.components_ / pca.singular_values_[:, np.newaxis] * np.sqrt(raw.shape[0] - 1)).astype(np.float32)
    else:
        proj = pca.components_.astype(np.float32)
        
    return mean, proj

def load_pca():
    if not os.path.exists(PCA_PATH):
        return None
    z = np.load(PCA_PATH)
    return z["mean"], z["proj"]


def finalize_descriptors(raw, pca):
    """raw VLAD (N, K*D) -> optional PCA(+whiten) -> L2 normalise. Use inner product for search."""
    x = np.asarray(raw, dtype=np.float32)
    if pca is not None:
        mean, proj = pca
        x = (x - mean) @ proj.T
    x = x / np.maximum(np.linalg.norm(x, axis=1, keepdims=True), 1e-12)
    return np.ascontiguousarray(x, dtype=np.float32)


# Model
class DINOv2Backbone(nn.Module):
    """(B, 3, H, W) -> value features of block `layer` as patch tokens (B, N, C)."""

    def __init__(self, model_type: str = MODEL_TYPE, layer: int = LAYER):
        super().__init__()
        self.model = torch.hub.load("facebookresearch/dinov2", model_type)
        assert 0 <= layer < len(self.model.blocks), f"layer must be in [0, {len(self.model.blocks) - 1}]"
        self.layer = layer
        self.model.eval()
        for p in self.model.parameters():
            p.requires_grad = False

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        m = self.model
        tokens = m.prepare_tokens_with_masks(x)
        feats = None
        for i, blk in enumerate(m.blocks):
            if i == self.layer:
                qkv = blk.attn.qkv(blk.norm1(tokens))
                c = qkv.shape[-1] // 3
                feats = qkv[..., 2 * c:]
                break
            tokens = blk(tokens)
        skip = 1 + getattr(m, "num_register_tokens", 0)
        return feats[:, skip:, :]


class AnyLocSoftVLAD(nn.Module):
    """VLAD over patch tokens (B, N, D) -> (B, K*D), intra- then globally L2-normalised."""

    def __init__(self, centroids, assignment: str = ASSIGNMENT,
                 temperature: float = SOFT_TEMPERATURE, normalize_patches: bool = NORMALIZE_PATCHES):
        super().__init__()
        if not isinstance(centroids, torch.Tensor):
            centroids = torch.tensor(np.asarray(centroids), dtype=torch.float32)
        self.register_buffer("centroids", centroids.float())
        self.num_clusters, self.dim = centroids.shape
        self.assignment = assignment
        self.temperature = temperature
        self.normalize_patches = normalize_patches

    @property
    def out_dim(self):
        return self.num_clusters * self.dim

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.dim() == 2:
            x = x.unsqueeze(0)
        x = x.float()
        if self.normalize_patches:
            x = F.normalize(x, p=2, dim=-1)
        c = self.centroids

        d2 = (x ** 2).sum(-1, keepdim=True) - 2 * x @ c.t() + (c ** 2).sum(-1)[None, None, :]
        d2 = d2.clamp_min(0)

        if self.assignment == "hard":
            a = F.one_hot(d2.argmin(-1), self.num_clusters).to(x.dtype)
        else:
            a = F.softmax(-self.temperature * d2, dim=-1)

        vlad = torch.einsum("bnk,bnd->bkd", a, x) - a.sum(1).unsqueeze(-1) * c.unsqueeze(0)
        vlad = F.normalize(vlad, p=2, dim=-1)
        vlad = F.normalize(vlad.flatten(1), p=2, dim=-1)
        return vlad


class knightModel(nn.Module):
    def __init__(self, centroids):
        super().__init__()
        self.backbone = DINOv2Backbone()
        self.vlad = AnyLocSoftVLAD(centroids)

    def forward(self, x):
        return self.vlad(self.backbone(x))


def load_vpr_model(device):
    check_meta("features", FEATURE_SETTINGS)
    centroids = np.load(CENTROIDS_PATH)
    return knightModel(centroids).to(device).eval()