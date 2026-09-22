"""
Tests for provider module.
"""
import pytest
from app.providers.base.provider import (
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
    QuotaInfo,
)


class TestGenerationRequest:
    """Test GenerationRequest class"""
    
    def test_create_request(self):
        """Test creating a basic generation request"""
        req = GenerationRequest(
            prompt="A cat walking",
            duration=8,
            resolution="720p",
        )
        
        assert req.prompt == "A cat walking"
        assert req.duration == 8
        assert req.resolution == "720p"
        assert req.aspect_ratio == "16:9"
    
    def test_request_to_dict(self):
        """Test converting request to dictionary"""
        req = GenerationRequest(
            prompt="Test prompt",
            duration=10,
            negative_prompt="blurry",
            seed=42,
        )
        
        d = req.to_dict()
        assert d["prompt"] == "Test prompt"
        assert d["duration"] == 10
        assert d["negative_prompt"] == "blurry"
        assert d["seed"] == 42


class TestGenerationResult:
    """Test GenerationResult class"""
    
    def test_create_result(self):
        """Test creating a result"""
        result = GenerationResult(
            job_id="test_123",
            status="completed",
            video_path="/path/to/video.mp4",
        )
        
        assert result.job_id == "test_123"
        assert result.status == "completed"
        assert result.video_path == "/path/to/video.mp4"
    
    def test_is_completed(self):
        """Test completion check"""
        completed = GenerationResult(job_id="1", status="completed")
        pending = GenerationResult(job_id="2", status="pending")
        failed = GenerationResult(job_id="3", status="failed")
        
        assert completed.is_completed() is True
        assert pending.is_completed() is False
        assert failed.is_completed() is False
    
    def test_is_failed(self):
        """Test failure check"""
        completed = GenerationResult(job_id="1", status="completed")
        pending = GenerationResult(job_id="2", status="pending")
        failed = GenerationResult(job_id="3", status="failed")
        
        assert failed.is_failed() is True
        assert completed.is_failed() is False
        assert pending.is_failed() is False


class TestProviderCapabilities:
    """Test ProviderCapabilities class"""
    
    def test_create_capabilities(self):
        """Test creating capabilities"""
        caps = ProviderCapabilities(
            provider_name="test",
            supported_resolutions=["720p", "1080p"],
            min_duration=3,
            max_duration=10,
            supported_models=["fast", "quality"],
        )
        
        assert caps.provider_name == "test"
        assert "720p" in caps.supported_resolutions
        assert caps.min_duration == 3
        assert caps.max_duration == 10
    
    def test_capabilities_to_dict(self):
        """Test converting capabilities to dictionary"""
        caps = ProviderCapabilities(
            provider_name="test",
            supported_resolutions=["720p"],
            min_duration=5,
            max_duration=15,
            supported_models=["model1"],
        )
        
        d = caps.to_dict()
        assert d["provider_name"] == "test"
        assert d["min_duration"] == 5


class TestQuotaInfo:
    """Test QuotaInfo class"""
    
    def test_create_quota(self):
        """Test creating quota info"""
        quota = QuotaInfo(
            daily_limit=10,
            daily_used=3,
            daily_remaining=7,
        )
        
        assert quota.daily_limit == 10
        assert quota.daily_used == 3
        assert quota.daily_remaining == 7
        assert quota.is_exhausted is False
    
    def test_quota_exhausted(self):
        """Test exhausted quota"""
        quota = QuotaInfo(
            daily_limit=10,
            daily_used=10,
            daily_remaining=0,
            is_exhausted=True,
        )
        
        assert quota.is_exhausted is True
        assert quota.can_generate() is False
    
    def test_quota_can_generate(self):
        """Test quota allows generation"""
        quota = QuotaInfo(
            daily_limit=10,
            daily_used=5,
            daily_remaining=5,
        )
        
        assert quota.can_generate() is True

    def test_zero_remaining_quota_is_exhausted(self):
        """Test zero remaining quota is preserved and treated as exhausted."""
        quota = QuotaInfo(
            daily_limit=None,
            daily_used=10,
            daily_remaining=0,
        )

        assert quota.daily_remaining == 0
        assert quota.is_exhausted is True
        assert quota.can_generate() is False
