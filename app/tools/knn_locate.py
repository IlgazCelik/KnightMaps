#!/usr/bin/env python3
"""
Finds which saved scan a new Wi-Fi reading is closest to, using KNN.

Uses the output folder from normalize_scans.py (vectors.json + bssid_order.json) as the database.
The new reading can be:
  - a vector of the same length:     "[-60, -55, -92, ...]"  (inline, or a .json file holding it)
  - a raw scan file from the phone:  wifi_scan_7.json  (aligned automatically to the same BSSID order)

Each location has exactly one scan, so the answer is the nearest scan's number
(e.g. 2 for wifi_scan_2.json). The next nearest are listed too, since nearby locations
usually come next.

Usage:
  python3 knn_locate.py vectors/ "[-60, -55, -92, -92, -80, -92, -85]"
  python3 knn_locate.py vectors/ new_scan.json -k 3
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize_scans import ORDER_FILE, VECTORS_FILE, load_scan  # noqa: E402


def label_of(name):
    """wifi_scan_12.json -> "12"; any other name is used as-is (minus .json)."""
    m = re.search(r"(\d+)\.json$", name)
    return m.group(1) if m else name.removesuffix(".json")


def read_query(arg, order, fill):
    """Returns the new reading as a vector in the database's BSSID order."""
    path = Path(arg)
    data = json.loads(path.read_text()) if path.is_file() else json.loads(arg)
    if not isinstance(data, list):
        sys.exit("The new reading must be a list of numbers or a scan file.")
    if data and isinstance(data[0], dict):
        readings = load_scan(path)
        return [readings.get(b, fill) for b in order]
    if len(data) != len(order):
        sys.exit(f"The vector has {len(data)} numbers but the database vectors have {len(order)}.")
    return [float(v) for v in data]


def main():
    parser = argparse.ArgumentParser(description="Find the closest saved scan to a new Wi-Fi reading (KNN).")
    parser.add_argument("database", help="folder with vectors.json and bssid_order.json (from normalize_scans.py)")
    parser.add_argument("query", help='new reading: a vector like "[-60, -55, ...]", a .json vector, or a scan file')
    parser.add_argument("-k", type=int, default=3, help="how many nearest scans to list (default: 3)")
    args = parser.parse_args()

    db = Path(args.database)
    vectors = json.loads((db / VECTORS_FILE).read_text())
    order = json.loads((db / ORDER_FILE).read_text())
    fill = min(v for vec in vectors.values() for v in vec)

    query = read_query(args.query, order, fill)

    # Euclidean distance to every saved scan, nearest first.
    neighbours = sorted((math.dist(query, vec), name) for name, vec in vectors.items())[: args.k]

    print(f"Closest: {label_of(neighbours[0][1])}")
    print(f"\n{len(neighbours)} nearest (k={args.k}):")
    for d, name in neighbours:
        print(f"  {label_of(name):>6}  distance {d:7.2f}  ({name})")


if __name__ == "__main__":
    main()
