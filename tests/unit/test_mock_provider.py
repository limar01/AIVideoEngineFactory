"""
Tests for mock provider.
"""
from pathlib import Path

import pytest
import asyncio
from app.providers.mock.mock_provider import MockVideoProvider, create_mock_provider
from app.providers.base.provider import GenerationRequest


@pytest.fixture
def mock_provider():
    """Create mock provider for testing"""
    config = {
        "generation_time_seconds": 0.1,  # Fast for testing
        "success_rate": 1.0,  # Always succeed
        "max_daily_generations": 100,
        "output_dir": "/tmp/mock_output",
    }
    return MockVideoProvider(config)


@pytest.mark.asyncio
async def test_mock_authenticate(mock_provider):
    """Test mock authentication"""
    result = await mock_provider.authenticate()
    assert result is True
    assert mock_provider._authenticated is True


@pytest.mark.asyncio
async def test_mock_check_session(mock_provider):
    """Test session check"""
    await mock_provider.authenticate()
    assert await mock_provider.check_session() is True


@pytest.mark.asyncio
async def test_mock_capabilities(mock_provider):
    """Test getting capabilities"""
    caps = await mock_provider.get_capabilities()
    
    assert caps.provider_name == "mock"
    assert "720p" in caps.supported_resolutions
    assert caps.min_duration == 2
    assert caps.max_duration == 30


@pytest.mark.asyncio
async def test_mock_quota(mock_provider):
    """Test quota tracking"""
    quota = await mock_provider.get_quota()
    
    assert quota.daily_limit == 100
    assert quota.daily_used == 0
    assert quota.can_generate() is True


@pytest.mark.asyncio
async def test_mock_submit_generation(mock_provider):
    """Test submitting generation request"""
    await mock_provider.authenticate()
    
    request = GenerationRequest(
        prompt="A cat walking",
        duration=8,
        resolution="720p",
    )
    
    result = await mock_provider.submit_generation(request)
    
    assert result.job_id.startswith("mock_")
    assert result.status == "pending"


@pytest.mark.asyncio
async def test_mock_generation_completion(mock_provider):
    """Test full generation cycle"""
    await mock_provider.authenticate()
    
    request = GenerationRequest(
        prompt="Test video",
        duration=5,
        resolution="720p",
    )
    
    result = await mock_provider.submit_generation(request)
    job_id = result.job_id
    
    # Wait for generation to complete
    await asyncio.sleep(0.2)
    
    # Check status
    status = await mock_provider.get_generation_status(job_id)
    assert status.is_completed()
    assert status.video_path is not None


@pytest.mark.asyncio
async def test_mock_download(mock_provider, tmp_path):
    """Test downloading generated video"""
    await mock_provider.authenticate()
    
    request = GenerationRequest(
        prompt="Download test",
        duration=5,
        resolution="720p",
    )
    
    result = await mock_provider.submit_generation(request)
    await asyncio.sleep(0.2)
    
    download_path = str(tmp_path / "test_video.mp4")
    success = await mock_provider.download_result(result.job_id, download_path)
    
    assert success is True


@pytest.mark.asyncio
async def test_mock_generation_creates_non_empty_video(mock_provider):
    """Test mock generation creates a non-empty output file."""
    await mock_provider.authenticate()

    request = GenerationRequest(
        prompt="Non-empty output test",
        duration=5,
        resolution="720p",
    )

    result = await mock_provider.submit_generation(request)
    await asyncio.sleep(0.2)

    status = await mock_provider.get_generation_status(result.job_id)
    assert status.status == "completed"
    assert status.video_path is not None

    path = Path(status.video_path)
    assert path.exists()
    assert path.stat().st_size > 0


@pytest.mark.asyncio
async def test_mock_quota_exhaustion():
    """Test quota exhaustion"""
    provider = MockVideoProvider({
        "generation_time_seconds": 0.01,
        "max_daily_generations": 2,
    })
    
    await provider.authenticate()
    
    # Use up quota
    for _ in range(2):
        request = GenerationRequest(prompt="Test", duration=5)
        await provider.submit_generation(request)
    
    quota = await provider.get_quota()
    assert quota.is_exhausted is True
    assert quota.can_generate() is False


@pytest.mark.asyncio
async def test_mock_close_session(mock_provider):
    """Test closing session"""
    await mock_provider.authenticate()
    await mock_provider.close_session()
    
    assert mock_provider._authenticated is False


def test_create_mock_provider():
    """Test factory function"""
    provider = create_mock_provider()
    assert isinstance(provider, MockVideoProvider)
    assert provider.provider_name == "mock"
