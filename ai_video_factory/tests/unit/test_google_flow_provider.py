"""Unit tests for GoogleFlowProvider (non-browser methods)."""
from __future__ import annotations

from app.providers.google_flow import (
    BASE_URL,
    CREDITS_PER_ACCOUNT_DAILY,
    CREDITS_PER_VIDEO,
    DEFAULT_ASPECT_RATIO,
    DEFAULT_MODEL,
    DEFAULT_RESOLUTION,
    GoogleFlowProvider,
    PROVIDER_NAME,
)


def test_constants():
    assert BASE_URL == "https://flow.google.com"
    assert PROVIDER_NAME == "google-flow"
    assert DEFAULT_MODEL == "Veo 3.1 - Lite"
    assert CREDITS_PER_VIDEO == 10
    assert CREDITS_PER_ACCOUNT_DAILY == 50
    assert DEFAULT_ASPECT_RATIO == "9:16"
    assert DEFAULT_RESOLUTION == "720p"


def test_get_provider_name():
    p = GoogleFlowProvider()
    assert p.PROVIDER_NAME == "google-flow"


def test_capabilities():
    p = GoogleFlowProvider()
    caps = p.get_capabilities()
    assert caps.supported_aspect_ratios == ["16:9", "9:16"]
    assert caps.supported_resolutions == ["720p"]
    assert caps.supports_narration is True
    assert caps.max_duration_seconds == 10.0
    assert caps.min_duration_seconds == 10.0


def test_quota():
    p = GoogleFlowProvider()
    q = p.get_quota()
    assert q.limit == 50
    assert q.used == 0
    assert q.remaining == 50


def test_quota_after_usage():
    p = GoogleFlowProvider()
    p._credits_used_today = 2
    q = p.get_quota()
    assert q.used == 20
    assert q.remaining == 30


def test_detect_error_quota():
    p = GoogleFlowProvider()
    code, msg = p.detect_error("", "Not enough credits to generate")
    assert code == "QUOTA_EXHAUSTED"
    assert msg


def test_detect_error_rate_limit():
    p = GoogleFlowProvider()
    code, _ = p.detect_error("", "Too many requests, please wait")
    assert code == "RATE_LIMITED"


def test_detect_error_none():
    p = GoogleFlowProvider()
    code, msg = p.detect_error("", "Video is ready")
    assert code is None
    assert msg is None


def test_detect_quota_exhaustion():
    p = GoogleFlowProvider()
    assert p.detect_quota_exhaustion("out of credits") is True
    assert p.detect_quota_exhaustion("all good") is False


def test_validate_error_before_auth():
    """submit_generation without ws8 Chrome returns a clean failure, not crash."""
    p = GoogleFlowProvider(cdp_port=19999)  # nothing listening
    result = p.submit_generation("test prompt", {})
    assert result.success is False
    assert result.error_code in (
        "BROWSER_NOT_RUNNING",
        "SESSION_EXPIRED",
        "NAVIGATION_FAILED",
        "VIDEO_FAILED",
        "SUBMIT_ERROR",
    )
