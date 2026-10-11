# KnightMaps: Never get lost!

KnightMaps is an advanced indoor and outdoor hybrid navigation system designed to help students seamlessly navigate campus buildings and classrooms.

## 👥 Team
* Adrian Stone
* Corbin Williams
* Faruk Celik
* Sean Robert Vicha

---

## 📌 Problem
Students often get lost trying to find classrooms on campus because standard map apps do not feature indoor floor plans[cite: 4]. For example, locating rooms like ENG 107 can be confusing when rooms like 105 and 106 are situated on the opposite side of a building.

---

## 💡 Solution & Architecture
Standard GPS lacks indoor accuracy, and Wi-Fi routers are inaccessible while outdoors[cite: 5]. To solve this, KnightMaps employs a **Localization via Nearest Router (LVNR)** and **Visual Place Recognition (VPR)** hybrid architecture to provide high-accuracy tracking both inside and outside of buildings.

### 1. Localization via Nearest Router (LVNR)
* RSSI (Received Signal Strength Indicator) and BSSID information across multiple points are captured and stored in the database.
* The system matches the user's current position to stored database points using k-nearest neighbors.
* To ensure smooth movement, it calculates a weighted average of the three nearest neighbors based on similarity and leverages device accelerometer data to mitigate latency.

### 2. Visual Place Recognition (VPR)
* Utilizes computer vision and feature clustering (`vpr/` module) to recognize locations and assist with exterior/hybrid positioning.

---

## 🗂️ Project Structure (`server/`)

```text
server/
├── app.py                # Main Flask backend application
├── templates/            # HTML front-end templates (e.g., index.html)
├── vpr/                  # Visual Place Recognition modules (clustering, network, database)
├── rssi/                 # RSSI scan datasets, vector points, and BSSID processing scripts
├── uploads/              # Dynamic user-uploaded images and photos
├── cluster_centroids.npy # NumPy array for cluster centroids
├── database_*.npy        # Processed NumPy matrix files for spatial/GPS paths and raw data
├── vlad_database.index   # Faiss / Vector index database for VPR
└── output.index          # Secondary feature index
