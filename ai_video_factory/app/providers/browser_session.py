"""Browser lifecycle manager for SnapGen provider.

Owns the Playwright ``sync_playwright()`` context so the SnapGenProvider
doesn't need to manage it directly.  The orchestrator (e.g. the queue
service or a CLI command) creates one BrowserSession, passes its page and
context into SnapGenProvider, and calls ``close()`` when done.

Usage::

    session = BrowserSession(headless=True)
    try:
        provider = SnapGenProvider()
        provider._browser = session.browser
        provider._context = session.context
        provider._page = session.page
        # ... use provider ...
    finally:
        session.close()
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from playwright.sync_api import (
    sync_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

from app.providers.snapgen import SnapGenProvider

logger = logging.getLogger(__name__)


class BrowserSession:
    """Manages the Playwright browser lifecycle for SnapGen automation.

    All sessions in one process share a single Playwright driver instance
    (Playwright's sync API allows only ONE sync instance per thread —
    starting a second raises "Sync API inside the asyncio loop").
    """

    _shared_playwright: Playwright | None = None

    def __init__(
        self,
        headless: bool = True,
        user_data_dir: str | Path | None = None,
        viewport: tuple[int, int] = (1280, 960),
        ignore_https_errors: bool = True,
    ) -> None:
        self.headless = headless
        self.user_data_dir = (
            Path(user_data_dir).expanduser()
            if user_data_dir
            else Path.home() / ".snapgen-browser-profile"
        )
        self.viewport = viewport
        self.ignore_https_errors = ignore_https_errors

        # Runtime — set by ``start()``, cleared by ``close()``
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def _get_shared_playwright(cls) -> Playwright:
        """Get or start the process-wide Playwright instance."""
        if cls._shared_playwright is None:
            cls._shared_playwright = sync_playwright().start()
        return cls._shared_playwright

    def start(self) -> None:
        """Launch the browser and create a context + page.

        Uses ``launch_persistent_context`` so the per-account user-data-dir
        (cookies, localStorage, Google OAuth session) persists across runs.
        """
        if self._context is not None:
            return  # already started

        self._playwright = self._get_shared_playwright()

        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=self.headless,
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
            ignore_https_errors=self.ignore_https_errors,
            locale="en-US",
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        # Persistent context owns its pages; use the first (or create one)
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = self._context.new_page()

        logger.info(
            "BrowserSession.start — launched persistent context "
            "(headless=%s, profile=%s)",
            self.headless,
            self.user_data_dir,
        )

    @property
    def browser(self) -> Browser:
        """The Playwright ``Browser`` instance."""
        if self._browser is None:
            raise RuntimeError("BrowserSession not started — call start() first")
        return self._browser

    @property
    def context(self) -> BrowserContext:
        """The Playwright ``BrowserContext`` instance."""
        if self._context is None:
            raise RuntimeError("BrowserSession not started — call start() first")
        return self._context

    @property
    def page(self) -> Page:
        """The Playwright ``Page`` instance."""
        if self._page is None:
            raise RuntimeError("BrowserSession not started — call start() first")
        return self._page

    def close(self) -> None:
        """Close this session's context and page.  Idempotent.

        The shared Playwright driver is NOT stopped here (other sessions
        may still be using it). Use ``shutdown_shared_playwright()`` when
        the whole process is done.
        """
        logger.info("BrowserSession.close — shutting down (profile=%s)", self.user_data_dir)
        try:
            if self._context is not None:
                try:
                    self._context.close()
                except Exception as exc:
                    logger.warning("BrowserSession.close — context close error: %s", exc)
        finally:
            self._context = None

        self._browser = None
        self._page = None
        self._playwright = None  # shared instance stays alive for others

    @classmethod
    def shutdown_shared_playwright(cls) -> None:
        """Stop the process-wide Playwright driver (call at process exit)."""
        pw = cls._shared_playwright
        cls._shared_playwright = None
        if pw is not None:
            try:
                pw.stop()
            except Exception as exc:
                logger.warning("BrowserSession.shutdown_shared_playwright — %s", exc)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def navigate(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 30000) -> None:
        """Navigate the page and wait for the given load state."""
        if self._page is None:
            raise RuntimeError("BrowserSession not started")
        self._page.goto(url, wait_until=wait_until, timeout=timeout)

    def wait_for_network_idle(self, timeout: int = 15000) -> None:
        """Wait until the network is idle."""
        if self._page is None:
            raise RuntimeError("BrowserSession not started")
        self._page.wait_for_load_state("networkidle", timeout=timeout)
