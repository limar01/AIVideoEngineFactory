#!/usr/bin/env python3
"""Probe: i-extract ang assistant text mula sa RSC flight data nang walang page navigation."""
from arenaAi_endpoints import ARENA_ORIGIN

def get_ws():
    data = json.load(urllib.request.urlopen('http://127.0.0.1:9222/json'))
    for t in data:
        if t.get('type') == 'page' and ARENA_ORIGIN in t.get('url', ''):
            return t['webSocketDebuggerUrl']
    return None

def main():
    sid = sys.argv[1] if len(sys.argv) > 1 else None
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

    # Kung walang sid, kunin ang kasalukuyan mula sa URL
    if not sid:
        expr = "location.pathname.split('/').pop()"
        r = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
        sid = r.get('result', {}).get('result', {}).get('value', '')
        print('USING current sid:', sid)

    # Fetch RSC at i-extract ang assistant text parts
    expr = f'''(async()=>{{
      const r=await fetch('/agent/{sid}', {{headers:{{'accept':'text/html','rsc':'1'}}}});
      const txt=await r.text();
      // i-extract ang lahat ng "text":"..." na may kasamang type:"text" (assistant reply, hindi reasoning)
      // Ang assistant text parts ay may {{"type":"text","text":"..."}} na state done.
      const matches=[];
      const re=/\\{{\"type\":\"text\",\"text\":\"((?:[^\"\\\\]|\\\\.)*)\"[^}}\\}}]*\\}}/g;
      let m;
      while((m=re.exec(txt))!==null){{ matches.push(m[1]); }}
      return JSON.stringify({{status:r.status, len:txt.length, texts:matches}});
    }})()'''
    r = send('Runtime.evaluate', {'expression': expr, 'awaitPromise': True, 'returnByValue': True})
    val = r.get('result', {}).get('result', {}).get('value', '')
    try:
        d = json.loads(val)
        print('STATUS:', d.get('status'), '| LEN:', d.get('len'))
        print('TEXTS found:', len(d.get('texts', [])))
        for i, t in enumerate(d.get('texts', [])):
            print(f'  [{i}] ({len(t)} chars):')
            print('  ----')
            print(t)
            print('  ----')
    except Exception as e:
        print('RAW:', val[:800])

main()
