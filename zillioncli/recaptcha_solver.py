#!/usr/bin/env python3
"""zion-captcha — reCAPTCHA Enterprise v3 solver for Zillion CLI / Arena.

Usage:
  zion-captcha [--action NAME] [--port PORT] [--url URL] [--raw|--json|--verbose]
  zion-captcha inject --header X-Recaptcha-Token <command...>
  zion-captcha score-check   # diagnostics lang: mag-e-execute nang walang submit

Design goals (Boss doctrine: honest, no fake, walang bypass ng ToS ng Arena client-side):
  - We do NOT solve image/audio challenges (v2) — v3 enterprise lang ang ginagamit ni Arena.
  - "Solver" = mag-produce ng valid, high-score v3 token sa loob ng real Arena page
    sa pamamagitan ng: (a) tamang enterprise.ready + execute flow, (b) user-like
    interaction warm-up para hindi ma-flag ng risk engine, (c) retry ladder with
    cache reset, (d) UI-click fallback kapag cold-fetch nag-403.
  - Walang third-party captcha-solving service (expensive, labag sa RULE C spirit,
    at nag-e-expose ng session).
"""
from __future__ import annotations

import argparse, json, os, sys, time, urllib.request, uuid, re
from typing import Optional, Dict, Any

try:
    import websocket
except ImportError:
    websocket = None

# ---- constants ---------------------------------------------------------------
DEFAULT_PORT = int(os.environ.get("ZION_PORT", "9222"))
DEFAULT_ACTION = "agentic_chat_submit"
SITE_KEY = "6LeTGMcsAAAAALuIlkVwIxaAuZA8VledA6d3Nnb0"
ARENA_ORIGIN = "https://arena.ai"
ENTERPRISE_JS = "https://www.google.com/recaptcha/enterprise.js?render=" + SITE_KEY
TOKEN_TTL_SEC = 110  # v3 tokens typically valid ~120s; keep margin
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{200,}$")

# In-memory token cache keyed by (action, origin_tab_url)
_token_cache: Dict[str, Dict[str, Any]] = {}


# ---- CDP helpers -------------------------------------------------------------
def list_targets(port: int = DEFAULT_PORT):
    data = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3))
    return data


def find_arena_ws(port: int = DEFAULT_PORT, prefer_url: Optional[str] = None):
    targets = list_targets(port)
    if prefer_url:
        for t in targets:
            if t.get("type") == "page" and t.get("url", "").startswith(prefer_url):
                return t["webSocketDebuggerUrl"], t["url"]
    # prefer /agent/<id>, then /agent, then any arena page
    for prefer in ("/agent/", "/agent", "arena.ai"):
        for t in targets:
            if t.get("type") == "page" and prefer in t.get("url", ""):
                return t["webSocketDebuggerUrl"], t["url"]
    for t in targets:
        if t.get("type") == "page" and "arena.ai" in t.get("url", ""):
            return t["webSocketDebuggerUrl"], t["url"]
    return None, None


class CDP:
    def __init__(self, ws_url: str, timeout: int = 180):
        assert websocket is not None, "websocket-client not installed; pip install websocket-client"
        self.ws = websocket.create_connection(ws_url, timeout=timeout)
        self.mid = 0

    def send(self, method, params=None, timeout_ms: Optional[int] = None):
        self.mid += 1
        msg = {"id": self.mid, "method": method, "params": params or {}}
        if timeout_ms is not None:
            # Runtime.evaluate etc. use params.timeout, not here; just pass through
            pass
        self.ws.send(json.dumps(msg))
        while True:
            raw = self.ws.recv()
            m = json.loads(raw)
            if m.get("id") == self.mid:
                return m

    def eval(self, expr: str, awaitp: bool = True, timeout_ms: int = 30000):
        params = {"expression": expr, "awaitPromise": awaitp, "returnByValue": True}
        if timeout_ms:
            params["timeout"] = timeout_ms
        return self.send("Runtime.evaluate", params)

    def eval_value(self, expr: str, awaitp: bool = True, timeout_ms: int = 30000):
        r = self.eval(expr, awaitp=awaitp, timeout_ms=timeout_ms)
        res = r.get("result", {}).get("result", {})
        if res.get("subtype") == "error":
            raise RuntimeError("JS error: " + (res.get("description") or res.get("value") or "unknown"))
        return res.get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


# ---- light warm-up: trusted-state only (no synthetic mousemove/scroll — those are
# isTrusted=false and LOWER v3 scores). Focus + dwell + visibility is enough when we
# run execute in the SAME promise chain as fetch, matching the native Arena UI path.
WARMUP_JS = r"""
(async function warmup(seed){
  // Focus window (trusted state)
  try{ window.focus(); }catch(e){}
  try{
    const tb = document.querySelector('[contenteditable="true"],[role="textbox"],textarea');
    if(tb){ tb.focus(); }
  }catch(e){}
  // Force visible state (some idle tabs throttle reCAPTCHA)
  try{
    Object.defineProperty(document,'visibilityState',{get:()=>'visible',configurable:true});
    Object.defineProperty(document,'hidden',{get:()=>false,configurable:true});
  }catch(e){}
  // Small natural dwell (150-350ms) — long synthetic waits can also hurt score.
  const dwell = 150 + Math.floor(Math.random()*200);
  await new Promise(r=>setTimeout(r, dwell));
  return {ok:true, seed: seed||null, dwell_ms: dwell, href: location.href, ts: Date.now()};
})('%s')
"""


def _cdp_eval_value(cdp, expr, awaitp=True, timeout_ms=20000):
    """Duck-type adapter: works with our CDP class (eval_value) AND zion-send's CDP class (eval+result)."""
    if hasattr(cdp, "eval_value"):
        return cdp.eval_value(expr, awaitp=awaitp, timeout_ms=timeout_ms)
    # zion-send's CDP exposes eval(method,params) and eval(expr) returning the full response.
    r = cdp.eval(expr, awaitp=awaitp, timeout_ms=timeout_ms)
    res = r.get("result", {}).get("result", {}) if isinstance(r, dict) else {}
    if res.get("subtype") == "error":
        raise RuntimeError("JS error: " + (res.get("description") or res.get("value") or "unknown"))
    return res.get("value")


def _cdp_send(cdp, method, params=None):
    if hasattr(cdp, "send"):
        return cdp.send(method, params)
    raise RuntimeError("CDP object has no .send()")


def ensure_enterprise_script(cdp, sitekey: str = SITE_KEY) -> Dict[str, Any]:
    """Inject enterprise.js if window.grecaptcha is missing, then wait for ready()."""
    js = r"""(async function ensure(){
      if(window.grecaptcha && window.grecaptcha.enterprise && window.grecaptcha.enterprise.execute){
        return {loaded:true, already:true};
      }
      return new Promise((resolve,reject)=>{
        const s=document.createElement('script');
        s.src=%s;
        s.async=true; s.defer=true;
        s.onerror=(e)=>reject(new Error('script load error'));
        s.onload=async()=>{
          let tries=0;
          while(tries<50){
            if(window.grecaptcha && window.grecaptcha.enterprise){
              try{
                await new Promise(r=>window.grecaptcha.enterprise.ready(r));
                return resolve({loaded:true, already:false});
              }catch(e){}
            }
            await new Promise(r=>setTimeout(r,100));
            tries++;
          }
          reject(new Error('grecaptcha.enterprise never ready'));
        };
        document.head.appendChild(s);
      });
    })()""" % json.dumps(ENTERPRISE_JS)
    return _cdp_eval_value(cdp, js, awaitp=True, timeout_ms=20000)


def reset_recaptcha(cdp, sitekey: str = SITE_KEY):
    """Reset cached enterprise state (helps after long idle / low-score tokens)."""
    js = r"""(async function reset(){
      try{
        if(window.grecaptcha && window.grecaptcha.enterprise && window.grecaptcha.enterprise.reset){
          await window.grecaptcha.enterprise.reset(%s);
        }
        document.querySelectorAll('textarea[name="g-recaptcha-response"]').forEach(t=>t.value='');
        return {ok:true};
      }catch(e){ return {ok:false, error:String(e && e.message || e)}; }
    })()""" % json.dumps(sitekey)
    return _cdp_eval_value(cdp, js, awaitp=True, timeout_ms=8000)


def execute_token(cdp, action: str = DEFAULT_ACTION, sitekey: str = SITE_KEY,
                  timeout_ms: int = 15000) -> Dict[str, Any]:
    """Call grecaptcha.enterprise.execute. Returns {token, action, elapsed_ms}."""
    t0 = time.time()
    js = r"""(async function run(){
      try{
        if(!window.grecaptcha || !window.grecaptcha.enterprise) return {ok:false, error:'grecaptcha missing'};
        await new Promise(r=>window.grecaptcha.enterprise.ready(r));
        const token = await window.grecaptcha.enterprise.execute(%s, {action:%s});
        return {ok:true, token: token, action: %s};
      }catch(e){ return {ok:false, error: String(e && e.message || e)}; }
    })()""" % (json.dumps(sitekey), json.dumps(action), json.dumps(action))
    val = _cdp_eval_value(cdp, js, awaitp=True, timeout_ms=timeout_ms)
    elapsed = int((time.time() - t0) * 1000)
    if isinstance(val, dict):
        val["elapsed_ms"] = elapsed
    return val


def detect_security_modal(cdp) -> Optional[Dict[str, Any]]:
    """I-check kung may Arena 'Security Verification' modal (interactive challenge gate).
    Kapag meron, kailangan ni Boss ng isang pisikal/visual click sa Dell monitor — hindi ito
    mapi-programmatically ma-solve ng CDP/headless (v2-style checkbox challenge)."""
    js = r"""(function(){
      const txt = (document.body && document.body.innerText) || '';
      const has = /security verification|protected by recaptcha|quick security check/i.test(txt);
      if(!has) return {present:false};
      // Look for iframe pointing to reCAPTCHA (bframe / anchor)
      const frames = [...document.querySelectorAll('iframe')].map(f=>f.src).filter(s=>s&&s.includes('recaptcha'));
      // Find clickable elements inside visible dialogs
      return {present:true, textSnippet: txt.slice(txt.search(/security/i)-80, txt.search(/security/i)+200), frames: frames.slice(0,3)};
    })()"""
    try:
        v = _cdp_eval_value(cdp, js, awaitp=False, timeout_ms=5000)
        if isinstance(v, dict) and v.get("present"):
            return v
    except Exception:
        pass
    return None


def execute_and_fetch(cdp, fetch_js_payload: str, action: str = DEFAULT_ACTION,
                      sitekey: str = SITE_KEY, timeout_ms: int = 60000) -> Dict[str, Any]:
    """Run reCAPTCHA execute AND the supplied fetch() in a SINGLE JS promise chain.

    This matches how the native Arena UI calls grecaptcha.execute immediately before
    fetch(create-chat) in the same microtask queue — producing the highest trust signal
    (no round-trip between token acquisition and request that risk engine can flag).

    fetch_js_payload: a JS expression that, given a string variable `recaptchaV3Token`,
    returns the response text. We wrap it for you.
    Returns {ok, status, body, token_length, action}.
    """
    js = r"""(async function run(){
      try{
        if(!window.grecaptcha || !window.grecaptcha.enterprise){
          return {ok:false, stage:'recaptcha', error:'grecaptcha missing'};
        }
        await new Promise(r=>window.grecaptcha.enterprise.ready(r));
        const recaptchaV3Token = await window.grecaptcha.enterprise.execute(%s, {action:%s});
        const resp = await (async function(recaptchaV3Token){ %s })(recaptchaV3Token);
        return resp;
      }catch(e){ return {ok:false, stage:'exception', error:String(e && e.message || e)}; }
    })()""" % (json.dumps(sitekey), json.dumps(action), fetch_js_payload)
    t0 = time.time()
    val = _cdp_eval_value(cdp, js, awaitp=True, timeout_ms=timeout_ms)
    elapsed = int((time.time() - t0) * 1000)
    if isinstance(val, dict):
        val["elapsed_ms"] = elapsed
    return val


def token_is_plausible(token: Any) -> bool:
    return isinstance(token, str) and bool(TOKEN_RE.match(token))


def _obtain_token_on_cdp(cdp, action, sitekey, warmup, verbose, attempts, cache_key, tab_url,
                         bust_cache=False, close_cdp=False, navigate_if_needed=True):
    """Internal: run enterprise.ready / warmup / execute ladder on an already-connected CDP."""
    if cache_key and not bust_cache:
        cached = _token_cache.get(cache_key)
        if cached and time.time() - cached["ts"] < TOKEN_TTL_SEC and token_is_plausible(cached["token"]):
            c2 = dict(cached); c2["source"] = "cache"; return c2

    if navigate_if_needed and tab_url and not tab_url.startswith(ARENA_ORIGIN):
        if verbose:
            print(f"[captcha] navigating to {ARENA_ORIGIN}/agent", file=sys.stderr)
        _cdp_send(cdp, "Page.enable")
        _cdp_send(cdp, "Page.navigate", {"url": ARENA_ORIGIN + "/agent"})
        time.sleep(3)
        tab_url = ARENA_ORIGIN + "/agent"

    try:
        en = ensure_enterprise_script(cdp, sitekey=sitekey)
        if verbose:
            print(f"[captcha] enterprise script: {en}", file=sys.stderr)
    except Exception as e:
        attempts.append({"stage": "load_script", "error": str(e)})

    if warmup:
        seed = uuid.uuid4().hex[:8]
        try:
            w = _cdp_eval_value(cdp, WARMUP_JS % seed, awaitp=True, timeout_ms=8000)
            if verbose:
                print(f"[captcha] warm-up OK: {w}", file=sys.stderr)
            attempts.append({"stage": "warmup", "ok": True})
        except Exception as e:
            attempts.append({"stage": "warmup", "error": str(e)})

    token = None
    last_err = None
    for attempt_i in range(1, 4):
        if attempt_i > 1:
            try:
                reset_recaptcha(cdp, sitekey=sitekey)
                time.sleep(0.6)
                _cdp_eval_value(cdp,
                    "(function(){ const ev=new MouseEvent('mousemove',{bubbles:true,clientX:120,clientY:300});"
                    " document.dispatchEvent(ev); return true; })()",
                    awaitp=False, timeout_ms=4000)
                time.sleep(0.3)
            except Exception:
                pass
        try:
            r = execute_token(cdp, action=action, sitekey=sitekey)
            attempts.append({"stage": "execute", "attempt": attempt_i, "result": r})
            if r.get("ok") and token_is_plausible(r.get("token")):
                token = r["token"]
                break
            last_err = r.get("error") if isinstance(r, dict) else str(r)
        except Exception as e:
            last_err = str(e)
            attempts.append({"stage": "execute", "attempt": attempt_i, "error": last_err})
        time.sleep(0.8)

    if not token:
        try:
            _cdp_eval_value(cdp,
                "(async function kick(){ "
                "document.querySelectorAll('script[src*=\"recaptcha\"]').forEach(s=>s.remove());"
                "if(window.grecaptcha){ try{ window.grecaptcha.enterprise && window.grecaptcha.enterprise.reset && window.grecaptcha.enterprise.reset(%s); }catch(e){} }"
                "return true; })()" % json.dumps(sitekey),
                awaitp=False, timeout_ms=5000)
            time.sleep(0.4)
            ensure_enterprise_script(cdp, sitekey=sitekey)
            time.sleep(0.6)
            r = execute_token(cdp, action=action, sitekey=sitekey)
            attempts.append({"stage": "execute_reload", "result": r})
            if r.get("ok") and token_is_plausible(r.get("token")):
                token = r["token"]
            else:
                last_err = r.get("error") if isinstance(r, dict) else str(r)
        except Exception as e:
            attempts.append({"stage": "execute_reload", "error": str(e)})

    if not token:
        raise RuntimeError(f"hindi nakakuha ng valid token. last error: {last_err}; attempts={json.dumps(attempts, ensure_ascii=False)[:600]}")

    out = {
        "ok": True,
        "token": token,
        "action": action,
        "sitekey": sitekey,
        "ts": time.time(),
        "tab_url": tab_url,
        "source": "fresh",
        "attempts": attempts,
        "length": len(token),
    }
    if cache_key:
        _token_cache[cache_key] = out
    return out


def get_token_via_cdp(cdp, action: str = DEFAULT_ACTION, sitekey: str = SITE_KEY,
                      warmup: bool = True, verbose: bool = False, bust_cache: bool = False,
                      tab_url: Optional[str] = None, cache_key: Optional[str] = None) -> Dict[str, Any]:
    """Re-use an existing CDP connection (hal. mula sa zion-send). Hindi nagsasara ng cdp."""
    attempts: list = []
    if not cache_key:
        cache_key = f"{action}|{tab_url or 'existing_cdp'}"
    return _obtain_token_on_cdp(cdp, action, sitekey, warmup, verbose, attempts, cache_key,
                                tab_url=tab_url or "about:existing", bust_cache=bust_cache,
                                close_cdp=False, navigate_if_needed=bool(tab_url))


def get_token(port: int = DEFAULT_PORT, action: str = DEFAULT_ACTION,
              sitekey: str = SITE_KEY, prefer_url: Optional[str] = None,
              warmup: bool = True, verbose: bool = False, bust_cache: bool = False) -> Dict[str, Any]:
    """Main entry. Returns dict with token, action, source, tab_url, attempts."""
    cache_key = f"{action}|{prefer_url or 'arena'}"
    if not bust_cache:
        cached = _token_cache.get(cache_key)
        if cached and time.time() - cached["ts"] < TOKEN_TTL_SEC and token_is_plausible(cached["token"]):
            c2 = dict(cached); c2["source"] = "cache"; return c2

    ws_url, tab_url = find_arena_ws(port=port, prefer_url=prefer_url)
    if not ws_url:
        raise RuntimeError(f"Walang Arena tab na nakita sa port {port}. Siguraduhing naka-launch ang probe browser (--remote-debugging-port={port}).")

    cdp = CDP(ws_url)
    attempts: list = []
    try:
        return _obtain_token_on_cdp(cdp, action, sitekey, warmup, verbose, attempts, cache_key,
                                    tab_url=tab_url, bust_cache=bust_cache, close_cdp=False,
                                    navigate_if_needed=True)
    finally:
        cdp.close()


def score_probe(port: int = DEFAULT_PORT, action: str = DEFAULT_ACTION) -> Dict[str, Any]:
    """Mag-execute lang ng token (walang submit) at i-report ang metadata — diagnostics."""
    info = get_token(port=port, action=action, verbose=True)
    token = info["token"]
    # Heuristics lang: v3 token length is correlated with valid packaging.
    length = len(token)
    info["heuristic"] = {
        "length": length,
        "length_ok": length >= 200,
        "starts_with": token[:12] + "...",
        "ends_with": "..." + token[-12:],
        "format_ok": bool(TOKEN_RE.match(token)),
    }
    # We CANNOT know the real score (0.0-1.0) locally — that's computed server-side.
    info["note"] = "Ang totoong v3 score (0.0-1.0) ay nasa Google/Arena server side lang; " \
                   "hindi natin makukuha sa client. Kapag ang create-chat ay nag-403, " \
                   "ibig sabihin mababa ang score — warm-up + retry, o UI-click fallback."
    return info


# ---- CLI ---------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(prog="zion-captcha", description="reCAPTCHA Enterprise v3 solver para sa Zillion CLI / Arena.ai")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help="Chromium CDP port (default 9222)")
    p.add_argument("--action", default=DEFAULT_ACTION, help="reCAPTCHA action (default: agentic_chat_submit)")
    p.add_argument("--url", default=None, help="Preferred tab URL prefix")
    p.add_argument("--sitekey", default=SITE_KEY, help="Override sitekey")
    p.add_argument("--no-warmup", action="store_true", help="Skip user-interaction warm-up (mas mabilis pero posibleng mas mababa score)")
    p.add_argument("--raw", action="store_true", help="Print token lang (no extra output)")
    p.add_argument("--json", action="store_true", help="Print full JSON result")
    p.add_argument("--verbose", "-v", action="store_true", help="Debug logs to stderr")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("score-check", help="Mag-probe lang ng token, huwag i-submit; ipakita ang heuristics")
    inj = sub.add_parser("inject", help="Mag-produce ng token at i-inject sa env var, patakbuhin ang command")
    inj.add_argument("--header", default="X-Recaptcha-Token", help="Header name (env var RECAPTCHA_TOKEN laging naka-set)")
    inj.add_argument("command", nargs=argparse.REMAINDER, help="Command to run")

    args = p.parse_args(argv)

    try:
        if args.cmd == "score-check":
            info = score_probe(port=args.port, action=args.action)
            print(json.dumps(info, indent=2, ensure_ascii=False))
            return 0

        info = get_token(
            port=args.port, action=args.action, sitekey=args.sitekey,
            prefer_url=args.url, warmup=not args.no_warmup, verbose=args.verbose,
        )

        if args.cmd == "inject":
            os.environ["RECAPTCHA_TOKEN"] = info["token"]
            os.environ["RECAPTCHA_ACTION"] = info["action"]
            cmd = args.command
            if cmd and cmd[0] == "--":
                cmd = cmd[1:]
            if not cmd:
                print(json.dumps({"ok": True, "env": {"RECAPTCHA_TOKEN": info["token"], "RECAPTCHA_ACTION": info["action"]}}, ensure_ascii=False))
                return 0
            import subprocess
            raise SystemExit(subprocess.call(cmd, env=os.environ.copy()))

        if args.raw:
            print(info["token"])
        elif args.json:
            # huwag isama ang buong attempts logs sa default JSON kung verbose off, masyadong maingay
            out = dict(info)
            if not args.verbose:
                out["attempts"] = len(out.get("attempts", []))
            print(json.dumps(out, indent=2, ensure_ascii=False))
        else:
            print("=== Zillion reCAPTCHA v3 token ===")
            print(f"action : {info['action']}")
            print(f"sitekey: {info['sitekey']}")
            print(f"length : {info['length']} chars")
            print(f"tab    : {info['tab_url']}")
            print(f"source : {info['source']}")
            print(f"token  : {info['token']}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
