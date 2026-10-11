import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import math
import queue
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PHONE_PORT = 8000   # the phone app posts scans to http://<this computer's IP>:8000/scan

GRID_SIZE = 120
CELL_SIZE = 8  # Matches the scale of the grid

PALETTE = {
    "Empty": {"color": "#FFFFFF"},
    "Wall": {"color": "#333333"},
    "Stairs": {"color": "#FF9800"},
    "Elevator": {"color": "#00BCD4"},
    "Door": {"color": "#8D6E63"}
}

class MapLocalizationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Architectural Map Wi-Fi Localizer (KNN)")
        self.root.geometry("1050x760")
        self.root.minsize(980, 700)

        self.map_data = {}       # (r, c) -> cell info dictionary
        self.query_scan = {}     # bssid -> rssi float
        self.match_results = []  # List of KNN match results
        self.selected_cell = None

        self.rects = {}          # (r, c) -> canvas rectangle item id
        self.vector_markers = {} # (r, c) -> canvas marker item id
        self.match_markers = {}  # (r, c) -> highlight item id for matches
        self.selection_rect = None

        # Main layout frames
        self.canvas_frame = ttk.Frame(root)
        self.canvas_frame.pack(side=tk.LEFT, padx=15, pady=15)

        self.control_frame = ttk.Frame(root, width=400)
        self.control_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=15, pady=15)

        # Build Canvas for 120x120 grid
        self.canvas = tk.Canvas(
            self.canvas_frame, 
            width=GRID_SIZE * CELL_SIZE, 
            height=GRID_SIZE * CELL_SIZE, 
            bg="white",
            highlightthickness=1,
            highlightbackground="#b0bec5"
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        self.init_grid()
        self.build_controls()
        self.start_phone_listener()

    def init_grid(self):
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                x1 = c * CELL_SIZE
                y1 = r * CELL_SIZE
                x2 = x1 + CELL_SIZE
                y2 = y1 + CELL_SIZE
                rect_id = self.canvas.create_rectangle(
                    x1, y1, x2, y2, 
                    fill="#FFFFFF", 
                    outline="#f0f0f0"
                )
                self.rects[(r, c)] = rect_id

    def build_controls(self):
        # File Loading Frame
        file_frame = ttk.LabelFrame(self.control_frame, text="Localization Inputs", padding=10)
        file_frame.pack(fill=tk.X, pady=5)

        load_map_btn = ttk.Button(file_frame, text="1. Load Enriched Map JSON", command=self.load_enriched_map)
        load_map_btn.pack(fill=tk.X, pady=2)

        self.map_status_lbl = ttk.Label(file_frame, text="Map: No file loaded.", font=("Arial", 9))
        self.map_status_lbl.pack(anchor=tk.W, pady=2)

        load_query_btn = ttk.Button(file_frame, text="2. Load Query Wi-Fi Scan JSON", command=self.load_query_json)
        load_query_btn.pack(fill=tk.X, pady=2)

        self.query_status_lbl = ttk.Label(file_frame, text="Query Scan: No file loaded.", font=("Arial", 9))
        self.query_status_lbl.pack(anchor=tk.W, pady=2)

        # Phone link: scans sent from the phone app arrive here and are run automatically
        phone_frame = ttk.LabelFrame(self.control_frame, text="Phone Link", padding=10)
        phone_frame.pack(fill=tk.X, pady=5)
        self.phone_addr_lbl = ttk.Label(phone_frame, text="Starting…", font=("Arial", 10, "bold"))
        self.phone_addr_lbl.pack(anchor=tk.W, pady=2)
        self.phone_status_lbl = ttk.Label(phone_frame, text="Waiting for a scan from the phone.", font=("Arial", 9))
        self.phone_status_lbl.pack(anchor=tk.W, pady=2)

        # KNN Configuration & Trigger Frame
        knn_frame = ttk.LabelFrame(self.control_frame, text="KNN Matching", padding=10)
        knn_frame.pack(fill=tk.X, pady=5)

        k_box_frame = ttk.Frame(knn_frame)
        k_box_frame.pack(fill=tk.X, pady=2)
        ttk.Label(k_box_frame, text="Neighbors (K):", font=("Arial", 9)).pack(side=tk.LEFT, padx=5)
        
        self.k_spinbox = ttk.Spinbox(k_box_frame, from_=1, to=10, width=5, font=("Arial", 9))
        self.k_spinbox.set(3)
        self.k_spinbox.pack(side=tk.LEFT, padx=5)

        run_knn_btn = ttk.Button(knn_frame, text="Run Localization & Show on Map", command=self.run_knn_matching)
        run_knn_btn.pack(fill=tk.X, pady=5)

        # Results Display Frame
        results_frame = ttk.LabelFrame(self.control_frame, text="Localization Results (KNN)", padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Treeview list for matches
        columns = ("rank", "coord", "type", "distance")
        self.tree = ttk.Treeview(results_frame, columns=columns, show="headings", height=8)
        self.tree.heading("rank", text="Rank")
        self.tree.heading("coord", text="Coordinate (r,c)")
        self.tree.heading("type", text="Type")
        self.tree.heading("distance", text="Distance")
        
        self.tree.column("rank", width=45, anchor=tk.CENTER)
        self.tree.column("coord", width=95, anchor=tk.CENTER)
        self.tree.column("type", width=75, anchor=tk.CENTER)
        self.tree.column("distance", width=85, anchor=tk.CENTER)
        
        self.tree.pack(fill=tk.BOTH, expand=True, pady=5)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # Cell Inspector / Details
        self.inspector_lbl = ttk.Label(results_frame, text="Select a match above to inspect details.", font=("Arial", 9))
        self.inspector_lbl.pack(anchor=tk.W, pady=5)

    def load_enriched_map(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")])
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self.map_data = json.load(f)

                annotated_count = sum(1 for v in self.map_data.values() if isinstance(v, dict) and "bssid_features" in v)
                self.map_status_lbl.config(text=f"Map: Loaded ({annotated_count} annotated cells)")
                self.redraw_canvas()
                messagebox.showinfo("Success", f"Successfully loaded enriched map with {len(self.map_data)} total entries ({annotated_count} with BSSID features).")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load map JSON:\n{e}")

    def load_query_json(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")])
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_list = json.load(f)
                
                # Parse query scan list of {"bssid": ..., "rssi": ...}
                self.query_scan = {item['bssid']: float(item['rssi']) for item in raw_list if 'bssid' in item and 'rssi' in item}
                self.query_status_lbl.config(text=f"Query Scan: Loaded ({len(self.query_scan)} BSSIDs)")
                messagebox.showinfo("Success", f"Successfully loaded query scan with {len(self.query_scan)} Wi-Fi BSSID features.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load query scan JSON:\n{e}")

    def run_knn_matching(self, notify=True):
        if not self.map_data:
            if notify:
                messagebox.showwarning("Warning", "Please load the Enriched Map JSON first.")
            return None
        if not self.query_scan:
            if notify:
                messagebox.showwarning("Warning", "Please load a Query Wi-Fi Scan JSON first.")
            return None

        try:
            k = int(self.k_spinbox.get())
        except ValueError:
            k = 3

        # 1. Gather all unique BSSIDs across query scan and all annotated map cells
        all_bssids = set(self.query_scan.keys())
        map_cells = {}

        for coord_key, cell_info in self.map_data.items():
            if isinstance(cell_info, dict) and "bssid_features" in cell_info:
                r, c = map(int, coord_key.split(","))
                map_cells[(r, c)] = {
                    "type": cell_info.get("type", "Empty"),
                    "features": cell_info["bssid_features"]
                }
                all_bssids.update(cell_info["bssid_features"].keys())

        if not map_cells:
            if notify:
                messagebox.showerror("Error", "No annotated map cells containing 'bssid_features' found in the map dataset.")
            return None

        sorted_bssids = sorted(list(all_bssids))
        query_vector = [self.query_scan.get(b, 0.0) for b in sorted_bssids]

        # 2. Compute Euclidean distance for each map cell
        results = []
        for (r, c), info in map_cells.items():
            features = info["features"]
            cell_vector = [features.get(b, 0.0) for b in sorted_bssids]
            
            distance = math.sqrt(sum((q - c_val) ** 2 for q, c_val in zip(query_vector, cell_vector)))
            results.append({
                "coord": (r, c),
                "type": info["type"],
                "distance": distance
            })

        # 3. Sort by distance ascending and pick top K
        results.sort(key=lambda x: x["distance"])
        self.match_results = results[:k]

        # 4. Populate Treeview
        for row in self.tree.get_children():
            self.tree.delete(row)

        for idx, match in enumerate(self.match_results, 1):
            r, c = match["coord"]
            self.tree.insert("", tk.END, values=(idx, f"({r}, {c})", match["type"], f"{match['distance']:.2f}"))

        self.redraw_canvas()
        if self.match_results:
            # Select top match by default
            self.tree.selection_set(self.tree.get_children()[0])
            top_coord = self.match_results[0]["coord"]
            if notify:
                messagebox.showinfo("Localization Complete", f"Closest match found at coordinate {top_coord} with distance {self.match_results[0]['distance']:.2f}!")
        return self.match_results

    # ---- Phone link -------------------------------------------------------------------------
    # The phone posts the same query-scan list "Load Query Wi-Fi Scan JSON" reads:
    # [{"bssid": "...", "rssi": -58}, ...]. The network thread hands it to
    # the window's thread (tkinter must only be touched from there), which loads it as the query,
    # runs KNN, and replies with the matches.

    def start_phone_listener(self):
        self.phone_inbox = queue.Queue()
        app = self

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._reply(200, {"ok": True})

            def do_POST(self):
                if self.path != "/scan":
                    return self._reply(404, {"error": "POST /scan"})
                try:
                    raw_list = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                    # parsed exactly like load_query_json: a list of {"bssid": ..., "rssi": ...}
                    features = {item['bssid']: float(item['rssi']) for item in raw_list if 'bssid' in item and 'rssi' in item}
                except (ValueError, KeyError, TypeError, AttributeError) as e:
                    return self._reply(400, {"error": f"expected a list of {{'bssid', 'rssi'}}: {e}"})
                done = threading.Event()
                job = {"features": features, "done": done, "result": None}
                app.phone_inbox.put(job)
                done.wait(timeout=10)
                self._reply(200, job["result"] or {"ok": False, "error": "timed out"})

            def log_message(self, *args):
                pass

        try:
            server = ThreadingHTTPServer(("0.0.0.0", PHONE_PORT), Handler)
        except OSError as e:
            self.phone_addr_lbl.config(text=f"Phone link off: port {PHONE_PORT} busy ({e.strerror})")
            return
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.phone_addr_lbl.config(text=f"Phone app address:  {self.local_ip()}:{PHONE_PORT}")
        self.root.after(100, self.check_phone_inbox)

    @staticmethod
    def local_ip():
        """This computer's address on the local network (no traffic is actually sent)."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"
        finally:
            s.close()

    def check_phone_inbox(self):
        try:
            while True:
                job = self.phone_inbox.get_nowait()
                job["result"] = self.handle_phone_scan(job["features"])
                job["done"].set()
        except queue.Empty:
            pass
        self.root.after(100, self.check_phone_inbox)

    def handle_phone_scan(self, features):
        self.query_scan = features
        self.query_status_lbl.config(text=f"Query Scan: From phone ({len(features)} BSSIDs)")
        matches = self.run_knn_matching(notify=False)
        if not matches:
            self.phone_status_lbl.config(text=f"Scan received ({len(features)} BSSIDs) - load a map to run KNN.")
            return {"ok": True, "bssids": len(features), "matches": [], "note": "no map loaded on the computer"}
        r, c = matches[0]["coord"]
        self.phone_status_lbl.config(text=f"Scan received ({len(features)} BSSIDs) - closest ({r}, {c}), "
                                          f"distance {matches[0]['distance']:.2f}")
        return {"ok": True, "bssids": len(features),
                "matches": [{"coord": list(m["coord"]), "type": m["type"], "distance": round(m["distance"], 2)}
                            for m in matches]}

    def redraw_canvas(self):
        # Reset base cell colors
        for rc, rect_id in self.rects.items():
            self.canvas.itemconfig(rect_id, fill="#FFFFFF", outline="#f0f0f0")
        
        # Draw loaded cell types
        for coord_key, cell_info in self.map_data.items():
            parts = coord_key.split(",")
            if len(parts) == 2:
                r, c = int(parts[0]), int(parts[1])
                if (r, c) in self.rects:
                    cell_type = cell_info.get("type", "Empty") if isinstance(cell_info, dict) else cell_info
                    color = PALETTE.get(cell_type, {"color": "#FFFFFF"})["color"]
                    self.canvas.itemconfig(self.rects[(r, c)], fill=color)

        # Clear old markers
        for marker_id in self.vector_markers.values():
            self.canvas.delete(marker_id)
        self.vector_markers.clear()

        for marker_id in self.match_markers.values():
            self.canvas.delete(marker_id)
        self.match_markers.clear()

        if self.selection_rect:
            self.canvas.delete(self.selection_rect)
            self.selection_rect = None

        # Draw standard vector presence indicators (small purple dots)
        for coord_key, cell_info in self.map_data.items():
            if isinstance(cell_info, dict) and "bssid_features" in cell_info:
                parts = coord_key.split(",")
                if len(parts) == 2:
                    r, c = int(parts[0]), int(parts[1])
                    if (r, c) in self.rects:
                        x1 = c * CELL_SIZE + 2
                        y1 = r * CELL_SIZE + 2
                        x2 = x1 + CELL_SIZE - 4
                        y2 = y1 + CELL_SIZE - 4
                        marker_id = self.canvas.create_rectangle(x1, y1, x2, y2, fill="#9C27B0", outline="")
                        self.vector_markers[(r, c)] = marker_id

        # Draw KNN Match Highlights (Distinct Bright Orange/Red Markers & Rings)
        for idx, match in enumerate(self.match_results):
            r, c = match["coord"]
            if (r, c) in self.rects:
                x1 = c * CELL_SIZE - 1
                y1 = r * CELL_SIZE - 1
                x2 = x1 + CELL_SIZE + 2
                y2 = y1 + CELL_SIZE + 2
                
                # Rank 1 gets a prominent red/orange box with border, others get lighter highlight
                color = "#FF3D00" if idx == 0 else "#FFEA00"
                match_id = self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2, fill="#FF9E80" if idx == 0 else "")
                self.match_markers[(r, c)] = match_id

        # Highlight selected cell if active
        if self.selected_cell:
            sr, sc = self.selected_cell
            if (sr, sc) in self.rects:
                x1 = sc * CELL_SIZE
                y1 = sr * CELL_SIZE
                x2 = x1 + CELL_SIZE
                y2 = y1 + CELL_SIZE
                self.selection_rect = self.canvas.create_rectangle(
                    x1, y1, x2, y2, outline="#1E88E5", width=2
                )

    def on_tree_select(self, event):
        selected_items = self.tree.selection()
        if not selected_items:
            return
        item_id = selected_items[0]
        values = self.tree.item(item_id, "values")
        if values:
            rank = values[0]
            coord_str = values[1].strip("()")
            r_str, c_str = coord_str.split(",")
            r, c = int(r_str.strip()), int(c_str.strip())
            match_type = values[2]
            dist = values[3]

            self.selected_cell = (r, c)
            self.inspector_lbl.config(text=f"Rank #{rank} | Coordinate: ({r}, {c})\nType: {match_type} | Distance: {dist}")
            self.redraw_canvas()

    def on_canvas_click(self, event):
        c = event.x // CELL_SIZE
        r = event.y // CELL_SIZE
        if 0 <= r < GRID_SIZE and 0 <= c < CELL_SIZE:
            self.selected_cell = (r, c)
            cell_type = "Unknown"
            coord_key = f"{r},{c}"
            if coord_key in self.map_data:
                info = self.map_data[coord_key]
                cell_type = info.get("type", "Empty") if isinstance(info, dict) else info
            
            self.inspector_lbl.config(text=f"Selected Cell: ({r}, {c}) | Type: {cell_type}")
            self.redraw_canvas()

if __name__ == "__main__":
    root = tk.Tk()
    app = MapLocalizationApp(root)
    root.mainloop()