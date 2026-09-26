---
name: "zion"
description: "Send a prompt to Arena AI agent mode and read the server reply. Use when the user wants to send a message to Arena, ask Arena a question, or check Arena chat history. Relies on the live browser session already logged into Arena at https://arena.ai/agent via Chrome DevTools Protocol on port 9222."
---

# Zion — Arena AI CLI

Send prompts to Arena AI agent mode and capture the model's reply.

## Requirements

- The **probe browser** must be running and logged into Arena, launched with
  `--remote-debugging-port=9222 --remote-allow-origins=*` against `https://arena.ai/agent`.
- `zion` CLI at `~/.local/bin/zion` (already installed).

## Commands

### `zion send "<message>"`

Sends a new chat message to Arena and prints the server reply. The request is made
inside the live browser (via CDP) because the reCAPTCHA v3 token and Cloudflare
cookies are bound to the browser context — a plain `curl` will not work.

```bash
zion send "Your question here"
```

### `zion ls [limit]`

Lists recent Arena chat history (uses `GET /api/history/unified` via `curl_cffi`
with a Chrome TLS fingerprint).

### `zion open <session-id>`

Prints the full transcript of an existing session, labelling each message as
`[YOU]` (user) or `[ARENA]` (assistant). Fetches `/agent/{sid}` via RSC inside the
live browser (same-origin fetch — does NOT navigate the page).

### `zion status`

Health check: is the probe browser online, is it logged in (auth cookies present),
and what is the current probe page URL.

## No-navigation reply retrieval (`fix_no_nav`)

The reply is read with a **same-origin RSC fetch** — `fetch('/agent/{sid}', {headers:
{'accept':'text/html','rsc':'1'}})` — evaluated inside the live browser. It does
NOT call `Page.navigate`, so the browser window/focus is never moved (important:
the probe window sits on the Boss's ASUS monitor and must not be brought forward).
The RSC payload's `{"type":"text","text":"..."}` parts are extracted and the
JSON escapes (`\n`, etc.) are decoded with `json.loads('"'+raw+'"')`.

## How it works (for debugging)

- Endpoint: `POST https://arena.ai/nextjs-api/stream/create-chat`
- Headers: `Content-Type: application/json` (+ browser cookies via CDP)
- Body:
  ```json
  {
    "message": {"id": "<UUIDv7>", "role": "user", "parts": [{"type": "text", "text": "..."}]},
    "recaptchaV3Token": "<token>",
    "timezone": "Asia/Manila"
  }
  ```
- `message.id` **must** be a valid UUIDv7 (use `crypto.randomUUID()`), otherwise the
  server returns `500 Failed to create session`.
- The `recaptchaV3Token` is obtained inside the browser via
  `grecaptcha.enterprise.execute('6LeTGMcsAAAAALuIlkVwIxaAuZA8VledA6d3Nnb0', {action: "agentic_chat_submit"})`.

## Note

Do not attempt to bypass reCAPTCHA with a standalone solver; the token is
session-bound and must be generated in the live browser. If the probe browser is
offline, tell the user to relaunch it.
