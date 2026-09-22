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
    """Manages the Playwright browser lifecycle for SnapGen automation."""

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

    def start(self) -> None:
        """Launch the browser and create a context + page."""
        if self._browser is not None:
            return  # already started

        self._playwright = sync_playwright()
        pw = self._playwright

        self._browser = pw.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )

        self._context = self._browser.new_context(
            user_data_dir=str(self.user_data_dir),
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
            ignore_https_errors=self.ignore_https_errors,
            locale="en-US",
        )

        self._page = self._context.new_page()

        logger.info(
            "BrowserSession.start — launched (headless=%s, profile=%s)",
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
        """Close browser, context, and page.  Idempotent."""
        logger.info("BrowserSession.close — shutting down")
        try:
            if self._context is not None:
                try:
                    self._context.close()
                except Exception as exc:
                    logger.warning("BrowserSession.close — context close error: %s", exc)
        finally:
            self._context = None

        try:
            if self._browser is not None:
                try:
                    self._browser.close()
                except Exception as exc:
                    logger.warning("BrowserSession.close — browser close error: %s", exc)
        finally:
            self._browser = None

            pw = self._playwright
            self._playwright = None
            if pw is not None:
                try:
                    pw.stop()
                except Exception as exc:
                    logger.warning("BrowserSession.close — playwright stop error: %s", exc)

        self._page = None

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
