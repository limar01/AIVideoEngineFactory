#!/usr/bin/env python3
import json, urllib.request, websocket, time, sys
PORT = 9333
SID = sys.argv[1] if len(sys.argv) > 1 else '01a0534d-de58-77d6-8c1d-5be288987fbd'
TEST = 'TEST followup 456'
def get_ws():
    data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{PORT}/json', timeout=3))
    for t in data:
        if t.get('type') == 'page':
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
    def collect(timeout_s):
        end = time.time() + timeout_s
        while time.time() < end:
            try:
                c.settimeout(1); msg = json.loads(c.recv())
            except Exception:
                continue
            m = msg.get('method')
            if m == 'Network.requestWillBeSent':
                url = msg.get('params', {}).get('request', {}).get('url', '')
                ua = msg.get('params', {}).get('request', {}).get('method', '')
                if ('stream' in url or 'nextjs-api' in url) :
                    captured.append((ua, url))
            elif m == 'Network.webSocketCreated':
                captured.append(('WS', msg.get('params', {}).get('url', '')))
    send('Page.navigate', {'url': f'{ARENA_ORIGIN}{ARENA_AGENT_PAGE_TEMPLATE.format(sid=sid)}'})
    collect(14)  # mahabang wait para sa render
    # Hanapin ang komposer — kahit anong visible na input
    expr = '''(function(){
      var cands=[];
      document.querySelectorAll('textarea,[contenteditable=true],input').forEach(function(e){
        var r=e.getBoundingClientRect();
        var isRecaptcha=(e.className||'').toString().indexOf('recaptcha')>-1;
        if(!isRecaptcha && r.width>100 && r.height>20){cands.push(e);}
      });
      var pick=cands.sort(function(a,b){return (b.getBoundingClientRect().width)-(a.getBoundingClientRect().width);})[0];
      if(!pick)return 'NONE';
      pick.focus(); pick.scrollIntoView();
      return pick.tagName+':'+(pick.getAttribute('placeholder')||'')+':'+(pick.className||'').toString().slice(0,30);
    })()'''
    r = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True})
    print('composer pick:', r.get('result', {}).get('result', {}).get('value'))
    # I-type at i-send
    send('Input.insertText', {'text': TEST})
    time.sleep(0.6)
    send('Input.dispatchKeyEvent', {'type': 'keyDown', 'windowsVirtualKeyCode': 13, 'key': 'Enter', 'code': 'Enter', 'text': '\r'})
    send('Input.dispatchKeyEvent', {'type': 'keyUp', 'windowsVirtualKeyCode': 13, 'key': 'Enter', 'code': 'Enter'})
    time.sleep(1)
    # Subukan ding i-click ang submit button kung mayroon
    click = send('Runtime.evaluate', {'expression': '''(function(){var btns=[].slice.call(document.querySelectorAll('button')); for(var i=0;i<btns.length;i++){var t=(btns[i].textContent||'').trim(); if(/submit|send/i.test(t)){btns[i].click(); return 'CLICKED:'+t;}} return 'no-submit-btn';})()''', 'returnByValue': True})
    print('submit attempt:', click.get('result', {}).get('result', {}).get('value'))
    print('waiting for the follow-up request...')
    collect(25)
    print('=== CAPTURED (stream/nextjs-api) ===')
    for m2, u in captured:
        print(m2, u)
main()
