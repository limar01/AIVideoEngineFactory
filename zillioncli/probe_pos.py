#!/usr/bin/env python3
import json, urllib.request, websocket
data = json.load(urllib.request.urlopen('http://127.0.0.1:9222/json'))
ws = [t['webSocketDebuggerUrl'] for t in data if t.get('type') == 'page' and 'arena.ai' in t.get('url', '')][0]
c = websocket.create_connection(ws, timeout=30); mid = [0]
def send(m, p=None):
    mid[0] += 1; c.send(json.dumps({'id': mid[0], 'method': m, 'params': p or {}}))
    while True:
        r = json.loads(c.recv())
        if r.get('id') == mid[0]: return r
send('Runtime.enable')
expr = 'window.screenX + "," + window.screenY + " | availLeft=" + screen.availLeft + " | dpr=" + window.devicePixelRatio'
r = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
print('probe window:', r.get('result', {}).get('result', {}).get('value'))
