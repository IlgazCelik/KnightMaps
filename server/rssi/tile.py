import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import json
import csv

GRID_SIZE = 120
CELL_SIZE = 8  # Matches the scale of the grid

PALETTE = {
    "Empty": {"color": "#FFFFFF"},
    "Wall": {"color": "#333333"},
    "Stairs": {"color": "#FF9800"},
    "Elevator": {"color": "#00BCD4"},
    "Door": {"color": "#8D6E63"}
}

class VectorAnnotatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Architectural Map Wi-Fi Vector Annotator")
        self.root.geometry("1020x780")
        self.root.minsize(950, 720)

        self.grid_data = {}             # (r, c) -> tile type string
        self.vector_data = {}            # (r, c) -> full list of BSSID RSSI values
        self.scan_library = {}           # scan_id -> full list of BSSID RSSI values from CSV
        self.bssid_columns = []          # List of all BSSID feature columns
        self.original_bssid_features = {}# (r, c) -> original bssid_features dict from map JSON
        self.cell_scan_map = {}          # (r, c) -> assigned scan_id string pointer
        self.selected_cell = None

        self.rects = {}                  # (r, c) -> canvas rectangle item id
        self.vector_markers = {}         # (r, c) -> canvas marker item id
        self.selection_rect = None

        # Main layout frames
        self.canvas_frame = ttk.Frame(root)
        self.canvas_frame.pack(side=tk.LEFT, padx=15, pady=15)

        self.control_frame = ttk.Frame(root, width=380)
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
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)

        self.init_grid()
        self.build_controls()

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
        file_frame = ttk.LabelFrame(self.control_frame, text="Dataset Sources", padding=8)
        file_frame.pack(fill=tk.X, pady=3)

        load_map_btn = ttk.Button(file_frame, text="1. Load Map JSON", command=self.load_map_json)
        load_map_btn.pack(fill=tk.X, pady=2)

        self.map_status_label = ttk.Label(file_frame, text="Map: No file loaded.", font=("Arial", 9))
        self.map_status_label.pack(anchor=tk.W, pady=2)

        load_csv_btn = ttk.Button(file_frame, text="2. Load Wi-Fi Scans CSV", command=self.load_wifi_csv)
        load_csv_btn.pack(fill=tk.X, pady=2)

        self.csv_status_label = ttk.Label(file_frame, text="Scans CSV: No file loaded.", font=("Arial", 9))
        self.csv_status_label.pack(anchor=tk.W, pady=2)

        self.vector_count_label = ttk.Label(file_frame, text="Total mapped vectors: 0", font=("Arial", 9, "bold"))
        self.vector_count_label.pack(anchor=tk.W, pady=2)

        # Map Editor / Brush Palette Frame
        brush_frame = ttk.LabelFrame(self.control_frame, text="Map Editor Brush (Click & Drag to Paint)", padding=8)
        brush_frame.pack(fill=tk.X, pady=3)

        self.brush_var = tk.StringVar(value="Wall")
        brush_select_frame = ttk.Frame(brush_frame)
        brush_select_frame.pack(fill=tk.X, pady=2)

        for t in PALETTE.keys():
            rb = ttk.Radiobutton(brush_select_frame, text=t, variable=self.brush_var, value=t)
            rb.pack(side=tk.LEFT, padx=4)

        # Assignment Frame
        self.inspector_frame = ttk.LabelFrame(self.control_frame, text="Cell Inspector & Vector Editor", padding=8)
        self.inspector_frame.pack(fill=tk.BOTH, expand=True, pady=3)

        self.cell_info_lbl = ttk.Label(self.inspector_frame, text="Click a cell on the map to inspect vectors.", font=("Arial", 9, "bold"))
        self.cell_info_lbl.pack(anchor=tk.W, pady=3)

        ttk.Label(self.inspector_frame, text="Select Scan ID to assign to cell:", font=("Arial", 9)).pack(anchor=tk.W, pady=1)
        
        self.scan_id_var = tk.StringVar()
        self.scan_combobox = ttk.Combobox(self.inspector_frame, textvariable=self.scan_id_var, state="readonly", font=("Arial", 9))
        self.scan_combobox.pack(fill=tk.X, pady=3)

        assign_btn = ttk.Button(self.inspector_frame, text="Assign Scan to Selected Cell", command=self.assign_scan_to_cell)
        assign_btn.pack(fill=tk.X, pady=3)

        unassign_btn = ttk.Button(self.inspector_frame, text="Remove Scan from Cell", command=self.remove_scan_from_cell)
        unassign_btn.pack(fill=tk.X, pady=3)

        ttk.Label(self.inspector_frame, text="Or edit vector values (comma-separated):", font=("Arial", 9)).pack(anchor=tk.W, pady=1)
        
        self.vector_entry_var = tk.StringVar()
        self.vector_entry = ttk.Entry(self.inspector_frame, textvariable=self.vector_entry_var, font=("Arial", 9))
        self.vector_entry.pack(fill=tk.X, pady=3)

        apply_btn = ttk.Button(self.inspector_frame, text="Save Vector for Cell", command=self.apply_vector)
        apply_btn.pack(fill=tk.X, pady=3)

        self.vector_status_lbl = ttk.Label(self.inspector_frame, text="", font=("Arial", 8, "italic"), foreground="green")
        self.vector_status_lbl.pack(anchor=tk.W, pady=2)

        # Export Button
        export_btn = ttk.Button(self.control_frame, text="Export Enriched JSON", command=self.export_json)
        export_btn.pack(fill=tk.X, pady=5)

    def load_map_json(self):
        file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")])
        if file_path:
            try:
                print(f"\n[DEBUG] --- Loading Map JSON: {file_path} ---")
                with open(file_path, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                
                self.grid_data = {}
                self.vector_data = {}
                self.cell_scan_map = {}
                self.original_bssid_features = {}

                pointer_count = 0
                for key, val in raw_data.items():
                    parts = key.split(",")
                    if len(parts) == 2:
                        r, c = int(parts[0]), int(parts[1])
                        if isinstance(val, dict):
                            self.grid_data[(r, c)] = val.get("type", "Empty")
                            
                            if "bssid_features" in val:
                                features_dict = val["bssid_features"]
                                if isinstance(features_dict, dict):
                                    self.original_bssid_features[(r, c)] = features_dict
                                    if not self.bssid_columns:
                                        self.bssid_columns = list(features_dict.keys())
                                    vec = [features_dict.get(b, 0.0) for b in self.bssid_columns]
                                    self.vector_data[(r, c)] = vec
                            elif "vector" in val:
                                vec = val["vector"]
                                self.vector_data[(r, c)] = vec
                                if isinstance(vec, list) and len(vec) == 1:
                                    pointer_count += 1
                                    scan_id_str = str(vec[0]).strip()
                                    if scan_id_str.endswith('.0'):
                                        scan_id_str = scan_id_str[:-2]
                                    self.cell_scan_map[(r, c)] = scan_id_str
                        else:
                            self.grid_data[(r, c)] = val

                print(f"[DEBUG] Total cells loaded: {len(self.grid_data)}")
                print(f"[DEBUG] Total mapped vectors loaded: {len(self.vector_data)}")

                matched = 0
                if self.scan_library:
                    matched = self.resolve_scan_pointers()

                self.redraw_canvas()
                self.map_status_label.config(text=f"Map: {len(self.grid_data)} cells loaded")
                self.vector_count_label.config(text=f"Total mapped vectors: {len(self.vector_data)}")
                messagebox.showinfo("Success", f"Loaded map with {len(self.grid_data)} cells and {len(self.vector_data)} vectors.")
            except Exception as e:
                print(f"[ERROR] Failed to load Map JSON: {e}")
                messagebox.showerror("Error", f"Failed to load Map JSON:\n{e}")

    def load_wifi_csv(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if file_path:
            try:
                print(f"\n[DEBUG] --- Loading Wi-Fi Scans CSV: {file_path} ---")
                self.scan_library = {}
                self.bssid_columns = []

                with open(file_path, mode="r", encoding="utf-8-sig") as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    if not header:
                        print("[ERROR] CSV file is empty.")
                        messagebox.showerror("Error", "CSV file is empty.")
                        return

                    self.bssid_columns = [h.strip() for h in header[1:]]
                    print(f"[DEBUG] Total BSSID feature columns: {len(self.bssid_columns)}")

                    row_count = 0
                    for row in reader:
                        if not row or all(not cell.strip() for cell in row):
                            continue
                        
                        scan_id = row[0].strip()
                        vector = []
                        for val in row[1:]:
                            val_str = val.strip()
                            if val_str == "":
                                vector.append(0.0)
                            else:
                                try:
                                    vector.append(float(val_str))
                                except ValueError:
                                    vector.append(0.0)

                        self.scan_library[scan_id] = vector
                        row_count += 1

                matched = 0
                if self.cell_scan_map:
                    matched = self.resolve_scan_pointers()

                sorted_ids = sorted(self.scan_library.keys(), key=lambda x: int(x) if x.isdigit() else str(x))
                self.scan_combobox['values'] = sorted_ids
                if sorted_ids:
                    self.scan_combobox.current(0)

                self.csv_status_label.config(text=f"Scans CSV: {len(self.scan_library)} scans loaded")
                self.vector_count_label.config(text=f"Total mapped vectors: {len(self.vector_data)}")
                self.redraw_canvas()
                messagebox.showinfo("Success", f"Loaded {len(self.scan_library)} scans. Successfully replaced pointers with CSV vectors for {matched} cells.")
            except Exception as e:
                print(f"[ERROR] Failed to load Wi-Fi Scans CSV: {e}")
                messagebox.showerror("Error", f"Failed to load Wi-Fi Scans CSV:\n{e}")

    def resolve_scan_pointers(self):
        replaced_count = 0
        for (r, c), scan_id in self.cell_scan_map.items():
            matched_key = None
            if scan_id in self.scan_library:
                matched_key = scan_id
            else:
                cleaned_id = scan_id[:-2] if scan_id.endswith('.0') else scan_id
                if cleaned_id in self.scan_library:
                    matched_key = cleaned_id
                else:
                    for sid in self.scan_library.keys():
                        try:
                            if float(sid) == float(scan_id):
                                matched_key = sid
                                break
                        except ValueError:
                            pass
            
            if matched_key:
                self.vector_data[(r, c)] = self.scan_library[matched_key]
                replaced_count += 1
        return replaced_count

    def redraw_canvas(self):
        for rc, rect_id in self.rects.items():
            self.canvas.itemconfig(rect_id, fill="#FFFFFF", outline="#f0f0f0")
        
        for (r, c), t in self.grid_data.items():
            if (r, c) in self.rects:
                color = PALETTE.get(t, {"color": "#FFFFFF"})["color"]
                self.canvas.itemconfig(self.rects[(r, c)], fill=color)

        for marker_id in self.vector_markers.values():
            self.canvas.delete(marker_id)
        self.vector_markers.clear()

        if self.selection_rect:
            self.canvas.delete(self.selection_rect)
            self.selection_rect = None

        for (r, c) in self.vector_data.keys():
            if (r, c) in self.rects:
                x1 = c * CELL_SIZE + 2
                y1 = r * CELL_SIZE + 2
                x2 = x1 + CELL_SIZE - 4
                y2 = y1 + CELL_SIZE - 4
                marker_id = self.canvas.create_rectangle(x1, y1, x2, y2, fill="#9C27B0", outline="")
                self.vector_markers[(r, c)] = marker_id

        if self.selected_cell:
            sr, sc = self.selected_cell
            if (sr, sc) in self.rects:
                x1 = sc * CELL_SIZE
                y1 = sr * CELL_SIZE
                x2 = x1 + CELL_SIZE
                y2 = y1 + CELL_SIZE
                self.selection_rect = self.canvas.create_rectangle(
                    x1, y1, x2, y2, outline="#E53935", width=2
                )

    def paint_cell(self, x, y):
        c = x // CELL_SIZE
        r = y // CELL_SIZE
        if 0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE:
            chosen_tool = self.brush_var.get()
            if chosen_tool == "Empty":
                if (r, c) in self.grid_data:
                    self.grid_data[(r, c)] = "Empty"
            else:
                self.grid_data[(r, c)] = chosen_tool
            
            self.selected_cell = (r, c)
            self.redraw_canvas()
            self.update_inspector()

    def on_canvas_click(self, event):
        self.paint_cell(event.x, event.y)

    def on_canvas_drag(self, event):
        self.paint_cell(event.x, event.y)

    def update_inspector(self):
        if not self.selected_cell:
            return
        r, c = self.selected_cell
        cell_type = self.grid_data.get((r, c), "Empty")
        
        if self.selected_cell in self.vector_data:
            vec = self.vector_data[self.selected_cell]
            assigned_scan = self.cell_scan_map.get(self.selected_cell, "Custom")
            self.cell_info_lbl.config(text=f"Selected: ({r}, {c}) [{cell_type}]\nLinked Scan ID: {assigned_scan}\nDimensions: {len(vec)}")
            if assigned_scan in self.scan_library:
                self.scan_id_var.set(assigned_scan)
            self.vector_entry_var.set(", ".join(str(v) for v in vec[:15]) + ("..." if len(vec) > 15 else ""))
            self.vector_status_lbl.config(text="Status: Vector loaded")
        else:
            self.cell_info_lbl.config(text=f"Selected: ({r}, {c}) [{cell_type}]\nDimensions: None")
            self.vector_entry_var.set("")
            self.vector_status_lbl.config(text="Status: No vector assigned")

    def assign_scan_to_cell(self):
        if not self.selected_cell:
            messagebox.showwarning("Warning", "Please select a cell on the grid first.")
            return
        
        chosen_scan = self.scan_id_var.get().strip()
        if not chosen_scan or chosen_scan not in self.scan_library:
            messagebox.showwarning("Warning", "Please select a valid Scan ID from the dropdown.")
            return

        vector = self.scan_library[chosen_scan]
        self.vector_data[self.selected_cell] = vector
        self.cell_scan_map[self.selected_cell] = chosen_scan
        self.vector_count_label.config(text=f"Total mapped vectors: {len(self.vector_data)}")
        self.vector_status_lbl.config(text=f"Status: Scan {chosen_scan} assigned!")
        self.redraw_canvas()
        self.update_inspector()

    def remove_scan_from_cell(self):
        if not self.selected_cell:
            return
        if self.selected_cell in self.vector_data:
            del self.vector_data[self.selected_cell]
        if self.selected_cell in self.cell_scan_map:
            del self.cell_scan_map[self.selected_cell]
        if self.selected_cell in self.original_bssid_features:
            del self.original_bssid_features[self.selected_cell]
        
        self.vector_count_label.config(text=f"Total mapped vectors: {len(self.vector_data)}")
        self.vector_status_lbl.config(text="Status: Vector removed")
        self.redraw_canvas()
        self.update_inspector()

    def apply_vector(self):
        if not self.selected_cell:
            messagebox.showwarning("Warning", "Please select a cell on the grid first.")
            return
        
        raw_text = self.vector_entry_var.get().strip()
        if not raw_text:
            self.remove_scan_from_cell()
            return

        try:
            parts = raw_text.split(",")
            vector = [float(p.strip()) for p in parts if p.strip() != ""]
            self.vector_data[self.selected_cell] = vector
            self.vector_status_lbl.config(text=f"Status: Saved {len(vector)} dimensions!")
            self.vector_count_label.config(text=f"Total mapped vectors: {len(self.vector_data)}")
            self.redraw_canvas()
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numbers separated by commas.")

    def export_json(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                exportable = {}
                all_coords = set(self.grid_data.keys()).union(self.vector_data.keys())
                
                for (r, c) in sorted(all_coords):
                    key = f"{r},{c}"
                    cell_type = self.grid_data.get((r, c), "Empty")
                    entry = {"type": cell_type}
                    
                    if (r, c) in self.vector_data:
                        vec = self.vector_data[(r, c)]
                        entry["vector"] = vec
                        
                        # Preserve and build bssid_features at the exact same dictionary level
                        if self.bssid_columns and len(self.bssid_columns) == len(vec):
                            entry["bssid_features"] = dict(zip(self.bssid_columns, vec))
                        elif (r, c) in self.original_bssid_features:
                            orig_dict = self.original_bssid_features[(r, c)]
                            keys = list(orig_dict.keys())
                            if len(keys) == len(vec):
                                entry["bssid_features"] = dict(zip(keys, vec))
                            else:
                                entry["bssid_features"] = orig_dict

                    exportable[key] = entry

                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(exportable, f, indent=2)
                messagebox.showinfo("Success", f"Enriched dataset successfully exported to:\n{file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to export JSON:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = VectorAnnotatorApp(root)
    root.mainloop()