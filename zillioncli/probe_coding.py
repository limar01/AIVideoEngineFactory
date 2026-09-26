#!/usr/bin/env python3
import json, urllib.request, websocket, time
PORT = 9222
SID = '01a0537a-c3ed-7b71-bdfa-0f41375c9638'
data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=3))
ws = [t['webSocketDebuggerUrl'] for t in data if t.get('type') == 'page'][0]
c = websocket.create_connection(ws, timeout=40); mid = [0]
def send(m, p=None):
    mid[0] += 1; c.send(json.dumps({'id': mid[0], 'method': m, 'params': p or {}}))
    while True:
        r = json.loads(c.recv())
        if r.get('id') == mid[0]: return r
send('Runtime.enable')
expr = '''(async()=>{
  const res = {};
  async function tryFetch(name, url){
    try{
      const r = await fetch(url, {credentials:'same-origin'});
      const t = await r.text();
      res[name] = 'STATUS:'+r.status+' LEN:'+t.length+' HEAD:'+t.slice(0,120);
    }catch(e){ res[name]='ERR '+e.message; }
  }
  await tryFetch('sessions', '/api/coding-agent/sessions/'+SID);
  await tryFetch('workflow', '/api/coding-agent/sessions/'+SID+'/workflow-checks');
  return JSON.stringify(res);
})()'''.replace('SID', json.dumps(SID))
r = send('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True})
print(r.get('result', {}).get('result', {}).get('value', ''))
