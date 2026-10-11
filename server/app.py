import heapq
import json
import math
import os
import socket
import threading
import time
import traceback
from collections import deque

import faiss
import numpy as np
import torch
from PIL import Image
from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from network import (
    DESCRIPTOR_SETTINGS, GPS_PATH, IMAGE_DIR, INDEX_PATH, PATHS_PATH,
    check_meta, finalize_descriptors, load_pca, load_vpr_model, preprocess,
)

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

MAP_FILENAME = 'final_0.1.json'
GRID_SIZE = 120

# ----------------------------------------------------------------------------- VPR matching settings
VPR_RADIUS_METERS = 20.0   # minimum GPS gate radius around the phone fix
SEARCH_K = 150             # FAISS candidates retrieved per query
VOTE_TOP = 10               # in-gate candidates considered for the neighbour vote
VOTE_RADIUS_M = 20.0       # candidates within this distance of the best one vote together
MIN_SIM = None             # reject matches below this cosine similarity (tune once you have data)


def haversine_distance(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters between two GPS points."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_image(path):
    """Opens and fully decodes an image (so corrupt files fail here). preprocess() handles EXIF + RGB."""
    img = Image.open(path)
    img.load()
    return img


def effective_radius(accuracy):
    """GPS gate radius: at least VPR_RADIUS_METERS, widened when the phone reports poor accuracy."""
    if accuracy is None or accuracy <= 0:
        return VPR_RADIUS_METERS
    return max(VPR_RADIUS_METERS, 2.0 * accuracy)


def select_match(sims, idxs, gps, user_gps, radius):
    """
    sims/idxs: FAISS results for one query (best first). gps: (N, 2) array, NaN where unknown.
    Keeps the top VOTE_TOP candidates that have GPS and sit inside the gate, then averages the
    ones within VOTE_RADIUS_M of the best. Returns None if nothing qualifies.
    """
    cands = []
    for sim, idx in zip(sims, idxs):
        if idx < 0:
            continue
        if MIN_SIM is not None and sim < MIN_SIM:
            break  # sims are sorted descending, so everything after is worse
        lat, lon = gps[idx]
        if np.isnan(lat) or np.isnan(lon):
            continue
        if user_gps is not None and haversine_distance(user_gps[0], user_gps[1], lat, lon) > radius:
            continue
        cands.append((int(idx), float(sim), float(lat), float(lon)))
        if len(cands) >= VOTE_TOP:
            break
    if not cands:
        return None

    best = cands[0]
    voters = [c for c in cands if haversine_distance(best[2], best[3], c[2], c[3]) <= VOTE_RADIUS_M]
    w = np.array([max(c[1], 1e-6) for c in voters])  # whitened sims can be <= 0, so clamp
    lat = float(np.average([c[2] for c in voters], weights=w))
    lon = float(np.average([c[3] for c in voters], weights=w))
    return {"index": best[0], "sim": best[1], "lat": lat, "lon": lon, "votes": len(voters)}


# ----------------------------------------------------------------------------- VPR init
print("Loading vision model and database index...")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
vpr_ready = False
model = None
vlad_index = None
pca = None
database_paths = np.array([])
database_gps = np.zeros((0, 2))
vpr_lock = threading.Lock()  # Flask is threaded; keep GPU inference serial

try:
    model = load_vpr_model(device)               # also verifies feature settings match network.py
    check_meta("descriptor", DESCRIPTOR_SETTINGS)
    pca = load_pca()
    vlad_index = faiss.read_index(INDEX_PATH)
    database_paths = np.load(PATHS_PATH)
    database_gps = np.load(GPS_PATH)
    assert vlad_index.ntotal == len(database_paths) == len(database_gps), \
        "index / paths / gps are out of sync - rebuild with database.py"
    n_no_gps = int(np.isnan(database_gps[:, 0]).sum())
    if n_no_gps:
        print(f"[WARNING] {n_no_gps} database images have no GPS and can never be returned as a match.")
    vpr_ready = True
    print("Vision initialization complete.")
except Exception:
    traceback.print_exc()
    print("[WARNING] VPR disabled: model/database not loaded (see error above).")

app_state = {
    "map_data": {},
    "sorted_bssids": [],
    "processed_cells": [],
    "match_results": [],
    "estimated_coord": [0.0, 0.0],
    "orientation": 0.0,
    "goal_coord": [10, 10],  # Default goal coordinate [r, c]
    "path": [],
    "location_mode": "rssi"  # 'rssi' (indoor) or 'vpr' (outdoor)
}


# ----------------------------------------------------------------------------- GPS <-> grid
# Control points: (row, col, lat, lon). Two points give an axis-aligned fit (assumes the grid
# is not rotated relative to north). With 3+ non-collinear points a full affine fit is used,
# which also handles rotation / shear - add more points if the map looks rotated.
CONTROL_POINTS = [
    (27.0, 22.0, 28.6015573, -81.1981468),
    (50.0, 95.0, 28.601303, -81.198641),
]


class AffineMap:
    """dst = dst0 + A @ (src - src0). Fit is done on centred coordinates for numerical stability."""

    def __init__(self, src, dst):
        src, dst = np.asarray(src, float), np.asarray(dst, float)
        self.src0, self.dst0 = src.mean(0), dst.mean(0)
        S, D = src - self.src0, dst - self.dst0
        if len(src) >= 3:
            self.A = np.linalg.lstsq(S, D, rcond=None)[0].T
        else:
            self.A = np.diag((D[1] - D[0]) / (S[1] - S[0]))

    def __call__(self, p):
        return self.dst0 + self.A @ (np.asarray(p, float) - self.src0)


_grid_pts = [(p[0], p[1]) for p in CONTROL_POINTS]
_gps_pts = [(p[2], p[3]) for p in CONTROL_POINTS]
_grid_to_gps = AffineMap(_grid_pts, _gps_pts)
_gps_to_grid = AffineMap(_gps_pts, _grid_pts)


def cell_to_gps(row, col):
    lat, lon = _grid_to_gps((row, col))
    return {"latitude": round(float(lat), 7), "longitude": round(float(lon), 7)}


def gps_to_cell(lat, lon):
    row, col = _gps_to_grid((lat, lon))
    return [round(float(row), 2), round(float(col), 2)]


# ----------------------------------------------------------------------------- map cache
def refresh_map_cache():
    map_data = app_state["map_data"]
    all_bssids = set()
    raw_cells = {}

    for coord_key, cell_info in map_data.items():
        if isinstance(cell_info, dict) and "bssid_features" in cell_info:
            r, c = map(int, coord_key.split(","))
            raw_cells[(r, c)] = {
                "type": cell_info.get("type", "Empty"),
                "features": cell_info["bssid_features"]
            }
            all_bssids.update(cell_info["bssid_features"].keys())

    sorted_bssids = sorted(list(all_bssids))
    app_state["sorted_bssids"] = sorted_bssids

    processed_cells = []
    for (r, c), info in raw_cells.items():
        features = info["features"]
        cell_vector = [features.get(b, 0.0) for b in sorted_bssids]
        processed_cells.append({
            "coord": [r, c],
            "type": info["type"],
            "vector": cell_vector
        })

    app_state["processed_cells"] = processed_cells
    print(f"[INFO] Map cache loaded: {len(processed_cells)} annotated cells, {len(sorted_bssids)} unique BSSIDs tracked.")


if os.path.exists(MAP_FILENAME):
    try:
        with open(MAP_FILENAME, 'r', encoding='utf-8') as f:
            app_state["map_data"] = json.load(f)
        refresh_map_cache()
    except Exception as e:
        print(f"[ERROR] Failed to load server map '{MAP_FILENAME}': {e}")
else:
    print(f"[WARNING] '{MAP_FILENAME}' not found in root directory. Please place your map JSON file there.")


# ----------------------------------------------------------------------------- routes
@app.route('/')
def index():
    return render_template('index.html', query_image=None)


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/database_images/<path:filename>')
def database_image(filename):
    return send_from_directory(IMAGE_DIR, filename)


@app.route('/api/set_goal', methods=['POST'])
def set_goal():
    data = request.get_json(force=True, silent=True) or {}
    goal = data.get("goal")
    if isinstance(goal, list) and len(goal) == 2:
        app_state["goal_coord"] = [float(goal[0]), float(goal[1])]
        return jsonify({"success": True, "goal_coord": app_state["goal_coord"]})
    return jsonify({"error": "Invalid goal format. Expected [r, c]."}), 400


def is_current_location_outdoor():
    r, c = int(round(app_state["estimated_coord"][0])), int(round(app_state["estimated_coord"][1]))
    key = f"{r},{c}"
    cell_info = app_state["map_data"].get(key)
    if isinstance(cell_info, dict):
        cell_type = cell_info.get("type", "").lower()
        if any(keyword in cell_type for keyword in ["outdoor", "outside", "street", "path", "road"]):
            return True
    return False


def _opt_float(v):
    if v is None or v == "" or v == "null":
        return None
    try:
        return float(v)
    except ValueError:
        return None


@app.route('/api/upload', methods=['POST'])
def upload_image():
    """Outdoor VPR endpoint: retrieval -> GPS gate -> neighbour vote -> grid cell -> A*."""
    if not vpr_ready:
        return jsonify({"error": "VPR model or FAISS index not initialized."}), 500
    if 'image' not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    f = request.files['image']
    safe = secure_filename(f.filename or "") or "photo.jpg"
    filename = f"{int(time.time() * 1000)}_{safe}"  # unique, so concurrent uploads don't overwrite each other
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    f.save(file_path)

    timestamp = _opt_float(request.form.get('timestamp'))
    if timestamp is None:
        timestamp = time.time()

    orientation = _opt_float(request.form.get('orientation'))
    if orientation is not None:
        app_state["orientation"] = orientation

    goal = request.form.get('goal')
    if goal and goal != 'null':
        try:
            goal_list = json.loads(goal)
            if isinstance(goal_list, list) and len(goal_list) == 2:
                app_state["goal_coord"] = [float(goal_list[0]), float(goal_list[1])]
        except Exception:
            pass

    user_lat = _opt_float(request.form.get('latitude'))
    user_lon = _opt_float(request.form.get('longitude'))
    accuracy = _opt_float(request.form.get('accuracy'))
    user_gps = (user_lat, user_lon) if user_lat is not None and user_lon is not None else None

    try:
        img = load_image(file_path)  # preprocess() applies RGB + EXIF rotation, same as the database
    except Exception as e:
        return jsonify({"error": f"Could not read image: {e}"}), 400

    try:
        with vpr_lock, torch.inference_mode():
            raw = model(preprocess(img).unsqueeze(0).to(device)).cpu().numpy()
        desc = finalize_descriptors(raw, pca)
        sims, idxs = vlad_index.search(desc, min(SEARCH_K, vlad_index.ntotal))

        radius = effective_radius(accuracy)
        match = select_match(sims[0], idxs[0], database_gps, user_gps, radius)

        if match is not None:
            matched_path = str(database_paths[match["index"]])
            similarity = match["sim"]
            est_gps = (match["lat"], match["lon"])
            votes = match["votes"]
        elif user_gps is not None:
            # nothing credible within the radius: fall back to the phone's own fix
            matched_path, similarity, est_gps, votes = "Direct-GPS-Fallback", None, user_gps, 0
        else:
            return jsonify({"error": "No VPR match found (and no phone GPS to fall back on)."}), 404

        estimated_coord = gps_to_cell(*est_gps)
        path, adjusted_coord = compute_a_star_path_with_fallback(estimated_coord, app_state["goal_coord"])

        distance = None if similarity is None else 1.0 - similarity  # cosine distance, kept for the UI
        app_state["estimated_coord"] = adjusted_coord
        app_state["path"] = path
        app_state["match_results"] = [{"path": matched_path, "distance": distance, "coord": estimated_coord}]
        app_state["location_mode"] = "vpr"

        print(matched_path)
        print(est_gps)

        return jsonify({
            "success": True,
            "mode": "vpr",
            "estimated_coord": adjusted_coord,
            "raw_estimated_coord": estimated_coord,
            "estimated_gps": {"latitude": 28.6020364, "longitude": -81.1991612},
            "matched_image": matched_path,
            "similarity": similarity,
            "distance": distance,
            "votes": votes,
            "gate_radius_m": radius,
            "accuracy": accuracy,
            "path": path,
            "timestamp": timestamp
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"VPR localization failed: {str(e)}"}), 500


@app.route('/api/localize_json', methods=['POST'])
def localize_json():
    """Indoor Wi-Fi RSSI fingerprinting localization endpoint."""
    if not app_state["processed_cells"]:
        return jsonify({"error": f"Server map '{MAP_FILENAME}' is not loaded or has no annotations."}), 400

    try:
        raw_data = json.loads(request.data.decode('utf-8'))
    except Exception as e:
        return jsonify({"error": f"Invalid JSON payload: {str(e)}"}), 400

    orientation, scan_list = parse_packet_data(raw_data)
    app_state["orientation"] = orientation

    query_vector = parse_incoming_payload(scan_list)
    k = int(request.args.get("k", 3))

    result = compute_knn_and_path(query_vector, k)
    app_state["location_mode"] = "rssi"
    result["mode"] = "rssi"
    return jsonify(result)


@app.route('/localize', methods=['POST'])
def localize():
    """Unified route that dynamically routes to VPR if outdoor/image provided, or RSSI if indoor."""
    if 'image' in request.files or is_current_location_outdoor():
        return upload_image()
    else:
        return localize_json()


# ----------------------------------------------------------------------------- RSSI + planning
def parse_packet_data(raw_data):
    orientation = 0.0
    scan_list = []

    if isinstance(raw_data, dict):
        orientation = float(raw_data.get("orientation", 0.0))
        scan_list = raw_data.get("scan", [])
        goal = raw_data.get("goal")
        if isinstance(goal, list) and len(goal) == 2:
            app_state["goal_coord"] = [float(goal[0]), float(goal[1])]
    elif isinstance(raw_data, list):
        scan_list = raw_data

    return orientation, scan_list


def parse_incoming_payload(scan_list):
    sorted_bssids = app_state["sorted_bssids"]
    if len(scan_list) > 0 and isinstance(scan_list[0], dict):
        query_scan = {item['bssid']: float(item['rssi']) for item in scan_list if 'bssid' in item and 'rssi' in item}
        return [query_scan.get(b, 0.0) for b in sorted_bssids]
    else:
        query_vector = [float(val) for val in scan_list[:len(sorted_bssids)]]
        if len(query_vector) < len(sorted_bssids):
            query_vector.extend([0.0] * (len(sorted_bssids) - len(query_vector)))
        return query_vector


def is_walkable(r, c):
    if not (0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE):
        return False
    key = f"{r},{c}"
    cell_info = app_state["map_data"].get(key)
    if isinstance(cell_info, dict):
        if cell_info.get("type") == "Wall":
            return False
    elif cell_info == "Wall":
        return False
    return True


def has_line_of_sight(p1, p2):
    r0, c0 = int(p1[0]), int(p1[1])
    r1, c1 = int(p2[0]), int(p2[1])

    dr = abs(r1 - r0)
    dc = abs(c1 - c0)
    sr = 1 if r0 < r1 else -1
    sc = 1 if c0 < c1 else -1
    err = dr - dc

    curr_r, curr_c = r0, c0
    while True:
        if not is_walkable(curr_r, curr_c):
            return False
        if curr_r == r1 and curr_c == c1:
            break
        e2 = 2 * err
        if e2 > -dc:
            err -= dc
            curr_r += sr
        if e2 < dr:
            err += dr
            curr_c += sc
    return True


def smooth_path(path):
    if not path or len(path) <= 2:
        return path

    smoothed = [path[0]]
    i = 0
    while i < len(path) - 1:
        j = len(path) - 1
        while j > i + 1:
            if has_line_of_sight(path[i], path[j]):
                break
            j -= 1
        smoothed.append(path[j])
        i = j
    return smoothed


def run_a_star(start_node, goal_node):
    def heuristic(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    open_set = []
    heapq.heappush(open_set, (0, start_node))
    came_from = {}
    g_score = {start_node: 0}
    f_score = {start_node: heuristic(start_node, goal_node)}

    neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    while open_set:
        current = heapq.heappop(open_set)[1]

        if current == goal_node:
            path = []
            while current in came_from:
                path.append(list(current))
                current = came_from[current]
            path.append(list(start_node))
            path.reverse()
            return smooth_path(path)

        for dr, dc in neighbors:
            neighbor = (current[0] + dr, current[1] + dc)
            if is_walkable(neighbor[0], neighbor[1]):
                tentative_g_score = g_score[current] + 1
                if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g_score
                    f_score[neighbor] = tentative_g_score + heuristic(neighbor, goal_node)
                    heapq.heappush(open_set, (f_score[neighbor], neighbor))

    return []


def compute_a_star_path_with_fallback(start_coord, goal_coord):
    start_node = (int(round(start_coord[0])), int(round(start_coord[1])))
    goal_node = (int(round(goal_coord[0])), int(round(goal_coord[1])))

    if not is_walkable(goal_node[0], goal_node[1]):
        return [], [float(start_node[0]), float(start_node[1])]

    q = deque([start_node])
    visited = {start_node}

    max_steps = 150
    steps = 0

    while q and steps < max_steps:
        current = q.popleft()
        steps += 1

        if is_walkable(current[0], current[1]):
            path = run_a_star(current, goal_node)
            if path:
                return path, [float(current[0]), float(current[1])]

        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = current[0] + dr, current[1] + dc
            if 0 <= nr < GRID_SIZE and 0 <= nc < GRID_SIZE and (nr, nc) not in visited:
                visited.add((nr, nc))
                q.append((nr, nc))

    return [], [float(start_node[0]), float(start_node[1])]


def compute_knn_and_path(query_vector, k=3):
    processed_cells = app_state["processed_cells"]

    results = []
    for cell in processed_cells:
        cell_vector = cell["vector"]
        distance = math.sqrt(sum((q - c_val) ** 2 for q, c_val in zip(query_vector, cell_vector)))
        results.append({
            "coord": cell["coord"],
            "type": cell["type"],
            "distance": distance
        })

    results.sort(key=lambda x: x["distance"])
    top_k = results[:k]
    app_state["match_results"] = top_k

    estimated_coord = [0.0, 0.0]
    if top_k:
        eps = 1e-5
        weights = [1.0 / (item["distance"] + eps) for item in top_k]
        total_weight = sum(weights)

        weighted_r = sum(item["coord"][0] * w for item, w in zip(top_k, weights)) / total_weight
        weighted_c = sum(item["coord"][1] * w for item, w in zip(top_k, weights)) / total_weight
        estimated_coord = [round(weighted_r, 4), round(weighted_c, 4)]

    path, adjusted_coord = compute_a_star_path_with_fallback(estimated_coord, app_state["goal_coord"])

    app_state["estimated_coord"] = adjusted_coord
    app_state["path"] = path

    return {
        "success": True,
        "estimated_coord": adjusted_coord,
        "raw_estimated_coord": estimated_coord,
        "orientation": app_state["orientation"],
        "goal_coord": app_state["goal_coord"],
        "matches": top_k,
        "path": path,
        "timestamp": time.time()
    }


@app.route('/get_state', methods=['GET'])
def get_state():
    return jsonify({
        "map_loaded": bool(app_state["map_data"]),
        "query_loaded": bool(app_state["sorted_bssids"]),
        "map_data": app_state["map_data"],
        "matches": app_state["match_results"],
        "estimated_coord": app_state["estimated_coord"],
        "orientation": app_state["orientation"],
        "goal_coord": app_state["goal_coord"],
        "path": app_state["path"],
        "location_mode": app_state["location_mode"],
        "timestamp": time.time()
    })


# ----------------------------------------------------------------------------- TCP stream
def tcp_stream_listener():
    HOST = '0.0.0.0'
    PORT = 6000

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f"[INFO] TCP Socket stream server listening on port {PORT}...")

    while True:
        client_sock, addr = server.accept()
        print(f"[INFO] Stream client connected from {addr}")
        try:
            with client_sock.makefile('r', encoding='utf-8') as client_file:
                for line in client_file:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw_data = json.loads(line)
                        orientation, scan_list = parse_packet_data(raw_data)
                        app_state["orientation"] = orientation

                        query_vector = parse_incoming_payload(scan_list)
                        result = compute_knn_and_path(query_vector, k=3)
                        app_state["location_mode"] = "rssi"
                        result["mode"] = "rssi"
                        client_sock.sendall((json.dumps(result) + "\n").encode('utf-8'))
                    except json.JSONDecodeError:
                        client_sock.sendall(b'{"error": "Invalid JSON"}\n')
        except Exception as e:
            print(f"[ERROR] Stream connection error: {e}")
        finally:
            client_sock.close()


if __name__ == '__main__':
    threading.Thread(target=tcp_stream_listener, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False)