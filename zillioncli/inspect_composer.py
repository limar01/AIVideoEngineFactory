#!/usr/bin/env python3
"""Suriin ang kasalukuyang agent page para sa message composer."""
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
expr = '''(function(){
  const ta=document.querySelector('textarea');
  const ce=document.querySelector('[contenteditable=true]');
  const inputs=[...document.querySelectorAll('input,[contenteditable=true],textarea')].map(i=>({tag:i.tagName,ph:(i.getAttribute('placeholder')||'').slice(0,40),cls:(i.className||'').toString().slice(0,30)}));
  const btns=[...document.querySelectorAll('button')].map(b=>(b.textContent||'').trim().slice(0,20)).filter(Boolean);
  return JSON.stringify({url:location.href, textarea:ta?'YES':'no', contenteditable:ce?'YES':'no', inputs, btns:btns.slice(0,15)});
})()'''
r = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
print(r.get('result', {}).get('result', {}).get('value', ''))
