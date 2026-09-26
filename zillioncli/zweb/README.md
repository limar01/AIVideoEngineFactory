# zweb — Web version of the `zion` CLI (MEMORY_CORE §34)

A **localhost web UI** over the existing `zion` CLI (`send` / `ls` / `open` / `status`).
The web front-end is `index.html`; the engine is the **existing `zion` binary** —
`zweb.py` just wraps it via `subprocess`, so it keeps the exact same
Cloudflare-impersonation / CDP / RSC-no-nav behavior (no re-implemented API).

## Run (on the Omarchy PC)
The PC must have `zion` in `~/.local/bin` and the probe browser up on `:9222`
(same prerequisites as the CLI itself).

```bash
python3 zweb.py                        # -> http://127.0.0.1:8791
ZWEB_PORT=8792 python3 zweb.py         # custom port
python3 zweb.py --host 127.0.0.1 --port 8791
ZION_BIN=/home/limar01/.local/bin/zion python3 zweb.py
```

Then open **http://127.0.0.1:8791** in a browser (on the PC).

## What it does
- **CHAT** — `zion send "<msg>"` → echoes the Arena AI response (RSC no-nav, zero focus steal).
- **SESSIONS** — `zion ls` (list) + `zion open <sid>` (transcript).
- **STATUS** — `zion status` (probe browser :9222, login state, current URL).

## Endpoints (zweb.py)
| Route | zion call |
|---|---|
| `GET /` | serves `index.html` |
| `GET /api/health` | `{ok:true,zweb:true}` (liveness) |
| `GET /api/status` | `zion status` |
| `GET /api/sessions?limit=N` | `zion ls N` |
| `GET /api/session/<sid>` | `zion open <sid>` |
| `POST /api/send` `{msg}` | `zion send "<msg>"` |

## Security
- **Binds to `127.0.0.1` by default** (localhost only).
- It wraps an **authenticated Arena session** (your `zion` CLI + probe browser).
  **DO NOT expose it to the LAN/WAN.** Use `--host 0.0.0.0` only on a trusted
  network you fully control (e.g., to reach it from your phone on the same Wi-Fi).

## Files
- `index.html` — the web UI (self-contained, no external deps).
- `zweb.py` — localhost backend that wraps `zion` (stdlib only).
