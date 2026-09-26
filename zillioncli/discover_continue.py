#!/usr/bin/env python3
"""I-discover ang continuation endpoint ng Arena agent chat sa headless Chrome (9333).
Naglo-load ng isang session page, nag-type ng follow-up sa composer, at kinukuha
ang network request na ginagawa ng frontend (para malaman ang endpoint)."""
import json, urllib.request, websocket, time, sys

PORT = 9333
SID = sys.argv[1] if len(sys.argv) > 1 else '01a0534d-de58-77d6-8c1d-5be288987fbd'
TEST_MSG = 'TEST followup 123'

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
    c = websocket.create_connection(ws_url, timeout=90); mid = [0]
    captured = []
    def send(m, p=None):
        mid[0] += 1; c.send(json.dumps({'id': mid[0], 'method': m, 'params': p or {}}))
        while True:
            r = json.loads(c.recv())
            if r.get('id') == mid[0]: return r
    # I-register ang event handler (dapat id 0-ish ang network events, wala id)
    send('Runtime.enable'); send('Page.enable'); send('Network.enable')
    # Basahin ang anumang incoming network events habang nasa loop
    # (kolektahin ang requestWillBeSent sa pamamagitan ng hiwalay na read loop)
    def collect(timeout_s):
        c.settimeout(1)
        end = time.time() + timeout_s
        while time.time() < end:
            try:
                msg = json.loads(c.recv())
            except Exception:
                continue
            m = msg.get('method')
            if m == 'Network.requestWillBeSent':
                url = msg.get('params', {}).get('request', {}).get('url', '')
                if 'stream' in url or 'nextjs-api' in url or ARENA_AGENT_PAGE_TEMPLATE[:-1] in url or 'api' in url:
                    captured.append(url)
            if m == 'Network.responseReceived':
                pass
    send('Page.navigate', {'url': f'{ARENA_ORIGIN}{ARENA_AGENT_PAGE_TEMPLATE.format(sid=sid)}'})
    collect(7)  # maghintay sa pag-load
    r = send('Runtime.evaluate', {'expression': 'document.body?document.body.innerText.slice(0,80):""', 'returnByValue': True})
    # Hanapin ang tiptap editor
    r2 = send('Runtime.evaluate', {'expression': 'var e=document.querySelector(".tiptap"); if(e){e.focus(); "FOCUSED"}else{"NO_TIPTAP"}', 'returnByValue': True})
    print('editor:', r2.get('result', {}).get('result', {}).get('value'))
    # I-type ang test message
    send('Input.insertText', {'text': TEST_MSG})
    time.sleep(0.5)
    # Pindutin ang Enter para mag-send
    send('Input.dispatchKeyEvent', {'type': 'keyDown', 'windowsVirtualKeyCode': 13, 'nativeVirtualKeyCode': 13, 'key': 'Enter', 'code': 'Enter', 'text': '\r'})
    send('Input.dispatchKeyEvent', {'type': 'keyUp', 'windowsVirtualKeyCode': 13, 'nativeVirtualKeyCode': 13, 'key': 'Enter', 'code': 'Enter'})
    print('typed + Enter pressed, waiting for network...')
    collect(15)  # makuha ang follow-up request
    # I-print ang mga nakuhang URL
    seen = []
    for u in captured:
        if u not in seen:
            seen.append(u)
    print('=== CAPTURED REQUESTS ===')
    for u in seen:
        print(u)

main()
