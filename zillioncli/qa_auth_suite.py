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
        self.ws = websocket.create_connection(ws_url, timeout=30)
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
    print('=== QA AUTH & ACCOUNT SUITE START ===')
    cdp = AppCDP()
    cdp.eval('clear()')
    time.sleep(2)

    # QA 1: WHOAMI (/api/me)
    print('▶ Running QA 1: WHOAMI (/api/me)...')
    cdp.eval("submitCmd('whoami')")
    time.sleep(3)

    # QA 2: SIGNUP INVALID EMAIL
    print('▶ Running QA 2: SIGNUP (Invalid email validation)...')
    cdp.eval("submitCmd('signup invalid_format_email')")
    time.sleep(3)

    # QA 3: SIGNUP VALID MAGIC LINK
    print('▶ Running QA 3: SIGNUP (Valid magic link dispatch)...')
    cdp.eval("submitCmd('signup zillion_boss_qa@fanzher.com')")
    time.sleep(3)

    # QA 4: LOGIN INVALID CREDENTIALS
    print('▶ Running QA 4: LOGIN (Invalid credentials check)...')
    cdp.eval("submitCmd('login boss_qa@arena.ai wrong_password_123')")
    time.sleep(3)

    # QA 5: STATUS CHECK
    print('▶ Running QA 5: STATUS DIAGNOSTIC...')
    cdp.eval("submitCmd('status')")
    time.sleep(3)

    print('=== QA AUTH & ACCOUNT SUITE COMPLETE ===')

if __name__ == '__main__':
    main()
