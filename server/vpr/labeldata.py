import os
import json
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk

class LatLonLabeler:
    def __init__(self, dataset_dir="dataset", output_json="annotations.json"):
        self.dataset_dir = dataset_dir
        self.output_json = output_json
        
        if not os.path.exists(self.dataset_dir):
            messagebox.showerror("Error", f"Dataset directory '{self.dataset_dir}' not found.")
            return

        self.image_files = sorted([f for f in os.listdir(self.dataset_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))])
        if not self.image_files:
            messagebox.showerror("Error", f"No images found in '{self.dataset_dir}'.")
            return

        self.annotations = {}
        if os.path.exists(self.output_json):
            try:
                with open(self.output_json, "r") as f:
                    self.annotations = json.load(f)
            except Exception:
                pass

        self.current_idx = 0

        self.root = tk.Tk()
        self.root.title("Lat/Lon Image Labeler")
        self.root.geometry("900x700")

        self.info_label = tk.Label(self.root, text="", font=("Arial", 12, "bold"))
        self.info_label.pack(pady=5)

        self.image_label = tk.Label(self.root)
        self.image_label.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

        form_frame = tk.Frame(self.root)
        form_frame.pack(pady=10)

        tk.Label(form_frame, text="Latitude:", font=("Arial", 11)).grid(row=0, column=0, padx=5, sticky="e")
        self.lat_entry = tk.Entry(form_frame, font=("Arial", 11), width=15)
        self.lat_entry.grid(row=0, column=1, padx=5)

        tk.Label(form_frame, text="Longitude:", font=("Arial", 11)).grid(row=0, column=2, padx=5, sticky="e")
        self.lon_entry = tk.Entry(form_frame, font=("Arial", 11), width=15)
        self.lon_entry.grid(row=0, column=3, padx=5)

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="Previous", command=self.prev_image, width=12, font=("Arial", 10)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Save & Next", command=self.save_and_next, width=15, bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Skip", command=self.next_image, width=12, font=("Arial", 10)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Quit", command=self.root.quit, width=10, bg="#f44336", fg="white", font=("Arial", 10)).pack(side=tk.LEFT, padx=5)

        self.root.bind('<Return>', lambda event: self.save_and_next())

        self.load_current_image()
        self.root.mainloop()

    def load_current_image(self):
        if not self.image_files:
            return
        
        img_name = self.image_files[self.current_idx]
        img_path = os.path.join(self.dataset_dir, img_name)

        self.info_label.config(text=f"Image {self.current_idx + 1} of {len(self.image_files)}: {img_name}")

        self.lat_entry.delete(0, tk.END)
        self.lon_entry.delete(0, tk.END)
        
        if img_name in self.annotations:
            lat = self.annotations[img_name].get("lat", "")
            lon = self.annotations[img_name].get("lon", "")
            if lat is not None: self.lat_entry.insert(0, str(lat))
            if lon is not None: self.lon_entry.insert(0, str(lon))

        try:
            pil_img = Image.open(img_path)
            max_w, max_h = 850, 450
            w, h = pil_img.size
            
            ratio = min(max_w / w, max_h / h)
            new_w = int(w * ratio)
            new_h = int(h * ratio)
            
            pil_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            self.tk_img = ImageTk.PhotoImage(pil_img)
            self.image_label.config(image=self.tk_img)
        except Exception as e:
            self.image_label.config(image="")
            print(f"Error loading image {img_path}: {e}")

    def save_and_next(self):
        img_name = self.image_files[self.current_idx]
        lat_str = self.lat_entry.get().strip()
        lon_str = self.lon_entry.get().strip()

        try:
            lat = float(lat_str) if lat_str else None
            lon = float(lon_str) if lon_str else None
            self.annotations[img_name] = {"lat": lat, "lon": lon}
            
            with open(self.output_json, "w") as f:
                json.dump(self.annotations, f, indent=4)
        except ValueError:
            messagebox.showerror("Invalid Input", "Latitude and Longitude must be valid numbers.")
            return

        self.next_image()

    def next_image(self):
        if self.current_idx < len(self.image_files) - 1:
            self.current_idx += 1
            self.load_current_image()
        else:
            messagebox.showinfo("Complete", "You have reached the end of the image list!")

    def prev_image(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self.load_current_image()

if __name__ == "__main__":
    LatLonLabeler()