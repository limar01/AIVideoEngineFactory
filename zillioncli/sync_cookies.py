#!/usr/bin/env python3
"""Kunin ang sariwang cookies mula sa probe browser (port 9222) at i-save sa
full_cookies.txt sa format na 'k=v, k=v' (kasya sa zion-ls)."""
from arenaAi_endpoints import ARENA_ORIGIN
import json, urllib.request, websocket
OUT = '/home/limar01/zillion/capture/full_cookies.txt'
data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=3))
ws = [t['webSocketDebuggerUrl'] for t in data if t.get('type') == 'page' and ARENA_ORIGIN in t.get('url', '')][0]
c = websocket.create_connection(ws, timeout=30); mid = [0]
def send(m, p=None):
    mid[0] += 1; c.send(json.dumps({'id': mid[0], 'method': m, 'params': p or {}}))
    while True:
        r = json.loads(c.recv())
        if r.get('id') == mid[0]: return r
send('Network.enable')
ck = send('Network.getAllCookies')
cookies = ck.get('result', {}).get('cookies', [])
# I-filter ang arena-related na cookies
pairs = []
for ck2 in cookies:
    name = ck2.get('name', '')
    val = ck2.get('value', '')
    # I-save ang mahahalagang cookies (auth, cf, atbp.)
    if name in ('arena-auth-prod-v1.0', 'arena-auth-prod-v1.1', 'cf_clearance', '__cf_bm', 'side-tsq', 'viewed_product_category'):
        pairs.append('%s=%s' % (name, val))
# Idagdag din ang lahat ng domain na arena.ai
for ck2 in cookies:
    if 'arena.ai' in ck2.get('domain', '') and (ck2.get('name') + '=' + ck2.get('value')) not in pairs:
        pairs.append('%s=%s' % (ck2.get('name'), ck2.get('value')))
text = ', '.join(dict.fromkeys(pairs))  # dedupe
open(OUT, 'w').write(text)
print('SAVED %d cookies (%d chars) -> %s' % (len(set(pairs)), len(text), OUT))
print(text[:120], '...')
