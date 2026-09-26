#!/usr/bin/env python3
import os, sys, time, json, urllib.request, websocket, base64

DEBUG_PORT = "9223"

class AppCDP:
    def __init__(self):
        data = json.load(urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=5))
        pages = [t for t in data if t.get("type") == "page" and "8890" in t.get("url", "")]
        if not pages:
            raise RuntimeError("Zillion CLI app page not found on port " + DEBUG_PORT)
        ws_url = pages[0]["webSocketDebuggerUrl"]
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self.mid = 0

    def eval(self, expr, await_promise=False):
        self.mid += 1
        payload = {
            "id": self.mid,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expr,
                "awaitPromise": await_promise,
                "returnByValue": True
            }
        }
        self.ws.send(json.dumps(payload))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == self.mid:
                return r.get("result", {}).get("result", {}).get("value")

def main():
    print("Connecting to ZILLION CLI App on DELL monitor...")
    cdp = AppCDP()
    print("Connected!")

    # 0. Clear and banner
    print("Resetting terminal view...")
    cdp.eval("clear()")
    time.sleep(2)

    # 1. Trigger STATUS
    print("▶ Triggering STATUS via UI...")
    cdp.eval("submitCmd('status')")
    time.sleep(4)

    # 2. Trigger HISTORY (ls 5)
    print("▶ Triggering HISTORY via UI...")
    cdp.eval("submitCmd('ls 5')")
    time.sleep(4)

    # 3. Trigger HELP
    print("▶ Triggering HELP via UI...")
    cdp.eval("submitCmd('help')")
    time.sleep(4)

    # 4. Trigger OPEN latest session
    print("▶ Triggering OPEN session transcript via UI...")
    cdp.eval("submitCmd('open 01a059ea-ecbf')")
    time.sleep(4)

    # 5. Trigger FILE ATTACHMENT + MULTIMODAL AGENT PROMPTING
    print("▶ Triggering ATTACHMENT + AGENT PROMPT via UI...")
    sample_text = "MISSION: Build Arena AI Tycoon and Autonomous Stack. PARTNERSHIP: Boss (Owner) + Zillion (Lead)."
    b64_data = "data:text/plain;base64," + base64.b64encode(sample_text.encode()).decode()
    inj_js = f"attachments=[{{filename:'mission_brief.txt',mimeType:'text/plain',dataUrl:'{b64_data}',size:{len(sample_text)}}}];renderAttach();cmdEl.value='Review mission brief and state our battle cry!';"
    cdp.eval(inj_js)
    time.sleep(3)

    # Click GO to submit
    print("▶ Submitting agent message with attachment...")
    cdp.eval("goEl.click()")
    print("Waiting for live AI stream in UI...")
    time.sleep(16)

    # 6. Trigger SAVE SESSION
    print("▶ Triggering SAVE SESSION via UI...")
    cdp.eval("document.getElementById('saveBtn').click()")
    time.sleep(3)

    print("Demo sequence finished!")

if __name__ == "__main__":
    main()