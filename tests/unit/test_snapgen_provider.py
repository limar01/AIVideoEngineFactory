"""Tests for the SnapGen provider adapter."""

from __future__ import annotations

import pytest

from app.providers import create_provider, get_provider_config
from app.providers.base.provider import GenerationRequest
from app.providers.snapgen import SnapGenVideoProvider
from app.queue.manager import GenerationQueueManager


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_snapgen_submit_generation_and_status(monkeypatch):
    """A SnapGen job should submit and report completion through the provider API."""

    generated = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.headers = kwargs.get("headers", {})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, timeout=None):
            generated["url"] = url
            generated["json"] = json
            return FakeResponse({"job_id": "snap_123", "status": "queued"})

        async def get(self, url, timeout=None):
            return FakeResponse({"job_id": "snap_123", "status": "completed", "video_url": "https://example.com/video.mp4"})

    monkeypatch.setattr("app.providers.snapgen.snapgen_provider.httpx.AsyncClient", FakeClient)

    provider = SnapGenVideoProvider({"api_key": "demo-key", "base_url": "https://snapgen.example.com"})
    result = await provider.authenticate()
    assert result is True

    request = GenerationRequest(prompt="A beach at sunrise", duration=5, resolution="720p")
    generated_result = await provider.submit_generation(request)
    assert generated_result.job_id == "snap_123"
    assert generated_result.status == "pending"

    status = await provider.get_generation_status("snap_123")
    assert status.status == "completed"
    assert status.video_url == "https://example.com/video.mp4"

    assert generated["json"]["prompt"] == "A beach at sunrise"


def test_provider_factory_uses_config_file():
    """The app should resolve provider names from the provider config file."""
    config = get_provider_config("mock")
    assert config["enabled"] is True

    provider = create_provider("mock")
    assert provider.provider_name == "mock"

    snap_provider = create_provider("snapgen", {"api_key": "demo-key"})
    assert isinstance(snap_provider, SnapGenVideoProvider)
    assert snap_provider.provider_name == "snapgen"


def test_queue_manager_resolves_provider_by_name():
    """The queue manager should resolve provider instances through the shared factory."""
    manager = GenerationQueueManager(None)

    mock_provider = manager.get_provider("mock")
    assert mock_provider.provider_name == "mock"

    snap_provider = manager.get_provider("snapgen", {"api_key": "demo-key"})
    assert isinstance(snap_provider, SnapGenVideoProvider)
    assert snap_provider.provider_name == "snapgen"
