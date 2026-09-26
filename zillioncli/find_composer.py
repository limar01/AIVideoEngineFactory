#!/usr/bin/env python3
"""I-load ang isang session page sa probe at i-poll hanggang 50s para sa composer.
Kapag nahanap, i-drive ito para mag-follow-up at makuha ang continuation request."""
import json, urllib.request, websocket, time, sys
PORT = 9222
SID = sys.argv[1] if len(sys.argv) > 1 else '01a0537a-c3ed-7b71-bdfa-0f41375c9638'
TEST = 'follow up: anong 9*9?'
def get_ws():
    data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=3))
    for t in data:
        if t.get('type') == 'page': return t['webSocketDebuggerUrl']
    return None
def main():
    ws_url = get_ws()
    if not ws_url:
        print('NO_WS'); sys.exit(1)
    c = websocket.create_connection(ws_url, timeout=140); mid = [0]
    captured = []
    def send(m, p=None):
        mid[0] += 1; c.send(json.dumps({'id': mid[0], 'method': m, 'params': p or {}}))
        while True:
            r = json.loads(c.recv())
            if r.get('id') == mid[0]: return r
    send('Runtime.enable'); send('Page.enable'); send('Network.enable')
    def collect(ts, also_capture=True):
        end = time.time() + ts
        while time.time() < end:
            try:
                c.settimeout(1); msg = json.loads(c.recv())
            except Exception:
                continue
            m = msg.get('method')
            if also_capture and m == 'Network.requestWillBeSent':
                req = msg.get('params', {}).get('request', {})
                url = req.get('url', '')
                if 'stream' in url or 'nextjs-api' in url:
                    captured.append(req.get('method','')+' '+url)
    send('Page.navigate', {'url': f'{ARENA_ORIGIN}{ARENA_AGENT_PAGE_TEMPLATE.format(sid=sid)}'})
    # Poll para sa composer (hanggang ~45s)
    found = False
    for i in range(15):
        collect(3)
        expr = '''(function(){
          var e=document.querySelector('.tiptap')||document.querySelector('[contenteditable=true]');
          var vis=[].slice.call(document.querySelectorAll('textarea')).filter(function(x){var r=x.getBoundingClientRect();return r.width>100&&r.height>20;})[0];
          var pick=e||vis;
          return pick ? (pick.tagName+':'+(pick.className||'').toString().slice(0,20)) : (document.body.innerText.slice(-100));
        })()'''
        r = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
        v = r.get('result', {}).get('result', {}).get('value', '')
        print('poll%d: %s' % (i, v[:60]))
        if v and ':' in v and v.split(':')[0] in ('DIV','TEXTAREA','P','INPUT'):
            # composer found
            found = True
            send('Runtime.evaluate', {'expression': __import__('json').dumps('(function(){var e=document.querySelector(".tiptap")||document.querySelector("[contenteditable=true]");e.focus();return "FOCUSED";})()'), 'returnByValue': True})
            send('Input.insertText', {'text': TEST})
            time.sleep(0.5)
            send('Input.dispatchKeyEvent', {'type':'keyDown','windowsVirtualKeyCode':13,'key':'Enter','code':'Enter','text':'\r'})
            send('Input.dispatchKeyEvent', {'type':'keyUp','windowsVirtualKeyCode':13,'key':'Enter','code':'Enter'})
            print('!!! COMPOSER FOUND - SAKAT NG TYPED SEND')
            collect(25)
            break
    if not found:
        print('NO COMPOSER after 45s')
    print('=== CAPTURED ===')
    for u in dict.fromkeys(captured):
        print(u)
main()
