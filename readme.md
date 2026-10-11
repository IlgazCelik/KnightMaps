# KnightMaps: Never get lost!

KnightMaps is an advanced indoor and outdoor hybrid navigation system designed to help students seamlessly navigate campus buildings and classrooms.

## 👥 Team
- Adrian Stone
- Corbin Williams
- Faruk Celik
- Sean Robert Vicha

---

## 📌 Problem
Students often get lost trying to find classrooms on campus because standard map apps do not feature indoor floor plans. For example, locating rooms like ENG 107 can be confusing when rooms like 105 and 106 are situated on the opposite side of a building.

---

## 💡 Solution & Architecture
Standard GPS lacks indoor accuracy, and Wi-Fi routers are inaccessible while outdoors. To solve this, KnightMaps employs a **Localization via Nearest Router (LVNR)** and **Visual Place Recognition (VPR)** hybrid architecture to provide high-accuracy tracking both inside and outside of buildings.

### 1. Localization via Nearest Router (LVNR)
- RSSI (Received Signal Strength Indicator) and BSSID information across multiple points are captured and stored in the database.
- The system matches the user's current position to stored database points using k-nearest neighbors.
- To ensure smooth movement, it calculates a weighted average of the three nearest neighbors based on similarity and leverages device accelerometer data to mitigate latency.

### 2. Visual Place Recognition (VPR)
- Powered by **AnyLoc** (Keetha et al., 2023) leveraging the self-supervised **DINOv2 Base** model (Oquab et al., 2024) loaded through Hugging Face, combined with feature clustering (`vpr/` module) to achieve domain-agnostic visual place recognition for exterior/hybrid positioning.

---

## 🗂️ Project Structure (`server/`)

```text
KnightMaps/
├── server/                     # Flask backend: localization + routing
│   ├── app.py                  # Main Flask app (/api/localize_json, /api/upload)
│   ├── final_0.1.json          # Processed RSSI fingerprint data
│   ├── templates/              # HTML front-end templates (index.html)
│   ├── rssi/                   # RSSI scan datasets, vector points, BSSID processing (processBSSID.py, tile.py)
│   ├── vpr/                    # Visual Place Recognition (AnyLoc + DINOv2)
│   │   ├── centroid.py, cluster.py, database.py, network.py, test.py   # feature clustering, network, index
│   │   ├── createDataset.py    # Extracts frames from a walk-through video into dataset/
│   │   └── labeldata.py        # GUI to tag each frame with latitude/longitude -> annotations.json
│   ├── uploads/                # (generated) user-uploaded photos
│   └── *.npy, *.index          # (generated) cluster centroids, VLAD/Faiss indexes, path matrices
│
├── app/                        # KnightMaps Android app (Capacitor + Vite)
│   ├── index.html              # Layout and styles
│   ├── src/
│   │   ├── main.js             # Tracking loop, server requests, dead reckoning, destination, Inside/Outside
│   │   ├── map.js              # Zoom, pan and tap on the floor plan
│   │   ├── nodes.js            # Position marker, accuracy circle, route line, room highlight
│   │   ├── rooms.js            # Rooms, restrooms, stairs and lifts (shapes + hallway goal cells)
│   │   ├── walkable.js         # Hallway mask (keeps the marker out of rooms)
│   │   ├── directions.js       # Indoor turn-by-turn instructions
│   │   ├── outside.js          # Outdoor directions (GPS bearing to the target)
│   │   ├── camera.js           # Outside camera / photo upload
│   │   ├── search.js, voice.js # Room search and voice search
│   │   ├── audio.js            # Spoken instruction clips + mute
│   │   ├── bssid_order.js      # BSSID order the server expects
│   │   └── wifi.js             # Bridge to the native plugin
│   ├── native-android/         # WifiScanPlugin.java: Wi-Fi scan, steps, compass, GPS, upload, speech-to-text
│   ├── public/                 # floorplan.svg, audio clips, font
│   ├── tools/                  # Scan normalization, KNN localizer, scan server, building outline
│   ├── vectors/, scans/        # Fingerprint vectors and sample scans
│   └── android/                # Android Studio project
│
├── rssi-monitor/               # Helper app: one BSSID's RSSI vs. time
│   ├── src/                    # main.js, chart.js, scanner.js
│   ├── native-android/         # RssiPlugin.java
│   └── android/                # Android Studio project
│
├── dataset/                    # Video frames for VPR (frame_*.jpg)
├── annotations.json            # Latitude/longitude label for each frame
├── input.mp4                   # Walk-through video the frames come from
└── readme.md
```
📚 References & Acknowledgments
Our Visual Place Recognition (VPR) pipeline builds upon foundational research from DINOv2 and AnyLoc:

Code snippet
@misc{oquab2024dinov2learningrobustvisual,
      title={DINOv2: Learning Robust Visual Features without Supervision}, 
      author={Maxime Oquab and Timothée Darcet and Théo Moutakanni and Huy Vo and Marc Szafraniec and Vasil Khalidov and Pierre Fernandez and Daniel Haziza and Francisco Massa and Alaaeldin El-Nouby and Mahmoud Assran and Nicolas Ballas and Wojciech Galuba and Russell Howes and Po-Yao Huang and Shang-Wen Li and Ishan Misra and Michael Rabbat and Vasu Sharma and Gabriel Synnaeve and Hu Xu and Hervé Jegou and Julien Mairal and Patrick Labatut and Armand Joulin and Piotr Bojanowski},
      year={2024},
      eprint={2304.07193},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={[https://arxiv.org/abs/2304.07193](https://arxiv.org/abs/2304.07193)}, 
}

@misc{keetha2023anylocuniversalvisualplace,
      title={AnyLoc: Towards Universal Visual Place Recognition}, 
      author={Nikhil Keetha and Avneesh Mishra and Jay Karhade and Krishna Murthy Jatavallabhula and Sebastian Scherer and Madhava Krishna and Sourav Garg},
      year={2023},
      eprint={2308.00688},
      archivePrefix={arXiv},
      primaryClass={cs.CV},
      url={[https://arxiv.org/abs/2308.00688](https://arxiv.org/abs/2308.00688)}, 
}
