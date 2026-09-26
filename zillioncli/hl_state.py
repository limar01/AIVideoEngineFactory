#!/usr/bin/env python3
import json, urllib.request, websocket, time
PORT = 9333
def get_ws():
    data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=3))
    for t in data:
        if t.get('type') == 'page':
            return t['webSocketDebuggerUrl']
    return None
ws_url = get_ws()
c = websocket.create_connection(ws_url, timeout=30); mid = [0]
def send(m, p=None):
    mid[0] += 1; c.send(json.dumps({'id': mid[0], 'method': m, 'params': p or {}}))
    while True:
        r = json.loads(c.recv())
        if r.get('id') == mid[0]: return r
send('Runtime.enable')
expr = '''(function(){
  return JSON.stringify({
    url: location.href,
    body: (document.body?document.body.innerText:'').slice(0,400),
    tiptap: document.querySelectorAll('.tiptap').length,
    prose: document.querySelectorAll('[contenteditable=true]').length,
    textarea: document.querySelectorAll('textarea').length,
    placeholder: (document.body?document.body.querySelectorAll('[data-placeholder]').length:0)
  });
})()'''
r = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
print(r.get('result', {}).get('result', {}).get('value', ''))
