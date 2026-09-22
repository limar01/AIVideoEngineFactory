"""SnapGen AI video generation provider (browser automation).

Source: docs/SNAPGEN_RECON.md (full recon report)
        docs/PROVIDER_INTERFACE.md §3 (SnapGen adapter)
        Master Spec §18 (provider abstraction)

All browser automation via Playwright. Authentication is Google OAuth only —
the agent never attempts to bypass CAPTCHA/2FA. If CAPTCHA appears, the
provider returns BLOCKED and escalates to the user.

Quota behaviour: Veo 3.1 Fast is free (0 credits per generation) with no
explicit daily cap. Implicit rate limits are detected via CAPTCHA/rate-limit
signals and mapped to configurable conservation mode.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Browser, BrowserContext

from app.providers.base import (
    VideoGenerationProvider,
    GenerationStatus,
    GenerationCapabilities,
    QuotaInfo,
    GenerationResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (from SNAPGEN_RECON.md §4, §6)
# ---------------------------------------------------------------------------

BASE_URL = "https://snapgen.ai"
APP_URL = "https://snapgen.ai/app/video-gen"
HISTORY_URL = "https://snapgen.ai/app/history"
LOGIN_URL = "https://snapgen.ai/app"

# UI element selectors (from SNAPGEN_RECON.md §4)
TEXTAREA_SELECTOR = 'textarea[placeholder*="Describe"]'
MODEL_BUTTON_TEXT = "Veo 3.1 Fast"
DURATION_BUTTON_TEXT = "8s"
ASPECT_RATIO_BUTTON_TEXT = "16:9"
RESOLUTION_BUTTON_TEXT = "720p"
GENERATE_BUTTON_SELECTOR = 'button:has-text("Generate")'
HISTORY_TABLE_SELECTOR = 'table'

# Error detection patterns (from SNAPGEN_RECON.md §5)
CAPTCHA_PATTERNS = [
    re.compile(r"human\s+verification", re.I),
    re.compile(r"verify\s+you\s+are\s+human", re.I),
    re.compile(r"\bcaptcha\b", re.I),
    re.compile(r"select\s+all\s+images", re.I),
    re.compile(r"click\s+the\s+objects", re.I),
]
RATE_LIMIT_PATTERNS = [
    re.compile(r"rate\s+limit", re.I),
    re.compile(r"too\s+many\s+requests", re.I),
    re.compile(r"please\s+wait", re.I),
    re.compile(r"try\s+again\s+later", re.I),
    re.compile(r"\b429\b", re.I),
]
ERROR_PATTERNS = [
    re.compile(r"generation\s+failed", re.I),
    re.compile(r"try\s+again", re.I),
    re.compile(r"session\s+expired", re.I),
    re.compile(r"sign\s+in", re.I),
    re.compile(r"under\s+maintenance", re.I),
]

# ---------------------------------------------------------------------------
# SnapGenProvider
# ---------------------------------------------------------------------------


class SnapGenProvider(VideoGenerationProvider):
    """Playwright-based SnapGen AI provider.

    Lifecycle:
    1. ``__init__`` — stores config, does NOT launch browser.
    2. ``authenticate`` — launches browser, navigates to APP_URL, checks if
       already logged in. Returns True if session is valid, False otherwise.
       Does NOT attempt interactive login.
    3. ``submit_generation`` — fills the prompt form, clicks Generate,
       captures result ID.
    4. ``get_generation_status`` — polls the generation status page.
    5. ``download_result`` — downloads the MP4 from the history/download page.
    6. ``close_session`` — closes browser.

    All methods that encounter CAPTCHA / rate-limit signals return failure
    results with appropriate error codes rather than retrying blindly.
    """

    PROVIDER_NAME = "snapgen"

    def __init__(
        self,
        base_url: str = BASE_URL,
        session_timeout_minutes: int = 30,
        generation_timeout_minutes: int = 15,
        polling_interval_seconds: int = 10,
        headless: bool = True,
        user_data_dir: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.app_url = f"{self.base_url}/app/video-gen"
        self.history_url = f"{self.base_url}/app/history"
        self.login_url = f"{self.base_url}/app"
        self.session_timeout = session_timeout_minutes * 60
        self.generation_timeout = generation_timeout_minutes * 60
        self.polling_interval = polling_interval_seconds
        self.headless = headless
        self.user_data_dir = user_data_dir or os.path.expanduser("~/.snapgen-browser-profile")

        # Runtime state
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._authenticated = False
        self._session_start: float | None = None

        # Logging
        self._last_page_text = ""
        self._last_error_code: str | None = None
        self._last_error_message: str | None = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self, account_credentials: dict) -> bool:
        """Launch browser and verify session.

        ``account_credentials`` may contain an encrypted session token or
        cookie store path. If a valid session exists in ``user_data_dir``,
        returns True immediately. Otherwise navigates to APP_URL and checks
        for login indicators.

        Does NOT attempt Google OAuth login — that requires user interaction.
        Returns False if re-authentication is needed.
        """
        logger.info("SnapGenProvider.authenticate — launching browser (headless=%s)", self.headless)
        try:
            self._launch_browser()
        except Exception as exc:
            logger.error("SnapGenProvider.authenticate — browser launch failed: %s", exc)
            self._last_error_code = "BROWSER_LAUNCH_FAILED"
            self._last_error_message = str(exc)
            return False

        if self._page is None:
            logger.error("SnapGenProvider.authenticate — no page available after launch")
            self._last_error_code = "BROWSER_LAUNCH_FAILED"
            self._last_error_message = "Browser launched but no page was created"
            return False

        try:
            self._page.goto(self.app_url, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_load_state("networkidle", timeout=15000)
            self._capture_page_text()

            if self._is_logged_in():
                logger.info("SnapGenProvider.authenticate — session valid")
                self._authenticated = True
                self._session_start = time.time()
                return True

            logger.warning(
                "SnapGenProvider.authenticate — not logged in. "
                "User must manually log in via Google OAuth in the browser."
            )
            self._last_error_code = "NOT_AUTHENTICATED"
            self._last_error_message = (
                "SnapGen requires Google OAuth login. "
                "Please log in manually at https://snapgen.ai/app then retry."
            )
            return False

        except Exception as exc:
            logger.error("SnapGenProvider.authenticate — navigation failed: %s", exc)
            self._last_error_code = "AUTH_NAVIGATION_FAILED"
            self._last_error_message = str(exc)
            return False

    def check_session(self) -> bool:
        """Check whether the current session is still valid."""
        if not self._page or not self._authenticated:
            return False
        try:
            self._page.goto(self.app_url, wait_until="domcontentloaded", timeout=15000)
            self._page.wait_for_load_state("networkidle", timeout=10000)
            self._capture_page_text()
            if self._detect_capcha_or_rate_limit():
                logger.warning("SnapGenProvider.check_session — CAPTCHA/rate-limit detected")
                return False
            return self._is_logged_in()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Capabilities & Quota
    # ------------------------------------------------------------------

    def get_capabilities(self) -> GenerationCapabilities:
        """Return SnapGen's known capabilities (from recon)."""
        return GenerationCapabilities(
            max_prompt_length=3000,
            supported_aspect_ratios=["16:9", "9:16", "4:3"],
            supported_resolutions=["720p"],
            max_duration_seconds=8.0,  # Free tier Veo 3.1 Fast is fixed at 8s
            min_duration_seconds=8.0,
            supports_narration=True,
        )

    def get_quota(self) -> QuotaInfo:
        """Check quota. Free Veo 3.1 Fast has 0 credits per generation, no explicit cap.

        Since there is no credit counter in the UI for the free tier, we return
        a QuotaInfo with no limit. The actual conservation is handled by the
        QuotaManager (app/queue/) which uses configurable fallback limits.
        """
        return QuotaInfo(
            limit=None,       # No explicit limit displayed for free tier
            used=None,
            remaining=None,
            reset_time=None,
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def submit_generation(self, prompt: str, scene_metadata: dict) -> GenerationResult:
        """Fill the SnapGen prompt form and submit a generation.

        Steps (from SNAPGEN_RECON.md §5):
        1. Navigate to APP_URL.
        2. Verify logged in.
        3. Select Veo 3.1 Fast model.
        4. Set duration to 8s.
        5. Set aspect ratio per scene_metadata (default 16:9).
        6. Fill textarea with prompt.
        7. Click Generate.
        8. Capture result ID from URL or history.
        """
        if not self._ensure_authenticated():
            return self._failed_result("NOT_AUTHENTICATED", "Session expired — re-authenticate first")

        aspect_ratio = scene_metadata.get("aspect_ratio", "16:9")
        duration = scene_metadata.get("duration_seconds", 8.0)

        logger.info(
            "SnapGenProvider.submit_generation — prompt_len=%d, aspect=%s, duration=%.1fs",
            len(prompt),
            aspect_ratio,
            duration,
        )

        try:
            self._page.goto(self.app_url, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_load_state("networkidle", timeout=15000)
            self._capture_page_text()

            if self._detect_capcha_or_rate_limit():
                return self._failed_result(
                    "CAPTCHA_DETECTED",
                    "Human verification / rate limit triggered. Please solve CAPTCHA manually and retry.",
                )

            # Select model
            if not self._select_model(MODEL_BUTTON_TEXT):
                return self._failed_result("MODEL_SELECTION_FAILED", f"Could not select model '{MODEL_BUTTON_TEXT}'")

            # Set duration
            if not self._click_button_with_text(DURATION_BUTTON_TEXT):
                return self._failed_result("DURATION_SELECTION_FAILED", f"Could not set duration to {duration}s")

            # Set aspect ratio
            if not self._click_button_with_text(aspect_ratio):
                return self._failed_result(
                    "ASPECT_RATIO_SELECTION_FAILED",
                    f"Could not set aspect ratio to {aspect_ratio}",
                )

            # Fill prompt
            if not self._fill_prompt(prompt):
                return self._failed_result("PROMPT_FILL_FAILED", "Could not fill the prompt textarea")

            # Click generate
            if not self._click_generate():
                return self._failed_result("GENERATE_CLICK_FAILED", "Could not click the Generate button")

            # Wait for result ID to appear (URL change or history entry)
            result_id = self._wait_for_result_id()
            if result_id:
                logger.info("SnapGenProvider.submit_generation — result_id=%s", result_id)
                return GenerationResult(
                    success=True,
                    result_id=result_id,
                    error_code=None,
                    error_message=None,
                    download_url=None,  # Will be populated on download
                    estimated_wait_seconds=self.polling_interval * 6,  # Rough estimate
                )

            # No result ID captured — check if page shows error
            self._capture_page_text()
            if self._detect_capcha_or_rate_limit():
                return self._failed_result(
                    "CAPTCHA_DETECTED",
                    "Human verification appeared after generation submission.",
                )

            return self._failed_result(
                "NO_RESULT_ID",
                "Generation submitted but could not capture a result ID. Check the SnapGen history page manually.",
            )

        except Exception as exc:
            logger.error("SnapGenProvider.submit_generation — unexpected error: %s", exc)
            return self._failed_result("SUBMIT_EXCEPTION", str(exc))

    def get_generation_status(self, result_id: str) -> GenerationStatus:
        """Poll the generation status page for the given result ID."""
        if not self._ensure_authenticated():
            logger.warning("SnapGenProvider.get_generation_status — not authenticated, returning UNKNOWN")
            return GenerationStatus.UNKNOWN

        try:
            self._page.goto(self.history_url, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_load_state("networkidle", timeout=15000)
            self._capture_page_text()

            if self._detect_capcha_or_rate_limit():
                logger.warning("SnapGenProvider.get_generation_status — CAPTCHA/rate-limit on status page")
                return GenerationStatus.UNKNOWN  # Can't determine status

            # Look for the result in the history table
            status_text = self._find_generation_status_in_history(result_id)
            if status_text:
                return self._status_from_text(status_text)

            # Not found in history — might still be generating
            # Check the generation page directly
            gen_url = f"{self.base_url}/app/video-gen/{result_id}"
            try:
                self._page.goto(gen_url, wait_until="domcontentloaded", timeout=15000)
                self._capture_page_text()
                if self._detect_capcha_or_rate_limit():
                    return GenerationStatus.UNKNOWN
                status_text = self._extract_status_from_page()
                if status_text:
                    return self._status_from_text(status_text)
            except Exception:
                pass

            return GenerationStatus.UNKNOWN

        except Exception as exc:
            logger.error("SnapGenProvider.get_generation_status — error: %s", exc)
            return GenerationStatus.UNKNOWN

    def download_result(self, result_id: str) -> bytes:
        """Download the completed MP4 from SnapGen.

        Navigates to the history page, finds the result thumbnail, clicks
        the download button, and captures the downloaded file.
        """
        if not self._ensure_authenticated():
            raise RuntimeError("Not authenticated — cannot download")

        download_dir = Path(os.path.expanduser("~/.snapgen-downloads"))
        download_dir.mkdir(parents=True, exist_ok=True)

        # Set up download handler
        context = self._context
        if context is None:
            raise RuntimeError("Browser context not available")
        context.set_default_download_dir(str(download_dir))

        try:
            self._page.goto(self.history_url, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_load_state("networkidle", timeout=15000)
            self._capture_page_text()

            if self._detect_capcha_or_rate_limit():
                raise RuntimeError("CAPTCHA/rate-limit detected on download page")

            # Find and click the download button for this result
            if not self._click_download_for_result(result_id):
                raise RuntimeError(
                    f"Could not find download button for result_id={result_id}. "
                    "Check history page manually."
                )

            # Wait for download to complete
            downloads = self._context.downloads() if self._context else []
            download = downloads[0] if downloads else None
            if download:
                download.save_as(str(download_dir / f"{result_id}.mp4"))
                download_path = download_dir / f"{result_id}.mp4"
                if download_path.exists():
                    return download_path.read_bytes()

            raise RuntimeError("Download did not complete in expected time")

        except Exception as exc:
            logger.error("SnapGenProvider.download_result — error: %s", exc)
            raise

    def detect_error(self, result_id: str, raw_response: str) -> tuple[str | None, str | None]:
        """Parse a raw page response for error indicators.

        Returns (error_code, error_message) or (None, None).
        """
        if not raw_response:
            return None, None

        for pattern in CAPTCHA_PATTERNS:
            if pattern.search(raw_response):
                return "CAPTCHA_DETECTED", "Human verification required — solve CAPTCHA manually"

        for pattern in RATE_LIMIT_PATTERNS:
            if pattern.search(raw_response):
                return "RATE_LIMIT", "Rate limit detected — please wait and retry"

        for pattern in ERROR_PATTERNS:
            if pattern.search(raw_response):
                return "GENERATION_ERROR", f"Generation issue detected: {raw_response[:200]}"

        return None, None

    def detect_quota_exhaustion(self, raw_response: str) -> bool:
        """Determine if the raw response indicates quota/rate-limit exhaustion.

        For the free Veo 3.1 Fast tier, the primary signal is CAPTCHA appearing
        after multiple generations (implicit rate limit).
        """
        if not raw_response:
            return False

        for pattern in CAPTCHA_PATTERNS:
            if pattern.search(raw_response):
                return True

        for pattern in RATE_LIMIT_PATTERNS:
            if pattern.search(raw_response):
                return True

        return False

    def close_session(self) -> None:
        """Close the browser and clean up."""
        logger.info("SnapGenProvider.close_session — closing browser")
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
        except Exception as exc:
            logger.warning("SnapGenProvider.close_session — cleanup error: %s", exc)
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            self._authenticated = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _launch_browser(self) -> None:
        """Launch Playwright browser and create context/page.

        Must be called within a ``sync_playwright()`` context manager that the
        caller provides. The real launch uses:

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless, ...)
                context = browser.new_context(user_data_dir=self.user_data_dir, ...)
                page = context.new_page()

        ``self._browser``, ``self._context``, and ``self._page`` are set by the
        caller after launch. This method is a no-op here — the real launch is
        done by the orchestrator that owns the Playwright lifecycle.
        """
        logger.info(
            "SnapGenProvider._launch_browser — called (external lifecycle expected)"
        )

    def _ensure_authenticated(self) -> bool:
        """Re-authenticate if session expired or not yet authenticated."""
        if self._authenticated and self._session_start:
            elapsed = time.time() - self._session_start
            if elapsed < self.session_timeout:
                if self._page and self.check_session():
                    return True
        # Need to re-authenticate
        if self._page:
            try:
                self._page.goto(self.app_url, wait_until="domcontentloaded", timeout=15000)
                self._capture_page_text()
                if self._is_logged_in() and not self._detect_capcha_or_rate_limit():
                    self._authenticated = True
                    self._session_start = time.time()
                    return True
            except Exception:
                pass
        return False

    def _capture_page_text(self) -> None:
        """Store the current page's visible text for error detection."""
        try:
            if self._page:
                self._last_page_text = self._page.inner_text("body") or ""
        except Exception:
            self._last_page_text = ""

    def _is_logged_in(self) -> bool:
        """Check if the user is logged in by looking for post-login indicators."""
        if not self._page:
            return False
        # After login, the header shows user avatar/name instead of "Login"/"Sign Up"
        # Check for absence of login buttons and presence of user indicators
        try:
            content = self._page.content()
            if "Login" in content and "Sign Up" in content:
                # Both login buttons present — likely not logged in
                # But also check if they're in a logged-in state (unlikely)
                pass
            # Look for user-specific elements
            user_indicators = [
                '[class*="user-avatar"]',
                '[class*="user-name"]',
                '[class*="profile"]',
                'text=user',  # generic
            ]
            for sel in user_indicators:
                try:
                    if self._page.locator(sel).count() > 0:
                        return True
                except Exception:
                    pass
            # Fallback: if "Login" button is absent, likely logged in
            login_button = self._page.locator('button:has-text("Login")')
            if login_button.count() == 0:
                return True
            return False
        except Exception:
            return False

    def _detect_capcha_or_rate_limit(self) -> bool:
        """Check the last captured page text for CAPTCHA or rate-limit signals."""
        text = self._last_page_text
        for pattern in CAPTCHA_PATTERNS:
            if pattern.search(text):
                logger.warning("CAPTCHA detected in page text")
                return True
        for pattern in RATE_LIMIT_PATTERNS:
            if pattern.search(text):
                logger.warning("Rate limit detected in page text")
                return True
        return False

    def _select_model(self, model_text: str) -> bool:
        """Click the model selection button."""
        try:
            locator = self._page.locator(f'button:has-text("{model_text}")')
            if locator.count() == 0:
                # Try broader search
                locator = self._page.locator(f'text={model_text}')
            if locator.count() > 0:
                locator.first.click(timeout=10000)
                return True
            return False
        except Exception as exc:
            logger.error("SnapGenProvider._select_model — error: %s", exc)
            return False

    def _click_button_with_text(self, text: str) -> bool:
        """Click a button that contains the given text."""
        try:
            locator = self._page.locator(f'button:has-text("{text}")')
            if locator.count() > 0:
                locator.first.click(timeout=10000)
                time.sleep(0.5)
                return True
            return False
        except Exception as exc:
            logger.error("SnapGenProvider._click_button_with_text(%s) — error: %s", text, exc)
            return False

    def _fill_prompt(self, prompt: str) -> bool:
        """Fill the prompt textarea with the given text."""
        try:
            textarea = self._page.locator(TEXTAREA_SELECTOR)
            if textarea.count() == 0:
                # Fallback: find any textarea
                textarea = self._page.locator("textarea").first
            if textarea.count() > 0:
                textarea.fill(prompt, timeout=10000)
                return True
            logger.error("SnapGenProvider._fill_prompt — no textarea found")
            return False
        except Exception as exc:
            logger.error("SnapGenProvider._fill_prompt — error: %s", exc)
            return False

    def _click_generate(self) -> bool:
        """Click the Generate button."""
        try:
            locator = self._page.locator(GENERATE_BUTTON_SELECTOR)
            if locator.count() > 0:
                locator.first.click(timeout=15000)
                # Wait for navigation/loading
                self._page.wait_for_load_state("networkidle", timeout=30000)
                return True
            logger.error("SnapGenProvider._click_generate — generate button not found")
            return False
        except Exception as exc:
            logger.error("SnapGenProvider._click_generate — error: %s", exc)
            return False

    def _wait_for_result_id(self) -> str | None:
        """Wait for a result ID to appear after generation submission.

        Checks:
        1. URL change (result ID in URL).
        2. History page entry.
        Returns the result ID string or None.
        """
        try:
            # Wait for URL to potentially change
            start = time.time()
            while time.time() - start < 30:
                current_url = self._page.url
                # Look for result ID patterns in URL
                match = re.search(r"/app/video-gen/([a-f0-9-]+)", current_url)
                if match:
                    return match.group(1)
                # Check history page URL
                match = re.search(r"/app/history/([a-f0-9-]+)", current_url)
                if match:
                    return match.group(1)
                time.sleep(2)

            # Poll history page for the result
            self._page.goto(self.history_url, wait_until="domcontentloaded", timeout=15000)
            self._capture_page_text()
            match = re.search(r"generation-??id[=:]\s*([a-f0-9-]+)", self._last_page_text, re.I)
            if match:
                return match.group(1)

            # Try to find any ID-like string in the page
            matches = re.findall(r"\b([a-f0-9]{8,})\b", self._last_page_text)
            if matches:
                return matches[0]

            return None

        except Exception as exc:
            logger.error("SnapGenProvider._wait_for_result_id — error: %s", exc)
            return None

    def _find_generation_status_in_history(self, result_id: str) -> str | None:
        """Search the history table for the given result ID and return status text."""
        try:
            # Search for result_id in the page text
            if result_id in self._last_page_text:
                # Find nearby status indicators
                idx = self._last_page_text.index(result_id)
                context = self._last_page_text[max(0, idx - 200): idx + 200]
                for status in ["Completed", "Processing", "Generating", "Failed"]:
                    if status.lower() in context.lower():
                        return status
            return None
        except Exception:
            return None

    def _extract_status_from_page(self) -> str | None:
        """Extract status from the current page text."""
        text = self._last_page_text
        for status in ["Completed", "Processing", "Generating", "Failed"]:
            if status.lower() in text.lower():
                return status
        return None

    def _status_from_text(self, text: str) -> GenerationStatus:
        """Convert a status text string to GenerationStatus enum."""
        text_lower = text.lower()
        if "completed" in text_lower:
            return GenerationStatus.COMPLETED
        if "processing" in text_lower or "generating" in text_lower:
            return GenerationStatus.GENERATING
        if "failed" in text_lower or "something went wrong" in text_lower:
            return GenerationStatus.FAILED
        return GenerationStatus.UNKNOWN

    def _click_download_for_result(self, result_id: str) -> bool:
        """Find the result in history and click its download button."""
        try:
            # Look for download buttons near the result ID
            # Pattern: find element containing result_id, then find download button nearby
            content = self._page.content()
            if result_id not in content:
                logger.warning("Result ID %s not found in history page", result_id)
                return False

            # Try clicking any download button
            download_button = self._page.locator('button:has-text("Download")')
            if download_button.count() > 0:
                download_button.first.click(timeout=15000)
                return True

            # Try clicking a download icon
            download_icon = self._page.locator('[class*="download"]')
            if download_icon.count() > 0:
                download_icon.first.click(timeout=15000)
                return True

            return False
        except Exception as exc:
            logger.error("SnapGenProvider._click_download_for_result — error: %s", exc)
            return False

    def _failed_result(self, error_code: str, error_message: str) -> GenerationResult:
        """Build a failed GenerationResult and store error info."""
        self._last_error_code = error_code
        self._last_error_message = error_message
        logger.warning("SnapGenProvider — failed: %s: %s", error_code, error_message)
        return GenerationResult(
            success=False,
            result_id=None,
            error_code=error_code,
            error_message=error_message,
            download_url=None,
            estimated_wait_seconds=None,
        )
