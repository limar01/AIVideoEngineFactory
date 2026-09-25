"""MetaVibesProvider — API-based automation for Vibes.ai video generation.

No browser required: drives Vibes.ai entirely through its REST API + SSE
progress stream. Auth uses Meta session cookies loaded from a JSON cookie jar
(first-party cookies captured from a logged-in browser session at
https://vibes.ai).

Discovered API surface (live probe, 2026-09-25):
  - POST /api/generation-batches          — create a generation batch
  - POST /api/generate/videos             — submit a video generation job
  - GET  /api/generation-batches/{id}/stream — SSE progress stream
  - GET  /api/projects/{id}/batches       — list batches for a project

Supported options (discovered):
  - aspect_ratios: 1:1, 9:16, 16:9
  - resolutions:   480p, 720p
  - variations:    1-4
  - models:        midjen-short, midjen-extend, (more discovered at runtime)
  - i2v frames:    start_frame + end_frame image attachments

Lifecycle:
  __init__ → authenticate (load cookies + verify) → submit_generation
  → get_generation_status (SSE poll) → download_result → close_session.

Auth model: no API keys. Meta session cookies (e.g. c_user, xs, etc.)
persist per-account in a JSON cookie jar on disk. First login is manual
(user logs into vibes.ai in a real browser and exports cookies). Never
bypasses CAPTCHA/2FA.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from app.providers.base import (
    GenerationCapabilities,
    GenerationResult,
    GenerationStatus,
    QuotaInfo,
    VideoGenerationProvider,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://vibes.ai"
API_PREFIX = "/api"

PROVIDER_NAME = "meta-vibes"

# Default cookie jar path (one per account; Meta session cookies)
DEFAULT_COOKIE_JAR = os.path.expanduser("~/.meta-vibes-cookies.json")

# Default download directory
DEFAULT_DOWNLOAD_DIR = os.path.expanduser("~/Data/meta-vibes-downloads")

# SSE reconnect backoff (seconds)
SSE_INITIAL_BACKOFF = 1.0
SSE_MAX_BACKOFF = 30.0

# Generation timeout (seconds) — Vibes.ai generations can take a few minutes
DEFAULT_GENERATION_TIMEOUT_SECONDS = 600

# Polling interval for non-SSE fallback status checks
DEFAULT_POLL_INTERVAL_SECONDS = 10

# ---------------------------------------------------------------------------
# Discovered API endpoint paths
# ---------------------------------------------------------------------------

ENDPOINT_CREATE_BATCH = "/api/generation-batches"
ENDPOINT_GENERATE_VIDEO = "/api/generate/videos"
ENDPOINT_BATCH_STREAM = "/api/generation-batches/{batch_id}/stream"
ENDPOINT_PROJECT_BATCHES = "/api/projects/{project_id}/batches"

# ---------------------------------------------------------------------------
# Discovered option sets (from live probe 2026-09-25)
# ---------------------------------------------------------------------------

SUPPORTED_ASPECT_RATIOS = ["1:1", "9:16", "16:9"]
SUPPORTED_RESOLUTIONS = ["480p", "720p"]
SUPPORTED_VARIATIONS = [1, 2, 3, 4]

# Models discovered from the Vibes.ai model picker.
# The live site exposes these; more may be added as they appear.
SUPPORTED_MODELS = [
    "midjen-short",
    "midjen-extend",
    "midjen-standard",
    "vibes-default",
]

# Default selections
DEFAULT_ASPECT_RATIO = "9:16"
DEFAULT_RESOLUTION = "720p"
DEFAULT_VARIATIONS = 1
DEFAULT_MODEL = "midjen-short"

# ---------------------------------------------------------------------------
# Error patterns (parsed from API responses / SSE messages)
# ---------------------------------------------------------------------------

ERROR_PATTERNS = [
    (re.compile(r"not\s+enough\s+credits", re.I), "QUOTA_EXHAUSTED"),
    (re.compile(r"out\s+of\s+credits", re.I), "QUOTA_EXHAUSTED"),
    (re.compile(r"daily\s+limit", re.I), "QUOTA_EXHAUSTED"),
    (re.compile(r"rate\s+limit", re.I), "RATE_LIMITED"),
    (re.compile(r"too\s+many\s+requests", re.I), "RATE_LIMITED"),
    (re.compile(r"generation\s+failed", re.I), "GENERATION_FAILED"),
    (re.compile(r"try\s+again\s+later", re.I), "RATE_LIMITED"),
    (re.compile(r"sign\s*in", re.I), "SESSION_EXPIRED"),
    (re.compile(r"invalid\s+session", re.I), "SESSION_EXPIRED"),
    (re.compile(r"unauthorized", re.I), "UNAUTHORIZED"),
    (re.compile(r"forbidden", re.I), "FORBIDDEN"),
    (re.compile(r"model\s+unavailable", re.I), "MODEL_UNAVAILABLE"),
    (re.compile(r"under\s+maintenance", re.I), "MAINTENANCE"),
]

# ---------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------


def load_cookies_from_jar(jar_path: str) -> list[dict[str, Any]]:
    """Load Meta session cookies from a JSON cookie jar file.

    Expected format: a list of dicts with at least ``name`` and ``value``,
    plus optional ``domain``, ``path``, ``expires``, ``secure``, ``httpOnly``,
    ``sameSite`` (mirrors Playwright's cookie dict schema so the same file
    can be used for both API and browser automation if needed).
    """
    if not os.path.exists(jar_path):
        return []
    try:
        with open(jar_path) as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        # Maybe a dict with a 'cookies' key
        if isinstance(data, dict) and isinstance(data.get("cookies"), list):
            return data["cookies"]
        return []
    except (json.JSONDecodeError, IOError) as exc:
        logger.warning("MetaVibes: failed to load cookie jar %s: %s", jar_path, exc)
        return []


def _build_cookie_dict(cookies: list[dict[str, Any]]) -> dict[str, str]:
    """Extract {name: value} from a Playwright-shaped cookie list."""
    result: dict[str, str] = {}
    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        if name:
            result[name] = value
    return result


def build_httpx_client(
    cookies: list[dict[str, Any]],
    timeout: float = 30.0,
    user_agent: Optional[str] = None,
) -> httpx.Client:
    """Build an ``httpx.Client`` pre-loaded with the given cookies."""
    cookie_dict = _build_cookie_dict(cookies)
    headers: dict[str, str] = {
        "User-Agent": user_agent or (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/",
    }
    kwargs: dict[str, Any] = {
        "base_url": BASE_URL,
        "timeout": timeout,
        "headers": headers,
    }
    if cookie_dict:
        kwargs["cookies"] = cookie_dict
    return httpx.Client(**kwargs)


def extract_error_from_response(response: httpx.Response) -> tuple[Optional[str], Optional[str]]:
    """Try to extract an error code + message from a Vibes.ai API response."""
    code = None
    message = None
    try:
        body = response.text
        for pattern, err_code in ERROR_PATTERNS:
            m = pattern.search(body)
            if m:
                code = err_code
                message = m.group(0)
                break
        # Also check JSON error bodies
        if response.headers.get("content-type", "").startswith("application/json"):
            try:
                data = response.json()
                if isinstance(data, dict):
                    message = data.get("message") or data.get("error") or message
                    code = data.get("code") or code
            except (json.JSONDecodeError, ValueError):
                pass
    except Exception:
        pass
    return code, message


# ---------------------------------------------------------------------------------------
# MetaVibesProvider
# ---------------------------------------------------------------------------------------


class MetaVibesProvider(VideoGenerationProvider):
    """API-based provider for Vibes.ai.

    All communication is via ``httpx`` + Meta session cookies — no browser
    automation required. Generation progress is tracked via SSE
    (``/api/generation-batches/{id}/stream``) with exponential backoff
    reconnect.

    scene_metadata keys (all optional):
      - aspect_ratio:    "1:1", "9:16", or "16:9"  (default: "9:16")
      - resolution:      "480p" or "720p"          (default: "720p")
      - variations:      1, 2, 3, or 4             (default: 1)
      - model:           model identifier string   (default: "midjen-short")
      - start_frame:     path to an image file for i2v start frame attachment
      - end_frame:       path to an image file for i2v end frame attachment
      - generation_type: "t2v" (text-to-video) or "i2v" (image-to-video)
    """

    PROVIDER_NAME = PROVIDER_NAME

    def __init__(
        self,
        base_url: str = BASE_URL,
        cookie_jar: Optional[str] = None,
        download_dir: str = DEFAULT_DOWNLOAD_DIR,
        generation_timeout_seconds: int = DEFAULT_GENERATION_TIMEOUT_SECONDS,
        poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
        sse_reconnect_base: float = SSE_INITIAL_BACKOFF,
        sse_reconnect_max: float = SSE_MAX_BACKOFF,
        user_agent: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookie_jar = cookie_jar or DEFAULT_COOKIE_JAR
        self.download_dir = os.path.abspath(download_dir)
        self.generation_timeout = generation_timeout_seconds
        self.poll_interval = poll_interval_seconds
        self.sse_reconnect_base = sse_reconnect_base
        self.sse_reconnect_max = sse_reconnect_max
        self.user_agent = user_agent

        os.makedirs(self.download_dir, exist_ok=True)

        # Runtime state
        self._client: Optional[httpx.Client] = None
        self._cookies: list[dict[str, Any]] = []
        self._authenticated = False
        self._last_error_code: Optional[str] = None
        self._last_error_message: Optional[str] = None
        # Stores completed result download paths for download_result()
        self._completed_results: dict[str, str] = {}  # result_id -> file path

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, scene_metadata: dict) -> tuple[bool, Optional[str]]:
        """Validate scene_metadata options against provider capabilities.

        Returns (is_valid, error_message). Checks aspect_ratio, resolution,
        variations, model, and generation_type.
        """
        aspect_ratio = str(scene_metadata.get("aspect_ratio", DEFAULT_ASPECT_RATIO))
        resolution = str(scene_metadata.get("resolution", DEFAULT_RESOLUTION))
        variations = int(scene_metadata.get("variations", DEFAULT_VARIATIONS))
        model = str(scene_metadata.get("model", DEFAULT_MODEL))
        generation_type = str(scene_metadata.get("generation_type", "t2v"))

        if aspect_ratio not in SUPPORTED_ASPECT_RATIOS:
            return False, f"Unsupported aspect_ratio '{aspect_ratio}'. Supported: {SUPPORTED_ASPECT_RATIOS}"
        if resolution not in SUPPORTED_RESOLUTIONS:
            return False, f"Unsupported resolution '{resolution}'. Supported: {SUPPORTED_RESOLUTIONS}"
        if variations not in SUPPORTED_VARIATIONS:
            return False, f"Unsupported variations '{variations}'. Supported: {SUPPORTED_VARIATIONS}"
        if model not in SUPPORTED_MODELS:
            return False, f"Unknown model '{model}'. Known: {SUPPORTED_MODELS}"
        if generation_type not in ("t2v", "i2v"):
            return False, f"Unsupported generation_type '{generation_type}'. Use 't2v' or 'i2v'."
        if generation_type == "i2v":
            start_frame = scene_metadata.get("start_frame")
            end_frame = scene_metadata.get("end_frame")
            if not start_frame:
                return False, "i2v generation requires 'start_frame' path"
        return True, None

    # ------------------------------------------------------------------
    # Capabilities (ABC rename: capabilities() → get_capabilities())
    # ------------------------------------------------------------------

    def capabilities(self) -> GenerationCapabilities:
        """Return the provider's capabilities (alias for get_capabilities)."""
        return self.get_capabilities()

    # ------------------------------------------------------------------
    # Authentication (ABC)
    # ------------------------------------------------------------------

    def authenticate(self, account_credentials: dict) -> bool:
        """Load Meta session cookies from the jar and verify the session.

        ``account_credentials`` may contain an optional ``cookie_jar`` key
        to override the default jar path for this account. If no cookies are
        found or the session is invalid, returns False — does NOT attempt
        interactive login.
        """
        jar_path = account_credentials.get("cookie_jar", self.cookie_jar)
        self._cookies = load_cookies_from_jar(jar_path)

        if not self._cookies:
            self._last_error_code = "NO_COOKIES"
            self._last_error_message = (
                "No Meta session cookies found. Log in manually at "
                f"{self.base_url} and export cookies to {jar_path} first."
            )
            logger.error(self._last_error_message)
            return False

        # Build the HTTP client with these cookies
        self._client = build_httpx_client(self._cookies, user_agent=self.user_agent)

        # Verify session by hitting a protected endpoint
        try:
            return self._verify_session()
        except Exception as exc:
            self._last_error_code = "AUTH_VERIFY_FAILED"
            self._last_error_message = str(exc)
            logger.error("MetaVibes: session verification failed: %s", exc)
            return False

    def check_session(self) -> bool:
        """Check whether the current session is still valid."""
        if not self._client or not self._authenticated:
            return False
        try:
            return self._verify_session()
        except Exception:
            return False

    def _verify_session(self) -> bool:
        """Hit the projects endpoint to verify the session is live."""
        assert self._client is not None
        try:
            resp = self._client.get(
                f"{self.base_url}{ENDPOINT_PROJECT_BATCHES.format(project_id='me')}",
                timeout=15.0,
            )
            # Vibes.ai returns 200 with a list (maybe empty) if logged in,
            # 401/403 if session is expired.
            if resp.status_code == 200:
                self._authenticated = True
                logger.info("MetaVibes: session verified (status 200)")
                return True
            code, msg = extract_error_from_response(resp)
            if code in ("SESSION_EXPIRED", "UNAUTHORIZED", "FORBIDDEN"):
                self._last_error_code = code
                self._last_error_message = msg or f"HTTP {resp.status_code}"
                self._authenticated = False
                logger.warning("MetaVibes: session invalid — %s: %s", code, msg)
                return False
            # Accept any 2xx as 'verified enough'
            if 200 <= resp.status_code < 300:
                self._authenticated = True
                return True
            self._last_error_code = "AUTH_UNKNOWN_STATUS"
            self._last_error_message = f"Unexpected status {resp.status_code}"
            self._authenticated = False
            return False
        except httpx.HTTPError as exc:
            self._last_error_code = "AUTH_NETWORK_ERROR"
            self._last_error_message = str(exc)
            self._authenticated = False
            return False

    # ------------------------------------------------------------------
    # Capabilities & Quota (ABC)
    # ------------------------------------------------------------------

    def get_capabilities(self) -> GenerationCapabilities:
        return GenerationCapabilities(
            max_prompt_length=4000,  # Vibes.ai observed limit
            supported_aspect_ratios=SUPPORTED_ASPECT_RATIOS,
            supported_resolutions=SUPPORTED_RESOLUTIONS,
            max_duration_seconds=10.0,  # observed: most generations ~5-10s
            min_duration_seconds=1.0,
            supports_narration=False,  # Vibes.ai focused on silent clips
        )

    def get_quota(self) -> QuotaInfo:
        """Attempt to read quota info from the account endpoint.

        Returns largely unknown values if the provider doesn't expose them.
        """
        if not self._client:
            return QuotaInfo()
        try:
            # Try to hit a quota/endpoint; fall back to unknowns
            resp = self._client.get(
                f"{self.base_url}/api/account/quota", timeout=10.0
            )
            if resp.status_code == 200 and resp.headers.get(
                "content-type", ""
            ).startswith("application/json"):
                try:
                    data = resp.json()
                    return QuotaInfo(
                        limit=data.get("limit"),
                        used=data.get("used"),
                        remaining=data.get("remaining"),
                        reset_time=data.get("reset_time"),
                    )
                except (json.JSONDecodeError, ValueError):
                    pass
        except Exception:
            pass
        return QuotaInfo()

    # ------------------------------------------------------------------
    # Generation (ABC)
    # ------------------------------------------------------------------

    def submit_generation(self, prompt: str, scene_metadata: dict) -> GenerationResult:
        """Submit a video generation request to Vibes.ai.

        Steps:
          1. Resolve options from scene_metadata (aspect_ratio, resolution,
             variations, model, start/end frame, generation_type).
          2. Optionally create a generation batch (if the API requires it).
          3. POST to /api/generate/videos with the payload.
          4. If SSE is available, start streaming progress; otherwise return
             a result_id for polling via get_generation_status().

        Returns a GenerationResult with result_id set on success.
        """
        if not self._ensure_authenticated():
            return self._fail("NOT_AUTHENTICATED", "Session expired — re-authenticate first")

        # Validate first
        valid, err_msg = self.validate(scene_metadata)
        if not valid:
            return self._fail("INVALID_OPTIONS", err_msg or "Validation failed")

        # Resolve options
        aspect_ratio = str(scene_metadata.get("aspect_ratio", DEFAULT_ASPECT_RATIO))
        resolution = str(scene_metadata.get("resolution", DEFAULT_RESOLUTION))
        variations = int(scene_metadata.get("variations", DEFAULT_VARIATIONS))
        model = str(scene_metadata.get("model", DEFAULT_MODEL))
        generation_type = str(scene_metadata.get("generation_type", "t2v"))
        start_frame_path = scene_metadata.get("start_frame")
        end_frame_path = scene_metadata.get("end_frame")

        logger.info(
            "MetaVibes.submit_generation — prompt_len=%d, aspect=%s, res=%s, "
            "variations=%d, model=%s, type=%s",
            len(prompt), aspect_ratio, resolution, variations, model, generation_type,
        )

        # Build the generation payload
        payload: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "variations": variations,
            "model": model,
            "generation_type": generation_type,
        }

        # Step 1: Optionally create a generation batch first
        batch_id = None
        try:
            batch_resp = self._client.post(
                f"{self.base_url}{ENDPOINT_CREATE_BATCH}",
                json={"prompt": prompt, "options": payload},
                timeout=30.0,
            )
            if batch_resp.status_code in (200, 201):
                try:
                    batch_data = batch_resp.json()
                    batch_id = batch_data.get("id") or batch_data.get("batch_id")
                except (json.JSONDecodeError, ValueError):
                    pass
        except httpx.HTTPError as exc:
            logger.debug(
                "MetaVibes: batch creation skipped (%s) — proceeding without batch",
                exc,
            )

        # Step 2: Submit the video generation
        try:
            # Use multipart if we have frame attachments, JSON otherwise
            if generation_type == "i2v" and (start_frame_path or end_frame_path):
                form = httpx.Request(
                    "POST",
                    f"{self.base_url}{ENDPOINT_GENERATE_VIDEO}",
                    content=_build_multipart_form(
                        prompt=prompt,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                        variations=variations,
                        model=model,
                        generation_type=generation_type,
                        batch_id=batch_id,
                        start_frame_path=start_frame_path,
                        end_frame_path=end_frame_path,
                    ),
                    headers={"Content-Type": "multipart/form-data"},
                )
                # We need to use the client properly for multipart
                gen_resp = self._submit_multipart(
                    payload,
                    start_frame_path,
                    end_frame_path,
                    batch_id,
                )
            else:
                gen_resp = self._client.post(
                    f"{self.base_url}{ENDPOINT_GENERATE_VIDEO}",
                    json=payload,
                    timeout=60.0,
                )

            if gen_resp.status_code in (200, 201):
                try:
                    gen_data = gen_resp.json()
                    result_id = (
                        gen_data.get("id")
                        or gen_data.get("result_id")
                        or gen_data.get("generation_id")
                    )
                    if not result_id:
                        result_id = batch_id or str(uuid.uuid4())[:8]

                    logger.info("MetaVibes.submit_generation — result_id=%s", result_id)

                    return GenerationResult(
                        success=True,
                        result_id=result_id,
                        error_code=None,
                        error_message=None,
                        download_url=None,
                        estimated_wait_seconds=self.generation_timeout // 2,
                    )
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.error(
                        "MetaVibes: failed to parse generation response: %s", exc
                    )
                    return self._fail("PARSE_ERROR", f"Could not parse response: {exc}")
            else:
                code, msg = extract_error_from_response(gen_resp)
                return self._fail(
                    code or "GENERATION_FAILED",
                    msg or f"HTTP {gen_resp.status_code}: {gen_resp.text[:200]}",
                )

        except httpx.HTTPError as exc:
            return self._fail("NETWORK_ERROR", str(exc))
        except Exception as exc:
            return self._fail("SUBMIT_EXCEPTION", str(exc))

    def _submit_multipart(
        self,
        payload: dict[str, Any],
        start_frame_path: Optional[str],
        end_frame_path: Optional[str],
        batch_id: Optional[str],
    ) -> httpx.Response:
        """Submit a multipart form request for i2v generation."""
        assert self._client is not None

        # Build multipart manually using httpx's request formatting
        form_data = _build_multipart_form(
            prompt=payload["prompt"],
            aspect_ratio=payload["aspect_ratio"],
            resolution=payload["resolution"],
            variations=payload["variations"],
            model=payload["model"],
            generation_type=payload["generation_type"],
            batch_id=batch_id,
            start_frame_path=start_frame_path,
            end_frame_path=end_frame_path,
        )
        req = httpx.Request(
            "POST",
            f"{self.base_url}{ENDPOINT_GENERATE_VIDEO}",
            content=form_data,
            headers={"Content-Type": "multipart/form-data"},
        )
        return self._client.send(req, timeout=60.0)

    def get_generation_status(self, result_id: str) -> GenerationStatus:
        """Poll the status of a submitted generation.

        Primary mechanism: SSE stream from /api/generation-batches/{id}/stream.
        Fallback: HTTP poll of the batch status endpoint.

        If the result was already downloaded, returns COMPLETED immediately.
        """
        if result_id in self._completed_results:
            return GenerationStatus.COMPLETED

        if not self._ensure_authenticated():
            return GenerationStatus.UNKNOWN

        try:
            status = self._poll_status(result_id)
            return status
        except Exception as exc:
            logger.warning("MetaVibes.get_generation_status — polling failed: %s", exc)
            return GenerationStatus.UNKNOWN

    def check_status(self, result_id: str) -> GenerationStatus:
        """Alias for get_generation_status (for callers that prefer check_status)."""
        return self.get_generation_status(result_id)

    def _poll_status(self, result_id: str) -> GenerationStatus:
        """Poll the generation status via the batch stream endpoint or HTTP fallback."""
        assert self._client is not None

        # Attempt to find the batch via the result_id
        # Try the stream endpoint (SSE) first
        try:
            # SSE is best-effort — we read one chunk to check status
            # For a non-blocking check, do a short HTTP GET on the batch status
            resp = self._client.get(
                f"{self.base_url}{ENDPOINT_CREATE_BATCH.rstrip('/')}/{result_id}",
                timeout=10.0,
            )
            if resp.status_code == 200 and resp.headers.get(
                "content-type", ""
            ).startswith("application/json"):
                data = resp.json()
                status_str = str(
                    data.get("status", data.get("state", "")).upper()
                )
                logger.info(
                    "MetaVibes._poll_status — result_id=%s status=%s",
                    result_id,
                    status_str,
                )
                return self._map_status(status_str)
        except httpx.HTTPError:
            pass

        # Fallback: try the project batches endpoint and search for the result_id
        try:
            resp = self._client.get(
                f"{self.base_url}{ENDPOINT_PROJECT_BATCHES.format(project_id='me')}",
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                batches = (
                    data
                    if isinstance(data, list)
                    else data.get("batches", data.get("results", []))
                )
                for batch in batches:
                    bid = (
                        batch.get("id")
                        or batch.get("result_id")
                        or batch.get("generation_id")
                    )
                    if bid == result_id or str(bid).endswith(result_id):
                        status_str = str(
                            batch.get("status", batch.get("state", "")).upper()
                        )
                        logger.info(
                            "MetaVibes._poll_status (fallback) — status=%s",
                            status_str,
                        )
                        return self._map_status(status_str)
        except Exception:
            pass

        return GenerationStatus.UNKNOWN

    def _map_status(self, status_str: str) -> GenerationStatus:
        """Map a Vibes.ai status string to GenerationStatus."""
        s = status_str.upper()
        if s in ("COMPLETED", "DONE", "SUCCESS", "FINISHED"):
            return GenerationStatus.COMPLETED
        if s in ("PENDING", "QUEUED", "SUBMITTED"):
            return GenerationStatus.PENDING
        if s in ("GENERATING", "PROCESSING", "RUNNING", "PROGRESSING"):
            return GenerationStatus.GENERATING
        if s in ("FAILED", "ERROR", "CANCELLED", "TIMEOUT"):
            return GenerationStatus.FAILED
        return GenerationStatus.UNKNOWN

    def download_result(self, result_id: str) -> bytes:
        """Download a completed generation result.

        The video URL is obtained from the batch status endpoint. The file is
        saved to download_dir and cached in _completed_results for idempotent
        re-downloads.
        """
        if result_id in self._completed_results:
            path = self._completed_results[result_id]
            if os.path.exists(path):
                with open(path, "rb") as f:
                    return f.read()

        if not self._ensure_authenticated():
            raise RuntimeError("Not authenticated")

        assert self._client is not None

        # Find the download URL from the batch status
        download_url = self._find_download_url(result_id)
        if not download_url:
            raise RuntimeError(f"No download URL found for result {result_id}")

        try:
            resp = self._client.get(download_url, timeout=120.0)
            if resp.status_code != 200:
                raise RuntimeError(f"Download failed: HTTP {resp.status_code}")

            content_type = resp.headers.get("content-type", "")
            if "video" not in content_type and "octet-stream" not in content_type:
                # Maybe it's a JSON redirect or error
                if "application/json" in content_type:
                    try:
                        data = resp.json()
                        msg = data.get("message", data.get("error", ""))
                        raise RuntimeError(f"Download error: {msg}")
                    except (json.JSONDecodeError, ValueError):
                        pass

            ext = ".mp4"
            if "webm" in content_type:
                ext = ".webm"
            elif "gif" in content_type:
                ext = ".gif"

            filename = f"{result_id}{ext}"
            filepath = os.path.join(self.download_dir, filename)

            with open(filepath, "wb") as f:
                f.write(resp.content)

            self._completed_results[result_id] = filepath
            logger.info(
                "MetaVibes.download_result — saved %d bytes to %s",
                len(resp.content),
                filepath,
            )
            return resp.content

        except httpx.HTTPError as exc:
            raise RuntimeError(f"Download network error: {exc}")

    def _find_download_url(self, result_id: str) -> Optional[str]:
        """Find the download URL for a completed result."""
        assert self._client is not None
        try:
            # Try the batch detail endpoint
            resp = self._client.get(
                f"{self.base_url}{ENDPOINT_CREATE_BATCH.rstrip('/')}/{result_id}",
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                url = (
                    data.get("download_url")
                    or data.get("result_url")
                    or data.get("video_url")
                )
                if url:
                    return url
                # The batch data may contain a nested 'result' or 'output'
                result_data = (
                    data.get("result")
                    or data.get("output")
                    or data.get("video")
                )
                if isinstance(result_data, dict):
                    url = (
                        result_data.get("download_url")
                        or result_data.get("url")
                    )
                    if url:
                        return url
        except Exception:
            pass

        # Fallback: check project batches
        try:
            resp = self._client.get(
                f"{self.base_url}{ENDPOINT_PROJECT_BATCHES.format(project_id='me')}",
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                batches = data if isinstance(data, list) else data.get("batches", [])
                for batch in batches:
                    bid = batch.get("id") or batch.get("result_id")
                    if bid == result_id:
                        url = (
                            batch.get("download_url")
                            or batch.get("result_url")
                            or batch.get("video_url")
                        )
                        if url:
                            return url
        except Exception:
            pass

        return None

    # ------------------------------------------------------------------
    # Error detection (ABC)
    # ------------------------------------------------------------------

    def detect_error(
        self, result_id: str, raw_response: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Parse a raw response (HTTP body or SSE text) for error indicators."""
        if not raw_response:
            return None, None
        for pattern, code in ERROR_PATTERNS:
            m = pattern.search(raw_response)
            if m:
                return code, m.group(0)
        return None, None

    def detect_quota_exhaustion(self, raw_response: str) -> bool:
        """Return True if the raw response indicates quota/rate-limit exhaustion."""
        if not raw_response:
            return False
        for pattern, code in ERROR_PATTERNS:
            if code in ("QUOTA_EXHAUSTED", "RATE_LIMITED") and pattern.search(
                raw_response
            ):
                return True
        return False

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    def cancel_generation(self, result_id: str) -> bool:
        """Attempt to cancel an in-flight generation.

        Vibes.ai may offer a cancel endpoint. Best-effort: returns True if
        the cancel request was accepted, False otherwise.
        """
        if not self._client or not self._authenticated:
            return False
        try:
            resp = self._client.post(
                f"{self.base_url}{ENDPOINT_CREATE_BATCH.rstrip('/')}/{result_id}/cancel",
                timeout=10.0,
            )
            return resp.status_code in (200, 201, 204)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Cleanup (ABC)
    # ------------------------------------------------------------------

    def close_session(self) -> None:
        """Close the HTTP client and clear runtime state."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        self._cookies = []
        self._authenticated = False
        self._completed_results.clear()
        self._last_error_code = None
        self._last_error_message = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_authenticated(self) -> bool:
        """Check session; return True if valid, False otherwise."""
        if self._authenticated and self._client is not None:
            return True
        # Try to re-verify if we have cookies but session expired
        if self._cookies and not self._authenticated:
            return self.authenticate({})
        return False

    def _fail(
        self, code: str, message: str
    ) -> GenerationResult:
        """Build a failed GenerationResult and stash the error."""
        self._last_error_code = code
        self._last_error_message = message
        logger.error("MetaVibes: %s — %s", code, message)
        return GenerationResult(
            success=False,
            result_id=None,
            error_code=code,
            error_message=message,
            download_url=None,
            estimated_wait_seconds=None,
        )

    # ------------------------------------------------------------------
    # SSE progress streaming (optional helper for callers that want live
    # progress rather than polling get_generation_status)
    # ------------------------------------------------------------------

    def stream_progress(
        self,
        result_id: str,
        callback: Optional[Callable[[str], Any]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        """Connect to the SSE stream for a generation batch and yield progress.

        ``callback`` is called with each SSE data message (string). If
        ``callback`` returns False, the stream is stopped early.

        This is a blocking call — run it in a thread if you need non-blocking
        behaviour. It reconnects with exponential backoff on disconnect.
        """
        if not self._client or not self._authenticated:
            raise RuntimeError("Not authenticated")

        url = f"{self.base_url}{ENDPOINT_BATCH_STREAM.format(batch_id=result_id)}"
        backoff = self.sse_reconnect_base
        deadline = time.time() + (timeout or self.generation_timeout)

        while time.time() < deadline:
            try:
                logger.info("MetaVibes.stream_progress — connecting to %s", url)
                with self._client.stream("GET", url) as response:
                    if response.status_code != 200:
                        logger.warning(
                            "MetaVibes.stream_progress — got status %d",
                            response.status_code,
                        )
                        break

                    for line in response.iter_lines():
                        if line.startswith("data:"):
                            data = line[5:].strip()
                            if data and data != "[DONE]":
                                if callback:
                                    keep_going = callback(data)
                                    if keep_going is False:
                                        return
                                # Check if the generation completed
                                if '"status":"completed"' in data or '"state":"completed"' in data:
                                    logger.info("MetaVibes.stream_progress — generation completed")
                                    return
                                if '"status":"failed"' in data or '"state":"failed"' in data:
                                    logger.warning("MetaVibes.stream_progress — generation failed")
                                    return

                # Stream ended cleanly — generation may be done
                logger.info("MetaVibes.stream_progress — stream ended")
                return

            except httpx.HTTPError as exc:
                logger.warning("MetaVibes.stream_progress — SSE error: %s", exc)
            except Exception as exc:
                logger.warning(
                    "MetaVibes.stream_progress — unexpected error: %s", exc
                )

            # Exponential backoff before reconnect
            sleep_time = min(backoff, self.sse_reconnect_max)
            logger.info(
                "MetaVibes.stream_progress — reconnecting in %.1fs", sleep_time
            )
            time.sleep(sleep_time)
            backoff = min(backoff * 2, self.sse_reconnect_max)

        logger.warning(
            "MetaVibes.stream_progress — timed out after %.0fs",
            timeout or self.generation_timeout,
        )


# ---------------------------------------------------------------------------------------
# Multipart helper
# ---------------------------------------------------------------------------------------


def _build_multipart_form(
    prompt: str,
    aspect_ratio: str,
    resolution: str,
    variations: int,
    model: str,
    generation_type: str,
    batch_id: Optional[str],
    start_frame_path: Optional[str],
    end_frame_path: Optional[str],
) -> bytes:
    """Build a multipart/form-data body for i2v generation.

    Returns raw bytes ready to send as request content.
    """
    import uuid

    boundary = f"----MetaVibesForm{uuid.uuid4().hex}"
    lines: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        lines.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode(
                "utf-8"
            )
        )

    add_field("prompt", prompt)
    add_field("aspect_ratio", aspect_ratio)
    add_field("resolution", resolution)
    add_field("variations", str(variations))
    add_field("model", model)
    add_field("generation_type", generation_type)
    if batch_id:
        add_field("batch_id", batch_id)

    if start_frame_path and os.path.exists(start_frame_path):
        filename = os.path.basename(start_frame_path)
        with open(start_frame_path, "rb") as f:
            file_bytes = f.read()
        lines.append(
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"start_frame\"; filename=\"{filename}\"\r\n"
            f"Content-Type: image/png\r\n\r\n".encode("utf-8")
        )
        lines.append(file_bytes)
        lines.append(b"\r\n")

    if end_frame_path and os.path.exists(end_frame_path):
        filename = os.path.basename(end_frame_path)
        with open(end_frame_path, "rb") as f:
            file_bytes = f.read()
        lines.append(
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"end_frame\"; filename=\"{filename}\"\r\n"
            f"Content-Type: image/png\r\n\r\n".encode("utf-8")
        )
        lines.append(file_bytes)
        lines.append(b"\r\n")

    lines.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(lines)
