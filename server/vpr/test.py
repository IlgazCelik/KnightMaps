import os
import faiss
import numpy as np
import torch
from PIL import Image

from network import (
    IMAGE_DIR, INDEX_PATH, PATHS_PATH,
    finalize_descriptors, load_pca, load_vpr_model, preprocess
)

def test_pure_vpr_match(query_image_path):
    """
    Loads a single query image, extracts its descriptor using the exact same model pipeline 
    as knn.py, and queries the FAISS index directly without any GPS filtering or limits.
    """
    # 1. Set up device
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    # 2. Load VPR model, PCA parameters, FAISS index, and database paths
    print("Loading VPR model, PCA, and FAISS index...")
    model = load_vpr_model(device)
    pca = load_pca()
    
    if not os.path.exists(INDEX_PATH):
        raise FileNotFoundError(f"FAISS index not found at: {INDEX_PATH}")
    if not os.path.exists(PATHS_PATH):
        raise FileNotFoundError(f"Database paths file not found at: {PATHS_PATH}")
        
    vlad_index = faiss.read_index(INDEX_PATH)
    database_paths = np.load(PATHS_PATH)
    
    # 3. Load the single query image (using knn.py's load_image style)
    if not os.path.exists(query_image_path):
        raise FileNotFoundError(f"Query image not found at: {query_image_path}")
        
    print(f"Processing query image: {query_image_path}")
    img = Image.open(query_image_path)
    img.load()  # Fully decode to catch corrupt files early
    
    model.eval()
    with torch.inference_mode():
        raw = model(preprocess(img).unsqueeze(0).to(device)).cpu().numpy()
    desc = finalize_descriptors(raw, pca)
    
    k = 1
    sims, idxs = vlad_index.search(desc, k)
    
    matched_idx = int(idxs[0][0])
    similarity = float(sims[0][0])
    distance = 1.0 - similarity
    
    matched_relative_path = str(database_paths[matched_idx])
    matched_full_path = os.path.join(IMAGE_DIR, matched_relative_path)
    
    # 6. Output match result cleanly
    print("\n" + "="*50)
    print("PURE VPR MATCH RESULT (No GPS Limit):")
    print(f"Query Image Path   : {query_image_path}")
    print(f"Matched Image Path : {matched_full_path}")
    print(f"Similarity Score   : {similarity:.4f}")
    print(f"Cosine Distance    : {distance:.4f}")
    print("="*50 + "\n")
    
    return matched_full_path

if __name__ == "__main__":
    QUERY_IMAGE_PATH = os.path.join("uploads/", "WhatsApp Image 2026-10-10 at 17.49.03.jpeg")
    
    try:
        test_pure_vpr_match(QUERY_IMAGE_PATH)
    except Exception as e:
        print(f"Error running test: {e}")