#!/usr/bin/env python3
"""I-drive ang probe (port 9222, DELL) para makuha ang continuation endpoint.
Naglo-load ng session page, nag-type ng follow-up sa composer, at kinukuha
ang network request (applies no vertical hotkey over)."""
import json, urllib.request, websocket, time, sys
PORT = 9222
SID = sys.argv[1] if len(sys.argv) > 1 else '01a0537a-c3ed-7b71-bdfa-0f41375c9638'
TEST = 'Sundan mo ito: anong 2+2?'
def get_ws():
    data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=3))
    for t in data:
        if t.get('type') == 'page' and 'arena.ai' in t.get('url', ''):
            return t['webSocketDebuggerUrl']
    return None
def main():
    ws_url = get_ws()
    if not ws_url:
        print('NO_WS'); sys.exit(1)
    c = websocket.create_connection(ws_url, timeout=120); mid = [0]
    captured = []
    def send(m, p=None):
        mid[0] += 1; c.send(json.dumps({'id': mid[0], 'method': m, 'params': p or {}}))
        while True:
            r = json.loads(c.recv())
            if r.get('id') == mid[0]: return r
    send('Runtime.enable'); send('Page.enable'); send('Network.enable')
    def collect(ts):
        end = time.time() + ts
        while time.time() < end:
            try:
                c.settimeout(1); msg = json.loads(c.recv())
            except Exception:
                continue
            m = msg.get('method')
            if m == 'Network.requestWillBeSent':
                req = msg.get('params', {}).get('request', {})
                url = req.get('url', '')
                if 'stream' in url or 'nextjs-api' in url:
                    captured.append((req.get('method','') + ' ' + url))
            elif m == 'Network.webSocketCreated':
                captured.append('WS ' + msg.get('params', {}).get('url', ''))
    send('Page.navigate', {'url': f'{ARENA_ORIGIN}{ARENA_AGENT_PAGE_TEMPLATE.format(sid=sid)}'})
    collect(15)
    # Hanapin ang composer pagkatapos ng load
    expr = '''(function(){
      var e=document.querySelector('.tiptap')||document.querySelector('[contenteditable=true]');
      var ta=[].slice.call(document.querySelectorAll('textarea')).filter(function(x){return (x.className||'').toString().indexOf('recaptcha')===-1;})[0];
      var pick=e||ta;
      if(!pick)return 'NONE';
      pick.focus(); pick.scrollIntoView();
      return pick.tagName+':'+(pick.className||'').toString().slice(0,25);
    })()'''
    r = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
    print('composer:', r.get('result', {}).get('result', {}).get('value'))
    try:
        send('Input.insertText', {'text': TEST})
        time.sleep(0.6)
        send('Input.dispatchKeyEvent', {'type': 'keyDown', 'windowsVirtualKeyCode': 13, 'key': 'Enter', 'code': 'Enter', 'text': '\r'})
        send('Input.dispatchKeyEvent', {'type': 'keyUp', 'windowsVirtualKeyCode': 13, 'key': 'Enter', 'code': 'Enter'})
    except Exception as ex:
        print('input err:', ex)
    print('waiting for continuation request...')
    collect(25)
    print('=== CAPTURED (stream/nextjs-api) ===')
    for u in dict.fromkeys(captured):
        print(u)
main()
