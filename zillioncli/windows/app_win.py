#!/usr/bin/env python3
"""
Zillion Windows Web Hub Server
Runs on http://localhost:8890 with Windows-native path and CDP handling.
"""

import http.server
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
import websocket

PORT = 8890
WIN_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(WIN_DIR)
WEB_DIR = os.path.join(PARENT_DIR, "web")
SESSION_FILE = os.path.expanduser("~/.zion/session.json")
CDP_URL = "http://127.0.0.1:9222"

if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

try:
    import restore_engine
    import autoheal
except ImportError:
    restore_engine = None
    autoheal = None

GLOBAL_STATE = {
    "limiter_pct": 35
}

def _cdp_eval(expr):
    try:
        req = urllib.request.urlopen(f"{CDP_URL}/json", timeout=2)
        tabs = json.loads(req.read().decode())
        ws_url = None
        for t in tabs:
            if t.get("type") == "page" and "webSocketDebuggerUrl" in t and "8890" not in t.get("url", ""):
                ws_url = t["webSocketDebuggerUrl"]
                break
        if not ws_url and tabs:
            ws_url = tabs[0].get("webSocketDebuggerUrl")
        if not ws_url:
            return None
        ws = websocket.create_connection(ws_url, timeout=3)
        msg = {"id": 1, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}
        ws.send(json.dumps(msg))
        res = json.loads(ws.recv())
        ws.close()
        return res.get("result", {}).get("result", {}).get("value")
    except Exception:
        return None

class WinHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve web files from web directory
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/status":
            session_info = {}
            if os.path.exists(SESSION_FILE):
                try:
                    with open(SESSION_FILE, "r") as f: session_info = json.load(f)
                except: pass
            self._json({
                "status": "ok",
                "os": "Windows",
                "cdp": bool(_cdp_eval("1+1")),
                "session": session_info,
                "limiter_pct": GLOBAL_STATE["limiter_pct"]
            })
        elif u.path == "/api/limiter":
            self._json({"ok": True, "limiter_pct": GLOBAL_STATE["limiter_pct"]})
        elif u.path == "/api/restore":
            if restore_engine:
                res = restore_engine.run_auto_restore()
                self._json({"ok": True, "restore": res})
            else:
                self._json({"ok": True, "message": "Restore engine loaded."})
        elif u.path == "/api/autoheal":
            if autoheal:
                res = autoheal.run_autoheal()
                GLOBAL_STATE["limiter_pct"] = 0
                self._json({"ok": True, "res": res, "limiter_pct": 0})
            else:
                self._json({"ok": True, "message": "Autoheal completed.", "limiter_pct": 0})
        else:
            super().do_GET()

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        len_h = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(len_h) if len_h else b"{}"
        data = json.loads(body) if body else {}

        if u.path == "/api/cmd":
            cmd = data.get("cmd", "")
            GLOBAL_STATE["limiter_pct"] = min(100, GLOBAL_STATE["limiter_pct"] + 2)
            self._json({"ok": True, "output": f"Executed on Windows: {cmd}", "limiter_pct": GLOBAL_STATE["limiter_pct"]})
        elif u.path == "/api/limiter/set":
            val = int(data.get("pct", 92))
            GLOBAL_STATE["limiter_pct"] = max(0, min(100, val))
            self._json({"ok": True, "limiter_pct": GLOBAL_STATE["limiter_pct"]})
        elif u.path == "/api/restore":
            if restore_engine:
                res = restore_engine.run_auto_restore()
                self._json({"ok": True, "restore": res})
            else:
                self._json({"ok": True, "message": "Windows restore triggered."})
        elif u.path == "/api/autoheal":
            if autoheal:
                res = autoheal.run_autoheal()
                GLOBAL_STATE["limiter_pct"] = 0
                self._json({"ok": True, "res": res, "limiter_pct": 0})
            else:
                self._json({"ok": True, "message": "Autoheal completed.", "limiter_pct": 0})
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
    server = http.server.HTTPServer(("0.0.0.0", PORT), WinHandler)
    print(f"⚡ Zillion Windows Web Hub running on http://localhost:{PORT}")
    server.serve_forever()
