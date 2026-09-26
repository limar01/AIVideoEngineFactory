#!/usr/bin/env python3
"""Probe: i-fetch ang raw RSC ng isang session at i-report ang role/type structure."""
from arenaAi_endpoints import ARENA_ORIGIN

def get_ws():
    data = json.load(urllib.request.urlopen('http://127.0.0.1:9222/json'))
    for t in data:
        if t.get('type') == 'page' and ARENA_ORIGIN in t.get('url', ''):
            return t['webSocketDebuggerUrl']
    return None

DEFAULT_SID = '01a0534d-de58'
SID_PREFIX = '01a0534d-de58'

def main():
    # Kunin ang buong sid mula sa history via /json? no. Subukan ang kasalukuyan at ang prefix.
    sid = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SID
    ws_url = get_ws()
    if not ws_url:
        print('NO_WS'); sys.exit(1)
    c = websocket.create_connection(ws_url, timeout=45)
    mid = [0]
    def send(m, p=None):
        mid[0] += 1
        c.send(json.dumps({'id': mid[0], 'method': m, 'params': p or {}}))
        while True:
            msg = json.loads(c.recv())
            if msg.get('id') == mid[0]:
                return msg
    send('Runtime.enable')
    expr = ("(async()=>{const r=await fetch('/agent/" + sid + "',"
            "{headers:{'accept':'text/html','rsc':'1'}});"
            "const t=await r.text();return t;})()")
    r = send('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True})
    t = r.get('result', {}).get('result', {}).get('value', '')
    print('LEN', len(t))
    print('roles:', sorted(set(re.findall(r'"role":"[a-z]+"', t))))
    print('types:', sorted(set(re.findall(r'"type":"[a-z]+"', t))))
    # sample ng bawat type:text na may paligid
    for mm in re.finditer(r'"type":"text"', t):
        i = mm.start()
        print('---')
        print(repr(t[max(0, i-60):i+90]))
        if i > 20000:
            break

main()
