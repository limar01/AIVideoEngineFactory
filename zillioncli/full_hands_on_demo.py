#!/usr/bin/env python3
import os, sys, time, json, urllib.request, websocket

DEBUG_PORT = '9223'

class AppCDP:
    def __init__(self):
        data = json.load(urllib.request.urlopen(f'http://127.0.0.1:{DEBUG_PORT}/json', timeout=5))
        pages = [t for t in data if t.get('type') == 'page' and '8890' in t.get('url', '')]
        if not pages:
            raise RuntimeError('Zillion CLI app page not found on port ' + DEBUG_PORT)
        ws_url = pages[0]['webSocketDebuggerUrl']
        self.ws = websocket.create_connection(ws_url, timeout=45)
        self.mid = 0

    def eval(self, expr):
        self.mid += 1
        payload = {
            'id': self.mid,
            'method': 'Runtime.evaluate',
            'params': {
                'expression': expr,
                'awaitPromise': False,
                'returnByValue': True
            }
        }
        self.ws.send(json.dumps(payload))
        while True:
            r = json.loads(self.ws.recv())
            if r.get('id') == self.mid:
                return r.get('result', {}).get('result', {}).get('value')

def main():
    print('Connecting to ZILLION CLI App on DELL monitor...')
    cdp = AppCDP()
    print('Connected!')

    # 0. Reset UI
    print('Resetting terminal console...')
    cdp.eval('clear()')
    time.sleep(2)

    # 1. STATUS
    print('▶ Step 1: Clicking STATUS button in UI...')
    cdp.eval("""document.querySelector('.btn[data-c="status"]').click()""")
    time.sleep(4.5)

    # 2. HISTORY
    print('▶ Step 2: Clicking HISTORY button in UI...')
    cdp.eval("""document.querySelector('.btn[data-c="ls 8"]').click()""")
    time.sleep(4.5)

    # 3. HELP
    print('▶ Step 3: Clicking HELP button in UI...')
    cdp.eval("""document.querySelector('.btn[data-c="help"]').click()""")
    time.sleep(4.5)

    # 4. OPEN
    print('▶ Step 4: Running OPEN command in UI...')
    cdp.eval('submitCmd("open 01a059f7-6275")')
    time.sleep(4.5)

    # 5. SEND PROMPT
    prompt = 'In one powerful sentence, describe how Boss and Zillion AI conquer any engineering challenge.'
    print(f'▶ Step 5: Typing and sending live prompt: {prompt}...')
    cdp.eval('cmdEl.value = ' + json.dumps(prompt) + '; goEl.click();')
    print('Waiting for live AI response in UI...')
    time.sleep(18)

    # 6. SAVE SESSION
    print('▶ Step 6: Clicking SAVE SESSION button in UI...')
    cdp.eval('document.getElementById("saveBtn").click()')
    time.sleep(3)

    print('Full Hands-on Demo Completed Successfully!')

if __name__ == '__main__':
    main()
