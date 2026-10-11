#!/usr/bin/env python3
"""
Turns Wi-Fi scan files into aligned RSSI vectors, ready for KNN.

Input:  scan files from the app, each a list of {"bssid": ..., "rssi": ...}
Output (in the output folder), two files:
  - bssid_order.json: ["bssid_1", "bssid_2", ...] -- what each position in a vector means
  - vectors.json:     {"wifi_scan_1.json": [-52, -71, ...], "wifi_scan_2.json": [...], ...}
A BSSID a scan didn't see (or reported as RSSI 0) is filled with one less than the
weakest real RSSI across all the scans.

Usage:
  # build vectors from your training scans
  python3 normalize_scans.py scans/ -o vectors
  # convert new scans to match an existing training set (same order and fill value)
  python3 normalize_scans.py new_scan.json -o query --train vectors
"""
import argparse
import json
import sys
from pathlib import Path

ORDER_FILE = "bssid_order.json"
VECTORS_FILE = "vectors.json"


def load_scan(path):
    """Returns {bssid: rssi} for one file. Drops RSSI 0 (no reading); keeps the strongest of duplicates."""
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON list of {{bssid, rssi}} entries")
    readings = {}
    for entry in data:
        bssid = entry["bssid"].lower()
        rssi = entry["rssi"]
        if rssi == 0:
            continue
        readings[bssid] = max(rssi, readings.get(bssid, rssi))
    return readings


def collect_files(inputs):
    files = []
    for item in inputs:
        p = Path(item)
        files.extend(sorted(p.glob("*.json")) if p.is_dir() else [p])
    return [f for f in files if f.name not in (ORDER_FILE, VECTORS_FILE)]


def main():
    parser = argparse.ArgumentParser(description="Convert Wi-Fi scan JSONs into aligned RSSI vectors.")
    parser.add_argument("inputs", nargs="+", help="scan JSON files and/or folders containing them")
    parser.add_argument("-o", "--out", default="vectors", help="output folder (default: vectors)")
    parser.add_argument("--train", help="folder of an existing training output; reuse its BSSID order and fill value")
    args = parser.parse_args()

    files = collect_files(args.inputs)
    if not files:
        sys.exit("No JSON files found.")
    scans = {f: load_scan(f) for f in files}

    if args.train:
        # Match the training set: same BSSID order, and the same fill value (its smallest number).
        train = Path(args.train)
        order = json.loads((train / ORDER_FILE).read_text())
        fill = min(v for vec in json.loads((train / VECTORS_FILE).read_text()).values() for v in vec)
        print(f"{len(files)} files, using {len(order)} BSSIDs and fill {fill} from {train}/")
    else:
        order = sorted(set().union(*scans.values()))
        real = [r for readings in scans.values() for r in readings.values()]
        if not real:
            sys.exit("The scans contain no readings.")
        fill = min(real) - 1
        print(f"{len(files)} files, {len(order)} unique BSSIDs, weakest RSSI {min(real)} -> missing = {fill}")

    vectors = {}
    for f, readings in scans.items():
        vectors[f.name] = [readings.get(b, fill) for b in order]
        seen = sum(b in readings for b in order)
        print(f"  {f.name}: {seen} seen, {len(order) - seen} filled")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / VECTORS_FILE).write_text(
        "{\n" + ",\n".join(f"  {json.dumps(name)}: {json.dumps(vec)}" for name, vec in vectors.items()) + "\n}\n"
    )
    if not args.train:
        (out_dir / ORDER_FILE).write_text(json.dumps(order, indent=2) + "\n")
    print(f"Saved to {out_dir.resolve()}/")


if __name__ == "__main__":
    main()
