"""
AI Video Factory - Mock Provider

Mock provider for testing and development.
Simulates video generation without using real API calls.
"""
import asyncio
import random
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path

from app.providers.base.provider import (
    VideoGenerationProvider,
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
    QuotaInfo,
)


class MockVideoProvider(VideoGenerationProvider):
    """
    Mock video generation provider for testing.
    
    This provider simulates the generation process with configurable
    success rates and delays. It does not make any real API calls.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("mock", config or {})
        
        # Configuration from config or defaults
        self.generation_time = config.get("generation_time_seconds", 5)
        self.success_rate = config.get("success_rate", 0.95)
        self.max_daily_generations = config.get("max_daily_generations", 1000)
        self.clip_duration_limits = config.get("clip_duration_limits", {"min": 2, "max": 30})
        self.resolution_limits = config.get("resolution_limits", ["480p", "720p", "1080p"])
        self.supported_models = config.get("supported_models", ["mock-fast", "mock-quality"])
        self.concurrent_limit = config.get("concurrent_limit", 5)
        
        # State
        self._daily_used = 0
        self._reset_time = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        self._active_jobs: Dict[str, GenerationResult] = {}
        self._authenticated = False
    
    async def authenticate(self) -> bool:
        """Mock authentication - always succeeds"""
        await asyncio.sleep(0.1)  # Simulate network delay
        self._authenticated = True
        return True
    
    async def check_session(self) -> bool:
        """Check if session is valid"""
        return self._authenticated
    
    async def get_capabilities(self) -> ProviderCapabilities:
        """Get mock provider capabilities"""
        return ProviderCapabilities(
            provider_name="mock",
            supported_resolutions=self.resolution_limits,
            min_duration=self.clip_duration_limits["min"],
            max_duration=self.clip_duration_limits["max"],
            supported_models=self.supported_models,
            supports_negative_prompts=True,
            supports_seeds=True,
            max_concurrent_generations=self.concurrent_limit,
        )
    
    async def get_quota(self) -> QuotaInfo:
        """Get current quota status"""
        # Check if reset time has passed
        now = datetime.utcnow()
        if now >= self._reset_time:
            self._daily_used = 0
            self._reset_time = now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
        
        remaining = self.max_daily_generations - self._daily_used
        
        return QuotaInfo(
            daily_limit=self.max_daily_generations,
            daily_used=self._daily_used,
            daily_remaining=remaining,
            reset_time=self._reset_time,
            is_exhausted=remaining <= 0,
            quota_type="daily",
        )
    
    async def submit_generation(
        self, 
        request: GenerationRequest
    ) -> GenerationResult:
        """Submit a mock generation request"""
        if not self._authenticated:
            return GenerationResult(
                job_id="",
                status="failed",
                error_message="Not authenticated",
            )
        
        # Check quota
        quota = await self.get_quota()
        if not quota.can_generate():
            return GenerationResult(
                job_id="",
                status="failed",
                error_message="Quota exhausted",
            )
        
        # Generate job ID
        job_id = f"mock_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{random.randint(1000, 9999)}"
        
        # Create result in pending state
        result = GenerationResult(
            job_id=job_id,
            status="pending",
            metadata={
                "prompt": request.prompt,
                "duration": request.duration,
                "resolution": request.resolution,
                "submitted_at": datetime.utcnow().isoformat(),
            }
        )
        
        # Store job for status tracking
        self._active_jobs[job_id] = result
        
        # Schedule completion
        asyncio.create_task(self._simulate_generation(job_id, request))
        
        # Increment quota usage
        self._daily_used += 1
        
        return result
    
    async def _simulate_generation(
        self, 
        job_id: str, 
        request: GenerationRequest
    ):
        """Simulate the generation process"""
        # Update to processing
        if job_id in self._active_jobs:
            self._active_jobs[job_id].status = "processing"
        
        # Wait for simulated generation time
        await asyncio.sleep(self.generation_time)
        
        # Determine success/failure
        success = random.random() < self.success_rate
        
        if success:
            # Create a dummy video file
            output_dir = Path(self.config.get("output_dir", "./output"))
            output_dir.mkdir(parents=True, exist_ok=True)
            video_path = output_dir / f"{job_id}.mp4"
            
            # For mock, we just create an empty file as placeholder
            # In real testing, you might want to create actual test videos
            video_path.touch()
            
            self._active_jobs[job_id].status = "completed"
            self._active_jobs[job_id].video_path = str(video_path)
            self._active_jobs[job_id].metadata["completed_at"] = datetime.utcnow().isoformat()
        else:
            self._active_jobs[job_id].status = "failed"
            self._active_jobs[job_id].error_message = "Random failure (simulated)"
            self._active_jobs[job_id].metadata["failed_at"] = datetime.utcnow().isoformat()
    
    async def get_generation_status(self, job_id: str) -> GenerationResult:
        """Get status of a generation job"""
        if job_id not in self._active_jobs:
            return GenerationResult(
                job_id=job_id,
                status="failed",
                error_message="Job not found",
            )
        
        return self._active_jobs[job_id]
    
    async def download_result(
        self, 
        job_id: str, 
        download_path: str
    ) -> bool:
        """Download mock result"""
        if job_id not in self._active_jobs:
            return False
        
        result = self._active_jobs[job_id]
        if result.status != "completed":
            return False
        
        # Copy or move the file
        if result.video_path:
            src = Path(result.video_path)
            dst = Path(download_path)
            
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                # For mock, just copy the content (empty file)
                dst.write_bytes(src.read_bytes())
                return True
        
        return False
    
    async def detect_error(self, result: GenerationResult) -> Optional[str]:
        """Detect errors in result"""
        if result.is_failed():
            return result.error_message or "Unknown error"
        return None
    
    async def detect_quota_exhaustion(self) -> bool:
        """Detect if quota is exhausted"""
        quota = await self.get_quota()
        return quota.is_exhausted
    
    async def close_session(self) -> None:
        """Close mock session"""
        self._authenticated = False
        self._active_jobs.clear()
    
    def reset_quota(self):
        """Reset daily quota (for testing)"""
        self._daily_used = 0
        self._reset_time = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)


def create_mock_provider(config: Optional[Dict[str, Any]] = None) -> MockVideoProvider:
    """Factory function to create mock provider"""
    return MockVideoProvider(config)
