#!/usr/bin/env python3
"""I-inject ang Arena cookies sa headless Chrome (port 9333) at i-verify ang login.
Hindi ito gumagamit ng probe (invisible headless) para hindi maistorbo ang user."""
from arenaAi_endpoints import ARENA_ORIGIN
import json, urllib.request, websocket, time, sys

PORT = 9333
COOKIE_FILE = '/home/limar01/zillion/capture/full_cookies.txt'

def get_ws():
    data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=3))
    for t in data:
        if t.get('type') == 'page':
            return t['webSocketDebuggerUrl']
    return None

def main():
    # I-parse ang cookies (k=v, k=v)
    raw = open(COOKIE_FILE).read().strip()
    cookies = {}
    for pair in raw.split(', '):
        if '=' in pair:
            k, v = pair.split('=', 1)
            cookies[k] = v
    print('COOKIES parsed:', len(cookies))
    ws_url = get_ws()
    if not ws_url:
        print('NO_WS'); sys.exit(1)
    c = websocket.create_connection(ws_url, timeout=60); mid = [0]
    def send(m, p=None):
        mid[0] += 1; c.send(json.dumps({'id': mid[0], 'method': m, 'params': p or {}}))
        while True:
            r = json.loads(c.recv())
            if r.get('id') == mid[0]: return r
    send('Network.enable')
    send('Page.enable')
    send('Runtime.enable')
    # UA override para hindi ma-block ng Cloudflare
    send('Network.setUserAgentOverride', {'userAgent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'})
    # I-set ang bawat cookie
    for k, v in cookies.items():
        send('Network.setCookie', {'name': k, 'value': v, 'domain': '.arena.ai', 'path': '/', 'url': ARENA_ORIGIN + '/'})
    time.sleep(0.5)
    send('Page.navigate', {'url': ARENA_ORIGIN + '/agent'})
    time.sleep(6)
    r = send('Runtime.evaluate', {'expression': 'location.href + " | " + (document.body?document.body.innerText.slice(0,150):"")', 'returnByValue': True})
    print('AFTER NAV:', r.get('result', {}).get('result', {}).get('value', ''))

main()
