#!/usr/bin/env python3
"""
zion status — kalusugan ng zion CLI at ng probe browser.

Tinitignan:
  - online ba ang probe browser (port 9222)?
  - naka-login ba sa Arena (may arena-auth cookie / naka-arena.ai page)?
  - ano ang kasalukuyang URL ng probe?
"""
import json, urllib.request, sys, os, time
from datetime import datetime

DEBUG_PORT = os.environ.get('ZION_PORT', '9222')

def cdp_ws():
    try:
        data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json', timeout=3))
    except Exception:
        return None, []
    pages = [t for t in data if t.get('type') == 'page' and 'arena.ai' in t.get('url', '')]
    ws = pages[0]['webSocketDebuggerUrl'] if pages else None
    return ws, pages

def main():
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'zion status — {now}')
    ws, pages = cdp_ws()
    if not ws:
        print('✗  probe browser: OFFLINE (wala sa port %s).' % DEBUG_PORT)
        print('   I-launch: chromium --user-data-dir=~/.config/chromium-zillion-probe \\')
        print('             --remote-debugging-port=%s --remote-allow-origins=* https://arena.ai/agent' % DEBUG_PORT)
        sys.exit(1)
    print('✓  probe browser: ONLINE')

    url = pages[0].get('url', '') if pages else ''
    print(f'   page: {url}')

    # Suriin ang login state
    import websocket
    c = websocket.create_connection(ws, timeout=15)
    mid = [0]
    def send(m, p=None):
        mid[0] += 1
        c.send(json.dumps({'id': mid[0], 'method': m, 'params': p or {}}))
        while True:
            r = json.loads(c.recv())
            if r.get('id') == mid[0]:
                return r
    send('Network.enable')
    ck = send('Network.getAllCookies')
    cookies = ck.get('result', {}).get('cookies', [])
    auth = [k for k in ('arena-auth-prod-v1.0', 'arena-auth-prod-v1.1', 'cf_clearance') if any(x.get('name') == k for x in cookies)]
    if auth:
        print('✓  login: naka-login sa Arena (may auth cookies: %s)' % ', '.join(auth))
    else:
        print('✗  login: HINDI mahanap ang auth cookies — baka na-logout (i-refresh ang login sa browser)')

    # User identifier mula sa cookies/URL kung available
    try:
        send('Runtime.enable')
        r = send('Runtime.evaluate', {'expression': 'document.body ? (document.body.innerText||"").slice(0,0) : ""', 'returnByValue': True})
    except Exception:
        pass

    # Bilang ng arena pages
    print(f'   arena page(s): {len(pages)}')
    print('\nGamit ng zion: tiyakin na ang probe browser ay ONLINE at naka-login bago gumamit ng `zion send`.')

main()
