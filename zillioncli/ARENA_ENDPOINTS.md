# arena.ai ENDPOINT CATALOG — LOGIN / ACCOUNT / LOGOUT / AGENT / UPLOAD
> Zillion · 2026-09-01 · Na-verify LIVE via reverse proxy (mitmdump :8899, path-only addon) + JS chunk analysis.
> Security: pati ang credentials/body ay HINDI kinuha — path+method lang. Query ay redacted.

## ✅ STATUS (live-verified)
- `/api/me` → **200, hasUser:true** — naka-login na (real account, hindi na provisional).
- `send` (create-chat) → **200, reply "READY"** — gumagana na ang send loop.
- Cookies: `arena-auth-prod-v1` (+code-verifier, .0, .1) — buong OAuth session.

## 🔑 LOGIN
| Method | Endpoint | Gamit / Notes |
|---|---|---|
| POST | `/nextjs-api/sign-in/email` | Email + password. Body `{email, ...}`. (Mula sa JS chunk 73227) |
| GET  | `/nextjs-api/sign-in/google?...` | Simula ng Google OAuth (redirect, `returnTo` param). |
| GET  | `auth.arena.ai/auth/v1/authorize` | OAuth authorize (hiwalay na auth host). |
| GET  | `auth.arena.ai/auth/v1/callback` | OAuth callback. |
| GET  | `/nextjs-api/callback/google` | Arena-side Google callback → finalize login. |
| GET  | `/api/me` | Current logged-in account info (`{user}`). |

## 📝 ACCOUNT CREATION (SIGN-UP) — 2-step (provisional → real)
| Method | Endpoint | Gamit / Notes |
|---|---|---|
| POST | `/nextjs-api/sign-up` | Convert provisional→real. Body `{recaptchaToken, provisionalUserId}`. |
| POST | `/nextjs-api/sign-up/magic-link` | Email magic-link account creation. Body `{email, ...}`. |
| GET  | `/nextjs-api/callback/email` | Pagpindot ng magic-link sa email → finalize. |
| GET  | `/auth/set-password` | Pahina para i-set ang password (magic-link flow). |
| POST | `/nextjs-api/auth/set-password` | I-save ang password. |
| POST | `/nextjs-api/resend-verification` | Resend verify email. Body `{email}`. |

## 🚪 LOGOUT
| Method | Endpoint | Gamit |
|---|---|---|
| GET  | `/nextjs-api/sign-out` | Logout (clear session). |

## 🔄 RESET / RECOVER
| Method | Endpoint |
|---|---|
| POST | `/nextjs-api/reset-password/request` |
| POST | `/nextjs-api/reset-password/confirm` |
| POST | `/nextjs-api/reset-password/change` |

## 🤖 AGENT SEND (verified working)
| Method | Endpoint |
|---|---|
| POST | `/nextjs-api/stream/create-chat` | Send message. Body `{message:{id:uuidv7,role:user,parts:[{type,text,image,file}]}, recaptchaV3Token, timezone}` |
| *(reply fetch)* | `GET /agent/{sid}` → RSC `text/html` (no navigation) | Kinukuha ang assistant reply. |
| GET | `/api/history/unified` | Chat history list (gumagana na after login). |
| GET | `/history/search` , `/image` | Search / image endpoints. |

## 📎 FILE UPLOAD (attachments) — identified from JS (chunk 54556)
Flow (two-step):
1. `POST {storage-rpc} generate-agent-upload-url` body `{hash: sha256Base64url(filebytes), contentType, size}` → returns `{uploadUrl, key}`.
2. `PUT {uploadUrl}` body=file, header `Content-Type: file.type` → upload bytes.
3. Then send the `key`/`url` in the message part.
Message part schema (updated, server validates with Zod):
- `text` → `{type:"text", text}`
- `image` → `{type:"image", image:<dataUrl>, mimeType}`
- `file` → `{type:"file", url:<uploaded-key-or-url>, mediaType:<mime>, filename?}`  ← **talagang `url`+`mediaType`, HINDI inline data**
- Unsupported mime → hinaharangan (`isAllowedAgentUploadMimeType`); may `CAS_INLINE_THRESHOLD=512` (maliit na files pwedeng inline).
- `metadata.uploads` → array ng uploaded file parts sa create-chat payload.
> NOTE: Ang eksaktong URL ng `generate-agent-upload-url` rpc route ay hindi pa nahuhuli sa proxy (hindi pa nag-fa-fire ang real upload sa test). Ang rpc base ay under `/rpc/`. Pending ng isang totoong upload (magandang file) para ma-confirm.

## 🛡️ TRIPWIRE (clean)
WALANG payment/wallet/banking endpoints na na-hit (gcash/okbet/maya/wallet) sa buong capture. Bawal pa rin ang mga iyon.

## 🧪 DONE SA REVERSE PROXY
- `mitmdump` v12.2.3 @ `127.0.0.1:8899`, addon `~/zillion/capture/zion_proxy.py` (path-only).
- Probe browser naka-route sa proxy (CDP 9222 buhay).
- Log: `~/zillion/capture/zillion_proxy_paths.log` (~37KB, lumalaki).
