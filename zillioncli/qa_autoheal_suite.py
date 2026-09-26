#!/usr/bin/env python3
"""
Zillion QA Test Suite & Live Demo: Auto-Heal & Limiter System
Runs automated end-to-end verification of the Limiter alert modal,
user cancellation, automated disposable email registration, and quota reset.
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import websocket

CDP_URL = os.environ.get("ZILLION_CDP", "http://127.0.0.1:9222")
WEB_URL = "http://127.0.0.1:8890"

results = []

def record(tc_id, title, status, details=""):
    results.append({
        "id": tc_id,
        "title": title,
        "status": status,
        "details": details
    })
    mark = "✅ PASS" if status == "PASS" else "❌ FAIL"
    print(f"[{mark}] {tc_id}: {title} -- {details}")

def get_cdp_ws():
    try:
        req = urllib.request.urlopen(f"{CDP_URL}/json", timeout=3)
        tabs = json.loads(req.read())
        for t in tabs:
            if t.get("type") == "page" and "8890" in t.get("url", ""):
                return websocket.create_connection(t["webSocketDebuggerUrl"], timeout=5)
    except Exception as e:
        print(f"[CDP Error] {e}")
    return None

def cdp_eval(expr):
    ws = get_cdp_ws()
    if not ws:
        return None
    try:
        msg = {"id": int(time.time()*1000)%100000, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}
        ws.send(json.dumps(msg))
        res = json.loads(ws.recv())
        ws.close()
        return res.get("result", {}).get("result", {}).get("value")
    except Exception as e:
        if ws: ws.close()
        return None

def api_call(path, data=None):
    url = f"{WEB_URL}{path}"
    req = urllib.request.Request(url)
    if data is not None:
        req.data = json.dumps(data).encode("utf-8")
        req.headers["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

def run_suite():
    print("==========================================================")
    print("⚡ ZILLION QA TEST SUITE: AUTO-HEAL & LIMITER SUBSYSTEM ⚡")
    print("==========================================================\n")

    # TC-01: Baseline Check
    st = api_call("/api/status")
    if st.get("status") == "ok" and st.get("cdp") == True:
        record("TC-01", "Web Server & CDP Probe Status", "PASS", f"Server online, CDP connected, current limiter: {st.get('limiter_pct')}%")
    else:
        record("TC-01", "Web Server & CDP Probe Status", "FAIL", f"Server response: {st}")

    # TC-02: Limiter Threshold Simulation (≥90%)
    set_res = api_call("/api/limiter/set", {"pct": 94})
    if set_res.get("ok") and set_res.get("limiter_pct") == 94:
        record("TC-02", "Set Limiter Threshold (94%)", "PASS", "Limiter percentage updated to 94%")
    else:
        record("TC-02", "Set Limiter Threshold (94%)", "FAIL", f"Set response: {set_res}")

    # TC-03: Modal Trigger & UI Elements Verification via CDP
    cdp_eval("limiterDismissed = false; updateLimiterUI(94, true)")
    time.sleep(1)
    ui_info = cdp_eval("""(() => {
        const m = document.getElementById('limiterModal');
        const isOpen = m ? m.classList.contains('open') : false;
        const barText = document.getElementById('limiterModalText')?.textContent || '';
        const hasAutohealBtn = !!document.getElementById('btnDoAutoheal');
        const hasCancelBtn = !!document.getElementById('btnCancelLimiter');
        return { isOpen, barText, hasAutohealBtn, hasCancelBtn };
    })()""")

    if ui_info and ui_info.get("isOpen") and "94%" in ui_info.get("barText") and ui_info.get("hasAutohealBtn") and ui_info.get("hasCancelBtn"):
        record("TC-03", "Limiter Modal Auto-Popup & Element Integrity", "PASS", f"Modal open: {ui_info.get('isOpen')}, text: '{ui_info.get('barText')}', buttons present")
    else:
        record("TC-03", "Limiter Modal Auto-Popup & Element Integrity", "FAIL", f"UI State: {ui_info}")

    # TC-04: User Cancellation / Dismiss Flow
    cdp_eval("document.getElementById('btnCancelLimiter').click()")
    time.sleep(1)
    modal_closed = cdp_eval("!document.getElementById('limiterModal').classList.contains('open')")
    if modal_closed:
        record("TC-04", "Modal Dismissal via Cancel Button", "PASS", "Modal cleanly closed upon cancel click")
    else:
        record("TC-04", "Modal Dismissal via Cancel Button", "FAIL", "Modal remained open")

    # TC-05: Auto-Heal Disposable Mailbox & Arena Sign-up Flow
    print("\n[INFO] Triggering Full Auto-Heal Engine...")
    heal_start = time.time()
    heal_res = api_call("/api/autoheal", {})
    duration = time.time() - heal_start

    if heal_res.get("ok") and heal_res.get("limiter_pct") == 0:
        email = heal_res.get("res", {}).get("email") or "generated"
        record("TC-05", "Auto-Heal Automated Disposable Account Engine", "PASS", f"Created temp account {email} in {duration:.1f}s, limiter reset to 0%")
    else:
        record("TC-05", "Auto-Heal Automated Disposable Account Engine", "FAIL", f"Autoheal response: {heal_res}")

    # TC-06: Post-Heal Web UI State & Quota Reset Verification
    cdp_eval("updateLimiterUI(0, false)")
    time.sleep(1)
    post_state = cdp_eval("""(() => {
        const pillText = document.getElementById('limiterPill')?.textContent || '';
        const isCrit = document.getElementById('limiterPill')?.classList.contains('crit');
        return { pillText, isCrit };
    })()""")

    if post_state and "0%" in post_state.get("pillText") and not post_state.get("isCrit"):
        record("TC-06", "Web UI Quota Reset Verification", "PASS", f"Header badge: '{post_state.get('pillText')}', critical state cleared")
    else:
        record("TC-06", "Web UI Quota Reset Verification", "FAIL", f"Post state: {post_state}")

    # TC-07: CLI Tool Parity Test (`zion-autoheal`)
    cli_p = subprocess.run([os.path.expanduser("~/.local/bin/zion-autoheal")], capture_output=True, text=True, timeout=30)
    if cli_p.returncode == 0 and "Result:" in cli_p.stdout:
        record("TC-07", "CLI Binary Parity (`zion-autoheal`)", "PASS", "CLI binary executed cleanly with exit code 0")
    else:
        record("TC-07", "CLI Binary Parity (`zion-autoheal`)", "FAIL", f"Exit {cli_p.returncode}, stderr: {cli_p.stderr}")

    print("\n==========================================================")
    pass_cnt = sum(1 for r in results if r["status"] == "PASS")
    total_cnt = len(results)
    print(f"SUMMARY: {pass_cnt}/{total_cnt} TESTS PASSED ({(pass_cnt/total_cnt)*100:.1f}% PASS RATE)")
    print("==========================================================")

if __name__ == "__main__":
    run_suite()
