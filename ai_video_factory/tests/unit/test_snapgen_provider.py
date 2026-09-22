"""Unit tests for the SnapGen provider (non-browser methods).

The browser-dependent methods (authenticate, submit_generation, etc.) are NOT
tested here — they require a real Playwright browser and an authenticated
SnapGen session.  This test file covers:

* Error pattern detection (detect_error, detect_quota_exhaustion)
* Status text parsing (_status_from_text)
* Capability / quota reporting (get_capabilities, get_quota)
* Configuration defaults
* The "Not authenticated" fast-fail path in public methods

Run:  .venv/bin/pytest tests/unit/test_snapgen_provider.py -v
"""

from __future__ import annotations

import pytest

from app.providers.base import GenerationStatus
from app.providers.snapgen import SnapGenProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def provider() -> SnapGenProvider:
    return SnapGenProvider()


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_capabilities_default(self, provider: SnapGenProvider) -> None:
        caps = provider.get_capabilities()
        assert caps.supported_aspect_ratios == ["16:9", "9:16", "4:3"]
        assert caps.supported_resolutions == ["720p"]
        assert caps.max_duration_seconds == 8.0
        assert caps.min_duration_seconds == 8.0
        assert caps.supports_narration is True
        assert caps.max_prompt_length == 3000

    def test_capabilities_fixed_8s(self, provider: SnapGenProvider) -> None:
        """Free tier Veo 3.1 Fast is locked at 8 seconds."""
        caps = provider.get_capabilities()
        assert caps.max_duration_seconds == caps.min_duration_seconds == 8.0


# ---------------------------------------------------------------------------
# Quota
# ---------------------------------------------------------------------------


class TestQuota:
    def test_quota_none_for_free_tier(self, provider: SnapGenProvider) -> None:
        """Free Veo 3.1 Fast has no credit counter — all fields None."""
        quota = provider.get_quota()
        assert quota.limit is None
        assert quota.used is None
        assert quota.remaining is None
        assert quota.reset_time is None


# ---------------------------------------------------------------------------
# Error detection
# ---------------------------------------------------------------------------


class TestErrorDetection:
    # -- CAPTCHA patterns -----------------------------------------------

    @pytest.mark.parametrize(
        "text",
        [
            "human verification required",
            "verify you are human",
            "select all images that contain",
            "click the objects",
            "CAPTCHA",
            "Human Verification",
        ],
    )
    def test_detect_capcha(self, provider: SnapGenProvider, text: str) -> None:
        code, msg = provider.detect_error("fake-id", text)
        assert code == "CAPTCHA_DETECTED"
        assert msg is not None
        assert "CAPTCHA" in msg.upper() or "human" in msg.lower()

    def test_detect_quota_exhaustion_capcha(self, provider: SnapGenProvider) -> None:
        assert provider.detect_quota_exhaustion("human verification required") is True

    # -- Rate-limit patterns -------------------------------------------

    @pytest.mark.parametrize(
        "text",
        [
            "rate limit exceeded",
            "too many requests",
            "please wait before trying again",
            "try again later",
            "429 Too Many Requests",
        ],
    )
    def test_detect_rate_limit(self, provider: SnapGenProvider, text: str) -> None:
        code, msg = provider.detect_error("fake-id", text)
        assert code == "RATE_LIMIT"
        assert msg is not None

    def test_detect_quota_exhaustion_rate_limit(self, provider: SnapGenProvider) -> None:
        assert provider.detect_quota_exhaustion("rate limit exceeded") is True

    # -- Generation error patterns -------------------------------------

    @pytest.mark.parametrize(
        "text",
        [
            "generation failed",
            "try again",
            "session expired",
            "sign in to continue",
            "under maintenance",
        ],
    )
    def test_detect_generation_error(self, provider: SnapGenProvider, text: str) -> None:
        code, msg = provider.detect_error("fake-id", text)
        assert code == "GENERATION_ERROR"
        assert msg is not None

    # -- No error ------------------------------------------------------

    def test_no_error_in_clean_text(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("fake-id", "Your video is ready!")
        assert code is None
        assert msg is None

    def test_no_error_in_empty_text(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("fake-id", "")
        assert code is None
        assert msg is None

    def test_no_error_in_none_text(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("fake-id", None)  # type: ignore[arg-type]
        assert code is None
        assert msg is None

    # -- Priority: CAPTCHA beats rate-limit ----------------------------

    def test_capcha_takes_priority_over_rate_limit(self, provider: SnapGenProvider) -> None:
        text = "human verification required. rate limit may also apply."
        code, msg = provider.detect_error("fake-id", text)
        assert code == "CAPTCHA_DETECTED"


# ---------------------------------------------------------------------------
# Status parsing
# ---------------------------------------------------------------------------


class TestStatusParsing:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("Completed", GenerationStatus.COMPLETED),
            ("completed", GenerationStatus.COMPLETED),
            ("Your video is Completed", GenerationStatus.COMPLETED),
            ("Processing", GenerationStatus.GENERATING),
            ("Generating", GenerationStatus.GENERATING),
            ("Still generating...", GenerationStatus.GENERATING),
            ("Failed", GenerationStatus.FAILED),
            ("generation failed", GenerationStatus.FAILED),
            ("Something went wrong", GenerationStatus.FAILED),
            ("Unknown status", GenerationStatus.UNKNOWN),
            ("", GenerationStatus.UNKNOWN),
        ],
    )
    def test_status_from_text(self, provider: SnapGenProvider, text: str, expected: GenerationStatus) -> None:
        assert provider._status_from_text(text) == expected


# ---------------------------------------------------------------------------
# Credentials / authentication fast-paths
# ---------------------------------------------------------------------------


class TestUnauthenticatedPaths:
    def test_authenticate_returns_false_when_browser_not_launched(
        self, provider: SnapGenProvider
    ) -> None:
        """Without a launched browser, authenticate returns False."""
        result = provider.authenticate({})
        assert result is False
        assert provider._last_error_code == "BROWSER_LAUNCH_FAILED"

    def test_check_session_returns_false_without_page(self, provider: SnapGenProvider) -> None:
        assert provider.check_session() is False

    def test_submit_generation_fails_without_auth(self, provider: SnapGenProvider) -> None:
        result = provider.submit_generation("test prompt", {})
        assert result.success is False
        assert result.error_code == "NOT_AUTHENTICATED"

    def test_get_generation_status_returns_unknown_without_auth(
        self, provider: SnapGenProvider
    ) -> None:
        status = provider.get_generation_status("fake-id")
        assert status == GenerationStatus.UNKNOWN

    def test_download_result_raises_without_auth(self, provider: SnapGenProvider) -> None:
        with pytest.raises(RuntimeError, match="Not authenticated"):
            provider.download_result("fake-id")

    def test_close_session_is_idempotent(self, provider: SnapGenProvider) -> None:
        provider.close_session()  # Should not raise
        provider.close_session()  # Second call also safe


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_default_values(self) -> None:
        p = SnapGenProvider()
        assert p.base_url == "https://snapgen.ai"
        assert p.app_url == "https://snapgen.ai/app/video-gen"
        assert p.history_url == "https://snapgen.ai/app/history"
        assert p.session_timeout == 30 * 60
        assert p.generation_timeout == 15 * 60
        assert p.polling_interval == 10
        assert p.headless is True

    def test_custom_values(self) -> None:
        p = SnapGenProvider(
            base_url="https://staging.snapgen.ai",
            session_timeout_minutes=60,
            generation_timeout_minutes=30,
            polling_interval_seconds=5,
            headless=False,
            user_data_dir="/tmp/test-profile",
        )
        assert p.base_url == "https://staging.snapgen.ai"
        assert p.app_url == "https://staging.snapgen.ai/app/video-gen"
        assert p.session_timeout == 60 * 60
        assert p.generation_timeout == 30 * 60
        assert p.polling_interval == 5
        assert p.headless is False
        assert p.user_data_dir == "/tmp/test-profile"

    def test_provider_name(self) -> None:
        assert SnapGenProvider.PROVIDER_NAME == "snapgen"
