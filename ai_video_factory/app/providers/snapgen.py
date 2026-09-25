"""SnapGen AI video generation provider (browser automation).

Source: docs/SNAPGEN_RECON.md (full recon report)
        docs/PROVIDER_INTERFACE.md §3 (SnapGen adapter)
        Master Spec §18 (provider abstraction)
        Live probe 2026-09-23: https://snapgen.ai/app/video-gen

All browser automation via Playwright. Authentication is Google OAuth only —
the agent never attempts to bypass CAPTCHA/2FA. If CAPTCHA appears, the
provider returns BLOCKED and escalates to the user.

Live probe findings (2026-09-23):
  - Site defaults to Grok model; Veo is a provider option
  - Click "Veo Google AI" button to switch to Veo provider
  - After Veo selection, Veo sub-models appear (Veo 3.1, Veo 3, Veo 2, etc.)
  - Duration options: 6s, 10s, 15s
  - Aspect ratio options: 16:9, 9:16, 1:1, 2:3, 3:2
  - Resolution options: 480p, 720p, 1080p
  - Audio toggle: "Audio On" (visible on site)
  - Credits remaining shown on page (user reports having credits)
  - NOT logged in when accessed fresh (localStorage user=null)
  - Veo model generates audio natively from prompt text (per Google Veo 3.1 docs)
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
# Constants (from live probe 2026-09-23)
# ---------------------------------------------------------------------------

BASE_URL = "https://snapgen.ai"
APP_URL = "https://snapgen.ai/app/video-gen"
HISTORY_URL = "https://snapgen.ai/app/history"
LOGIN_URL = "https://snapgen.ai/app"

# UI element selectors
TEXTAREA_SELECTOR = 'textarea[placeholder*="Describe"]'
MODEL_BUTTON_TEXT = "Veo"  # "Veo Google AI" — the provider selector button
GENERATE_BUTTON_SELECTOR = 'button:has-text("Generate Video")'
HISTORY_TABLE_SELECTOR = 'table'

# Duration options (live probe 2026-09-24: 4s/6s/8s as <label> elements)
DURATION_OPTIONS = ["4s", "6s", "8s"]

# Aspect ratio options (live probe: 16:9, 9:16, 1:1, 2:3, 3:2)
ASPECT_RATIO_OPTIONS = ["16:9", "9:16", "1:1", "2:3", "3:2"]

# Resolution options (live probe: 480p, 720p, 1080p)
RESOLUTION_OPTIONS = ["480p", "720p", "1080p"]

# Audio toggle (live probe: "Audio On" visible on site)
AUDIO_TOGGLE_TEXT = "Audio On"

# Maintenance / outage patterns (live probe 2026-09-24)
MAINTENANCE_PATTERNS = [
    re.compile(r"under\s+maintenance", re.I),
    re.compile(r"model\s+maintenance", re.I),
    re.compile(r"try\s+other\s+models", re.I),
]

# Error detection patterns
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

    scene_metadata keys (all optional):
      - aspect_ratio: "16:9" or "9:16"  (default: "9:16")
      - resolution: "720p" or "1080p"    (default: "1080p")
      - duration_seconds: 6, 10, or 15   (default: 6)
      - audio_on: True/False             (default: True)
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
        return GenerationCapabilities(
            max_prompt_length=5000,
            supported_aspect_ratios=["16:9", "9:16", "1:1", "2:3", "3:2"],
            supported_resolutions=["480p", "720p", "1080p"],
            max_duration_seconds=15.0,
            min_duration_seconds=6.0,
            supports_narration=True,
        )

    def get_quota(self) -> QuotaInfo:
        """SnapGen: credits-based. User sees 'Credits remaining' on page."""
        return QuotaInfo(
            limit=None,
            used=None,
            remaining=None,
            reset_time=None,
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def submit_generation(self, prompt: str, scene_metadata: dict) -> GenerationResult:
        """Fill the SnapGen prompt form and submit a generation.

        Uses scene_metadata for all settings:
          - aspect_ratio: "9:16" for FB Reels (default: "9:16")
          - resolution: "1080p" for full HD (default: "1080p")
          - duration_seconds: 6, 10, or 15 (default: 6)
          - audio_on: True/False (default: True)
        """
        if not self._ensure_authenticated():
            return self._failed_result("NOT_AUTHENTICATED", "Session expired — re-authenticate first")

        aspect_ratio = scene_metadata.get("aspect_ratio", "9:16")
        resolution = scene_metadata.get("resolution", "1080p")
        duration = scene_metadata.get("duration_seconds", 6.0)
        audio_on = scene_metadata.get("audio_on", True)

        # Validate against known options
        if str(aspect_ratio) not in ASPECT_RATIO_OPTIONS:
            aspect_ratio = "9:16"
        if str(resolution) not in RESOLUTION_OPTIONS:
            resolution = "1080p"
        # Duration may arrive as number (10) or string ("10s") — normalize
        duration_text = str(duration).strip().lower()
        if not duration_text.endswith("s"):
            duration_text = f"{int(float(duration_text))}s"
        if duration_text not in DURATION_OPTIONS:
            duration_text = "6s"

        logger.info(
            "SnapGenProvider.submit_generation — prompt_len=%d, aspect=%s, "
            "resolution=%s, duration=%ss, audio=%s",
            len(prompt), aspect_ratio, resolution, duration_text, audio_on,
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

            # Dismiss any modal overlay (special-offer popup, cookie/policy
            # dialog) that would intercept pointer events.
            self._dismiss_overlays()

            # 1. Select the Veo provider tab
            try:
                veo_tab = self._page.locator('button[data-provider="veo"]')
                if veo_tab.count() == 0:
                    veo_tab = self._page.locator('button:has-text("Veo")')
                veo_tab.first.click()
                self._page.wait_for_timeout(2000)
            except Exception as exc:
                return self._failed_result(
                    "MODEL_SELECTION_FAILED", f"Could not click the Veo provider tab: {exc}"
                )

            # 2. Open the Model dropdown (near the "Model" label) and pick
            #    the preferred Veo variant. Preference order (live status
            #    2026-09-24): Lite (61% success) > Fast (21%) > others.
            selected_variant = self._select_veo_variant_from_dropdown(
                ["Veo 3.1 Lite", "Veo 3.1 Fast", "Veo 3.1", "Veo 2"]
            )
            if selected_variant is None:
                return self._failed_result(
                    "MODEL_SELECTION_FAILED",
                    "Could not select a Veo variant from the Model dropdown.",
                )
            logger.info("SnapGenProvider.submit_generation — model: %s", selected_variant)

            # Open the Advanced tab — duration/aspect/resolution live there
            # (Basic tab only has the prompt).
            try:
                adv = self._page.locator('button:has-text("Advanced")')
                if adv.count() > 0 and adv.first.is_visible():
                    adv.first.click()
                    self._page.wait_for_timeout(1000)
                    logger.info("SnapGenProvider.submit_generation — opened Advanced tab")
            except Exception:
                pass

            # Set duration — durations are <label> elements on the live site
            if not self._click_option_with_text(duration_text):
                return self._failed_result(
                    "DURATION_SELECTION_FAILED",
                    f"Could not set duration to {duration_text}",
                )

            # Set aspect ratio (9:16 for FB Reels)
            if not self._click_option_with_text(aspect_ratio):
                return self._failed_result(
                    "ASPECT_RATIO_SELECTION_FAILED",
                    f"Could not set aspect ratio to {aspect_ratio}",
                )

            # Set resolution
            if not self._click_option_with_text(resolution):
                return self._failed_result(
                    "RESOLUTION_SELECTION_FAILED",
                    f"Could not set resolution to {resolution}",
                )

            # Audio toggle — ensure it's ON (best effort; site may not show it)
            if audio_on:
                self._click_button_with_text(AUDIO_TOGGLE_TEXT)

            # Return to the Basic tab — the prompt textarea lives there
            try:
                basic = self._page.locator('button:has-text("Basic")')
                if basic.count() > 0 and basic.first.is_visible():
                    basic.first.click()
                    self._page.wait_for_timeout(1000)
                    logger.info("SnapGenProvider.submit_generation — back on Basic tab")
            except Exception:
                pass

            # Fill prompt
            if not self._fill_prompt(prompt):
                return self._failed_result("PROMPT_FILL_FAILED", "Could not fill the prompt textarea")

            # Click generate
            if not self._click_generate():
                return self._failed_result("GENERATE_CLICK_FAILED", "Could not click the Generate button")

            # Check for the maintenance dialog that appears after Generate
            self._page.wait_for_timeout(3000)
            try:
                body_text = self._page.inner_text("body")
            except Exception:
                body_text = ""
            for pattern in MAINTENANCE_PATTERNS:
                if pattern.search(body_text):
                    # Dismiss the dialog for the next attempt
                    try:
                        understood = self._page.locator('button:has-text("Understood")')
                        if understood.count() > 0:
                            understood.first.click()
                    except Exception:
                        pass
                    return self._failed_result(
                        "MODEL_MAINTENANCE",
                        "Veo model is under maintenance on SnapGen. "
                        "Check https://snapgen.ai/status and retry later.",
                    )

            # Wait for result ID
            result_id = self._wait_for_result_id()
            if result_id:
                logger.info("SnapGenProvider.submit_generation — result_id=%s", result_id)
                return GenerationResult(
                    success=True,
                    result_id=result_id,
                    error_code=None,
                    error_message=None,
                    download_url=None,
                    estimated_wait_seconds=self.polling_interval * 6,
                )

            # Check for error
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
                return GenerationStatus.FAILED

            # Check for completed status
            if "completed" in self._last_page_text.lower() or "download" in self._last_page_text.lower():
                return GenerationStatus.COMPLETED

            if "generating" in self._last_page_text.lower() or "processing" in self._last_page_text.lower():
                return GenerationStatus.GENERATING

            return GenerationStatus.UNKNOWN

        except Exception as exc:
            logger.error("SnapGenProvider.get_generation_status — error: %s", exc)
            return GenerationStatus.UNKNOWN

    def download_result(self, result_id: str) -> bytes:
        """Download a completed generation result (raw bytes)."""
        if not self._ensure_authenticated():
            raise RuntimeError("Not authenticated")

        try:
            self._page.goto(self.history_url, wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_load_state("networkidle", timeout=15000)

            # Click download button for this result
            download_btn = self._page.locator(
                f'button:has-text("Download"):has-ancestor(\'tr\'):has-text("{result_id[:8]}")'
            )
            if download_btn.count() == 0:
                # Try alternate selector
                download_btn = self._page.locator(
                    f'a:has-text("{result_id[:8]}") ~ button'
                )
            if download_btn.count() > 0:
                download_btn.first.click()

                # Wait for download
                download_dir = Path(self.user_data_dir) / "downloads"
                download_dir.mkdir(parents=True, exist_ok=True)
                with self._page.expect_download(timeout=30000) as download_info:
                    # Trigger download again if needed
                    pass

                download = download_info.value
                download_path = download_dir / f"{result_id}.mp4"
                download.save_as(download_path)
                return download_path.read_bytes()

            raise RuntimeError(f"Download button not found for result {result_id[:8]}")

        except Exception as exc:
            logger.error("SnapGenProvider.download_result — error: %s", exc)
            raise

    def detect_error(self, result_id: str, raw_response: str) -> tuple[str | None, str | None]:
        """Parse a raw page response for error indicators."""
        if not raw_response:
            return None, None

        for pattern in ERROR_PATTERNS:
            if pattern.search(raw_response):
                return "GENERATION_ERROR", f"Generation issue detected: {raw_response[:200]}"

        for pattern in RATE_LIMIT_PATTERNS:
            if pattern.search(raw_response):
                return "RATE_LIMIT", "Rate limit detected — please wait and retry"

        for pattern in CAPTCHA_PATTERNS:
            if pattern.search(raw_response):
                return "CAPTCHA_DETECTED", "Human verification required — solve CAPTCHA manually"

        return None, None

    def detect_quota_exhaustion(self, raw_response: str) -> bool:
        """Determine if the raw response indicates quota/rate-limit exhaustion."""
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
        """Cleanly close the provider session."""
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if getattr(self, "_playwright", None) is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._browser = None
        self._page = None
        self._authenticated = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_authenticated(self) -> bool:
        """Check session; re-authenticate if needed."""
        if self._authenticated and self._session_start is not None:
            elapsed = time.time() - self._session_start
            if elapsed < self.session_timeout:
                return True
        return self.authenticate({})

    def _launch_browser(self) -> None:
        """Launch browser with the persistent profile (cookies/session)."""
        from playwright.sync_api import sync_playwright

        if self._context is not None:
            return  # already launched

        self._playwright = sync_playwright().start()
        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                viewport={"width": 1280, "height": 960},
                ignore_https_errors=True,
                locale="en-US",
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = self._context.new_page()
        except Exception:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
            raise

    def _is_logged_in(self) -> bool:
        """Check if current page shows logged-in state."""
        login_visible = self._page.locator('text="Login"').count() > 0
        signup_visible = self._page.locator('text="Sign Up"').count() > 0
        return not (login_visible and signup_visible)

    def _detect_capcha_or_rate_limit(self) -> bool:
        """Check page text for CAPTCHA or rate-limit patterns."""
        text = self._last_page_text.lower()
        for pattern in CAPTCHA_PATTERNS:
            if pattern.search(text):
                return True
        for pattern in RATE_LIMIT_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def _capture_page_text(self) -> None:
        """Snapshot current page text."""
        try:
            self._last_page_text = self._page.content()
        except Exception:
            self._last_page_text = ""

    def _dismiss_overlays(self) -> None:
        """Dismiss modal overlays that intercept pointer events.

        Tries, in order: Escape key, close (×) buttons, "Accept"/"Got it"/
        "Continue" buttons, and clicking the backdrop itself.
        """
        try:
            self._page.keyboard.press("Escape")
            self._page.wait_for_timeout(500)
        except Exception:
            pass

        dismissal_selectors = [
            'button[aria-label="Close"]',
            'button:has-text("×")',
            'button:has-text("Close")',
            'button:has-text("Accept")',
            'button:has-text("Got it")',
            'button:has-text("Continue")',
            'button:has-text("Later")',
            'button:has-text("No thanks")',
        ]
        for sel in dismissal_selectors:
            try:
                btn = self._page.locator(sel)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    self._page.wait_for_timeout(500)
                    return
            except Exception:
                continue

        # Last resort: click the overlay backdrop itself (closes on outside click)
        try:
            backdrop = self._page.locator(
                'div[data-state="open"][aria-hidden="true"]'
            )
            if backdrop.count() > 0:
                backdrop.first.click(force=True)
                self._page.wait_for_timeout(500)
        except Exception:
            pass

    def _select_model(self, model_text: str) -> bool:
        """Click the model selection button (tries multiple strategies)."""
        try:
            # Strategy 1: direct button with exact text
            locator = self._page.locator(f'button:has-text("{model_text}")')
            if locator.count() > 0:
                locator.first.click()
                return True
            # Strategy 2: XPath text match
            locator = self._page.locator(f'xpath=//button[contains(text(), "{model_text}")]')
            if locator.count() > 0:
                locator.first.click()
                return True
            logger.error("SnapGenProvider._select_model — could not find '%s'", model_text)
            return False
        except Exception as exc:
            logger.error("SnapGenProvider._select_model — error: %s", exc)
            return False

    def _select_veo_variant_from_dropdown(self, preference: list[str]) -> str | None:
        """Open the Model dropdown (near the 'Model' label) and pick a variant.

        The dropdown is a reka/radix-style listbox trigger: a button with
        aria-haspopup="listbox" in the section labeled "Model". Element IDs
        are auto-generated and change between renders, so we locate by
        structure. Returns the selected variant name, or None.
        """
        try:
            # Find the Model dropdown trigger (visible one)
            trigger_id = self._page.evaluate(
                """() => {
                const triggers = document.querySelectorAll('button[aria-haspopup="listbox"]');
                for (const t of triggers) {
                    if (t.offsetParent === null) continue;  // skip hidden
                    let section = t.closest('div');
                    for (let i = 0; i < 5 && section; i++) {
                        const lbl = section.querySelector('label');
                        if (lbl && lbl.innerText.trim() === 'Model') return t.id;
                        section = section.parentElement;
                    }
                }
                return null;
            }"""
            )
            if not trigger_id:
                logger.error("SnapGenProvider._select_veo_variant — Model dropdown not found")
                return None

            # Open the dropdown
            self._page.locator(f"#{trigger_id}").click()
            self._page.wait_for_timeout(1000)

            # Read available options
            options = self._page.evaluate(
                """() => {
                const listbox = document.querySelector('[role="listbox"]');
                if (!listbox) return [];
                return Array.from(listbox.querySelectorAll('[role="option"]')).map(o => ({
                    text: (o.innerText || '').split('\\n')[0].trim(),
                    el: true
                })).map((o, i) => ({...o, idx: i}));
            }"""
            )
            if not options:
                logger.error("SnapGenProvider._select_veo_variant — no options in dropdown")
                self._page.keyboard.press("Escape")
                return None

            available_names = [o["text"] for o in options]
            logger.info(
                "SnapGenProvider._select_veo_variant — options: %s", available_names
            )

            # Pick by preference
            target_idx = None
            for pref in preference:
                for o in options:
                    if o["text"] == pref:
                        target_idx = o["idx"]
                        break
                if target_idx is not None:
                    break
            if target_idx is None:
                logger.error(
                    "SnapGenProvider._select_veo_variant — none of %s available", preference
                )
                self._page.keyboard.press("Escape")
                return None

            # Click the option
            option_loc = self._page.locator('[role="option"]').nth(target_idx)
            option_loc.click()
            self._page.wait_for_timeout(1000)

            return options[target_idx]["text"]

        except Exception as exc:
            logger.error("SnapGenProvider._select_veo_variant — error: %s", exc)
            try:
                self._page.keyboard.press("Escape")
            except Exception:
                pass
            return None

    def _click_option_with_text(self, text: str) -> bool:
        """Click an option element with the given exact text.

        The live site renders options as visually-hidden radio buttons
        wrapped in clickable <label> cards. Try, in order:
        1. The <label> wrapping a radio with matching aria-label/value
        2. Plain button/label/div/span with exact text
        3. Contains-text fallback
        """
        # Strategy 1: radio card labels (aspect ratio, resolution, duration)
        for attr in ["aria-label", "value"]:
            try:
                locator = self._page.locator(
                    f'label:has(button[role="radio"][{attr}="{text}"])'
                )
                if locator.count() > 0:
                    locator.first.click()
                    self._page.wait_for_timeout(300)
                    return True
            except Exception:
                continue
        # Strategy 2: exact-text elements
        for tag in ["button", "label", "div", "span"]:
            try:
                locator = self._page.locator(f'{tag}:text-is("{text}")')
                if locator.count() > 0:
                    locator.first.click()
                    self._page.wait_for_timeout(300)
                    return True
            except Exception:
                continue
        # Fallback: contains-text match
        for tag in ["button", "label", "div", "span"]:
            try:
                locator = self._page.locator(f'{tag}:has-text("{text}")')
                if locator.count() > 0:
                    locator.first.click()
                    self._page.wait_for_timeout(300)
                    return True
            except Exception:
                continue
        logger.warning("SnapGenProvider._click_option_with_text — '%s' not found", text)
        return False

    def _click_button_with_text(self, text: str) -> bool:
        """Click a button with the given text."""
        try:
            locator = self._page.locator(f'button:has-text("{text}")')
            if locator.count() > 0:
                locator.first.click()
                return True
            logger.warning("SnapGenProvider._click_button_with_text — '%s' not found", text)
            return False
        except Exception as exc:
            logger.error("SnapGenProvider._click_button_with_text — '%s': %s", text, exc)
            return False

    def _fill_prompt(self, prompt: str) -> bool:
        """Fill the prompt textarea."""
        try:
            textarea = self._page.locator(TEXTAREA_SELECTOR)
            if textarea.count() > 0:
                textarea.first.fill(prompt)
                return True
            logger.error("SnapGenProvider._fill_prompt — textarea not found")
            return False
        except Exception as exc:
            logger.error("SnapGenProvider._fill_prompt — error: %s", exc)
            return False

    def _click_generate(self) -> bool:
        """Click the Generate button."""
        try:
            locator = self._page.locator(GENERATE_BUTTON_SELECTOR)
            if locator.count() > 0:
                locator.first.click()
                return True
            # Fallback: any button with "Generate" text
            locator = self._page.locator('button:has-text("Generate")')
            if locator.count() > 0:
                locator.first.click()
                return True
            logger.error("SnapGenProvider._click_generate — generate button not found")
            return False
        except Exception as exc:
            logger.error("SnapGenProvider._click_generate — error: %s", exc)
            return False

    def _wait_for_result_id(self) -> str | None:
        """Wait for a result ID to appear (from URL change or history)."""
        try:
            # Wait for URL to change (result page)
            self._page.wait_for_url(lambda url: "result" in url or "history" in url, timeout=30000)
            # Extract result ID from URL
            url = self._page.url
            if "result" in url:
                parts = url.split("/")
                for part in parts:
                    if len(part) >= 8 and part.isalnum():
                        return part
            return None
        except Exception:
            return None

    @staticmethod
    def _failed_result(error_code: str, error_message: str) -> GenerationResult:
        """Build a failed GenerationResult."""
        return GenerationResult(
            success=False,
            result_id=None,
            error_code=error_code,
            error_message=error_message,
            download_url=None,
            estimated_wait_seconds=None,
        )