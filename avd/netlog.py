"""mitmproxy addon: append one JSON object per completed flow (agent-readable).

Used by net_proxy.sh so agents can read captured traffic as JSON lines:
  method, url, host, path, status, sizes, content-type, user-agent, request body (POST data).
"""
import datetime
import json
import os

OUT = os.environ.get("AVD_NET_LOG", os.path.expanduser("~/arenabridge/net/flows.jsonl"))
MAX_BODY = 4000          # keep POST bodies readable but bounded
SECRET_HINTS = ("authorization", "cookie", "token", "password", "secret", "api-key", "apikey")


def _text(raw):
    try:
        return raw.decode("utf-8", "replace")
    except Exception:
        return None


def _redact(headers):
    """Keep header names visible, redact obviously sensitive values."""
    out = {}
    for k, v in headers.items():
        out[k] = "<redacted>" if any(h in k.lower() for h in SECRET_HINTS) else v[:200]
    return out


def response(flow):
    req, res = flow.request, flow.response
    rec = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "method": req.method,
        "url": req.pretty_url,
        "host": req.pretty_host,
        "path": req.path,
        "status": getattr(res, "status_code", None),
        "req_bytes": len(req.raw_content or b""),
        "resp_bytes": len(res.raw_content or b"") if res else 0,
        "content_type": (res.headers.get("content-type", "") if res else ""),
        "ua": req.headers.get("user-agent", "")[:140],
        "req_headers": _redact(req.headers),
    }
    try:
        if req.raw_content:
            body = _text(req.raw_content)
            if body:
                rec["req_body"] = body[:MAX_BODY]
                rec["req_body_truncated"] = len(body) > MAX_BODY
    except Exception:
        pass
    try:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
