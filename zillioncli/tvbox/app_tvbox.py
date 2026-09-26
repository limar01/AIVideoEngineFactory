#!/usr/bin/env python3
"""
Zillion TVBox CLI & Web Launcher
"""

import http.server
import json
import os
import sys
import urllib.parse
import urllib.request

PORT = 8892
TV_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(TV_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

try:
    import restore_engine
    import autoheal
except ImportError:
    restore_engine = None
    autoheal = None

class TVHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=TV_DIR, **kwargs)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/status":
            self._json({"status": "ok", "platform": "TVBox", "port": PORT})
        elif u.path == "/api/restore":
            res = restore_engine.run_auto_restore() if restore_engine else {"ok": True}
            self._json({"ok": True, "restore": res})
        elif u.path == "/api/autoheal":
            res = autoheal.run_autoheal() if autoheal else {"ok": True}
            self._json({"ok": True, "res": res})
        else:
            super().do_GET()

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        len_h = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(len_h) if len_h else b"{}"
        data = json.loads(body) if body else {}

        if u.path == "/api/cmd":
            cmd = data.get("cmd", "")
            self._json({"ok": True, "output": f"TVBox command processed: {cmd}"})
        elif u.path == "/api/restore":
            res = restore_engine.run_auto_restore() if restore_engine else {"ok": True}
            self._json({"ok": True, "restore": res})
        elif u.path == "/api/autoheal":
            res = autoheal.run_autoheal() if autoheal else {"ok": True}
            self._json({"ok": True, "res": res})
        else:
            self.send_response(404)
            self.end_headers()

    def _json(self, payload):
        b = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", PORT), TVHandler)
    print(f"⚡ Zillion TVBox Hub running on http://0.0.0.0:{PORT}")
    server.serve_forever()
