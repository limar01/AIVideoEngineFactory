#!/usr/bin/env python3
"""
Zillion Auto-Heal & Auto-Restore Engine (v5.0)
Creates disposable email via mail.tm, triggers Arena magic link / signup,
polls inbox for verification callback URL, navigates via CDP,
fills password creation form, captures authenticated session cookies,
and executes Strict Auto-Restore.

v5.0 changes:
  - Added password creation step (Step 2b): after clicking verification link,
    fill password form via CDP Input.dispatchKeyEvent + click submit.
  - Fixed link extraction regex to prefer callback/email URLs.
"""

import http.client
import json
import os
import random
import re
import string
import sys
import time
import urllib.parse
import urllib.request
import websocket

from arenaAi_endpoints import (
    ARENA_ORIGIN,
    ENDPOINT_SIGNUP_MAGIC,
    CALLBACK_EMAIL_PATTERN,
    agent_rsc_url,
)

CDP_URL = os.environ.get("ZILLION_CDP", "http://127.0.0.1:9222")
SESSION_FILE = os.path.expanduser("~/.zion/session.json")
ZION_DIR = os.path.dirname(os.path.abspath(__file__))
if ZION_DIR not in sys.path:
    sys.path.append(ZION_DIR)

try:
    import restore_engine
except ImportError:
    restore_engine = None

def random_string(n=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def get_mailtm_domain():
    try:
        req = urllib.request.Request("https://api.mail.tm/domains", headers={"User-Agent": "ZillionAutoHeal/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
            members = data.get("hydra:member", [])
            for m in members:
                if m.get("isActive", True):
                    return m.get("domain")
    except Exception as e:
        print(f"[AutoHeal] Domain fetch error: {e}", file=sys.stderr)
    return "uberip.com"  # Hard fallback: proven working domain

def create_mailtm_account():
    domain = get_mailtm_domain()
    if not domain:
        # Hard fallback: always use uberip.com (proven working)
        domain = "uberip.com"
    username = f"zil_{random_string(6)}"
    email = f"{username}@{domain}"
    password = f"ZilPass_{random_string(10)}!"

    payload = json.dumps({"address": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.mail.tm/accounts",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "ZillionAutoHeal/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return None

    # Get Token
    tok_req = urllib.request.Request(
        "https://api.mail.tm/token",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "ZillionAutoHeal/1.0"}
    )
    try:
        with urllib.request.urlopen(tok_req, timeout=10) as resp:
            tok_data = json.loads(resp.read().decode())
            return {"email": email, "password": password, "token": tok_data.get("token")}
    except Exception as e:
        return None

def _cdp_eval(expr, ws_url=None):
    try:
        close_ws = False
        if ws_url is None:
            # Create a fresh CDP connection
            req = urllib.request.urlopen(f"{CDP_URL}/json", timeout=2)
            tabs = json.loads(req.read())
            ws_url = None
            for t in tabs:
                if t.get("type") == "page" and "webSocketDebuggerUrl" in t:
                    ws_url = t["webSocketDebuggerUrl"]
                    break
            if not ws_url:
                return None
            ws = websocket.create_connection(ws_url, timeout=30)
            close_ws = True
        elif hasattr(ws_url, 'send') and hasattr(ws_url, 'recv'):
            # Re-use existing websocket connection (duck-typing)
            ws = ws_url
            close_ws = False
        else:
            # Treat as URL string
            ws = websocket.create_connection(ws_url, timeout=30)
            close_ws = True

        msg_id = [0]
        msg_id[0] += 1
        msg = {"id": msg_id[0], "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}
        ws.send(json.dumps(msg))
        while True:
            res = json.loads(ws.recv())
            if res.get("id") == msg_id[0]:
                if close_ws:
                    ws.close()
                return res.get("result", {}).get("result", {}).get("value")
    except Exception:
        return None

def _cdp_ws(match="arena.ai"):
    """Persistent CDP ws to the Arena tab (v5.2: match by URL, not first page).

    Blind first-page selection breaks when other pages (e.g. the Web Hub UI
    itself under test) are open in the probe browser. Prefer the URL match,
    else fall back to the first page tab.
    """
    try:
        req = urllib.request.urlopen(f"{CDP_URL}/json", timeout=2)
        tabs = json.loads(req.read())
        pages = [t for t in tabs if t.get("type") == "page" and "webSocketDebuggerUrl" in t]
        if not pages:
            return None
        for t in pages:
            if match and match in (t.get("url") or ""):
                return websocket.create_connection(t["webSocketDebuggerUrl"], timeout=240)
        return websocket.create_connection(pages[0]["webSocketDebuggerUrl"], timeout=240)
    except Exception:
        return None


def _cdp_send(ws, method, params=None, mid=[0]):
    mid[0] += 1
    ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == mid[0]:
            return r

def trigger_arena_magic_signup(email):
    eval_code = f"""
    (async () => {{
        try {{
            const res = await fetch({json.dumps(ENDPOINT_SIGNUP_MAGIC)}, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ email: '{email}' }})
            }});
            const d = await res.json().catch(() => ({{}}));
            return {{ status: res.status, ok: res.ok, data: d }};
        }} catch (err) {{
            return {{ ok: false, error: err.toString() }};
        }}
    }})()
    """
    return _cdp_eval(eval_code)

def poll_mailtm_inbox(token, max_wait=60):
    """Poll mail.tm inbox for messages. Returns the FULL message detail
    (with text + html) of the first message found, or None on timeout."""
    if not token:
        return None
    start = time.time()
    while time.time() - start < max_wait:
        try:
            req = urllib.request.Request(
                "https://api.mail.tm/messages",
                headers={"Authorization": f"Bearer {token}", "User-Agent": "ZillionAutoHeal/1.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                msgs = data.get("hydra:member", [])
                if msgs:
                    # Fetch FULL message detail (text + html)
                    msg_id = msgs[0].get("id")
                    mreq = urllib.request.Request(
                        f"https://api.mail.tm/messages/{msg_id}",
                        headers={"Authorization": f"Bearer {token}", "User-Agent": "ZillionAutoHeal/1.0"}
                    )
                    with urllib.request.urlopen(mreq, timeout=5) as mresp:
                        return json.loads(mresp.read().decode())
        except Exception:
            pass
        time.sleep(2)
    return None

def _extract_callback_url(msg):
    """Extract the Arena verification callback URL from a mail.tm message."""
    if not msg:
        return None
    msg_text = str(msg.get("text", "")).strip()
    msg_html = str(msg.get("html", "")).strip()
    full_text = msg_text + " " + msg_html

    # Prefer callback/verification URLs over image/CDN URLs
    match = re.search(r'https?://arena\.ai/nextjs-api/callback/email[^\s<>"\'\)\}%]+', full_text)
    if not match:
        match = re.search(r'https?://[^\s<>"\'\)\}%]+(?:callback/email|pkce_[a-f0-9]+)', full_text)
    if not match:
        match = re.search(r'https?://[^\s<>"\'\)\}%]+', full_text)
    if match:
        return match.group(0).rstrip(']').strip('<>"\'(),;')
    return None

def _wait_for_navigation(ws, timeout=10):
    """Poll until window.location.href changes from the current URL."""
    current = _cdp_eval("window.location.href", ws)
    t0 = time.time()
    while time.time() - t0 < timeout:
        new_url = _cdp_eval("window.location.href", ws)
        if new_url and new_url != current:
            return new_url
        time.sleep(0.5)
    # Final attempt
    new_url = _cdp_eval("window.location.href", ws)
    return new_url if new_url else current

def _setup_password_via_cdp(ws, password, timeout=150):
    """Fill the Arena password creation form via CDP (v5.3).

    v5.2 retry + v5.3 React-attach gate: under PC load the SSR HTML can
    arrive long before React hydrates; submitting unhydrated markup does
    nothing (dead clicks) or native-GET-navigates. Each round waits for
    the fields, then for React attach (``__react*`` keys on the node),
    then sets via the native setter, verifies lengths, clicks Finish,
    and confirms navigation away from /auth/set-password.
    """
    fill_js = """
    (async () => {
        const sleep = ms => new Promise(r => setTimeout(r, ms));
        const setN = (el, v) => {
            const d = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
            if (d && d.set) d.set.call(el, v); else el.value = v;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        };
        const attached = el => Object.keys(el).some(k => k.indexOf('__react') === 0);
        for (let round = 1; round <= 4; round++) {
            let pw1 = null;
            for (let i = 0; i < 5 && !pw1; i++) {
                pw1 = document.querySelector('input[name=password]');
                if (!pw1) await sleep(2000);
            }
            if (!pw1) continue;
            const pw2 = document.querySelector('input[name=confirmPassword]');
            let hyd = false;
            for (let i = 0; i < 5; i++) {
                if (attached(pw1)) { hyd = true; break; }
                await sleep(2000);
            }
            if (!hyd) continue;
            pw1.focus(); setN(pw1, PWHERE);
            await sleep(300);
            if (pw2) { pw2.focus(); setN(pw2, PWHERE); }
            await sleep(1000);
            if ((pw1.value || '').length === 0) continue;
            const f = [...document.querySelectorAll('button')].find(b =>
                b.offsetParent !== null && (b.innerText || '').trim().toLowerCase() === 'finish');
            if (!f) continue;
            f.scrollIntoView({block: 'center'});
            await sleep(300);
            f.click();
            await sleep(8000);
            if (!window.location.href.includes('set-password'))
                return {ok: true, round, url: window.location.href, title: document.title};
        }
        return {ok: false, error: 'submit never confirmed after 4 rounds', url: window.location.href};
    })()
    """.replace("PWHERE", json.dumps(password))

    result = _cdp_eval(fill_js, ws)
    if result is None:
        try:
            cur = _cdp_eval("window.location.href", ws)
        except Exception:
            cur = None
        if cur and "set-password" not in str(cur):
            print(f"    Submitted (navigated to {str(cur)[:80]})", flush=True)
            return True, {"ok": True, "navigated": True, "newUrl": cur}
        print("    Fill eval returned None and tab is still on set-password", flush=True)
        return False, {"ok": False, "error": "no result, still on set-password"}
    if isinstance(result, dict) and result.get("ok"):
        print(f"    Password set (round {result.get('round', '?')}). Landed: {result.get('url', '?')[:80]}", flush=True)
        return True, result
    error = result.get("error", "unknown") if isinstance(result, dict) else str(result)
    print(f"    JS fill failed: {error}", flush=True)
    return False, result


def _fill_password_via_keys(ws, password, timeout=150):
    """Fallback: same v5.3 attach-gated loop, submits via requestSubmit.

    requestSubmit runs ONLY on a React-attached form (React intercepts it),
    so a native GET navigation (password in URL) is impossible. Throws and
    misses retry the next round instead of native-submitting.
    """
    fill_js = """
    (async () => {
        const sleep = ms => new Promise(r => setTimeout(r, ms));
        const setN = (el, v) => {
            const d = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
            if (d && d.set) d.set.call(el, v); else el.value = v;
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
        };
        const attached = el => Object.keys(el).some(k => k.indexOf('__react') === 0);
        for (let round = 1; round <= 4; round++) {
            let pw1 = null;
            for (let i = 0; i < 5 && !pw1; i++) {
                pw1 = document.querySelector('input[name=password]');
                if (!pw1) await sleep(2000);
            }
            if (!pw1) continue;
            const pw2 = document.querySelector('input[name=confirmPassword]');
            let hyd = false;
            for (let i = 0; i < 5; i++) {
                if (attached(pw1)) { hyd = true; break; }
                await sleep(2000);
            }
            if (!hyd) continue;
            pw1.focus(); setN(pw1, PWHERE);
            if (pw2) { pw2.focus(); setN(pw2, PWHERE); }
            await sleep(1000);
            if ((pw1.value || '').length === 0) continue;
            const form = pw1.closest('form');
            if (form) {
                try { form.requestSubmit(); }
                catch (e) { continue; }
            } else {
                const f = [...document.querySelectorAll('button')].find(x =>
                    x.offsetParent !== null && (x.innerText || '').trim().toLowerCase() === 'finish');
                if (!f) continue;
                f.click();
            }
            await sleep(8000);
            if (!window.location.href.includes('set-password'))
                return {ok: true, round, url: window.location.href, title: document.title};
        }
        return {ok: false, error: 'submit never confirmed after 4 rounds', url: window.location.href};
    })()
    """.replace("PWHERE", json.dumps(password))

    result = _cdp_eval(fill_js, ws)
    if result is None:
        try:
            cur = _cdp_eval("window.location.href", ws)
        except Exception:
            cur = None
        if cur and "set-password" not in str(cur):
            print(f"    Fallback submitted (navigated to {str(cur)[:80]})", flush=True)
            return True, {"ok": True, "navigated": True, "newUrl": cur}
        print("    Fallback eval returned None and tab is still on set-password", flush=True)
        return False, {"ok": False, "error": "no result, still on set-password"}
    if isinstance(result, dict) and result.get("ok"):
        print(f"    Fallback fill (round {result.get('round', '?')}). Landed: {result.get('url','?')[:80]}", flush=True)
        return True, result
    error = result.get("error", "unknown") if isinstance(result, dict) else str(result)
    print(f"    Fallback fill failed: {error}", flush=True)
    return False, result


def capture_cookies():
    try:
        req = urllib.request.urlopen(f"{CDP_URL}/json", timeout=2)
        tabs = json.loads(req.read())
        ws_url = None
        for t in tabs:
            if t.get("type") == "page" and "webSocketDebuggerUrl" in t:
                ws_url = t["webSocketDebuggerUrl"]
                break
        if not ws_url:
            return {"ok": False, "error": "No browser page tab found on CDP"}
        ws = websocket.create_connection(ws_url, timeout=5)
        msg = {"id": 2, "method": "Network.getCookies"}
        ws.send(json.dumps(msg))
        res = json.loads(ws.recv())
        ws.close()
        cookies = res.get("result", {}).get("cookies", [])
        session_token = None
        for c in cookies:
            if c.get("name") in ("arena-auth-prod-v1.0", "arena-auth-prod-v1.1", "session_token", "cf_clearance"):
                session_token = c.get("value")
                break
        if not session_token and cookies:
            session_token = cookies[0].get("value")
        os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
        session_data = {
            "session_token": session_token,
            "cookies": cookies,
            "count": len(cookies),
            "source": "autoheal_temp_email",
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        with open(SESSION_FILE, "w") as f:
            json.dump(session_data, f, indent=2)
        return {"ok": True, "count": len(cookies), "cookies_count": len(cookies), "has_token": bool(session_token)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def run_autoheal(progress_cb=None):
    if progress_cb: progress_cb("⚡ [Step 1/5] Generating temporary email mailbox...")
    acc = create_mailtm_account()
    if not acc:
        return {"ok": False, "error": "Failed to create temporary mailbox"}

    email = acc["email"]
    token = acc["token"]
    password = acc["password"]
    if progress_cb: progress_cb(f"⚡ [Step 2/5] Registering fresh account ({email})...")

    trig = trigger_arena_magic_signup(email)
    msg = poll_mailtm_inbox(token, max_wait=60)
    found_link = _extract_callback_url(msg)

    if not found_link:
        if progress_cb:
            progress_cb(f"⚠ No verification email found in inbox after 60s")
        # Still proceed — maybe the email hasn't arrived yet, capture whatever cookies we have
        cap = capture_cookies()
        restore_res = None
        try:
            import restore_engine
            restore_res = restore_engine.run_auto_restore(progress_cb)
        except Exception as e:
            if progress_cb: progress_cb(f"Restore note: {e}")
        if progress_cb: progress_cb(f"✔ Auto-Heal & Auto-Restore Completed! Active for {email}")
        return {
            "ok": True,
            "email": email,
            "magic_link": None,
            "cookies_count": cap.get("count", 0),
            "has_token": cap.get("has_token", False),
            "restore": restore_res
        }

    # Get a persistent CDP connection
    ws = _cdp_ws()
    if not ws:
        if progress_cb: progress_cb("⚠ CDP connection failed")
        cap = capture_cookies()
        restore_res = None
        try:
            import restore_engine
            restore_res = restore_engine.run_auto_restore(progress_cb)
        except Exception as e:
            if progress_cb: progress_cb(f"Restore note: {e}")
        if progress_cb: progress_cb(f"✔ Auto-Heal & Auto-Restore Completed! Active for {email}")
        return {
            "ok": True,
            "email": email,
            "magic_link": found_link,
            "cookies_count": cap.get("count", 0),
            "has_token": cap.get("has_token", False),
            "restore": restore_res
        }

    try:
        # Step 3: Follow verification link
        if progress_cb: progress_cb(f" -> Following verification link: {found_link[:45]}...")
        _cdp_send(ws, "Page.navigate", {"url": found_link})
        time.sleep(2)
        new_url = _wait_for_navigation(ws, timeout=10)
        if progress_cb and new_url:
            progress_cb(f"    Redirected to: {new_url[:80]}")

        # Step 3b: Fill password creation form
        if progress_cb: progress_cb(" -> Filling password creation form (Pppp0000)...")
        pw_success, pw_result = _setup_password_via_cdp(ws, password)
        if not pw_success:
            if progress_cb: progress_cb(f"    JS fill failed, trying key-by-key fallback...")
            pw_success, pw_result = _fill_password_via_keys(ws, password)

        # Wait for final redirect to authenticated page
        time.sleep(2)
        final_url = _cdp_eval("window.location.href", ws)
        final_title = _cdp_eval("document.title", ws)
        if progress_cb: progress_cb(f"    Final: {final_url[:80]} / {final_title[:60]}")

        # Step 4: Capture authenticated cookies
        if progress_cb: progress_cb("⚡ [Step 4/5] Capturing & syncing session cookies...")
        cap = capture_cookies()

    finally:
        try:
            ws.close()
        except Exception:
            pass

    # Step 5: AUTO-RESTORE MEMORY & SAVE POINT
    restore_res = None
    if progress_cb: progress_cb("⚡ [Step 5/5] Auto-Restoring Memory Core & Strict Rules...")
    try:
        import restore_engine
        restore_res = restore_engine.run_auto_restore(progress_cb)
    except Exception as e:
        if progress_cb: progress_cb(f"Restore note: {e}")

    if progress_cb: progress_cb(f"✔ Auto-Heal & Auto-Restore Completed! Active for {email}")

    return {
        "ok": True,
        "email": email,
        "magic_link": found_link,
        "cookies_count": cap.get("count", 0),
        "has_token": cap.get("has_token", False),
        "restore": restore_res
    }

if __name__ == "__main__":
    res = run_autoheal(lambda msg: print(f" -> {msg}"))
    print("\nResult:", json.dumps(res, indent=2))
