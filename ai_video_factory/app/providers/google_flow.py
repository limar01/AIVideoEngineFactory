"""GoogleFlowProvider — Playwright/CDP automation for flow.google.com.

Fully probed selectors (2026-09-24). Flow:
  1. Inject Google session cookies (from Firefox profile or exported jar)
  2. /about → "Create with Google Flow" → /?pli=1 → "New project" → /project/<uuid>
  3. Settings trigger → Video mode + Veo 3.1 - Lite + 9:16 + x1 (10 credits)
  4. Click prompt box, keyboard.type prompt, click Generate
  5. Poll for result tiles; click tile → editor (needs 1920x1080 emulation)
  6. Download media → 720p Original → MP4 lands in download dir

Auth model: no API keys. Google account session via cookies. First login
is manual (user logs into flow.google.com in a real browser); the cookie
jar is then reused for automation. Never bypasses CAPTCHA/2FA.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from typing import Any, Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

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
BASE_URL = "https://flow.google.com"
PROVIDER_NAME = "google-flow"

DEFAULT_MODEL = "Veo 3.1 - Lite"
CREDITS_PER_VIDEO = 10          # x1 output on Veo 3.1 Lite (agent may quote 15)
CREDITS_PER_ACCOUNT_DAILY = 50  # free tier
MAX_VIDEOS_PER_ACCOUNT_DAILY = CREDITS_PER_ACCOUNT_DAILY // CREDITS_PER_VIDEO
DEFAULT_ASPECT_RATIO = "9:16"
DEFAULT_RESOLUTION = "720p"     # 1080p/4K are paid "Upgrade" tiers on Lite
DEFAULT_DURATION_SECONDS = 10   # verified: agent generates 10.0s clips

# Driver (persistent ws8 Chrome via CDP)
DRIVER_CDP_PORT = 9228

# Default Firefox profile that holds the logged-in Google session
DEFAULT_FIREFOX_COOKIE_DB = os.path.expanduser(
    "~/.firefox-google-flow-profile/cookies.sqlite"
)
DEFAULT_DOWNLOAD_DIR = os.path.expanduser("~/Data/gf-downloads")

# ---------------------------------------------------------------------------
# UI selectors (live-probed 2026-09-24)
# ---------------------------------------------------------------------------
SEL_LANDING_CREATE = 'button.flow-button.variant-primary:has-text("Create with Google Flow")'
SEL_NEW_PROJECT = 'button:has-text("New project")'
SEL_SETTINGS_TRIGGER = ".settings-trigger-button"
SEL_TOGGLE = ".cdk-overlay-pane .mat-button-toggle-button"  # + :has-text()
SEL_MODEL_TRIGGER = ".cdk-overlay-pane .mat-mdc-menu-trigger"
SEL_MODEL_ITEM = '.mat-mdc-menu-item, [role="menuitem"]'
SEL_CREDITS_LABEL = ".cdk-overlay-pane .credit-cost-label, .cdk-overlay-pane flow-credit-cost-label"
SEL_PROMPT_BOX = ".base-prompt-box"
SEL_GENERATE = ".generate-icon-button"
SEL_RESULT_TILE_ICON = "mat-icon"  # text 'play_circle' — located via JS
SEL_EDITOR_DOWNLOAD = 'button[aria-label="Download media"]'
SEL_DOWNLOAD_720P = None  # located in overlay by text "720p"
SEL_VIDEO_TILE = "flow-video-tile"

ERROR_PATTERNS = [
    (re.compile(r"not\s+enough\s+credits", re.I), "QUOTA_EXHAUSTED"),
    (re.compile(r"out\s+of\s+credits", re.I), "QUOTA_EXHAUSTED"),
    (re.compile(r"daily\s+limit", re.I), "QUOTA_EXHAUSTED"),
    (re.compile(r"rate\s+limit", re.I), "RATE_LIMITED"),
    (re.compile(r"too\s+many\s+requests", re.I), "RATE_LIMITED"),
    (re.compile(r"generation\s+failed", re.I), "GENERATION_FAILED"),
    (re.compile(r"try\s+again\s+later", re.I), "RATE_LIMITED"),
    (re.compile(r"sign\s*in", re.I), "SESSION_EXPIRED"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_firefox_cookies(db_path: str = DEFAULT_FIREFOX_COOKIE_DB) -> list[dict]:
    """Read cookies from a Firefox profile DB into Playwright cookie dicts."""
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT host, path, name, value, expiry, isSecure, sameSite FROM moz_cookies"
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    seen: set[tuple[str, str]] = set()
    cookies: list[dict[str, Any]] = []
    for host, path, name, value, expiry, is_secure, same_site in rows:
        domain = host[1:] if host.startswith(".") else host
        key = (name, domain)
        if key in seen:
            continue
        seen.add(key)
        # Firefox sameSite ints: 0 unset, 1 strict(?), 2/3 lax, 6 none
        ss = "Lax"
        if same_site in (0, 6):
            ss = "None"
        elif same_site == 1:
            ss = "Strict"
        cookies.append(
            {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "expires": max(1, min(int(expiry), 9999999999)) if expiry and expiry > 0 else -1,
                "secure": bool(is_secure),
                "httpOnly": False,
                "sameSite": ss,
            }
        )
    return cookies


class GoogleFlowProvider(VideoGenerationProvider):
    """Playwright/CDP-driven provider for Google Flow (flow.google.com).

    Lifecycle:
      __init__ → authenticate (launch + cookies) → submit_generation
      → get_generation_status → download_result → close_session.

    The provider drives a real Chromium via CDP. First-run login is manual;
    sessions persist via cookie jars (one per account, JSON on disk).
    """

    PROVIDER_NAME = PROVIDER_NAME

    def __init__(
        self,
        base_url: str = BASE_URL,
        headless: bool = False,
        cookie_jar: Optional[str] = None,
        firefox_cookie_db: Optional[str] = None,
        download_dir: str = DEFAULT_DOWNLOAD_DIR,
        cdp_port: Optional[int] = None,
        viewport_width: int = 1920,
        viewport_height: int = 1080,
        generation_timeout_seconds: int = 300,
        download_timeout_seconds: int = 180,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headless = headless
        self.cookie_jar = cookie_jar
        self.firefox_cookie_db = firefox_cookie_db
        self.download_dir = os.path.abspath(download_dir)
        self.cdp_port = cdp_port
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.generation_timeout = generation_timeout_seconds
        self.download_timeout = download_timeout_seconds

        os.makedirs(self.download_dir, exist_ok=True)

        # Runtime state
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._cdp = None
        self._authenticated = False
        self._project_url: Optional[str] = None
        self._credits_used_today = 0
        self._last_error_code: Optional[str] = None
        self._last_error_message: Optional[str] = None
        self._last_page_text = ""
        self._pending_downloads: dict[str, str] = {}  # result_id -> file path

    # ------------------------------------------------------------------
    # Browser plumbing
    # ------------------------------------------------------------------
    def _launch_browser(self) -> None:
        if self._page is not None:
            return
        self._playwright = sync_playwright().start()
        if self.cdp_port:
            self._browser = self._playwright.chromium.connect_over_cdp(
                f"http://localhost:{self.cdp_port}", timeout=15000
            )
            self._context = self._browser.contexts[0]
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        else:
            self._context = self._playwright.chromium.launch_persistent_context(
                "/tmp/gf-provider-profile",
                headless=self.headless,
                args=[
                    "--ozone-platform=x11",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

        # Editor view requires a big viewport — real window may be tiny.
        try:
            self._cdp = self._context.new_cdp_session(self._page)
            self._cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": self.viewport_width,
                    "height": self.viewport_height,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
            )
            self._cdp.send(
                "Browser.setDownloadBehavior",
                {
                    "behavior": "allow",
                    "downloadPath": self.download_dir,
                    "eventsEnabled": True,
                },
            )
        except Exception as exc:  # pragma: no cover — env-dependent
            logger.warning("CDP setup partial failure: %s", exc)

    def _inject_cookies(self) -> int:
        """Load cookies from jar (JSON) or Firefox DB and inject into context."""
        assert self._context is not None
        cookies: list[dict[str, Any]] = []
        if self.cookie_jar and os.path.exists(self.cookie_jar):
            with open(self.cookie_jar) as f:
                cookies = json.load(f)
        elif self.firefox_cookie_db and os.path.exists(self.firefox_cookie_db):
            cookies = load_firefox_cookies(self.firefox_cookie_db)
        elif os.path.exists(DEFAULT_FIREFOX_COOKIE_DB):
            cookies = load_firefox_cookies(DEFAULT_FIREFOX_COOKIE_DB)
        if not cookies:
            return 0
        try:
            self._context.clear_cookies()
        except Exception:
            pass
        self._context.add_cookies(cookies)  # type: ignore[arg-type]
        return len(cookies)

    def _wait(self, ms: int) -> None:
        assert self._page is not None
        self._page.wait_for_timeout(ms)

    def _click(self, selector: str, timeout_ms: int = 10000) -> bool:
        assert self._page is not None
        try:
            loc = self._page.locator(selector)
            if loc.count() == 0:
                return False
            loc.first.click(timeout=timeout_ms)
            return True
        except Exception as exc:
            logger.debug("click %s failed: %s", selector, exc)
            return False

    def _js_click(self, js: str) -> bool:
        """Click via JS locator expression (returns element or null)."""
        assert self._page is not None
        try:
            return bool(self._page.evaluate(js))
        except Exception as exc:
            logger.debug("js click failed: %s", exc)
            return False

    def _capture_page_text(self) -> None:
        try:
            assert self._page is not None
            self._last_page_text = self._page.inner_text("body")
        except Exception:
            self._last_page_text = ""

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def _goto_landing(self) -> None:
        assert self._page is not None
        self._page.goto(f"{self.base_url}/about", wait_until="domcontentloaded", timeout=30000)
        self._wait(3000)

    def _open_projects_gallery(self) -> bool:
        assert self._page is not None
        url = self._page.url or ""
        if "accounts.google.com" in url:
            self._last_error_code = "SESSION_EXPIRED"
            self._last_error_message = "Redirected to Google sign-in — cookies invalid"
            return False
        # Already inside the app (gallery or project)? Nothing to do.
        if "/about" not in url and self.base_url in url:
            return True
        ok = self._click(SEL_LANDING_CREATE, 15000)
        self._wait(2500)
        if self._page and "accounts.google.com" in self._page.url:
            self._last_error_code = "SESSION_EXPIRED"
            self._last_error_message = "Redirected to Google sign-in — cookies invalid"
            return False
        return ok

    def _new_project(self) -> bool:
        ok = self._click(SEL_NEW_PROJECT, 15000)
        if not ok:
            return False
        assert self._page is not None
        deadline = time.time() + 30
        project_url = None
        while time.time() < deadline:
            self._wait(1000)
            url = self._page.url or ""
            if "/project/" in url:
                project_url = url
                break
        if not project_url:
            return False
        self._project_url = project_url
        # Wait for the workspace to render (prompt box + settings icon)
        deadline = time.time() + 30
        while time.time() < deadline:
            self._wait(1000)
            try:
                if (
                    self._page.locator(SEL_PROMPT_BOX).count() > 0
                    and self._page.locator('button[aria-label="Settings"]').count() > 0
                ):
                    return True
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------
    # Settings panel
    # ------------------------------------------------------------------
    def _open_settings(self) -> bool:
        """Open the Agent settings drawer via the tune icon.

        The drawer has persistent defaults: Image generation default and
        Video generation default (aspect, x-count, model) + Save button.
        """
        assert self._page is not None
        # Close any open drawer first
        try:
            self._page.keyboard.press("Escape")
            self._wait(400)
        except Exception:
            pass
        ok = self._click('button[aria-label="Settings"]', 10000)
        if not ok:
            ok = self._click('button:has-text("tune")', 10000)
        self._wait(1500)
        # Drawer is open if settings-section elements exist
        try:
            return self._page.locator(".settings-section").count() > 0
        except Exception:
            return False

    def _config_video_default(
        self,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        output_count: int = 1,
        model: str = DEFAULT_MODEL,
    ) -> bool:
        """Set Video generation defaults in the Agent settings drawer + Save.

        Requires the drawer to be open (call _open_settings first).
        """
        assert self._page is not None
        # Locate the "Video generation default" section
        section = None
        secs = self._page.locator(".settings-section")
        for i in range(secs.count()):
            try:
                txt = secs.nth(i).inner_text(timeout=2000)
            except Exception:
                continue
            if "Video generation default" in txt:
                section = secs.nth(i)
                break
        if section is None:
            logger.error("Video generation default section not found")
            return False

        def click_in_section(text: str) -> bool:
            try:
                loc = section.locator(f'.mat-button-toggle-button:has-text("{text}")')
                if loc.count() == 0:
                    return False
                loc.first.click(timeout=5000)
                self._wait(500)
                return True
            except Exception:
                return False

        if not click_in_section(aspect_ratio):
            logger.warning("aspect %s toggle not found in video section", aspect_ratio)
        if not click_in_section(f"x{output_count}"):
            logger.warning("x%d toggle not found in video section", output_count)

        # Model dropdown inside the section
        try:
            trigger = section.locator(".mat-mdc-menu-trigger")
            if trigger.count() > 0:
                current = trigger.first.inner_text(timeout=2000)
                if model not in current:
                    trigger.first.click(timeout=5000)
                    self._wait(1200)
                    item = self._page.locator(SEL_MODEL_ITEM).get_by_text(model, exact=False).first
                    item.click(timeout=5000)
                    self._wait(800)
        except Exception as exc:
            logger.warning("model select failed (may already be default): %s", exc)

        # Save
        try:
            save = self._page.locator(".settings-save-button, button:has-text('Save')")
            if save.count() > 0:
                save.first.click(timeout=5000)
                self._wait(1000)
                logger.info("Agent settings saved (video default: %s, x1, %s)", aspect_ratio, model)
        except Exception as exc:
            logger.warning("save failed: %s", exc)

        # Close drawer
        try:
            self._page.keyboard.press("Escape")
            self._wait(400)
        except Exception:
            pass
        return True

    def _select_toggle(self, text: str) -> bool:
        assert self._page is not None
        sel = f'.cdk-overlay-pane .mat-button-toggle-button:has-text("{text}")'
        loc = self._page.locator(sel)
        if loc.count() == 0:
            return False
        try:
            loc.first.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        try:
            loc.first.click(timeout=5000)
            self._wait(600)
            return True
        except Exception as exc:
            logger.debug("toggle %s failed: %s", text, exc)
            return False

    def _select_model(self, model_text: str = DEFAULT_MODEL) -> bool:
        assert self._page is not None
        # Open the model dropdown (the trigger whose text mentions a model)
        triggers = self._page.locator(SEL_MODEL_TRIGGER)
        for i in range(triggers.count()):
            try:
                t = triggers.nth(i).inner_text(timeout=2000)
            except Exception:
                continue
            if any(k in t for k in ("Veo", "Nano", "Omni")):
                try:
                    triggers.nth(i).click(timeout=5000)
                except Exception:
                    return False
                self._wait(1200)
                item = self._page.locator(SEL_MODEL_ITEM).get_by_text(model_text, exact=False).first
                try:
                    item.click(timeout=5000)
                    self._wait(800)
                    return True
                except Exception:
                    return False
        return False

    def _read_credits_label(self) -> Optional[int]:
        assert self._page is not None
        loc = self._page.locator(SEL_CREDITS_LABEL)
        if loc.count() == 0:
            return None
        try:
            text = loc.first.inner_text(timeout=3000)
        except Exception:
            return None
        m = re.search(r"(\d+)\s*credits", text, re.I)
        return int(m.group(1)) if m else None

    def _configure_video_mode(
        self,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        output_count: int = 1,
        model: str = DEFAULT_MODEL,
    ) -> bool:
        """Set persistent Video generation defaults via the Agent settings drawer."""
        if not self._open_settings():
            return False
        return self._config_video_default(
            aspect_ratio=aspect_ratio, output_count=output_count, model=model
        )

    # ------------------------------------------------------------------
    # Authentication (ABC)
    # ------------------------------------------------------------------
    def authenticate(self, account_credentials: dict) -> bool:
        """Launch browser, inject cookies, verify session. No interactive login."""
        try:
            self._launch_browser()
        except Exception as exc:
            self._last_error_code = "BROWSER_LAUNCH_FAILED"
            self._last_error_message = str(exc)
            return False

        n = self._inject_cookies()
        logger.info("GoogleFlow: injected %d cookies", n)
        if n == 0:
            self._last_error_code = "NO_COOKIES"
            self._last_error_message = (
                "No Google session cookies found. Log in manually at "
                "https://flow.google.com and export cookies first."
            )
            return False

        try:
            self._goto_landing()
            if not self._open_projects_gallery():
                return False
            # Session is valid if we reached the gallery without sign-in redirect
            self._authenticated = True
            logger.info("GoogleFlow: session valid (gallery reached)")
            return True
        except Exception as exc:
            self._last_error_code = "AUTH_NAVIGATION_FAILED"
            self._last_error_message = str(exc)
            return False

    def check_session(self) -> bool:
        if not self._page or not self._authenticated:
            return False
        try:
            self._goto_landing()
            url = self._page.url or ""
            if "accounts.google.com" in url:
                return False
            return self._open_projects_gallery()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Capabilities & quota (ABC)
    # ------------------------------------------------------------------
    def get_capabilities(self) -> GenerationCapabilities:
        return GenerationCapabilities(
            max_prompt_length=10000,
            supported_aspect_ratios=["16:9", "9:16"],
            supported_resolutions=["720p"],  # 1080p/4K are paid upgrades
            max_duration_seconds=10.0,
            min_duration_seconds=10.0,
            supports_narration=True,  # Veo native audio confirmed
        )

    def get_quota(self) -> QuotaInfo:
        remaining = max(
            0, CREDITS_PER_ACCOUNT_DAILY - self._credits_used_today * CREDITS_PER_VIDEO
        )
        return QuotaInfo(
            limit=CREDITS_PER_ACCOUNT_DAILY,
            used=self._credits_used_today * CREDITS_PER_VIDEO,
            remaining=remaining,
            reset_time=None,
        )

    # ------------------------------------------------------------------
    # Generation (ABC)
    # ------------------------------------------------------------------
    def submit_generation(self, prompt: str, scene_metadata: dict) -> GenerationResult:
        """Two-stage generation via the persistent ws8 Chrome driver.

        Stage 1: reference image (free) from scene prompt + character info.
        Stage 2: attach image + generate 10s Veo 3.1 Lite video (10 credits).
        """
        try:
            from app.providers.google_flow_driver import GoogleFlowDriver

            driver = GoogleFlowDriver(
                cdp_port=self.cdp_port or DRIVER_CDP_PORT,
                download_dir=self.download_dir,
            )
            if not driver.connect():
                return self._fail(
                    "BROWSER_NOT_RUNNING",
                    "ws8 Chrome not running on :9228 — launch it first",
                )
            try:
                if not driver.ensure_session():
                    return self._fail("SESSION_EXPIRED", "Login needed in ws8 Chrome")

                # Stage 1: reference image (free) — reuse if one exists
                project_url = driver.new_project()
                if not project_url:
                    return self._fail("NAVIGATION_FAILED", "Could not create project")

                driver.set_video_defaults()  # 9:16, x1, Veo 3.1 - Lite

                img_path = driver.generate_image(
                    scene_metadata.get("reference_prompt", prompt), project_url
                )
                if not img_path:
                    logger.warning("reference image failed — generating video without it")

                # Stage 2: video with image attached
                video_path = driver.generate_video(prompt, project_url)
                if not video_path:
                    return self._fail("VIDEO_FAILED", "Video generation/download failed")

                self._credits_used_today += 1
                result_id = f"gf-{os.path.basename(video_path)}"
                self._pending_downloads[result_id] = video_path
                return GenerationResult(
                    success=True,
                    result_id=result_id,
                    download_url=video_path,
                    estimated_wait_seconds=0,  # already complete
                )
            finally:
                driver.close()
        except Exception as exc:
            return self._fail("SUBMIT_ERROR", str(exc))

    def get_generation_status(self, result_id: str) -> GenerationStatus:
        """The driver completes synchronously — a known result is COMPLETED."""
        if result_id in self._pending_downloads:
            return GenerationStatus.COMPLETED
        return GenerationStatus.UNKNOWN

    def _count_result_tiles(self) -> int:
        assert self._page is not None
        try:
            return int(
                self._page.evaluate(
                    """() => [...document.querySelectorAll('mat-icon')]
                         .filter(i => i.textContent.trim() === 'play_circle').length"""
                )
            )
        except Exception:
            return 0

    def download_result(self, result_id: str) -> bytes:
        """Return the already-downloaded file bytes for a completed result."""
        path = self._pending_downloads.get(result_id)
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        return b""

    # ------------------------------------------------------------------
    # Error detection (ABC)
    # ------------------------------------------------------------------
    def detect_error(self, result_id: str, raw_response: str) -> tuple[Optional[str], Optional[str]]:
        for pattern, code in ERROR_PATTERNS:
            m = pattern.search(raw_response or "")
            if m:
                return code, m.group(0)
        return None, None

    def detect_quota_exhaustion(self, raw_response: str) -> bool:
        code, _ = self.detect_error("", raw_response or "")
        return code == "QUOTA_EXHAUSTED"

    # ------------------------------------------------------------------
    # Cleanup (ABC)
    # ------------------------------------------------------------------
    def close_session(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._cdp = None
        self._authenticated = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _fail(self, code: str, message: str) -> GenerationResult:
        self._last_error_code = code
        self._last_error_message = message
        logger.error("GoogleFlow: %s — %s", code, message)
        return GenerationResult(success=False, error_code=code, error_message=message)
