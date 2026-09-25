"""Unit tests for the SnapGen provider (non-browser methods).

The browser-dependent methods (authenticate, submit_generation, etc.) are NOT
tested here — they require a real Playwright browser and an authenticated
SnapGen session.  This test file covers:

* Error pattern detection (detect_error, detect_quota_exhaustion)
* Capability / quota reporting (get_capabilities, get_quota)
* Configuration defaults
* The "Not authenticated" fast-fail path in public methods

Run:  .venv/bin/pytest tests/unit/test_snapgen_provider.py -v
"""

from __future__ import annotations

import pytest

from app.providers.base import GenerationStatus, GenerationCapabilities, QuotaInfo
from app.providers.snapgen import (
    SnapGenProvider,
    MODEL_BUTTON_TEXT,
    DURATION_OPTIONS,
    ASPECT_RATIO_OPTIONS,
    RESOLUTION_OPTIONS,
)


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
        assert caps is not None
        assert "16:9" in caps.supported_aspect_ratios
        assert "9:16" in caps.supported_aspect_ratios
        assert "720p" in caps.supported_resolutions
        assert "1080p" in caps.supported_resolutions
        assert caps.max_duration_seconds == 15.0
        assert caps.min_duration_seconds == 6.0
        assert caps.supports_narration is True
        assert caps.max_prompt_length == 5000

    def test_capabilities_fixed_15s(self, provider: SnapGenProvider) -> None:
        caps = provider.get_capabilities()
        assert caps.max_duration_seconds == 15.0
        assert caps.min_duration_seconds == 6.0


# ---------------------------------------------------------------------------
# Quota
# ---------------------------------------------------------------------------


class TestQuota:
    def test_quota_no_limit(self, provider: SnapGenProvider) -> None:
        quota = provider.get_quota()
        assert quota is not None
        assert quota.limit is None
        assert quota.used is None
        assert quota.remaining is None
        assert quota.reset_time is None


# ---------------------------------------------------------------------------
# Error pattern detection
# ---------------------------------------------------------------------------


class TestErrorDetection:
    def test_detect_captcha(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("test123", "human verification required")
        assert code == "CAPTCHA_DETECTED"
        assert msg is not None

    def test_detect_captcha_word(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("test123", "Please solve the captcha")
        assert code == "CAPTCHA_DETECTED"

    def test_detect_rate_limit(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("test123", "rate limit exceeded, please wait")
        assert code == "RATE_LIMIT"
        assert msg is not None

    def test_detect_429(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("test123", "HTTP 429 Too Many Requests")
        assert code == "RATE_LIMIT"

    def test_detect_generation_error(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("test123", "generation failed, try again later")
        assert code == "GENERATION_ERROR"
        assert msg is not None

    def test_detect_session_expired(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("test123", "session expired, please sign in")
        assert code == "GENERATION_ERROR"

    def test_no_error_on_clean_text(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("test123", "This is a normal page")
        assert code is None
        assert msg is None

    def test_empty_response(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("test123", "")
        assert code is None
        assert msg is None

    def test_none_response(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("test123", None)  # type: ignore[arg-type]
        assert code is None
        assert msg is None


# ---------------------------------------------------------------------------
# Quota exhaustion detection
# ---------------------------------------------------------------------------


class TestQuotaExhaustion:
    def test_captcha_means_exhausted(self, provider: SnapGenProvider) -> None:
        assert provider.detect_quota_exhaustion("human verification required") is True

    def test_rate_limit_means_exhausted(self, provider: SnapGenProvider) -> None:
        assert provider.detect_quota_exhaustion("rate limit exceeded") is True

    def test_clean_text_not_exhausted(self, provider: SnapGenProvider) -> None:
        assert provider.detect_quota_exhaustion("everything is fine") is False

    def test_empty_not_exhausted(self, provider: SnapGenProvider) -> None:
        assert provider.detect_quota_exhaustion("") is False


# ---------------------------------------------------------------------------
# Re-authentication needed
# ---------------------------------------------------------------------------


class TestReauthNeeded:
    def test_detects_sign_in_prompt(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("test123", "please sign in to continue")
        assert code is not None

    def test_detects_under_maintenance(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("test123", "service under maintenance")
        assert code == "GENERATION_ERROR"

    def test_detects_try_again(self, provider: SnapGenProvider) -> None:
        code, msg = provider.detect_error("test123", "something went wrong, try again")
        assert code == "GENERATION_ERROR"


# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_base_url_default(self, provider: SnapGenProvider) -> None:
        assert provider.base_url == "https://snapgen.ai"

    def test_app_url(self, provider: SnapGenProvider) -> None:
        assert provider.app_url == "https://snapgen.ai/app/video-gen"

    def test_history_url(self, provider: SnapGenProvider) -> None:
        assert provider.history_url == "https://snapgen.ai/app/history"

    def test_model_button_text(self, provider: SnapGenProvider) -> None:
        assert MODEL_BUTTON_TEXT == "Veo"

    def test_duration_options(self, provider: SnapGenProvider) -> None:
        # Live probe 2026-09-24: Veo durations are 4s/6s/8s only
        assert "4s" in DURATION_OPTIONS
        assert "6s" in DURATION_OPTIONS
        assert "8s" in DURATION_OPTIONS

    def test_aspect_ratio_options(self, provider: SnapGenProvider) -> None:
        assert "16:9" in ASPECT_RATIO_OPTIONS
        assert "9:16" in ASPECT_RATIO_OPTIONS

    def test_resolution_options(self, provider: SnapGenProvider) -> None:
        assert "720p" in RESOLUTION_OPTIONS
        assert "1080p" in RESOLUTION_OPTIONS


# ---------------------------------------------------------------------------
# Provider name
# ---------------------------------------------------------------------------


class TestProviderName:
    def test_provider_name(self, provider: SnapGenProvider) -> None:
        assert provider.PROVIDER_NAME == "snapgen"
