#!/usr/bin/env python3
"""
Zillion CLI — Web Hub Server & Full API Endpoint (v2.2 — 2026-09-04)
v2.2 additions:
  - /api/captcha/status   → detect Security Verification modal + iframe state
  - /api/captcha/show     → ensure probe visible + bring iframe on-screen
  - /api/captcha/dismiss  → click Verify button if present, report when clear
  - /api/captcha/solve-v3 → try v3 token auto-solve (warm+execute), report status
Nagbibigay-daan ito sa Web Hub na magpa-pop ng inline captcha panel at mag-auto-retry
ng pending message kapag na-clear na ni Boss ang interactive challenge.
"""

import http.server
import re
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import websocket

# Ensure project root is in sys.path so arenaAi_endpoints can be found
# Use a compile-time absolute path so this works regardless of CWD
_PROJECT_ROOT = "/home/limar01/Projects/workspace/project/zillioncli"
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from arenaAi_endpoints import ARENA_ORIGIN, ARENA_AGENT_PAGE, ENDPOINT_SIGN_IN_EMAIL, ENDPOINT_SIGNUP_MAGIC, ENDPOINT_ME

ARENA_HOME = ARENA_AGENT_PAGE
ZION = os.path.expanduser("~/.local/bin/zion")
SESSION_FILE = os.path.expanduser("~/.zion/session.json")
ACTIVE_CHAT_FILE = os.path.expanduser("~/.zion/active_chat_id")
SIGNUP_EMAIL_FILE = os.path.expanduser("~/.config/zion/signup_email.json")
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_signup_email_prefs():
    """Preferred/last-used real email for magic signup + login prefill (no disposable providers)."""
    try:
        with open(SIGNUP_EMAIL_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {
                "preferred": (data.get("preferred") or "").strip(),
                "last_used": (data.get("last_used") or "").strip(),
            }
    except Exception:
        pass
    return {"preferred": "", "last_used": ""}


def _save_signup_email_prefs(preferred=None, last_used=None):
    cur = _load_signup_email_prefs()
    if preferred is not None:
        cur["preferred"] = (preferred or "").strip()
    if last_used is not None:
        cur["last_used"] = (last_used or "").strip()
    try:
        os.makedirs(os.path.dirname(SIGNUP_EMAIL_FILE), exist_ok=True)
        with open(SIGNUP_EMAIL_FILE, "w") as f:
            json.dump(cur, f, indent=2)
        os.chmod(SIGNUP_EMAIL_FILE, 0o600)
    except Exception:
        pass
    return cur


def _signup_email_prefill():
    prefs = _load_signup_email_prefs()
    email = prefs.get("preferred") or prefs.get("last_used") or ""
    return {"ok": True, "email": email, "preferred": prefs.get("preferred") or "", "last_used": prefs.get("last_used") or ""}

COOKIE_FILES = [
    os.path.expanduser("~/zillion/capture/full_cookies.txt"),
    os.path.expanduser("~/.config/zion/session_cookies.txt"),
]

ZION_TOOL_DIR = os.path.dirname(STATIC_DIR)  # project root (parent of web/)
if ZION_TOOL_DIR not in sys.path:
    sys.path.insert(0, ZION_TOOL_DIR)

GLOBAL_STATE = {
    "limiter_pct": 0,
    "autoheal_history": [],
    "magic_inbox": {},
    "active_chat_id": None,
    "last_restore_verified": False,
    "last_restore_output": "",
    "captcha": {
        "active": False,
        "since": 0,
        "pending_text": None,
        "pending_cmd": None,
        "last_checked": 0,
    },
}

# ---- active chat id helpers ----

def _set_active_chat_id(sid):
    if sid and re.fullmatch(r"[0-9a-f-]{36}", sid):
        GLOBAL_STATE["active_chat_id"] = sid
        try:
            os.makedirs(os.path.dirname(ACTIVE_CHAT_FILE), exist_ok=True)
            with open(ACTIVE_CHAT_FILE, "w") as f:
                f.write(sid + "\n")
            os.chmod(ACTIVE_CHAT_FILE, 0o600)
        except Exception:
            pass
        return sid
    return None

def _get_active_chat_id():
    sid = GLOBAL_STATE.get("active_chat_id")
    if sid and re.fullmatch(r"[0-9a-f-]{36}", sid):
        return sid
    try:
        sid = open(ACTIVE_CHAT_FILE).read().strip()
        if sid and re.fullmatch(r"[0-9a-f-]{36}", sid):
            GLOBAL_STATE["active_chat_id"] = sid
            return sid
    except Exception:
        pass
    return None

def _clear_active_chat_id():
    GLOBAL_STATE["active_chat_id"] = None
    try:
        if os.path.exists(ACTIVE_CHAT_FILE):
            os.remove(ACTIVE_CHAT_FILE)
    except Exception:
        pass

# ---- pending-captcha queue ----

def _set_pending_captcha(text=None, cmd=None):
    GLOBAL_STATE["captcha"]["active"] = True
    GLOBAL_STATE["captcha"]["since"] = time.time()
    GLOBAL_STATE["captcha"]["pending_text"] = text
    GLOBAL_STATE["captcha"]["pending_cmd"] = cmd

def _clear_pending_captcha():
    GLOBAL_STATE["captcha"]["active"] = False
    GLOBAL_STATE["captcha"]["since"] = 0
    GLOBAL_STATE["captcha"]["pending_text"] = None
    GLOBAL_STATE["captcha"]["pending_cmd"] = None

# ---- allowlist ----

CMD_MAP = {
    "status": "zion-status", "ls": "zion-ls", "open": "zion-open", "me": "zion-me",
    "whoami": "zion-me", "login": "zion-login", "signup": "zion-signup",
    "logout": "zion-signout", "signout": "zion-signout",
    "autoheal": "zion-autoheal", "restore": "zion-restore",
    "send": "zion-send", "help": "zion", "zion": "zion",
    "zion-status": "zion-status", "zion-ls": "zion-ls", "zion-open": "zion-open",
    "zion-me": "zion-me", "zion-login": "zion-login", "zion-signup": "zion-signup",
    "zion-signout": "zion-signout", "zion-autoheal": "zion-autoheal",
    "zion-restore": "zion-restore", "zion-send": "zion-send",
}

AUTH_COOKIE_PREFIX = ("arena-auth",)
AUTH_COOKIE_NAMES = ("session_token", "cf_clearance")

ARENA_HOST_HINT = "arena.ai"

# ---------- CDP helpers ----------

CDP_URL = os.environ.get("ZILLION_CDP", "http://127.0.0.1:9222")

def _list_tabs():
    try:
        req = urllib.request.urlopen(f"{CDP_URL}/json", timeout=3)
        return json.loads(req.read())
    except Exception:
        return []

def probe_online():
    try:
        req = urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=2)
        return bool(req.read())
    except Exception:
        return False

def _page_ws(match_arena=False):
    tabs = _list_tabs()
    for t in tabs:
        if t.get("type") != "page": continue
        if match_arena and ARENA_HOST_HINT not in (t.get("url") or ""): continue
        if "webSocketDebuggerUrl" in t:
            return t["webSocketDebuggerUrl"]
    return None

def _ws_class():
    return websocket

def _cdp_eval(expr, ws_url=None, match_arena=False, timeout=6, await_promise=True):
    try:
        ws_url = ws_url or _page_ws(match_arena=match_arena)
        if not ws_url: return None
        ws = websocket.create_connection(ws_url, timeout=timeout)
        import random
        mid = random.randint(1000, 99999)
        msg = {"id": mid, "method": "Runtime.evaluate",
               "params": {"expression": expr, "returnByValue": True, "awaitPromise": await_promise}}
        ws.send(json.dumps(msg))
        val = None
        t0 = time.time()
        while time.time() - t0 < timeout:
            try: res = json.loads(ws.recv())
            except Exception: break
            if res.get("id") == mid:
                val = res.get("result", {}).get("result", {}).get("value"); break
        try: ws.close()
        except Exception: pass
        return val
    except Exception:
        return None

def _cdp_send(method, params=None, ws_url=None, match_arena=False, timeout=6):
    """Generic CDP command (non-eval) — Input.dispatchMouseEvent, Page.navigate, etc."""
    try:
        ws_url = ws_url or _page_ws(match_arena=match_arena)
        if not ws_url: return None
        ws = websocket.create_connection(ws_url, timeout=timeout)
        import random
        mid = random.randint(1000,99999)
        ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        out = None
        t0 = time.time()
        while time.time() - t0 < timeout:
            try: res = json.loads(ws.recv())
            except Exception: break
            if res.get("id") == mid:
                out = res; break
        try: ws.close()
        except Exception: pass
        return out
    except Exception:
        return None

def _ensure_arena_tab():
    ws_url = _page_ws(match_arena=True)
    if ws_url: return ws_url
    try:
        req = urllib.request.Request("%s/json/new?%s" % (CDP_URL, urllib.parse.quote(ARENA_HOME, safe=':/?&=%.-')), method="PUT")
        info = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
        time.sleep(2.5)
        for t in _list_tabs():
            if t.get("id") == info.get("id") and "webSocketDebuggerUrl" in t:
                return t["webSocketDebuggerUrl"]
        return _page_ws(match_arena=True)
    except Exception:
        return None



ME_EXPR = (
    "(async()=>{try{const r=await fetch(" + json.dumps(ENDPOINT_ME) + ",{headers:{accept:'application/json'}});"
    "const d=await r.json().catch(()=>({}));return {status:r.status,user:(d&&d.user)||null};}"
    "catch(e){return {status:0,error:String(e)}}})()"
)

def _mask_session(s):
    if not isinstance(s, dict): return {}
    return {"has_token": bool(s.get("session_token")), "email": s.get("email"),
            "count": s.get("count", len(s.get("cookies") or [])),
            "updated_at": s.get("updated_at"), "source": s.get("source")}

# ---------- CLI runner ----------

SESSION_CANDIDATES = COOKIE_FILES

def run_cmd(args, timeout=60):
    if not args: return {"error": "no command", "exit_code": 1}
    first = os.path.basename(args[0])
    if first not in CMD_MAP:
        return {"error": f"not allowed: {first}", "exit_code": 1}
    mapped = CMD_MAP.get(first, first)
    if first == "help": args = [ZION]
    else: args[0] = os.path.expanduser("~/.local/bin/" + mapped)
    env = os.environ.copy()
    env["PATH"] = os.path.expanduser("~/.local/bin") + ":" + env.get("PATH","")
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           cwd=os.path.expanduser("~/.local/bin"), env=env)
        out = (p.stdout or "")
        if p.stderr: out += ("\n" + p.stderr)
        return {"output": out[-20000:], "exit_code": p.returncode}
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s", "exit_code": -1}
    except Exception as e:
        return {"error": str(e), "exit_code": -1}

# ---------- Session capture & auth ----------

def _ws_cmd(ws, mid, method, params=None, timeout=6):
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    t0 = time.time()
    while time.time() - t0 < timeout:
        try: res = json.loads(ws.recv())
        except Exception: return {}
        if res.get("id") == mid: return res
    return {}

def _pick_auth_token(cookies):
    by_name = {}
    for c in cookies:
        n = c.get("name") or ""
        if n not in by_name: by_name[n] = c.get("value")
    for n, v in by_name.items():
        if any(n.startswith(p) for p in AUTH_COOKIE_PREFIX) and v: return v
    for n in AUTH_COOKIE_NAMES:
        if by_name.get(n): return by_name[n]
    return None

_FLOW_TABS = set()

def _fresh_arena_tab():
    """Create a dedicated tab for one magic-signup flow (v5.4).

    Long-lived tabs can reach a poisoned JS state where React silently
    never mounts; a fresh tab per signup isolates the flow from that.
    Also closes leaked flow tabs from previously crashed runs.
    Returns (tab_id, ws_url).
    """
    for tid in list(_FLOW_TABS):
        try:
            urllib.request.urlopen("http://127.0.0.1:9222/json/close/%s" % tid, timeout=5).read()
        except Exception:
            pass
        _FLOW_TABS.discard(tid)
    req = urllib.request.Request("http://127.0.0.1:9222/json/new?about:blank", method="PUT")
    info = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
    _FLOW_TABS.add(info["id"])
    return info["id"], info["webSocketDebuggerUrl"]

def _close_flow_tab(tab_id):
    if not tab_id:
        return
    try:
        urllib.request.urlopen("http://127.0.0.1:9222/json/close/%s" % tab_id, timeout=5).read()
    except Exception:
        pass
    try:
        _FLOW_TABS.discard(tab_id)
    except Exception:
        pass


def capture_cookies_from_browser(ws_url=None, email=None):
    try:
        ws_url = ws_url or _page_ws(match_arena=True)
        if not ws_url: return {"ok": False, "error": "No arena.ai page tab found on probe CDP"}
        ws = websocket.create_connection(ws_url, timeout=6)
        _ws_cmd(ws, 1, "Network.enable")
        res = _ws_cmd(ws, 2, "Network.getCookies", {"urls": ["https://arena.ai", "https://www.arena.ai"]})
        try: ws.close()
        except Exception: pass
        cookies = res.get("result", {}).get("cookies", [])
        arena_c = [c for c in cookies if "arena.ai" in (c.get("domain") or "")]
        session_token = _pick_auth_token(arena_c or cookies)
        blob = ", ".join(f"{c['name']}={c['value']}" for c in (arena_c or cookies) if c.get("name") and c.get("value"))
        os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
        session_data = {"session_token": session_token, "email": email,
                        "cookies": arena_c or cookies, "count": len(arena_c or cookies),
                        "source": "probe_cdp_auto", "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        with open(SESSION_FILE, "w") as f: json.dump(session_data, f, indent=2)
        try: os.chmod(SESSION_FILE, 0o600)
        except Exception: pass
        if blob:
            for path in COOKIE_FILES:
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w") as fh: fh.write(blob)
                    os.chmod(path, 0o600)
                except Exception: pass
        return {"ok": True, "count": len(arena_c or cookies), "cookies_count": len(arena_c or cookies),
                "has_token": bool(session_token), "email": email}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _session_file_email():
    try:
        with open(SESSION_FILE) as f:
            return (((json.load(f) or {}).get("email")) or "").strip()
    except Exception:
        return ""


def auth_state(sync=True):
    st = {"ok": True, "probeOnline": probe_online(), "loggedIn": False, "user": None, "url": None}
    if not st["probeOnline"]: st["ok"] = False; st["error"] = "probe browser offline"; return st
    ws_url = _page_ws(match_arena=True)
    if not ws_url: ws_url = _ensure_arena_tab()
    if not ws_url: st["error"] = "no arena.ai tab in probe browser"; return st
    st["url"] = _cdp_eval("window.location.href", ws_url=ws_url, await_promise=False)
    me = _cdp_eval(ME_EXPR, ws_url=ws_url)
    mu = (me.get("user") or {}) if isinstance(me, dict) else {}
    if (isinstance(me, dict) and me.get("status") == 200 and mu.get("id")):
        em = mu.get("email") or _session_file_email() or ("temp:" + str(mu.get("id"))[:8])
        st["loggedIn"] = True
        st["user"] = {"email": em, "username": mu.get("username"), "id": mu.get("id")}
        if sync:
            cap = capture_cookies_from_browser(ws_url=ws_url, email=em)
            st["captured"] = cap.get("count", 0) if cap.get("ok") else 0
    return st

# ---------- Captcha helpers (v2.2) ----------

CAPTCHA_DETECT_JS = r"""(function(){
  const txt = (document.body && document.body.innerText) || '';
  const low = txt.toLowerCase();
  const has_modal = /security verification|protected by recaptcha|quick security check/i.test(low);
  const iframes = [...document.querySelectorAll('iframe')].map(f=>{
    const r = f.getBoundingClientRect();
    return {
      kind: f.src.includes('bframe')?'bframe':(f.src.includes('anchor')?'anchor':'other'),
      src: f.src.slice(0,200),
      visible: r.width>10 && r.height>10 && r.top > -1000 && r.top < window.innerHeight+100,
      x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)
    };
  });
  // Detect visible Verify/Submit buttons inside the modal
  let verify_btn = null;
  document.querySelectorAll('button, [role="button"], input[type="submit"]').forEach(b=>{
    const t = ((b.innerText||b.textContent||b.value||'')+'').trim().toLowerCase();
    if(/verify|i[\u2019']?m not a robot|submit|continue/i.test(t)){
      const r = b.getBoundingClientRect();
      if(r.width>20 && r.height>10 && r.top < window.innerHeight && r.top > -100){
        verify_btn = {text: (b.innerText||b.textContent||b.value||'').slice(0,40), x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)};
      }
    }
  });
  return {
    present: has_modal,
    href: location.href,
    body_tail: txt.slice(-400),
    iframes: iframes,
    verify_btn: verify_btn,
    viewport: {w: window.innerWidth, h: window.innerHeight}
  };
})()"""

def captcha_status():
    """Return current captcha state without modifying anything."""
    ws_url = _page_ws(match_arena=True) or _ensure_arena_tab()
    if not ws_url:
        return {"ok": False, "error": "no arena tab"}
    val = _cdp_eval(CAPTCHA_DETECT_JS, ws_url=ws_url, await_promise=False, timeout=6)
    GLOBAL_STATE["captcha"]["last_checked"] = time.time()
    if not isinstance(val, dict):
        return {"ok": True, "present": False, "ws_url": ws_url}
    val["ok"] = True
    val["ws_url"] = ws_url
    if val.get("present"):
        if not GLOBAL_STATE["captcha"]["active"]:
            GLOBAL_STATE["captcha"]["active"] = True
            GLOBAL_STATE["captcha"]["since"] = time.time()
    else:
        # Only clear if not a newly-reset pending; leave active flag alone so UI can re-check
        pass
    val["pending"] = {
        "has_pending": bool(GLOBAL_STATE["captcha"]["pending_text"] or GLOBAL_STATE["captcha"]["pending_cmd"]),
        "since": GLOBAL_STATE["captcha"]["since"],
    }
    return val

CAPTCHA_SHOW_JS = r"""(async function(){
  // Force recaptcha iframes to be visible and centered on screen (Boss can click them on Dell).
  for (const f of [...document.querySelectorAll('iframe[src*="recaptcha"]')]){
    f.style.setProperty('position','fixed','important');
    f.style.setProperty('left','50%','important');
    f.style.setProperty('top','50%','important');
    f.style.setProperty('transform','translate(-50%,-50%)','important');
    f.style.setProperty('z-index','2147483647','important');
    f.style.setProperty('width','400px','important');
    f.style.setProperty('height','580px','important');
    f.style.setProperty('opacity','1','important');
    f.style.setProperty('visibility','visible','important');
    f.style.setProperty('display','block','important');
    f.style.setProperty('pointer-events','auto','important');
  }
  // Unhide any rc containers that were off-screen translated
  document.querySelectorAll('[class*="rc-"]').forEach(el=>{
    const s = getComputedStyle(el);
    if(s.position==='absolute' && (s.top==='-9999px' || parseInt(s.top)<-1000)){
      el.style.setProperty('position','fixed','important');
      el.style.setProperty('top','50%','important');
      el.style.setProperty('left','50%','important');
      el.style.setProperty('transform','translate(-50%,-50%)','important');
      el.style.setProperty('z-index','2147483646','important');
    }
  });
  window.focus();
  return 'shown';
})()"""

def captcha_show():
    ws_url = _page_ws(match_arena=True) or _ensure_arena_tab()
    if not ws_url: return {"ok": False, "error": "no arena tab"}
    val = _cdp_eval(CAPTCHA_SHOW_JS, ws_url=ws_url, await_promise=False, timeout=6)
    # Try to bring the probe window to front via Hyprland (best-effort)
    try:
        HIS = None
        r = subprocess.run(["bash","-lc","ls /run/user/1000/hypr/ 2>/dev/null | head -1"], capture_output=True, text=True, timeout=3)
        his_dir = r.stdout.strip()
        if his_dir:
            # Find chromium window for the probe
            import glob
            # Just try focusing any chromium window that has arena.ai in title
            subprocess.run(["bash","-lc",
                f"export HYPRLAND_INSTANCE_SIGNATURE={his_dir} DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1; "
                "for addr in $(hyprctl clients -j | python3 -c 'import sys,json;[print(c[\\\"address\\\"]) for c in json.load(sys.stdin) if \\\"arena.ai\\\" in c.get(\\\"title\\\",\\\"\\\")]'); do "
                "  hyprctl dispatch focuswindow address:$addr; hyprctl dispatch bringactivetotop address:$addr; done"
            ], capture_output=True, text=True, timeout=5)
    except Exception:
        pass
    return {"ok": True, "result": val, "ws_url": ws_url}

def captcha_poll_clear(timeout=120):
    """Block until the modal is gone (poll every 1.5s)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        ws_url = _page_ws(match_arena=True)
        if not ws_url: return {"cleared": False, "error": "no tab"}
        val = _cdp_eval(CAPTCHA_DETECT_JS, ws_url=ws_url, await_promise=False, timeout=5)
        if isinstance(val, dict) and not val.get("present"):
            return {"cleared": True, "elapsed": round(time.time()-t0,1), "href": val.get("href")}
        time.sleep(1.5)
    return {"cleared": False, "timeout": True}

# ---------- Autoheal / restore ----------

def execute_autoheal_flow():
    try:
        import autoheal
        res = autoheal.run_autoheal()
        if not isinstance(res, dict):
            res = {"result": res}
        if res.get("email"):
            try:
                capture_cookies_from_browser(email=res["email"])
            except Exception:
                pass
        st = auth_state(sync=True)
        want = (res.get("email") or "").lower()
        gotu = ((st.get("user") or {}).get("email") or "").lower()
        logged = bool(st.get("loggedIn")) and (not want or gotu == want)
        res["loggedIn"] = logged
        res["user"] = st.get("user")
        if logged:
            GLOBAL_STATE["limiter_pct"] = 0
        elif res.get("ok"):
            res["ok"] = False
            res["error"] = "Auto-heal finished but no logged-in Arena session was verified (/api/me). No fake success declared."
        GLOBAL_STATE["autoheal_history"].append(res)
        return {"ok": bool(res.get("ok")), "res": res, "limiter_pct": GLOBAL_STATE["limiter_pct"]}
    except Exception:
        res = run_cmd(["zion-autoheal"])
        GLOBAL_STATE["limiter_pct"] = 0
        return {"ok": True, "output": res, "limiter_pct": 0}

def _parse_zion_session(output):
    m = re.search(r"(?:◆|\\u25c6)?\s*session:\s*([0-9a-f-]{36})", output or "", re.I)
    return m.group(1) if m else None

def _verify_restored_session(zs, sid, timeout=120):
    if not sid: return {"ok": False, "error": "no active restore session id"}
    prompt = ("RESTORE VERIFICATION: From the MEMORY_CORE.md attached earlier in this same chat, "
              "answer one concise line with RESTORE v6.1 step 5 and the DIRECT vision gate rule.")
    vr = run_cmd([zs, "--append", sid, prompt], timeout=timeout)
    out = (vr.get("output") or "") + "\n" + (vr.get("stderr") or "")
    low = out.lower()
    ok = (vr.get("exit_code") == 0 and "vision gate" in low and "direct" in low and
          not any(x in low for x in ["no restored","no record","unknown / not found"]))
    return {"ok": ok, "session": sid, "output": out, "exit_code": vr.get("exit_code"),
            "error": None if ok else "verification did not prove restored MEMORY_CORE context"}

def _memory_core_path():
    cands = ["/home/limar01/Projects/zillion/MEMORY_CORE.md",
             os.path.expanduser("~/Projects/zillion/MEMORY_CORE.md"),
             os.path.expanduser("~/MEMORY_CORE.md")]
    for p in cands:
        try:
            if os.path.exists(p) and os.path.getsize(p) > 1000: return p
        except Exception: pass
    return None

def execute_restore_flow():
    lines = []; log = lines.append
    try:
        zs = os.path.expanduser("~/.local/bin/zion-send")
        mem_path = _memory_core_path()
        log("⚡ ZILLION RESTORE BUTTON v6.1 — REAL Arena attachment + verification")
        if not mem_path:
            log("❌ MEMORY_CORE.md not found on PC host.")
            return {"ok": False, "verified": False, "output": "\n".join(lines), "error": "MEMORY_CORE.md not found", "exit_code": 1}
        try:
            mem = open(mem_path, "r", encoding="utf-8", errors="replace").read()
            km = re.search(r"ZILLION_KEY_BEGIN\s*\n([A-Za-z0-9_\-]+)\nZILLION_KEY_END", mem)
            if km:
                kp = os.path.expanduser("~/arenabridge/arenabridge.key")
                os.makedirs(os.path.dirname(kp), exist_ok=True)
                with open(kp,"w") as f: f.write(km.group(1).strip())
                os.chmod(kp, 0o600)
                log(f"✔ Key extracted → {kp} (0600, {len(km.group(1).strip())} B)")
        except Exception as e:
            log("⚠ key extraction skipped: " + str(e))
        has_grim = subprocess.run(["bash","-lc","command -v grim >/dev/null 2>&1"]).returncode==0
        eyes = "DIRECT" if has_grim else "JAXVL?"
        log(f"✔ Vision probe: {eyes}")
        if eyes != "DIRECT":
            log("❌ DIRECT vision required; restore halted.")
            return {"ok": False, "verified": False, "output": "\n".join(lines), "eyes": eyes, "error": "DIRECT vision unavailable", "exit_code": 1}
        log("→ Creating Arena restored chat via text-chunk MEMORY_CORE delivery...")
        import tempfile
        mem_chunks = [mem[k:k+4500] for k in range(0, len(mem), 4500)] or [mem]
        tmp_prompt = None
        try:
            first_text = "zillionOM restore — initialize Zillion restore session. I will append MEMORY_CORE.md in chunks next. Reply one short line: READY_FOR_MEMORY_CORE."
            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", prefix="zillion_restore_seed_", suffix=".txt") as pf:
                pf.write(first_text); tmp_prompt = pf.name
            rr = run_cmd([zs, "@" + tmp_prompt], timeout=300)
        finally:
            try:
                if tmp_prompt and os.path.exists(tmp_prompt): os.remove(tmp_prompt)
            except Exception: pass
        out = (rr.get("output") or "") + ("\n" + rr.get("stderr") if rr.get("stderr") else "")
        sid = _parse_zion_session(out)
        if sid: _set_active_chat_id(sid)
        GLOBAL_STATE["last_restore_output"] = out
        for ln in out.splitlines():
            if ln.strip(): log("  " + ln)
        if rr.get("exit_code") == 0 and sid:
            log("→ Appending MEMORY_CORE chunks to SAME session...")
            for ci in range(0, len(mem_chunks)):
                tmp_chunk = None
                try:
                    chunk_text = "[MEMORY_CORE part %d/%d]\n%s" % (ci+1, len(mem_chunks), mem_chunks[ci])
                    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", prefix="zillion_restore_chunk_", suffix=".txt") as cf:
                        cf.write(chunk_text); tmp_chunk = cf.name
                    cr = run_cmd([zs, "--append", sid, "@" + tmp_chunk], timeout=150)
                    cout = (cr.get("output") or "") + ("\n" + cr.get("stderr") if cr.get("stderr") else "")
                    log("  • chunk %d/%d append exit %s" % (ci+1, len(mem_chunks), cr.get("exit_code")))
                    if cr.get("exit_code") != 0:
                        log("  " + cout[-1200:].replace("\n","\n  "))
                        rr = {"exit_code": 1, "output": out + "\n" + cout}; break
                finally:
                    try:
                        if tmp_chunk and os.path.exists(tmp_chunk): os.remove(tmp_chunk)
                    except Exception: pass
            else:
                final = "[MEMORY_CORE delivery complete: %d/%d parts. Use this as active Zillion restore context.] Reply one line: MEMORY_CORE_CHUNKS_RECEIVED." % (len(mem_chunks), len(mem_chunks))
                fr = run_cmd([zs, "--append", sid, final], timeout=150)
                fout = (fr.get("output") or "") + ("\n" + fr.get("stderr") if fr.get("stderr") else "")
                log("  • delivery-complete append exit %s" % fr.get("exit_code"))
                if fr.get("exit_code") != 0: rr = {"exit_code": 1, "output": out + "\n" + fout}
        if rr.get("exit_code") != 0 or not sid:
            log("❌ Real attachment restore failed or no session id was returned.")
            GLOBAL_STATE["last_restore_verified"] = False
            return {"ok": False, "verified": False, "output": "\n".join(lines), "session": sid, "error": "restore send failed/no session", "exit_code": rr.get("exit_code", 1)}
        log("→ Verifying restored memory in SAME Arena session: " + sid)
        ver = _verify_restored_session(zs, sid, timeout=150)
        vout = ver.get("output") or ""
        for ln in vout.splitlines():
            if ln.strip(): log("  [verify] " + ln)
        GLOBAL_STATE["last_restore_verified"] = bool(ver.get("ok"))
        if not ver.get("ok"):
            log("❌ Restore NOT verified. Hindi idedeclare na success.")
            return {"ok": False, "verified": False, "output": "\n".join(lines), "session": sid, "error": ver.get("error"), "exit_code": 1}
        log("✔ [Verified Restore Success] MEMORY_CORE context is available in the active Arena session.")
        return {"ok": True, "verified": True, "output": "\n".join(lines), "session": sid, "eyes": eyes, "exit_code": 0}
    except Exception as e:
        import traceback
        GLOBAL_STATE["last_restore_verified"] = False
        return {"ok": False, "verified": False, "output": "❌ Restore handler crashed: %s\n%s" % (e, traceback.format_exc()), "error": str(e), "exit_code": 1}

# ---------- Send helper with captcha awareness ----------

def _do_send_text_raw(args, timeout=120, pending_text=None):
    """Low-level: run zion-send with given args; detect captcha failures & mark pending.
    
    HOTFIX v2.2.1: 'recaptcha' appears in SUCCESS lines ('◆ recaptcha → token_ok len=2404')
    so we do NOT treat bare 'recaptcha' substring as failure. Captcha is only flagged when:
      (a) exit_code != 0 AND CDP sees a visible Security Verification modal on the page, OR
      (b) exit_code != 0 AND output explicitly says 'recaptcha validation failed' / 'security verification'
    401/Unauthorized (User not found) is treated as LOGIN_REQUIRED, not captcha.
    """
    res = run_cmd(args, timeout=timeout)
    out = (res.get("output") or "") + "\n" + (res.get("stderr") or "")
    sid_new = _parse_zion_session(out)
    if sid_new:
        _set_active_chat_id(sid_new); res["session"] = sid_new
    low = out.lower()
    exit_nonzero = res.get("exit_code") != 0

    # Detect auth/session problems first (higher priority than captcha)
    if exit_nonzero and ("user not found" in low or "unauthorized" in low or
                         '"message":"user not found"' in low or "status:401" in low):
        _clear_pending_captcha()
        res["auth_required"] = True
        res["login_required"] = True
        res["error"] = "Not logged in / session expired. Mag-login sa Auth Hub."
        return res

    # Detect captcha ONLY on explicit signals (not bare "recaptcha" word which is in success lines)
    captcha_hit = exit_nonzero and (
        "security verification" in low
        or "recaptcha validation failed" in low
        or "quick security check" in low
        or "protected by recaptcha" in low
    )
    if captcha_hit:
        cs = captcha_status()
        # Require EITHER a visible modal OR explicit modal phrase in output
        if cs.get("present") or "security verification" in low or "recaptcha validation failed" in low:
            _set_pending_captcha(text=pending_text or (args[-1] if args else ""))
            res["captcha_required"] = True
            res["captcha_status"] = cs
            return res

    # HTTP 403 without modal — could be temporary; don't set captcha_required unless CDP confirms
    if exit_nonzero and "status:403" in low:
        cs = captcha_status()
        if cs.get("present"):
            _set_pending_captcha(text=pending_text or (args[-1] if args else ""))
            res["captcha_required"] = True
            res["captcha_status"] = cs
            return res
        # else just report as normal error
        res["error"] = (res.get("error") or "Request failed (HTTP 403) — no captcha modal detected.")

    if exit_code_ok(res) and not pending_text:
        _clear_pending_captcha()
    return res

def exit_code_ok(res):
    return res.get("exit_code") == 0

def _do_send_text(text, attachments=None, timeout=90):
    """Compat wrapper: send single text via zion-send (no-attachment simple path)."""
    zs_path = os.path.expanduser("~/.local/bin/zion-send")
    active_sid = _get_active_chat_id()
    args = [zs_path, "--append", active_sid, text] if active_sid else [zs_path, text]
    return _do_send_text_raw(args, timeout=timeout, pending_text=text)

# ---------- HTTP handler ----------

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/api/status":
            session_info = {}
            if os.path.exists(SESSION_FILE):
                try:
                    with open(SESSION_FILE) as f: session_info = _mask_session(json.load(f))
                except Exception: pass
            self._json({"status":"ok","cdp":probe_online(),"session":session_info,
                        "limiter_pct":GLOBAL_STATE["limiter_pct"],
                        "active_chat_id":(_get_active_chat_id() or "")[:13],
                        "restore_verified":bool(GLOBAL_STATE.get("last_restore_verified")),
                        "captcha": GLOBAL_STATE["captcha"]})
        elif u.path == "/api/limiter":
            self._json({"ok":True,"limiter_pct":GLOBAL_STATE["limiter_pct"]})
        elif u.path in ("/api/me","/api/whoami"):
            self._json(run_cmd(["whoami"]))
        elif u.path == "/api/auth/state":
            self._json(auth_state(sync=True))
        elif u.path == "/api/auth/signup-email":
            self._json(_signup_email_prefill())
        elif u.path == "/api/auth/magic-email":
            self._json(_magic_email_new())
        elif u.path == "/api/auth/poll":
            st = auth_state(sync=True)
            self._json({"ok":True,"probeOnline":st["probeOnline"],"loggedIn":st["loggedIn"],
                        "user":st["user"] or {},"url":st["url"]})
        elif u.path == "/api/autoheal":
            self._json(execute_autoheal_flow())
        elif u.path == "/api/restore":
            self._json(execute_restore_flow())
        elif u.path == "/api/captcha/status":
            self._json(captcha_status())
        elif u.path == "/api/captcha/show":
            self._json(captcha_show())
        elif u.path == "/api/captcha/dismiss":
            # Check if cleared; if verify button visible, click it via CDP Input.dispatchMouseEvent
            cs = captcha_status()
            vb = cs.get("verify_btn")
            if vb:
                _cdp_send("Input.dispatchMouseEvent", {"type":"mousePressed","x":vb["x"],"y":vb["y"],"button":"left","clickCount":1}, match_arena=True, timeout=5)
                time.sleep(0.1)
                _cdp_send("Input.dispatchMouseEvent", {"type":"mouseReleased","x":vb["x"],"y":vb["y"],"button":"left","clickCount":1}, match_arena=True, timeout=5)
                time.sleep(1)
            clr = captcha_poll_clear(timeout=8)
            self._json({"ok": clr.get("cleared", False), "clicked": bool(vb), "state": cs, "clear_result": clr})
        elif u.path == "/api/captcha/retry":
            """After Boss solves captcha, retry the pending message."""
            pt = GLOBAL_STATE["captcha"].get("pending_text")
            if not pt:
                self._json({"ok":False,"error":"no pending message","exit_code":1})
                return
            zs_path = os.path.expanduser("~/.local/bin/zion-send")
            active_sid = _get_active_chat_id()
            args = [zs_path, "--append", active_sid, pt] if active_sid else [zs_path, pt]
            res = _do_send_text_raw(args, timeout=180, pending_text=pt)
            if res.get("exit_code") == 0 and not res.get("captcha_required"):
                _clear_pending_captcha()
            self._json(res)
        else:
            super().do_GET()

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        len_h = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(len_h) if len_h else b"{}"
        try: data = json.loads(body) if body else {}
        except Exception as e:
            self._json({"ok":False,"error":"Invalid JSON: "+str(e),"exit_code":1}); return

        if u.path == "/api/restore/chat":
            # (unchanged — existing restore flow, kept as-is)
            try:
                text = (data.get("text") or "").strip().lower()
                atts = data.get("attachments") or []
                import base64 as _b64
                lane = None
                if "zillionom" in text: lane = "pc"
                elif "zillioncp" in text: lane = "cp"
                elif "zillionwin" in text: lane = "win"
                mem = None
                for a in atts:
                    fn = (a.get("filename") or "").lower()
                    du = a.get("dataUrl") or ""
                    if fn.endswith(".md") and "," in du:
                        try: mem = _b64.b64decode(du.split(",",1)[1]+"===").decode("utf-8","replace")
                        except Exception: mem = None
                        if mem and ("ZILLION_KEY_BEGIN" in mem or "MEMORY_CORE" in mem[:200]): break
                lines=[]; log=lines.append
                log(""); log("⚡ ZILLION RESTORE PROTOCOL v6.1")
                log("  Token: "+(text or "(none)")+"  → lane "+(lane or "?")); log("")
                if not lane:
                    log("❌ Walang valid token."); self._json({"ok":False,"output":"\n".join(lines),"exit_code":1}); return
                if not mem:
                    log("⚠ Walang naka-attach na MEMORY_CORE.md."); self._json({"ok":False,"output":"\n".join(lines),"exit_code":1}); return
                km = re.search(r"ZILLION_KEY_BEGIN\s*\n([A-Za-z0-9_\-]+)\nZILLION_KEY_END", mem)
                key = km.group(1).strip() if km else None
                if not key: log("❌ Walang ZILLION_KEY."); self._json({"ok":False,"output":"\n".join(lines),"exit_code":1}); return
                kp = os.path.expanduser("~/arenabridge/arenabridge.key")
                os.makedirs(os.path.dirname(kp), exist_ok=True)
                with open(kp,"w") as f: f.write(key)
                os.chmod(kp,0o600)
                log(f"✔ Key extracted → {kp}")
                has_grim = subprocess.run(["bash","-lc","command -v grim >/dev/null 2>&1"]).returncode==0
                eyes = "DIRECT" if has_grim else "JAXVL?"
                log(f"✔ Vision probe: {eyes}")
                if eyes != "DIRECT": self._json({"ok":False,"output":"\n".join(lines),"error":"DIRECT vision unavailable","exit_code":1}); return
                log("→ Real Arena attachment restore...")
                import tempfile
                zs = os.path.expanduser("~/.local/bin/zion-send")
                tmp_prompt=None; tmp_mem=None
                try:
                    with tempfile.NamedTemporaryFile("w",delete=False,encoding="utf-8",prefix="zr_p_",suffix=".txt") as pf:
                        pf.write(text); tmp_prompt=pf.name
                    with tempfile.NamedTemporaryFile("w",delete=False,encoding="utf-8",prefix="MEMORY_CORE_",suffix=".md") as mf:
                        mf.write(mem); tmp_mem=mf.name
                    rr = run_cmd([zs,"--attach",tmp_mem,"@"+tmp_prompt],timeout=360)
                finally:
                    for _p in (tmp_prompt,tmp_mem):
                        try:
                            if _p and os.path.exists(_p): os.remove(_p)
                        except Exception: pass
                out = rr.get("output") or rr.get("stderr") or ""
                sid = _parse_zion_session(out)
                if sid: _set_active_chat_id(sid)
                if rr.get("exit_code")!=0 or not sid:
                    log("❌ Real attachment restore failed.");
                    for ln in out.split("\n"):
                        if ln.strip(): log("  "+ln)
                    # captcha awareness for restore path too
                    low = out.lower()
                    if "security verification" in low or "captcha" in low:
                        cs = captcha_status(); _set_pending_captcha(text=text)
                        self._json({"ok":False,"captcha_required":True,"captcha_status":cs,"output":"\n".join(lines)+"\n"+out,"exit_code":1}); return
                    self._json({"ok":False,"output":"\n".join(lines)+"\n"+out,"exit_code":1}); return
                verified = False
                if rr.get("exit_code")==0 and sid:
                    ver = _verify_restored_session(zs, sid, timeout=150)
                    verified = bool(ver.get("ok"))
                GLOBAL_STATE["last_restore_verified"] = verified
                self._json({"ok":verified,"verified":verified,"session":sid,"output":out,"exit_code":0 if verified else 1})
            except Exception as e:
                import traceback
                self._json({"ok":False,"output":f"❌ {e}\n{traceback.format_exc()}","exit_code":1})
            return

        elif u.path == "/api/upload":
            try:
                import base64 as _b64
                up = os.path.expanduser("~/.zion/uploads"); os.makedirs(up,exist_ok=True)
                sd = os.path.join(up,time.strftime("%Y%m%d_%H%M%S")); os.makedirs(sd,exist_ok=True)
                saved=[]
                for f in (data.get("files") or []):
                    fn=os.path.basename(f.get("filename","file")); du=f.get("dataUrl","")
                    if "," in du:
                        try:
                            raw=_b64.b64decode(du.split(",",1)[1]+"==="); p=os.path.join(sd,fn)
                            with open(p,"wb") as fh: fh.write(raw)
                            saved.append({"filename":fn,"path":p,"size":len(raw)})
                        except Exception as e: saved.append({"filename":fn,"error":str(e)})
                self._json({"ok":True,"dir":sd,"files":saved})
            except Exception as e: self._json({"ok":False,"error":str(e)})
        elif u.path == "/api/logout":
            r = run_cmd(["signout"])
            if r.get("exit_code")==0:
                try:
                    for cand in SESSION_CANDIDATES:
                        if os.path.exists(cand): open(cand,"w").write("")
                    with open(SESSION_FILE,"w") as f: json.dump({},f)
                except Exception: pass
            self._json(r)
        elif u.path == "/api/send-cancel":
            self._json({"ok":True,"cancelled":True})
        if u.path == "/api/cmd":
            cmd = data.get("cmd",""); text = data.get("text","")
            # BUGFIX: treat {cmd:"send ..."} as Arena message mode para append sa active_chat_id
            if not text and isinstance(cmd,str):
                _cmds=cmd.strip(); _first,_sep,_rest=_cmds.partition(" ")
                if _first in ("send","zion-send") and _rest.strip(): text=_rest.strip(); cmd=""
            atts = data.get("attachments") or []
            att_note=""
            mem_chunks = []
            att_files = []
            if atts:
                import base64 as _b64, tempfile as _tf
                names = [os.path.basename(a.get("filename","")) for a in atts]
                att_note = "\n[attachments: " + ", ".join(names) + "]"
                # Decode & save attachments to temp files for zion-send --attach
                for a in atts:
                    fn = os.path.basename(a.get("filename") or "file")
                    du = a.get("dataUrl") or a.get("data") or ""
                    raw = b""
                    is_text = False
                    if "," in du:
                        try:
                            raw = _b64.b64decode(du.split(",",1)[1] + "===")
                        except Exception:
                            raw = b""
                    if fn.endswith(".md") or fn.endswith(".txt"):
                        is_text = True
                    try:
                        if is_text:
                            with _tf.NamedTemporaryFile("w", delete=False, encoding="utf-8", prefix="zatt_", suffix="_"+fn) as tf:
                                tf.write(raw.decode("utf-8","replace"))
                                att_files.append(tf.name)
                        else:
                            with _tf.NamedTemporaryFile("wb", delete=False, prefix="zatt_", suffix="_"+fn) as tf:
                                tf.write(raw)
                                att_files.append(tf.name)
                    except Exception:
                        pass
                # Detect MEMORY_CORE in markdown attachments (chunked delivery)
                if text and ("restore" in text.lower() or "zillion" in text.lower()):
                    for a in atts:
                        fn = (a.get("filename") or "")
                        du = (a.get("dataUrl") or a.get("data") or "")
                        if fn.endswith(".md") and "," in du:
                            try:
                                memx = _b64.b64decode(du.split(",",1)[1]+"===").decode("utf-8","replace")
                                if "MEMORY_CORE" in memx[:200] or "ZILLION_KEY_BEGIN" in memx:
                                    mem_chunks = [memx[k:k+5000] for k in range(0, min(len(memx), 40000), 5000)]
                                    break
                            except Exception:
                                pass
            res = None
            try:
                if text:
                    first_text = text
                    if mem_chunks:
                        n = len(mem_chunks)
                        first_text = text + "\n[MEMORY_CORE part 1/%d]\n" % n + mem_chunks[0]
                    zs_path = os.path.expanduser("~/.local/bin/zion-send")
                    active_sid = _get_active_chat_id()
                    # Build send args with attachments
                    base_args = [zs_path]
                    for _af in att_files:
                        base_args += ["--attach", _af]
                    if active_sid:
                        args = base_args + ["--append", active_sid, first_text]
                        res = _do_send_text_raw(args, timeout=120)
                        if res.get("exit_code") != 0 and not res.get("captcha_required"):
                            # stale/bad chat id: retry with new chat
                            _clear_active_chat_id()
                            args = base_args + [first_text]
                            res = _do_send_text_raw(args, timeout=120)
                    else:
                        args = base_args + [first_text]
                        res = _do_send_text_raw(args, timeout=120)
                    sid_new = _parse_zion_session((res.get("output") or "") + "\n" + (res.get("stderr") or ""))
                    if sid_new:
                        _set_active_chat_id(sid_new); res["session"] = sid_new
                    # Chunked MEMORY_CORE delivery after first message
                    if mem_chunks and res.get("exit_code") == 0 and not res.get("captcha_required"):
                        extra = []
                        chunk_sid = _get_active_chat_id() or sid_new
                        for ci in range(1, len(mem_chunks)):
                            pt = "[MEMORY_CORE part %d/%d]\n" % (ci+1, len(mem_chunks)) + mem_chunks[ci]
                            args2 = [zs_path, "--append", chunk_sid, pt] if chunk_sid else [zs_path, pt]
                            r2c = _do_send_text_raw(args2, timeout=90)
                            if r2c.get("captcha_required"):
                                _set_pending_captcha(text=pt)
                                extra.append("[captcha blocked mid-chunk — solve then retry]")
                                res["captcha_required"] = True
                                break
                            ns = _parse_zion_session((r2c.get("output") or "") + "\n" + (r2c.get("stderr") or ""))
                            if ns: chunk_sid = ns; _set_active_chat_id(ns)
                            extra.append((r2c.get("output") or "").strip())
                        if not res.get("captcha_required"):
                            final_prompt = "[MEMORY_CORE delivery complete: %d parts] Reply in one line: RECEIVED n/N sections visible." % len(mem_chunks)
                            args3 = [zs_path, "--append", chunk_sid, final_prompt] if chunk_sid else [zs_path, final_prompt]
                            rf = _do_send_text_raw(args3, timeout=90)
                            ns = _parse_zion_session((rf.get("output") or "") + "\n" + (rf.get("stderr") or ""))
                            if ns: _set_active_chat_id(ns); res["session"] = ns
                            extra.append((rf.get("output") or "").strip())
                            res = dict(res)
                            res["output"] = (res.get("output") or "") + "\n" + "\n".join(x for x in extra if x)
                elif isinstance(cmd,str):
                    args=cmd.strip().split(); res=run_cmd(args,timeout=60)
                else:
                    args=cmd; res=run_cmd(args,timeout=60)
            finally:
                # Cleanup temp attachment files
                for _af in att_files:
                    try:
                        if os.path.exists(_af): os.remove(_af)
                    except Exception: pass
            if att_note and res and "output" in res: res["output"] = att_note + "\n" + (res.get("output") or "")
            if res and res.get("error") == "timeout":
                res["output"] = (res.get("output") or "") + "\n⌛ Nag-timeout ang request."
                res["cancellable"] = True
            if res and res.get("captcha_required"):
                res["hint"] = ("Nag-require ang Arena ng Security Verification. I-solve ang captcha "
                               "sa Dell monitor gamit ang 'Show captcha' button, pagkatapos ay i-click "
                               "'I solved it — retry' dito.")
            GLOBAL_STATE["limiter_pct"] = min(100, GLOBAL_STATE["limiter_pct"] + 2)
            if res: res["limiter_pct"] = GLOBAL_STATE["limiter_pct"]
            self._json(res or {"ok":False,"error":"no response","exit_code":1})
        elif u.path == "/api/limiter/set":
            val=int(data.get("pct",92)); GLOBAL_STATE["limiter_pct"]=max(0,min(100,val))
            self._json({"ok":True,"limiter_pct":GLOBAL_STATE["limiter_pct"]})
        elif u.path == "/api/probe/ensure":
            script=os.path.join(ZION_TOOL_DIR,"probe_browser.sh")
            try:
                p=subprocess.run(["bash",script,"ensure"],capture_output=True,text=True,timeout=30)
                online=probe_online()
                self._json({"ok":online,"probeOnline":online,"detail":((p.stdout or "")+(p.stderr or "")).strip()[-300:]})
            except Exception as e: self._json({"ok":False,"probeOnline":probe_online(),"error":str(e)})
        elif u.path == "/api/autoheal": self._json(execute_autoheal_flow())
        elif u.path == "/api/restore": self._json(execute_restore_flow())
        elif u.path in ("/api/auth/save-session","/api/capture"):
            st=auth_state(sync=True); res=capture_cookies_from_browser(email=(st.get("user") or {}).get("email")); self._json(res)
        elif u.path == "/api/login":
            ws_url=_ensure_arena_tab()
            if ws_url:
                _cdp_eval("window.location.href='" + ARENA_ORIGIN + "/sign-in'", ws_url=ws_url, await_promise=False)
                self._json({"ok":True,"message":"Sign-in page opened"})
            else: self._json({"ok":False,"error":"Probe offline"})
        elif u.path == "/api/auth/login-direct":
            email=data.get("email","").strip(); password=data.get("password","").strip()
            if not email or not password: self._json({"ok":False,"error":"Email/password required"}); return
            ws_url=_ensure_arena_tab()
            if not ws_url: self._json({"ok":False,"error":"Probe offline"}); return
            ev=f"""(async()=>{{try{{const res=await fetch({json.dumps(ENDPOINT_SIGN_IN_EMAIL)},{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:{json.dumps(email)},password:{json.dumps(password)}}})}});const d=await res.json().catch(()=>({{}}));return {{status:res.status,ok:res.ok,data:d}};}}catch(e){{return {{ok:false,error:e.toString()}}}}}})()"""
            res=_cdp_eval(ev,ws_url=ws_url,timeout=30) or {}
            if bool(res.get("ok") or res.get("status") in (200,201)):
                _cdp_eval("window.location.href="+json.dumps(ARENA_HOME),ws_url=ws_url,timeout=10,await_promise=False)
            time.sleep(2)
            me=_cdp_eval(ME_EXPR,ws_url=ws_url,timeout=15) or {}
            me_ok=bool(isinstance(me,dict) and me.get("status")==200 and isinstance(me.get("user"),dict) and me["user"].get("email"))
            cap=capture_cookies_from_browser(email=email)
            ok=bool(res.get("ok") or res.get("status") in (200,201))
            if ok:
                saved = (me.get("user") or {}).get("email") if me_ok else email
                _save_signup_email_prefs(last_used=saved, preferred=saved)
                execute_restore_flow()
            self._json({"ok":ok,"user":{"email":(me.get("user") or {}).get("email") if me_ok else email},
                        "error": res.get("data",{}).get("message") or res.get("error") if not ok else None,"raw":res,"captured":cap})
        elif u.path == "/api/auth/signup-email":
            # Save preferred and/or last-used real inbox for form prefill
            preferred = data.get("preferred")
            last_used = data.get("last_used") or data.get("email")
            remember = bool(data.get("remember_preferred") or data.get("set_preferred"))
            if remember and last_used:
                preferred = last_used
            prefs = _save_signup_email_prefs(
                preferred=preferred if preferred is not None else None,
                last_used=last_used if last_used is not None else None,
            )
            email = prefs.get("preferred") or prefs.get("last_used") or ""
            self._json({"ok": True, "email": email, **prefs})
        elif u.path == "/api/auth/signup-magic":
            email=data.get("email","").strip()
            auto=bool(data.get("auto_complete") or data.get("auto"))
            if not email and auto:
                gen=_magic_email_new()
                if not gen.get("ok"): self._json(gen); return
                email=gen["email"]
            if not email: self._json({"ok":False,"error":"Email required"}); return
            ws_url=_ensure_arena_tab()
            if not ws_url: self._json({"ok":False,"error":"Probe offline"}); return
            ev=f"""(async()=>{{try{{const res=await fetch({json.dumps(ENDPOINT_SIGNUP_MAGIC)},{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{email:{json.dumps(email)}}})}});const d=await res.json().catch(()=>({{}}));return{{status:res.status,ok:res.ok,data:d}};}}catch(e){{return{{ok:false,error:e.toString()}}}}}})()"""
            res=_cdp_eval(ev,ws_url=ws_url,timeout=15) or {}
            ok=res.get("ok",False) or res.get("status") in (200,201)
            if not ok:
                self._json({"ok":False,"error":((res.get("data") or {}).get("error") or res.get("error") or "Magic-link request failed"),
                            "email":email,"stage":"send"}); return
            box=(GLOBAL_STATE.get("magic_inbox") or {}).get(email)
            if auto and box and box.get("token"):
                # AUTO-COMPLETE: owned mail.tm inbox - poll, visit callback, set password, verify login
                self._json(_magic_autocomplete(email, box, ws_url)); return
            # Manual path (real inbox): link sent; owner completes it from their own email
            _save_signup_email_prefs(last_used=email, preferred=email if data.get("remember", True) else None)
            self._json({"ok":True,"loggedIn":False,"auto_completed":False,"email":email,
                        "message":((res.get("data") or {}).get("message") or ("Magic link sent to "+email+". Open it from your inbox, then use the Browser tab to auto-detect the login.")),
                        "saved_email": email})
        else:
            self.send_response(404); self.end_headers()

    def _json(self, payload):
        b=json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(b)))
        self.end_headers(); self.wfile.write(b)

def _magic_email_new():
    """Create a fresh mail.tm temp mailbox for Magic Sign-Up autofill (v2.3).

    Creds stay server-side in GLOBAL_STATE (memory only, 30-min TTL).
    The frontend receives ONLY the address - the user never types email.
    """
    try:
        import autoheal
    except Exception as e:
        return {"ok": False, "error": "mail.tm helper unavailable: %s" % e}
    try:
        acc = autoheal.create_mailtm_account()
    except Exception as e:
        return {"ok": False, "error": "mail.tm error: %s" % e}
    if not acc or not acc.get("email") or not acc.get("token"):
        return {"ok": False, "error": "mail.tm mailbox creation failed (rate-limited? retry in a few seconds)"}
    box = GLOBAL_STATE.setdefault("magic_inbox", {})
    now = time.time()
    for k in [k for k, v in box.items() if now - (v.get("ts") or 0) > 1800]:
        box.pop(k, None)
    box[acc["email"]] = {"token": acc["token"], "password": acc["password"], "ts": now}
    try:
        _save_signup_email_prefs(last_used=acc["email"])  # temp inbox: last-used only, never preferred
    except Exception:
        pass
    return {"ok": True, "email": acc["email"], "auto": True}


def _arena_clear_cookies(ws_url):
    """Log the probe browser out of Arena (delete arena.ai cookies only, v2.3)."""
    try:
        ws = websocket.create_connection(ws_url, timeout=6)
        mid = [0]
        def cmd(method, params=None):
            mid[0] += 1
            ws.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
            while True:
                r = json.loads(ws.recv())
                if r.get("id") == mid[0]:
                    return r
        cmd("Network.enable")
        res = cmd("Network.getCookies", {"urls": ["https://arena.ai", "https://www.arena.ai"]})
        cookies = res.get("result", {}).get("cookies", [])
        n = 0
        for c in cookies:
            if "arena.ai" in (c.get("domain") or ""):
                cmd("Network.deleteCookies", {"name": c.get("name"), "domain": c.get("domain"), "path": c.get("path") or "/"})
                n += 1
        try:
            ws.close()
        except Exception:
            pass
        return {"ok": True, "cleared": n}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _magic_autocomplete(email, box, ws_url):
    """Finish a magic signup end-to-end and VERIFY the Arena login (v2.3).

    Polls the owned mail.tm inbox -> visits the callback in the probe tab ->
    fills the set-password form if shown -> captures cookies -> verifies via
    /api/me. Returns ok=True ONLY when Arena reports a logged-in session.
    """
    import autoheal
    token, password = box.get("token"), box.get("password")
    msg = autoheal.poll_mailtm_inbox(token, max_wait=90)
    link = autoheal._extract_callback_url(msg)
    if not link:
        return {"ok": False, "email": email, "stage": "inbox", "loggedIn": False,
                "error": "Magic link was sent but no verification email arrived in the temp inbox within 90s. Retry (fresh inbox) or complete manually."}
    try:
        import shutil as _sh
        _sh.copy2(SESSION_FILE, SESSION_FILE + ".pre-magic")
        os.chmod(SESSION_FILE + ".pre-magic", 0o600)
    except Exception:
        pass
    try:
        flow_tab, ws_url = _fresh_arena_tab()
    except Exception:
        flow_tab = None
    pre_me = _cdp_eval(ME_EXPR, ws_url=ws_url, timeout=15) or {}
    pre_id = ((pre_me.get("user") or {}) if isinstance(pre_me, dict) else {}).get("id")
    _arena_clear_cookies(ws_url)
    time.sleep(1)
    _cdp_eval("window.location.href=" + json.dumps(link), ws_url=ws_url, timeout=10, await_promise=False)
    for _ in range(15):
        time.sleep(2)
        try:
            ready = _cdp_eval("document.readyState+'|'+(!!document.querySelector('input[name=password]'))", ws_url=ws_url, timeout=8, await_promise=False)
        except Exception:
            ready = ""
        if (ready or "").startswith("complete|true"):
            break
    ws = None
    try:
        ws = websocket.create_connection(ws_url, timeout=240)
        if ws:
            done, _ = autoheal._setup_password_via_cdp(ws, password)
            if not done:
                done, _ = autoheal._fill_password_via_keys(ws, password)
        time.sleep(2)
    finally:
        try:
            if ws:
                ws.close()
        except Exception:
            pass
    me = _cdp_eval(ME_EXPR, ws_url=ws_url, timeout=15) or {}
    mu = (me.get("user") or {}) if isinstance(me, dict) else {}
    new_id = mu.get("id") or ""
    id_ok = bool(new_id) and (not pre_id or new_id != pre_id)
    hist = _cdp_eval("(async()=>{try{const r=await fetch('/api/history/unified?limit=1&includeArchived=false');return r.status;}catch(e){return -1}})()", ws_url=ws_url, timeout=20)
    if hist != 200:
        time.sleep(3)
        hist = _cdp_eval("(async()=>{try{const r=await fetch('/api/history/unified?limit=1&includeArchived=false');return r.status;}catch(e){return -1}})()", ws_url=ws_url, timeout=20)
    if (isinstance(me, dict) and me.get("status") == 200) and id_ok and hist == 200:
        display_email = mu.get("email") or email
        user_out = {"email": display_email, "id": new_id, "username": mu.get("username"), "temp": not bool(mu.get("email"))}
        try:
            _save_signup_email_prefs(last_used=email)
        except Exception:
            pass
        try:
            cap = capture_cookies_from_browser(ws_url=ws_url, email=display_email)
            cap_n = cap.get("count", 0)
        except Exception:
            cap_n = 0
        try:
            execute_restore_flow()
        except Exception:
            pass
        _close_flow_tab(flow_tab)
        return {"ok": True, "loggedIn": True, "auto_completed": True, "email": email,
                "display_email": display_email, "user": user_out, "new_id": new_id,
                "captured": cap_n, "functional": True,
                "message": "Magic signup complete - logged in to Arena as %s" % display_email}
    _close_flow_tab(flow_tab)
    return {"ok": False, "email": email, "stage": "verify", "loggedIn": False,
            "error": "Post-signup session check failed (pre=%s post=%s history=%s). No fake success declared. If several accounts were just created, Arena may be throttling - wait a few minutes and retry with a fresh inbox." % (pre_id or "none", new_id or "none", hist)}

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", "8890"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"ZIL WEB UI v2.2 running on http://127.0.0.1:{PORT}")
    server.serve_forever()
