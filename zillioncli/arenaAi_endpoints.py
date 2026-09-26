#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
arenaAi_endpoints.py — single source of truth for every Arena.ai URL endpoint
used by Zillion CLI / Zillion AI App.

Bakit may file na? Dati, ang bawat endpoint ay naka-bury sa CDP eval strings,
subprocess args, at magic-link regex patterns sa kalahating-dozen files. Kung
magbago ang Arena ang route, gagawa ng bug ang lahat nang hindi nakikita.
Ingatan: ang MAJORITY ng endpoints ay nasa loob ng JS strings na dinadala ng
CDP Runtime.evaluate sa live browser — sila ay same-origin relative paths
("/nextjs-api/...") at hindi kumpleto na URLs. Ang base origin ay
ARENA_ORIGIN ; ang ibang hardcoded headers o cookie-domain strings ay naka-bahagi
naman (hal. ".arena.ai").

I-update ito lang kapag nagbago ang Arena. I-re-export sa file na kumukuha.
"""

from __future__ import annotations

import os
from typing import Final

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
ARENA_ORIGIN: Final[str] = "https://arena.ai"
ARENA_AGENT_PAGE: Final[str] = ARENA_ORIGIN + "/agent"
ARENA_AGENT_PAGE_CDP: Final[str] = ARENA_AGENT_PAGE + "/"  # trailing slash for tab URL matching

DOMAINS: Final[list[str]] = [ARENA_ORIGIN, "https://www.arena.ai", "arena.ai", ".arena.ai"]

# ---------------------------------------------------------------------------
# reCAPTCHA Enterprise v3
# ---------------------------------------------------------------------------
RECAPTCHA_SITE_KEY: Final[str] = "6LeTGMcsAAAAALuIlkVwIxaAuZA8VledA6d3Nnb0"
RECAPTCHA_ENTERPRISE_JS: Final[str] = (
    "https://www.google.com/recaptcha/enterprise.js?render=" + RECAPTCHA_SITE_KEY
)
RECAPTCHA_ACTION_DEFAULT: Final[str] = "agentic_chat_submit"
RECAPTCHA_TOKEN_TTL_SEC: Final[int] = 110  # ~120 s valid; keep margin

# ---------------------------------------------------------------------------
# Endpoints — relative paths (same-origin when fetched inside the Arena tab)
# ---------------------------------------------------------------------------
# Kumpirmado sa code: zion-send.py, web/app.py, autoheal.py, zion-ls.py,
# list_full_ids.py.
ENDPOINT_CREATE_CHAT: Final[str] = "/nextjs-api/stream/create-chat"
ENDPOINT_SIGN_IN_EMAIL: Final[str] = "/nextjs-api/sign-in/email"
ENDPOINT_SIGNUP_MAGIC: Final[str] = "/nextjs-api/sign-up/magic-link"
ENDPOINT_ME: Final[str] = "/api/me"
ENDPOINT_HISTORY_UNIFIED: Final[str] = "/api/history/unified"
ENDPOINT_AGENT_RSC: Final[str] = "/agent/{sid}"       # RSC GET, same-origin fetch

# Magic-link callback URL pattern (hanapin sa mail.tm inbox text) — regex lang.
# Kumpirmado sa autoheal.py: r'https?://arena\.ai/nextjs-api/callback/email[^\s<>"\')\)]+'
CALLBACK_EMAIL_PATTERN: Final[str] = r"https://arena\.ai/nextjs-api/callback/email[^\s<>\"')\)]+"

# Alias for backward compatibility with files that use the old name
API_HISTORY_UNIFIED: Final[str] = ENDPOINT_HISTORY_UNIFIED

# Template for agent page URL with session ID (used by discover* and zion-open)
ARENA_AGENT_PAGE_TEMPLATE: Final[str] = ARENA_AGENT_PAGE + "/{sid}"

# ---------------------------------------------------------------------------
# Distance endpoints — documented sa QA demo (2026-09-04) pero HINDI pa na-code
# sa anumang file sa repo. Inilagay dito para may track kung saan dapat pumasok
# kapag nag-need ng follow-up send nang hindi bagong chat.
# ---------------------------------------------------------------------------
ENDPOINT_CHAT_REVIEW_FEEDBACK: Final[str] = "/api/chat/{sid}/review-feedback"   # POST — UI-gated composer follow-up
ENDPOINT_CHAT_WORKSPACE_LATEST: Final[str] = "/api/chat/{sid}/workspace/latest"  # GET ?includeManifest=true
ENDPOINT_CHAT_PREVIEW: Final[str] = "/api/chat/{sid}/preview"                    # GET

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def agent_rsc_url(sid: str) -> str:
    """Kompletong same-origin path para sa RSC /agent/{sid} fetch."""
    return ENDPOINT_AGENT_RSC.format(sid=sid)


def history_unified_url(limit: int = 10, include_archived: bool = False) -> str:
    return ARENA_ORIGIN + ENDPOINT_HISTORY_UNIFIED + f"?limit={limit}&includeArchived={'true' if include_archived else 'false'}"


def callback_email_regex() -> str:
    return CALLBACK_EMAIL_PATTERN


# For backward compat with files that i-import lang ang ARENA_ORIGIN / SITE_KEY.
# (Dati silang hardcoded; pwede pang i-access direkta.)
SITE_KEY: Final[str] = RECAPTCHA_SITE_KEY
ENTERPRISE_JS: Final[str] = RECAPTCHA_ENTERPRISE_JS
