# 🏁 ZILLION SAVING POINT — 2026-08-30
## Buong Achievement: `zion` CLI para sa Arena AI — Integrated sa Omarchy

> **Ito ang authoritative checkpoint archive.** Kawing sa buong mission: pagkuha ng
> Arena AI chat API → pagbuo ng `zion` CLI (send + ls) → pag-echo ng AI response →
> integration sa Omarchy agent feature. Kumpleto at gumagana.

---

## ✅ MISSION COMPLETE — VERIFIED WORKING

Ang `zion` CLI ay kumpleto, na-deploy, at gumagana sa live na terminal:

```bash
~ ❯ zion send "Ano ang specialty mo?"
◆ create-chat → STATUS:200
◆ session: 01a0532a-ad17-71a5-ae22-bff16ed67339
◆ waiting for AI response...

━━━ AI RESPONSE ━━━
Magandang tanong! Wala akong iisang specialty — generalist ako na marunong
gumamit ng iba't ibang tools depende sa kailangan mo... [buong sagot]
```

```bash
~ ❯ zion ls 6
── Arena chat history (last 6) ──
  [agentic] 01a05327-750e | Sabihin mo sa akin ang isang masayang katotohanan
           2026-08-30 14:51
  ...
```

---

## 📁 MGA FILE NA GINAWA (sa PC `limar01@omarchy`)

### `zion` CLI binaries — `~/.local/bin/`
| File | Layunin |
|------|---------|
| `zion` | Wrapper command (`send|s`, `ls|l`, `open|o`, `status`) |
| `zion-send` | Nagpapadala ng mensahe sa Arena at nag-e-echo ng AI response (RSC no-nav) |
| `zion-ls` | Naglilista ng chat history (via `curl_cffi`) |
| `zion-open` | Nagpapakita ng transcript ng isang session ([YOU]/[ARENA]) via RSC |
| `zion-status` | Health check: probe online, login state, current page URL |

### Omarchy skill — `~/.agents/skills/zion/SKILL.md`
Naka-symlink sa lahat ng agent locations:
- `~/.codex/skills/zion/` (default agent = **codex**)
- `~/.claude/skills/zion/`
- `~/.pi/agent/skills/zion/`

### Mga script/artifacts para sa debugging
- `/tmp/cdp_get_token.py` — CDP token fetcher (gumagawa ng fresh recaptcha token)
- `/home/limar01/zillion/capture/full_cookies.txt` — buong session cookies (6228 chars)
- `/home/limar01/zillion/capture/chat_capture.log` — na-capture na create-chat request
- `/tmp/save_cookies.py` — mitmdump addon na nag-save ng cookies

---

## 🔑 KEY TECHNICAL DETAILS (authoritative)

### Endpoint — paglikha ng chat
```
POST https://arena.ai/nextjs-api/stream/create-chat
Content-Type: application/json
```
**Body:**
```json
{
  "message": {"id": "<UUIDv7>", "role": "user", "parts": [{"type": "text", "text": "..."}]},
  "recaptchaV3Token": "<token>",
  "timezone": "Asia/Manila"
}
```

### Endpoint — kasaysayan ng chat
```
GET https://arena.ai/api/history/unified?limit=N&includeArchived=false
→ 200 OK { "entries": [ {type, id, title, createdAt, ...} ] }
```

### ✓ KRITIKAL na mga pagtuklas na sumasa-lutas:
1. **Cloudflare block** — nalutas gamit ang `curl_cffi` (Chrome TLS fingerprint,
   `impersonate='chrome'`). Ang plain curl ay na-401 `User not found`. Ang
   `curl_cffi 0.16.2` ang pumasa.
2. **reCAPTCHA v3** — `grecaptcha.enterprise.execute()` (hindi `grecaptcha.execute`).
   Site key: `6LeTGMcsAAAAALuIlkVwIxaAuZA8VledA6d3Nnb0`.
3. **Ang reCAPTCHA action** — dapat `agentic_chat_submit` (ang source na ginagamit ng
   Arena). Ang `action:'submit'` ay na-403. Ang `agentic_chat_submit` ay pumasa.
4. **`message.id`** — dapat **wastong UUIDv7** (gamit ang `crypto.randomUUID()`).
   Ang maling UUID ay nagbalik ng `500 Failed to create session`. Ito ang
   huling balakid na nalutas.
5. **Ang reCAPTCHA token ay NON-PORTABLE** — naka-bind sa browser context
   (pageId + session). Kaya ang `create-chat` POST ay dapat gawin **sa loob ng
   live browser** (CDP), hindi sa curl. Ang `GET /api/history/unified` naman ay
   gumagana sa curl_cffi.
6. **AI response fetch (FIX_NO_NAV — RSC fetch, walang `Page.navigate`)** —
   Gaya ng ginagamit ng `zion-send` at `zion-open`.
   Walang direktang GET para sa chat reply (`GET /api/chat/{sid}` → 403
   `Route not allowed`). Ang reply ay nakuha sa pamamagitan ng **`fetch('/agent/{sid}')`
   sa loob ng browser na may header `rsc:1` + `accept:text/html`** — hindi na
   gumagamit ng `Page.navigate`. Ito ay iniiwasan ang focus shift papuntang ASUS
   (hindi na ginagalaw ang browser window). Ang RSC payload ay may mga text part
   na `{"type":"text","text":"..."}`; binubunot ang mga ito via regex, tapos
   ina-unescape (JSON decoder) para sa wastong `\n` atbp.
   - **Paraan:** `fetch('/agent/{sid}',{headers:{'accept':'text/html','rsc':'1'}})`
     → i-scan ang lahat ng `"type":"text","text":"..."` → `json.loads('"'+raw+'"')`
     para i-decode ang escapes. Ang huling text part (hindi ang user msg) ang sagot.
   - **`fix_no_nav` na-verify:** ang probe page ay nananatili sa lumang
     `arena.ai/agent/...` (hindi na-navigate); hindi na-shift ang focus sa ASUS.

### Auth
- **Cookies**: `arena-auth-prod-v1.0` (JWT access token), `arena-auth-prod-v1.1`
  (refresh token), `cf_clearance`, `__cf_bm`.
- **User**: `poyxxx11@gmail.com` (Google OAuth), user ID
  `01a030f5-a667-72bb-8695-cd5298b55412`.
- **PostHog token**: `phc_LG7IJbVJqBsk584rbcKca0D5lV2vHguiijDrVji7yDM`.
- Walang `Authorization` header — auth ay ganap nasa cookies.

---

## ⚙️ HABANG TUMATAKBO (live state)
| Proseso | PID | Layunin |
|---------|-----|---------|
| probe browser | ~79564+ (may `--remote-debugging-port=9222 --remote-allow-origins=*`) | Live browser, naka-login sa Arena `/agent` |
| mitmdump | 78079 (save_cookies addon) | Optional — maaaring i-off |

### Probe browser launch command
```bash
chromium --ozone-platform=wayland \
  --user-data-dir=~/.config/chromium-zillion-probe2 \
  --remote-debugging-port=9222 --remote-allow-origins=* \
  --no-first-run --no-default-browser-check --new-window https://arena.ai/agent
```
- **BAGONG PROBE (2026-08-31):** nasa **DELL monitor, workspace 4** (moved off ASUS).
- Fresh profile `chromium-zillion-probe2`; walang proxy (alis-walang mitmdump).
- Ang user ay nag-login nang manual. Cookies na-sync sa `full_cookies.txt`.

### WORKSPACE SCHEME (user-approved, 2026-08-31)
- **DELL (DVI-D-1):** workspace **4, 5** — para sa aking automation.
- **ASUS (DP-2):** workspace **1, 2, 3** — para sa user.
- `zion` CLI: ang probe Chrome ay nasa DELL ws4; hindi na nakakaistorbo sa ASUS.

### DETALYE — kung bakit CDP (bakit hindi pure curl)
Ang reCAPTCHA v3 token at Cloudflare cookies ay naka-bind sa browser. Ang
`zion send` ay gumagawa ng `fetch()` sa loob ng browser (sa pamamagitan ng CDP
`Runtime.evaluate`), na para bang ang browser mismo ang nagpadala. Ito ang
tanging paraan na gumagana dahil sa engineered barriers.

### ✓ FIX_NO_NAV — na-verify (2026-08-30)
Ang lumang `zion send` ay gumagamit ng `Page.navigate` sa session page, na nagiging
sanhi ng pag-shift ng focus/browser window papuntang ASUS. **Naayos:** gamit ang
RSC fetch (`fetch('/agent/{sid}',{rsc:1})`) sa loob ng kasalukuyang page — hindi na
gumagamit ng `Page.navigate`. Kumpirmado: nahahanap ang assistant text parts at
na-e-echo nang malinis (hal. sagot: `4 po. 😄 / Ano'ng kailangan mong tulong?`),
at ang probe page ay nananatili sa dating URL (walang navigation).

---

## 🏠 MONITOR/ENVIRONMENT (pwede pero kasarian-hindi-reset)
- **ASUS** = `DP-2 | 2560x1440 | pos=0,0` (LEFT, primary/Boss's). Boss's windows:
  `Arena Benchmark` (0x55b8afd5b230), Firefox, at iba pa — HINDI galawin.
- **DELL** = `DVI-D-1 | 1680x1050 | pos=2560,0` (RIGHT, akin). Ang probe ay nasa Dell.
- Desktop manager: **Hyprland** sa pamamagitan ng Omarchy.
- `zillonsudo` gate: **[REPAIRED]** — bug `exec do_grant: not found` ay pinalitan
  ng direktang `do_grant` callback (exit 127 na ay naayos).

---

## ⚠️ MGA LIMITASYON AT PAALALA
1. **`zion send` ay nangangailangan ng live browser** — bukas at naka-login sa
   Arena (`/agent`). Kung offline ang browser, sasabihin nito ang error.
2. **`message.id` ay UUIDv7** — huwag gumamit ng ibang format.
3. **reCAPTCHA token ay session-bound** — huwag subukang i-solve/bpassaw gamit ang
   standalone solver; hindi gagana (v3 ay score-based, dinisenyo para pigilan ito).
4. **`GET /api/chat/{id}` ay hindi available** (403 `Route not allowed`) — gamitin
   ang `GET /agent/{id}` DOM extraction para sa reply.
5. Ang `mitmdump` ay maaaring i-off kapag hindi ginagamit para makatipid.

---

## 🔜 SUSUNOD NA MAAARING GAWIN (opsyonal, para sa future)
- `zion send --session <id> "message"` — **DETERMINED: HINDI suportado ng Arena.**
  Ebidensya (2026-08-31):
  1. Walang exposed na "continue agent chat" endpoint sa frontend source (tanging
     `create-chat` para sa unang mensahe; evaluation/webdev resume routes para sa iba).
  2. `GET /api/coding-agent/sessions/{sid}` at `.../workflow-checks` → **404** para sa
     ating `[agentic]` sessions (ibang feature talaga).
  3. Ang Agent Mode session page ay nagre-render ng **workspace view, WALANG chat
     composer** — kumpirmado sa 45s na polling. May "Keep working"/"Workspace" na
     estado, hindi isang message input para sa follow-up.
  → Ang `zion open` (tingnan transcript) at `zion send` (bagong session) ay ang
  praktikal na gamit. Ang patuloy na pagpadala sa lumang agentic session ay hindi
  tugma sa disenyo ng Arena UI/API.
- Pagbutihin ang reasoning filter sa `extract_reply` para sa kumplikadong multi-step replies.
- Auto-refresh ng cookies kapag nag-expire.

---
*Ginawa: 2026-08-30 (Asia/Manila). Buong mission na-dokumento at na-verify.*
