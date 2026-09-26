#!/usr/bin/env python3
"""
zweb.py — Web version of the `zion` CLI  (see MEMORY_CORE §34).

A localhost-only HTTP server that WRAPS the existing `zion` binary
(send / ls / open / status) and serves a web chat UI (index.html).
It does NOT re-implement the Arena API — it shells out to `zion`, so it
inherits the exact same Cloudflare-impersonation / CDP / RSC-no-nav engine.

RUN ON THE OMARCHY PC (where `zion` is in ~/.local/bin and the probe
browser is up on :9222):

    python3 zweb.py                       # -> http://127.0.0.1:8791
    ZWEB_PORT=8792 python3 zweb.py
    python3 zweb.py --host 127.0.0.1 --port 8791
    ZION_BIN=/home/limar01/.local/bin/zion python3 zweb.py

Security:
  * Binds to 127.0.0.1 by default (localhost only).
  * It wraps an authenticated Arena session, so DO NOT expose it to the
    LAN/WAN without care. Use --host 0.0.0.0 ONLY on a trusted network.
"""
import http.server, socketserver, json, subprocess, os, sys, urllib.parse

ZION = os.environ.get("ZION_BIN", "zion")
PORT = int(os.environ.get("ZWEB_PORT", "8791"))
HOST = "127.0.0.1"
HERE = os.path.dirname(os.path.abspath(__file__))


def run_zion(args, timeout=120):
    """Run the zion CLI, capture stdout/stderr, return a JSON-able dict."""
    try:
        p = subprocess.run([ZION] + args, capture_output=True, text=True, timeout=timeout)
        return {"ok": p.returncode == 0, "code": p.returncode,
                "stdout": p.stdout, "stderr": p.stderr}
    except FileNotFoundError:
        return {"ok": False, "code": -1, "stdout": "",
                "stderr": "zion binary not found ('%s'). Run zweb.py on the Omarchy PC where zion lives." % ZION}
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": -2, "stdout": "",
                "stderr": "zion timed out after %ss" % timeout}
    except Exception as e:
        return {"ok": False, "code": -3, "stdout": "", "stderr": str(e)}


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, body, code=200, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj), code)

    def _html(self, name):
        fp = os.path.join(HERE, name)
        try:
            with open(fp, "rb") as f:
                body = f.read()
            ctype = "text/html" if name.endswith(".html") else "text/plain"
        except Exception as e:
            body = ("not found: %s" % e).encode()
            ctype = "text/plain"
        self._send(body, 200, ctype)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p = u.path
        if p in ("/", "/index.html"):
            return self._html("index.html")
        if p == "/api/health":
            return self._json({"ok": True, "zweb": True, "zion": ZION})
        if p == "/api/status":
            return self._json(run_zion(["status"], timeout=30))
        if p == "/api/sessions":
            q = urllib.parse.parse_qs(u.query)
            lim = (q.get("limit") or ["20"])[0]
            return self._json(run_zion(["ls", str(lim)], timeout=60))
        if p.startswith("/api/session/"):
            sid = p.rsplit("/", 1)[-1]
            return self._json(run_zion(["open", sid], timeout=60))
        return self._json({"ok": False, "stderr": "unknown route " + p}, 404)

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        p = u.path
        ln = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(ln).decode("utf-8", "replace") if ln else ""
        if p == "/api/send":
            try:
                msg = json.loads(body).get("msg", "").strip()
            except Exception:
                msg = body.strip()
            if not msg:
                return self._json({"ok": False, "stderr": "empty message"}, 400)
            return self._json(run_zion(["send", msg], timeout=240))
        return self._json({"ok": False, "stderr": "unknown route " + p}, 404)

    def log_message(self, *a):
        pass  # quiet


class ThreadingServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--host" in args:
        HOST = args[args.index("--host") + 1]
    if "--port" in args:
        PORT = int(args[args.index("--port") + 1])
    print("zweb: web version of `zion` CLI")
    print("      UI      -> http://%s:%d" % (HOST, PORT))
    print("      zion    -> %s" % ZION)
    print("      binding -> %s (localhost-only unless you pass --host)" % HOST)
    print("      Ctrl-C to stop.")
    ThreadingServer((HOST, PORT), Handler).serve_forever()
