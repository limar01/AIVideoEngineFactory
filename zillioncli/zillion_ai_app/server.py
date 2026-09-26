#!/usr/bin/env python3
import http.server, json, os, subprocess, time, urllib.parse, re

PORT = int(os.environ.get('ZILLION_AI_PORT', '8891'))
ROOT = os.path.dirname(os.path.abspath(__file__))
ZION_SEND = os.path.expanduser('~/.local/bin/zion-send')
ACTIVE_CHAT_FILE = os.path.expanduser('~/.zion/active_chat_id')
HUB_STATUS = 'http://127.0.0.1:8890/api/status'

UUID_RE = re.compile(r'^[0-9a-f-]{36}$')

def read_active_sid():
    try:
        sid = open(ACTIVE_CHAT_FILE).read().strip()
        return sid if UUID_RE.match(sid) else ''
    except Exception:
        return ''

def write_active_sid(sid):
    if not sid or not UUID_RE.match(sid): return False
    os.makedirs(os.path.dirname(ACTIVE_CHAT_FILE), exist_ok=True)
    with open(ACTIVE_CHAT_FILE, 'w') as f: f.write(sid+'\n')
    os.chmod(ACTIVE_CHAT_FILE, 0o600)
    return True

def run(args, timeout=180):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=os.path.expanduser('~'))
        out = (p.stdout or '') + (('\n'+p.stderr) if p.stderr else '')
        return {'ok': p.returncode == 0, 'exit_code': p.returncode, 'output': out[-30000:]}
    except subprocess.TimeoutExpired:
        return {'ok': False, 'exit_code': -1, 'error': 'timeout', 'output': 'Timed out while waiting for Arena/Zillion response.'}
    except Exception as e:
        return {'ok': False, 'exit_code': -1, 'error': str(e), 'output': str(e)}

def parse_session(out):
    m = re.search(r'session:\s*([0-9a-f-]{36})', out or '', re.I)
    return m.group(1) if m else ''

def is_rate_limited(out):
    low = (out or '').lower()
    return 'too many requests' in low or 'rate limit' in low or '429' in low

def friendly_error(out, err=None):
    if is_rate_limited(out or err):
        return 'Arena is rate-limiting this session right now. Please wait a bit before sending again.'
    text = (out or err or '').strip()
    # Hide raw JSON/server wrapper unless it is the only useful detail.
    text = re.sub(r'^server:\s*', '', text, flags=re.I).strip()
    try:
        j = json.loads(text)
        return j.get('message') or j.get('error') or text
    except Exception:
        return text[-2000:] if text else 'Request failed.'

def extract_answer(out):
    if not out: return ''
    if is_rate_limited(out):
        return friendly_error(out)
    marker = '━━━ AI RESPONSE ━━━'
    if marker in out:
        return out.split(marker, 1)[1].strip()
    lines = []
    for ln in out.splitlines():
        if ln.startswith('◆ '): continue
        if ln.strip(): lines.append(ln)
    return '\n'.join(lines).strip()

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=ROOT, **kw)
    def _json(self, obj, code=200):
        b=json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u=urllib.parse.urlparse(self.path)
        if u.path == '/api/status':
            sid=read_active_sid()
            self._json({'ok': True, 'app': 'Zillion AI App', 'version': '0.1-reskin', 'active_chat_id': sid[:13] if sid else '', 'has_active_session': bool(sid), 'port': PORT})
            return
        return super().do_GET()
    def do_POST(self):
        n=int(self.headers.get('Content-Length','0') or '0')
        raw=self.rfile.read(n) if n else b'{}'
        try: data=json.loads(raw or b'{}')
        except Exception as e: self._json({'ok':False,'error':'bad json: '+str(e)},400); return
        if self.path == '/api/session':
            sid=(data.get('session') or '').strip()
            ok=write_active_sid(sid)
            self._json({'ok':ok,'active_chat_id':sid[:13] if ok else '', 'error':None if ok else 'invalid session id'})
            return
        if self.path == '/api/send':
            msg=(data.get('message') or '').strip()
            if not msg:
                self._json({'ok':False,'error':'empty message'},400); return
            sid=read_active_sid()
            if sid:
                res=run([ZION_SEND, '--append', sid, msg], timeout=220)
                out=res.get('output','')
                # If Arena throttles us, DO NOT fallback to create-chat; that worsens throttling/recaptcha.
                if (not res.get('ok')) and is_rate_limited(out):
                    self._json({'ok': False, 'rate_limited': True, 'session': sid, 'session_display': sid[:13],
                                'raw': out, 'answer': friendly_error(out), 'exit_code': res.get('exit_code'),
                                'error': 'Too Many Requests'})
                    return
                # if stale/non-rate-limit session failed, create a new normal chat once
                if not res.get('ok'):
                    res=run([ZION_SEND, msg], timeout=220)
            else:
                res=run([ZION_SEND, msg], timeout=220)
            out=res.get('output','')
            ns=parse_session(out)
            if ns: write_active_sid(ns); sid=ns
            rate=is_rate_limited(out)
            self._json({'ok': bool(res.get('ok')) and not rate, 'rate_limited': rate,
                        'session': sid, 'session_display': sid[:13] if sid else '', 'raw': out,
                        'answer': extract_answer(out), 'exit_code': res.get('exit_code'),
                        'error': 'Too Many Requests' if rate else res.get('error')})
            return
        self._json({'ok':False,'error':'not found'},404)

if __name__ == '__main__':
    print(f'Zillion AI App listening on http://127.0.0.1:{PORT}', flush=True)
    http.server.ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
