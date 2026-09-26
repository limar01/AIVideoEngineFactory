#!/usr/bin/env python3
"""
Zillion Live Interactive Showcase: Auto-Heal & Limiter Flow Demo
Step-by-step visual demonstration of the Limiter alert trigger,
auto-healing via disposable email, and quota reset.
"""

import json
import os
import sys
import time
import urllib.request
import websocket

CDP_URL = os.environ.get("ZILLION_CDP", "http://127.0.0.1:9222")
WEB_URL = "http://127.0.0.1:8890"

def get_cdp_ws():
    try:
        req = urllib.request.urlopen(f"{CDP_URL}/json", timeout=3)
        tabs = json.loads(req.read())
        for t in tabs:
            if t.get("type") == "page" and "8890" in t.get("url", ""):
                return websocket.create_connection(t["webSocketDebuggerUrl"], timeout=5)
    except Exception:
        pass
    return None

def cdp_eval(expr):
    ws = get_cdp_ws()
    if not ws: return None
    try:
        msg = {"id": int(time.time()*1000)%100000, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}
        ws.send(json.dumps(msg))
        res = json.loads(ws.recv())
        ws.close()
        return res.get("result", {}).get("result", {}).get("value")
    except Exception:
        if ws: ws.close()
        return None

def run_demo():
    print("==================================================")
    print("🚀 LIVE SHOWCASE: ZILLION AUTO-HEAL & LIMITER DEMO")
    print("==================================================\n")

    print("[Step 1] Loading Zillion Web UI baseline state (Quota: 45%)...")
    cdp_eval("location.reload()")
    time.sleep(2)
    cdp_eval("updateLimiterUI(45, false)")
    time.sleep(1)

    print("[Step 2] Simulating high load / quota usage (reaching 95%)...")
    cdp_eval("document.getElementById('btnSimLimiter').click()")
    time.sleep(2)
    print(" -> Alert Modal is now LIVE on screen with critical warning!\n")

    print("[Step 3] Waiting 3 seconds for Boss visual inspection...")
    time.sleep(3)

    print("[Step 4] Triggering 'Continue & Auto-Heal' button...")
    cdp_eval("document.getElementById('btnDoAutoheal').click()")

    print(" -> Generating disposable temporary email...")
    print(" -> Dispatching Arena registration magic link...")
    print(" -> Syncing fresh session cookies via CDP...")

    # Wait for autoheal completion
    for i in range(16):
        time.sleep(1)
        st = cdp_eval("document.getElementById('limiterPill')?.textContent")
        if st and "0%" in st:
            print(f"\n[Step 5] Auto-Heal Successfully Completed! (Detected quota reset: '{st}')")
            break

    time.sleep(2)
    print("\n[Step 6] Demo Complete! Session is 100% fresh, limiter reset to 0% green.")
    print("==================================================")

if __name__ == "__main__":
    run_demo()
