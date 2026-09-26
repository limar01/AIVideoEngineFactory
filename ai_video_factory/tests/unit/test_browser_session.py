"""Unit tests for BrowserSession (Playwright lifecycle manager).

Runs without a real browser — all tests use mocks or the no-browser path.
The real browser smoke test is in ``test_browser_smoke.py`` and is skipped
unless ``--run-slow`` is passed.

Run:  .venv/bin/pytest tests/unit/test_browser_session.py -v
      .venv/bin/pytest tests/ -v --run-slow   # includes browser smoke test
"""

from __future__ import annotations

import pytest
from pathlib import Path

from app.providers.browser_session import BrowserSession


# ---------------------------------------------------------------------------
# Construction / defaults
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_headless(self) -> None:
        s = BrowserSession()
        assert s.headless is True

    def test_default_user_data_dir(self) -> None:
        s = BrowserSession()
        assert s.user_data_dir == Path.home() / ".snapgen-browser-profile"

    def test_custom_user_data_dir(self) -> None:
        s = BrowserSession(user_data_dir="/tmp/my-profile")
        assert s.user_data_dir == Path("/tmp/my-profile")

    def test_expanduser_on_tilde(self) -> None:
        s = BrowserSession(user_data_dir="~/custom-profile")
        assert s.user_data_dir == Path.home() / "custom-profile"

    def test_default_viewport(self) -> None:
        s = BrowserSession()
        assert s.viewport == (1280, 960)

    def test_default_ignore_https_errors(self) -> None:
        s = BrowserSession()
        assert s.ignore_https_errors is True


# ---------------------------------------------------------------------------
# Not-started state
# ---------------------------------------------------------------------------


class TestNotStarted:
    @pytest.fixture
    def session(self) -> BrowserSession:
        return BrowserSession()

    def test_browser_property_raises(self, session: BrowserSession) -> None:
        with pytest.raises(RuntimeError, match="not started"):
            _ = session.browser

    def test_context_property_raises(self, session: BrowserSession) -> None:
        with pytest.raises(RuntimeError, match="not started"):
            _ = session.context

    def test_page_property_raises(self, session: BrowserSession) -> None:
        with pytest.raises(RuntimeError, match="not started"):
            _ = session.page

    def test_navigate_raises(self, session: BrowserSession) -> None:
        with pytest.raises(RuntimeError, match="not started"):
            session.navigate("https://example.com")

    def test_wait_for_network_idle_raises(self, session: BrowserSession) -> None:
        with pytest.raises(RuntimeError, match="not started"):
            session.wait_for_network_idle()


# ---------------------------------------------------------------------------
# Close before start (idempotent)
# ---------------------------------------------------------------------------


class TestCloseIdempotent:
    def test_close_before_start_is_safe(self) -> None:
        session = BrowserSession()
        session.close()  # should not raise

    def test_double_close_is_safe(self) -> None:
        session = BrowserSession()
        session.close()
        session.close()


# ---------------------------------------------------------------------------
# Type-check convenience
# ---------------------------------------------------------------------------


class TestTypeHints:
    def test_import_snapgen_provider(self) -> None:
        """Verify the re-export of SnapGenProvider works."""
        from app.providers.snapgen import SnapGenProvider

        assert SnapGenProvider.PROVIDER_NAME == "snapgen"
