#!/usr/bin/env python3
import json, urllib.request, websocket, time
PORT = 9222
data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=3))
ws = [t['webSocketDebuggerUrl'] for t in data if t.get('type') == 'page'][0]
c = websocket.create_connection(ws, timeout=30); mid = [0]
def send(m, p=None):
    mid[0] += 1; c.send(json.dumps({'id': mid[0], 'method': m, 'params': p or {}}))
    while True:
        r = json.loads(c.recv())
        if r.get('id') == mid[0]: return r
send('Runtime.enable')
expr = '''(function(){
  var txt=document.body?document.body.innerText:'';
  return JSON.stringify({
    url: location.href,
    len: txt.length,
    head: txt.slice(0,300),
    tiptap: document.querySelectorAll('.tiptap').length,
    ce: document.querySelectorAll('[contenteditable=true]').length,
    ta: document.querySelectorAll('textarea').length,
    sendbtns: [].slice.call(document.querySelectorAll('button')).filter(function(b){return /send|submit|ask/i.test(b.textContent||'')}).length
  });
})()'''
r = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
print(r.get('result', {}).get('result', {}).get('value', ''))
