# KnightMaps: Never get lost![cite: 1]

KnightMaps is an advanced indoor and outdoor hybrid navigation system designed to help students seamlessly navigate campus buildings and classrooms[cite: 4].

## 👥 Team
* Adrian[cite: 2]
* Corbin[cite: 2]
* Faruk[cite: 2]
* Sean[cite: 2]

---

## 📌 Problem
Students often get lost trying to find classrooms on campus because standard map apps do not feature indoor floor plans[cite: 4]. For example, locating rooms like ENG 107 can be confusing when rooms like 105 and 106 are situated on the opposite side of a building[cite: 4].

---

## 💡 Solution & Architecture
Standard GPS lacks indoor accuracy, and Wi-Fi routers are inaccessible while outdoors[cite: 5]. To solve this, KnightMaps employs a **Localization via Nearest Router (LVNR)** and **Visual Place Recognition (VPR)** hybrid architecture to provide high-accuracy tracking both inside and outside of buildings[cite: 5].

### 1. Localization via Nearest Router (LVNR)
* RSSI (Received Signal Strength Indicator) and BSSID information across multiple points are captured and stored in the database[cite: 6].
* The system matches the user's current position to stored database points using k-nearest neighbors[cite: 6].
* To ensure smooth movement, it calculates a weighted average of the three nearest neighbors based on similarity and leverages device accelerometer data to mitigate latency[cite: 6].

### 2. Visual Place Recognition (VPR)
* Utilizes computer vision and feature clustering (`vpr/` module) to recognize locations and assist with exterior/hybrid positioning[cite: 5].

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