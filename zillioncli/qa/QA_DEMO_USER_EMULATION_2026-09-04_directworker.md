# QA — FULL USER-EMULATION DEMO (2026-09-04, live sa Dell DVI-D-1, Boss watching)

Session: restore v6.1 chain verified, then clean-start Web Hub demo with per-action DIRECT vision.
Demo account: **bobede2470@mediseat.com** (Boss-provided). Probe = HIDDEN (Hyprland rule → workspace 9 silent), visible hub = workspace 1.
Boss order mid-session: run the MQTT worker **directly on the PC** (TV relay was slow) → `~/arenabridge/worker_pc.py` (lane pc/cmd/res/pres). ping ~1.0s.

## PER-ACTION VISION RESULTS
| Step | Result (vision-verified on Dell) |
|---|---|
| Clean close | :9334 hub app + :9222 probe killed; :8890 hub natira. (4x "Process crashed: chromium" toasts = clean-kill artifact) |
| Clean start | visible hub `chrome-127.0.0.1` → ws1; probe `chromium-browser` → ws9 (hidden). Probe HINDI nakikita sa Dell ✔ |
| Logout | Auth Hub opened, Direct Login tab, green "✔ Logged out na. Pwede nang mag-login ulit." |
| Direct Login | fields filled + Sign In clicked → "✔ Welcome, bobede2470@mediseat.com! Session synced & Memory Restored."; modal closed; Quota 0% |
| Attach MEMORY_CORE.md | chip "📎 16 KB MEMORY_CORE.md ✕" lumitaw (DataTransfer; dating TC-10 bug = healthy na) |
| Send `zillionOM restore` + attach | /api/restore/chat ran: key extracted (0o600,32B) ✔, vision DIRECT ✔, digest 2215 chars → create-chat STATUS:200, session 01a068b9-28a9-7ea7-9e9f-0616c5fe8a59. On-screen AI RESPONSE showed **`$31`**. |
| Restore test | Agent session RSC actually contains **"DOCTRINE LOADED 6 rules."** → restore DID succeed; the `$31` was a fetch/extraction bug, NOT an agent failure. |

## BUGS FOUND THIS SESSION
- **BUG-17 (headline, FIXED):** `zion-send wait_for_reply` locks onto an RSC forward-reference **placeholder token** (`$31`) as the "answer" before the real text streams → hub prints `$31` even though the agent really replied. FIX: `_real_replies()` filters placeholders (`^$[0-9A-Za-z]{1,8}$`) + 2-poll stabilization; `wait_for_reply` now waits for real content. Backup `zion-send.bak_pre_placeholder_fix_*`.
- **Secondary (FIXED):** CDP websocket `timeout=90` < wait window (45×2s) on slow quota accounts → `WebSocketTimeoutException`. BUMPED to 150s. Backup `.bak_pre_wstimeout_*`.
- **Hub crash loop (FIXED, BUG-5 class):** stale duplicate hub process held `:8890` → `zillion-webui.service` crash-loop with `OSError: [Errno 98] Address already in use`, **restart counter = 1544**; caused transient "TypeError: Failed to fetch". Cleared stale holders → service active, MainPID = sole listener, NRestarts=0.

## ARENA.AI ENDPOINTS (via mitt/mitmproxy :8899, probe --proxy-server + ignore-cert)
- POST `/nextjs-api/stream/create-chat` — new chat (zion-send uses this; reCAPTCHA v3 enterprise `agentic_chat_submit`).
- Follow-up (same session): after review panel, POST **`/api/chat/{sid}/review-feedback`** then composer (contenteditable + "Send message") appears; follow-up message POST goes via the composer (UI-gated; "Send message" shows "Preparing message…" / disabled state on this quota session).
- GET `/api/chat/{sid}/workspace/latest?includeManifest=true`, GET `/api/chat/{sid}/preview`, GET RSC `/agent/{sid}` (text parts incl. `$31` placeholder + real text).

## STATE POST-DEMO
- Hub :8890 = healthy, 127.0.0.1, NRestarts 0. Probe :9222 = HIDDEN ws9 (via mitm :8899; cookies/profile intact). Visible app :9334 ws1.
- PC direct MQTT worker running (`~/arenabridge/worker_pc.py`) per Boss order.
- Backups present. BUG-17 patch compiles; live end-to-end retest pending next healthy-quota send (quota account ~0% but slow).
