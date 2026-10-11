#!/usr/bin/env python3
"""
Receives Wi-Fi scans from the phone app, in the form the KNN map tool (message.txt)
holds BSSID data for each map cell:

  POST /scan   <-  {"bssid_features": {"24:16:1b:8f:e6:01": -58.0, ...}}

Each scan is saved unchanged as <out>/wifi_scan_<n>.json.

With the phone on USB, make the phone's localhost:8000 reach this Mac:
    adb reverse tcp:8000 tcp:8000

Usage:
    python3 scan_server.py [--port 8000] [--out received]
"""
import argparse
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def make_handler(out_dir):
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._reply(200, {"ok": True, "scans": len(list(out_dir.glob("wifi_scan_*.json")))})

        def do_POST(self):
            if self.path != "/scan":
                return self._reply(404, {"error": "POST /scan"})
            try:
                scan = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                features = scan["bssid_features"]
                if not isinstance(features, dict) or not all(isinstance(v, (int, float)) for v in features.values()):
                    raise ValueError("bssid_features must map each BSSID to a number")
                scan = {"bssid_features": {str(b): float(v) for b, v in features.items()}}
            except (ValueError, KeyError, TypeError) as e:
                return self._reply(400, {"error": f"bad scan: {e}"})

            n = len(list(out_dir.glob("wifi_scan_*.json"))) + 1
            name = f"wifi_scan_{n}.json"
            (out_dir / name).write_text(json.dumps(scan, indent=2) + "\n")
            feats = scan["bssid_features"]
            top = max(feats.items(), key=lambda kv: kv[1], default=None)
            print(f"[{datetime.now():%H:%M:%S}] {name}: {len(feats)} BSSIDs"
                  + (f", strongest {top[0]} {top[1]} dBm" if top else ""), flush=True)
            self._reply(200, {"ok": True, "saved": name})

        def log_message(self, *args):
            pass  # one line per scan is enough

    return Handler


def main():
    parser = argparse.ArgumentParser(description="Save Wi-Fi scans sent by the phone app.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--out", default="received", help="folder to save scans in (default: received)")
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(out_dir))
    print(f"Listening on port {args.port}, saving scans to {out_dir.resolve()}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
