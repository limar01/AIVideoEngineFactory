#!/usr/bin/env python3
"""
Zillion Mobile CLI (Phone Edition)
Full CLI client for Android Termux / Linux Phone
"""

import json
import os
import sys
import time
import urllib.request

SESSION_FILE = os.path.expanduser("~/.zion/session.json")
PC_BRIDGE_HOST = os.environ.get("ZILLION_PC_HOST", "127.0.0.1:8890")

def print_banner():
    print("⚡ Z I L L I O N   M O B I L E   C L I ⚡")
    print("Arena AI Agent Mode — Phone Edition (Android / Termux)")
    print("Commands: send, status, autoheal, restore, me, ls, help\n")

def run_cmd(cmd_name, args):
    if cmd_name in ("help", "--help", "-h", ""):
        print_banner()
        print("Usage:")
        print("  zion send <message>      Send prompt to Arena AI")
        print("  zion status              Check connection & probe status")
        print("  zion restore             Run Strict Auto-Restore (§37)")
        print("  zion autoheal            Trigger 1-Click Auto-Heal & Temp Account")
        print("  zion me                  Show current account info")
        print("  zion ls                  List chat history")
        return

    url = f"http://{PC_BRIDGE_HOST}/api/cmd"
    full_cmd = f"{cmd_name} {' '.join(args)}".strip()
    payload = json.dumps({"cmd": full_cmd}).encode()
    
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode())
            if data.get("error"):
                print(f"❌ Error: {data['error']}")
            elif data.get("output"):
                print(data["output"])
            else:
                print("✔ Done.")
    except Exception as e:
        print(f"❌ Connection error to Zillion host ({PC_BRIDGE_HOST}): {e}")
        print("Hint: Make sure Zillion Web Hub is running on your PC or locally.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_banner()
        print("Tip: run 'zion send \"hello\"' or 'zion help'")
    else:
        run_cmd(sys.argv[1], sys.argv[2:])
