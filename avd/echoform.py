"""echoform.py — form + POST echo server used to prove network capture works.

Endpoints
  GET  /        manual form (user taps Submit test)
  GET  /auto    page that POSTs immediately on load (no UI automation needed)
  POST /submit  echoes the body back and appends it to the log file

Served on the PC; reachable from the emulator at http://10.0.2.2:8099/ and, through a
cloudflared quick tunnel, at a public https URL (Chrome does not proxy private IPs, so the
public URL is the reliable browser test).
"""
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FORM = """<!doctype html><html><head><title>zillion net test</title>
<meta name="viewport" content="width=device-width,initial-scale=1"></head><body>
<h3>zillion network capture test</h3>
<form method="POST" action="/submit">
  <p><input name="username" value="boss" style="font-size:22px;padding:14px;width:80%"></p>
  <p><input name="note" value="hello-from-emulator" style="font-size:22px;padding:14px;width:80%"></p>
  <button type="submit" style="font-size:24px;padding:18px 34px">Submit test</button>
</form></body></html>"""

AUTO = """<!doctype html><html><head><title>zillion auto post</title></head><body>
<h4>sending a POST from this browser…</h4><pre id="r">…</pre>
<script>
fetch('/submit', {method:'POST',
  headers:{'Content-Type':'application/x-www-form-urlencoded'},
  body:'username=boss&note=auto-post-from-emulator-browser'})
 .then(r => r.text()).then(t => { document.title='posted ok';
    document.getElementById('r').textContent = t.replace(/<[^>]+>/g,''); })
 .catch(e => { document.title='post failed'; document.getElementById('r').textContent = e; });
</script></body></html>"""

LOGFILE = os.path.expanduser(os.environ.get("ECHO_LOG", "~/arenabridge/net/echoform.log"))


def log(line):
    try:
        os.makedirs(os.path.dirname(LOGFILE), exist_ok=True)
        with open(LOGFILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


class H(BaseHTTPRequestHandler):
    def _send(self, code, body):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        path = self.path.split("?")[0]
        log(f"{datetime.now().isoformat(timespec='seconds')} GET  {self.path} from {self.client_address[0]}")
        self._send(200, AUTO if path == "/auto" else FORM)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8", "replace")
        log(f"{datetime.now().isoformat(timespec='seconds')} POST {self.path} from {self.client_address[0]} body={body}")
        self._send(200, "<h3>received</h3><pre>" + body + "</pre>")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    log(f"{datetime.now().isoformat(timespec='seconds')} server up on 0.0.0.0:8099 (log={LOGFILE})")
    ThreadingHTTPServer(("0.0.0.0", 8099), H).serve_forever()
