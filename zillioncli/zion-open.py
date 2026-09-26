#!/usr/bin/env python3
"""
zion open <session-id> — ipakita ang transcript ng isang Arena AI session.

Nag-fetch ng /agent/{sid} via RSC sa loob ng live browser (same-origin fetch,
WALANG page.navigate — hindi naglilipat ng focus). Ipinapakita ang mga message
(user at assistant). Heuristic para sa role: ang mga text parts ay pa-halili
[user, assistant, user, assistant, ...] — ito ang pattern ng Arena agent chat.
"""
from arenaAi_endpoints import ARENA_ORIGIN, ARENA_AGENT_PAGE_TEMPLATE
import json, urllib.request, websocket, sys, os, time

DEBUG_PORT = os.environ.get('ZION_PORT', '9222')

def get_ws():
    for _ in range(5):
        try:
            data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json', timeout=3))
            for t in data:
                if t.get('type') == 'page' and ARENA_ORIGIN in t.get('url', ''):
                    return t['webSocketDebuggerUrl']
        except Exception:
            time.sleep(1)
    return None

def rsc_texts(cdp, sid):
    js_re = r'\{"type":"text","text":"((?:[^"\\]|\\.)*)"[^}]*\}'
    expr = (
        "(async()=>{"
        "try{"
        "const r=await fetch('/agent/" + sid + "',"
        "{headers:{'accept':'text/html','rsc':'1'}});"
        "const txt=await r.text();"
        "const out=[];const re=/" + js_re + "/g;let m;"
        "while((m=re.exec(txt))!==null){out.push(m[1]);}"
        "return out;"
        "}catch(e){return ['__ERR__'+e.message];}"
        "})()"
    )
    r = cdp.eval(expr)
    val = r.get('result', {}).get('result', {}).get('value', '')
    if not isinstance(val, list):
        return []
    out = []
    for v in val:
        if isinstance(v, str):
            try:
                out.append(json.loads('"' + v + '"'))
            except Exception:
                out.append(v)
        else:
            out.append(v)
    return out

class CDP:
    def __init__(self, ws):
        self.ws = websocket.create_connection(ws, timeout=60)
        self.mid = [0]
    def eval(self, expr, awaitp=True):
        self.mid[0] += 1
        self.ws.send(json.dumps({'id': self.mid[0], 'method': 'Runtime.evaluate',
                                 'params': {'expression': expr, 'awaitPromise': awaitp, 'returnByValue': True}}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get('id') == self.mid[0]:
                return m

def main():
    if len(sys.argv) < 2:
        print('Usage: zion open <session-id>')
        sys.exit(1)
    sid = sys.argv[1].strip()
    ws_url = get_ws()
    if not ws_url:
        print('ERROR: probe browser offline — i-launch ito bago gamitin ang zion open.')
        sys.exit(1)
    cdp = CDP(ws_url)
    cdp.eval('void 0')
    texts = rsc_texts(cdp, sid)
    if not texts:
        print(f'(walang nahanap na message para sa session {sid} — siguraduhing tama ang session id)')
        sys.exit(1)
    # Heuristic: [user, assistant, user, assistant, ...]
    print(f'── Session: {sid} ──')
    for i, t in enumerate(texts):
        role = 'YOU' if i % 2 == 0 else 'ARENA'
        print(f'\n[{role}]')
        print(t.strip())
    print('\n── dulo ng transcript ──')

main()
