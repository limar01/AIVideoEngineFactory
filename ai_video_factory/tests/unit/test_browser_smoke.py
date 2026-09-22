"""Smoke test for SnapGen browser automation (real Playwright).

This test actually launches Chromium and navigates to a URL to verify the
Playwright installation works end-to-end.  It does NOT authenticate with
SnapGen — that requires a real Google OAuth session.

Because it touches a real browser it is SKIPPED by default.  Run with::

    .venv/bin/pytest tests/unit/test_browser_smoke.py -v --run-slow

Run:  .venv/bin/pytest tests/unit/test_browser_smoke.py -v --run-slow
"""

from __future__ import annotations

import pytest

from app.providers.browser_session import BrowserSession


# ---------------------------------------------------------------------------
# Browser smoke test (real Playwright)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="Real browser test — run with --run-slow")
def test_browser_launches_and_navigates() -> None:
    """Verify Playwright can launch Chromium and load a page."""
    session = BrowserSession(headless=True)
    session.start()
    try:
        session.navigate("https://example.com", wait_until="domcontentloaded")
        session.wait_for_network_idle(timeout=10000)
        title = session.page.title()
        assert title == "Example Domain"
    finally:
        session.close()


@pytest.mark.skip(reason="Real browser test — run with --run-slow")
def test_browser_session_context_page_properties() -> None:
    """Verify the property accessors return real objects after start()."""
    session = BrowserSession(headless=True)
    session.start()
    try:
        _ = session.browser
        _ = session.context
        _ = session.page
        assert session.page is not None
        assert session.browser is not None
        assert session.context is not None
    finally:
        session.close()


@pytest.mark.skip(reason="Real browser test — run with --run-slow")
def test_browser_navigate_to_snapgen() -> None:
    """Navigate to SnapGen's homepage (no login)."""
    session = BrowserSession(headless=True)
    session.start()
    try:
        session.navigate("https://snapgen.ai", wait_until="domcontentloaded")
        session.wait_for_network_idle(timeout=15000)
        content = session.page.content()
        assert "SnapGen" in content or "snapgen" in content.lower()
    finally:
        session.close()
