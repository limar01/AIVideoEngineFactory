"""Unit tests for MockVideoProvider.

All provider tests use the MockVideoProvider only — no real provider
quota is consumed (Master Spec §27).
"""
import os
import tempfile

import pytest
from pathlib import Path

from app.providers.base import GenerationStatus, GenerationCapabilities, QuotaInfo
from app.providers.mock import MockVideoProvider
from app.providers.registry import create_provider


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture
def mock_provider() -> MockVideoProvider:
    return MockVideoProvider(quota_limit=100, output_dir=tempfile.mkdtemp())


@pytest.fixture
def mock_provider_with_failures() -> MockVideoProvider:
    return MockVideoProvider(
        quota_limit=100,
        fail_on_call=3,
        output_dir=tempfile.mkdtemp(),
    )


# --------------------------------------------------------------------------- #
# Authentication & Session
# --------------------------------------------------------------------------- #

class TestMockAuthentication:
    def test_authenticate_always_succeeds(self, mock_provider: MockVideoProvider) -> None:
        assert mock_provider.authenticate({"email": "test@example.com"}) is True

    def test_check_session_after_auth(self, mock_provider: MockVideoProvider) -> None:
        mock_provider.authenticate({})
        assert mock_provider.check_session() is True

    def test_check_session_before_auth(self, mock_provider: MockVideoProvider) -> None:
        assert mock_provider.check_session() is False

    def test_close_session(self, mock_provider: MockVideoProvider) -> None:
        mock_provider.authenticate({})
        mock_provider.close_session()
        assert mock_provider.check_session() is False


# --------------------------------------------------------------------------- #
# Capabilities
# --------------------------------------------------------------------------- #

class TestMockCapabilities:
    def test_get_capabilities(self, mock_provider: MockVideoProvider) -> None:
        caps = mock_provider.get_capabilities()
        assert isinstance(caps, GenerationCapabilities)
        assert caps.max_prompt_length > 0
        assert "16:9" in caps.supported_aspect_ratios
        assert caps.max_duration_seconds == 5.0


# --------------------------------------------------------------------------- #
# Quota
# --------------------------------------------------------------------------- #

class TestMockQuota:
    def test_initial_quota(self, mock_provider: MockVideoProvider) -> None:
        quota = mock_provider.get_quota()
        assert isinstance(quota, QuotaInfo)
        assert quota.limit == 100
        assert quota.used == 0
        assert quota.remaining == 100

    def test_quota_decreases_after_generation(self, mock_provider: MockVideoProvider) -> None:
        result = mock_provider.submit_generation("A cat video", {"target_clip_seconds": 8.0})
        assert result.success
        quota = mock_provider.get_quota()
        assert quota.used == 1
        assert quota.remaining == 99

    def test_quota_never_exhausts_in_tests(self, mock_provider: MockVideoProvider) -> None:
        # Generate 100 videos
        for i in range(100):
            result = mock_provider.submit_generation(f"Video {i}", {"target_clip_seconds": 8.0})
            assert result.success
        quota = mock_provider.get_quota()
        assert quota.used == 100
        assert quota.remaining == 0


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #

class TestMockGeneration:
    def test_submit_and_complete(self, mock_provider: MockVideoProvider) -> None:
        result = mock_provider.submit_generation("A spooky scene", {"target_clip_seconds": 8.0})
        assert result.success
        assert result.result_id is not None
        assert result.estimated_wait_seconds == 0  # instant

        # Check status
        status = mock_provider.get_generation_status(result.result_id)
        assert status == GenerationStatus.COMPLETED

    def test_download_result(self, mock_provider: MockVideoProvider) -> None:
        result = mock_provider.submit_generation("A cat", {"target_clip_seconds": 8.0})
        assert result.success

        data = mock_provider.download_result(result.result_id)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_download_to_file(self, mock_provider: MockVideoProvider, tmp_path: Path) -> None:
        result = mock_provider.submit_generation("A dog", {"target_clip_seconds": 8.0})
        dest = tmp_path / "output.mp4"
        mock_provider.download_result_to_file(result.result_id, dest)
        assert dest.exists()
        assert dest.stat().st_size > 0

    def test_failure_injection(self, mock_provider_with_failures: MockVideoProvider) -> None:
        # First two calls succeed
        r1 = mock_provider_with_failures.submit_generation("Video 1", {})
        assert r1.success
        r2 = mock_provider_with_failures.submit_generation("Video 2", {})
        assert r2.success

        # Third call fails
        r3 = mock_provider_with_failures.submit_generation("Video 3", {})
        assert not r3.success
        assert r3.error_code == "SIMULATED_ERROR"

        # Fourth call succeeds again
        r4 = mock_provider_with_failures.submit_generation("Video 4", {})
        assert r4.success

    def test_detect_no_error_on_success(self, mock_provider: MockVideoProvider) -> None:
        result = mock_provider.submit_generation("Test", {})
        err_code, err_msg = mock_provider.detect_error(result.result_id, "some response")
        assert err_code is None
        assert err_msg is None

    def test_detect_no_quota_exhaustion_when_available(self, mock_provider: MockVideoProvider) -> None:
        assert mock_provider.detect_quota_exhaustion("anything") is False


# --------------------------------------------------------------------------- #
# Registry / Factory
# --------------------------------------------------------------------------- #

class TestProviderRegistry:
    def test_create_mock_provider(self) -> None:
        provider = create_provider("mock", {"quota_limit": 50})
        assert isinstance(provider, MockVideoProvider)
        assert provider.get_quota().limit == 50

    def test_unknown_provider_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown provider"):
            create_provider("nonexistent")

    def test_create_mock_with_defaults(self) -> None:
        provider = create_provider("mock")
        assert isinstance(provider, MockVideoProvider)
        assert provider.get_quota().limit == 10000  # default
