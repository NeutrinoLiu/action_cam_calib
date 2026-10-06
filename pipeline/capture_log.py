#!/usr/bin/env python3
"""Serve capture_log.html and keep its records in a JSON file.

The page saves every change to the JSON file (default: capture_log.json next to
HANDOVER.md). Each save carries the revision it was based on; a save from a stale
page (e.g. a second open tab) is refused instead of overwriting newer records.

Usage:
    python tools/capture_log.py                       # http://localhost:8765
    python tools/capture_log.py --data my_log.json --port 8766
"""
import argparse
import json
import os
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
data_path = None


def read_log():
    try:
        with open(data_path, encoding="utf-8") as f:
            j = json.load(f)
    except FileNotFoundError:
        return 0, {}
    return j.pop("rev", 0), {k: v for k, v in j.items() if k != "updated"}


def write_log(rev, data):
    tmp = data_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"rev": rev, "updated": datetime.now().isoformat(timespec="seconds"), **data},
                  f, ensure_ascii=False, indent=1)
    os.replace(tmp, data_path)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            with open(os.path.join(HERE, "capture_log.html"), "rb") as f:
                self.send(200, f.read(), "text/html; charset=utf-8")
        elif self.path == "/api/log":
            rev, data = read_log()
            self.send(200, {"rev": rev, "data": data, "file": data_path})
        else:
            self.send(404, {"error": "not found"})

    def do_PUT(self):
        if self.path != "/api/log":
            return self.send(404, {"error": "not found"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        rev, data = read_log()
        if body.get("rev") != rev:
            return self.send(409, {"rev": rev, "data": data})
        write_log(rev + 1, body["data"])
        self.send(200, {"rev": rev + 1})


def main():
    global data_path
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=os.path.join(os.path.dirname(HERE), "capture_log.json"),
                    help="JSON file holding the records (default: capture_log.json next to HANDOVER.md)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    data_path = os.path.abspath(args.data)
    url = f"http://localhost:{args.port}/"
    srv = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"capture log on {url}  records: {data_path}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
