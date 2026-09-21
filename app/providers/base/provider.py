"""
AI Video Factory - Provider Base Interface

Abstract base class defining the interface for video generation providers.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from datetime import datetime


class GenerationRequest:
    """Video generation request"""
    
    def __init__(
        self,
        prompt: str,
        duration: int,
        resolution: str = "720p",
        aspect_ratio: str = "16:9",
        model: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        **kwargs
    ):
        self.prompt = prompt
        self.duration = duration
        self.resolution = resolution
        self.aspect_ratio = aspect_ratio
        self.model = model
        self.negative_prompt = negative_prompt
        self.seed = seed
        self.extra_params = kwargs
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "prompt": self.prompt,
            "duration": self.duration,
            "resolution": self.resolution,
            "aspect_ratio": self.aspect_ratio,
            "model": self.model,
            "negative_prompt": self.negative_prompt,
            "seed": self.seed,
            **self.extra_params
        }


class GenerationResult:
    """Video generation result"""
    
    def __init__(
        self,
        job_id: str,
        status: str,
        video_url: Optional[str] = None,
        video_path: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.job_id = job_id
        self.status = status  # pending, processing, completed, failed
        self.video_url = video_url
        self.video_path = video_path
        self.error_message = error_message
        self.metadata = metadata or {}
        self.created_at = datetime.utcnow()
    
    def is_completed(self) -> bool:
        """Check if generation is complete"""
        return self.status == "completed"
    
    def is_failed(self) -> bool:
        """Check if generation failed"""
        return self.status == "failed"
    
    def is_pending(self) -> bool:
        """Check if generation is still pending"""
        return self.status in ("pending", "processing")


class ProviderCapabilities:
    """Provider capabilities"""
    
    def __init__(
        self,
        provider_name: str,
        supported_resolutions: List[str],
        min_duration: int,
        max_duration: int,
        supported_models: List[str],
        supports_negative_prompts: bool = True,
        supports_seeds: bool = True,
        max_concurrent_generations: int = 1,
        **kwargs
    ):
        self.provider_name = provider_name
        self.supported_resolutions = supported_resolutions
        self.min_duration = min_duration
        self.max_duration = max_duration
        self.supported_models = supported_models
        self.supports_negative_prompts = supports_negative_prompts
        self.supports_seeds = supports_seeds
        self.max_concurrent_generations = max_concurrent_generations
        self.extra_capabilities = kwargs
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "provider_name": self.provider_name,
            "supported_resolutions": self.supported_resolutions,
            "min_duration": self.min_duration,
            "max_duration": self.max_duration,
            "supported_models": self.supported_models,
            "supports_negative_prompts": self.supports_negative_prompts,
            "supports_seeds": self.supports_seeds,
            "max_concurrent_generations": self.max_concurrent_generations,
            **self.extra_capabilities
        }


class QuotaInfo:
    """Quota information"""
    
    def __init__(
        self,
        daily_limit: Optional[int] = None,
        daily_used: int = 0,
        daily_remaining: Optional[int] = None,
        reset_time: Optional[datetime] = None,
        is_exhausted: bool = False,
        quota_type: str = "daily",
        **kwargs
    ):
        self.daily_limit = daily_limit
        self.daily_used = daily_used
        self.daily_remaining = daily_remaining or (
            daily_limit - daily_used if daily_limit else None
        )
        self.reset_time = reset_time
        self.is_exhausted = is_exhausted or (
            self.daily_remaining is not None and self.daily_remaining <= 0
        )
        self.quota_type = quota_type
        self.extra_info = kwargs
    
    def can_generate(self) -> bool:
        """Check if generation is allowed under quota"""
        return not self.is_exhausted


class VideoGenerationProvider(ABC):
    """
    Abstract base class for video generation providers.
    
    All provider implementations must inherit from this class and
    implement all abstract methods.
    """
    
    def __init__(self, provider_name: str, config: Dict[str, Any]):
        self.provider_name = provider_name
        self.config = config
        self._authenticated = False
        self._session = None
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Authenticate with the provider.
        
        Returns:
            bool: True if authentication successful
            
        Note: 
            This method should NOT automate CAPTCHA solving or bypass 2FA.
            If human verification is required, set requires_attention flag
            and let the user handle it.
        """
        pass
    
    @abstractmethod
    async def check_session(self) -> bool:
        """
        Check if current session is valid.
        
        Returns:
            bool: True if session is valid
        """
        pass
    
    @abstractmethod
    async def get_capabilities(self) -> ProviderCapabilities:
        """
        Get provider capabilities.
        
        Returns:
            ProviderCapabilities: Provider's capabilities
        """
        pass
    
    @abstractmethod
    async def get_quota(self) -> QuotaInfo:
        """
        Get current quota status.
        
        Returns:
            QuotaInfo: Current quota information
        """
        pass
    
    @abstractmethod
    async def submit_generation(
        self, 
        request: GenerationRequest
    ) -> GenerationResult:
        """
        Submit a video generation request.
        
        Args:
            request: Generation request with prompt and parameters
            
        Returns:
            GenerationResult: Result with job ID for tracking
        """
        pass
    
    @abstractmethod
    async def get_generation_status(self, job_id: str) -> GenerationResult:
        """
        Get status of a generation job.
        
        Args:
            job_id: Job ID from submit_generation
            
        Returns:
            GenerationResult: Current job status
        """
        pass
    
    @abstractmethod
    async def download_result(
        self, 
        job_id: str, 
        download_path: str
    ) -> bool:
        """
        Download generated video.
        
        Args:
            job_id: Job ID of completed generation
            download_path: Local path to save video
            
        Returns:
            bool: True if download successful
        """
        pass
    
    @abstractmethod
    async def detect_error(self, result: GenerationResult) -> Optional[str]:
        """
        Detect errors in generation result.
        
        Args:
            result: Generation result to analyze
            
        Returns:
            Optional[str]: Error message if error detected, None otherwise
        """
        pass
    
    @abstractmethod
    async def detect_quota_exhaustion(self) -> bool:
        """
        Detect if quota has been exhausted.
        
        Returns:
            bool: True if quota is exhausted
        """
        pass
    
    @abstractmethod
    async def close_session(self) -> None:
        """
        Close provider session and cleanup resources.
        """
        pass
    
    async def validate_request(self, request: GenerationRequest) -> bool:
        """
        Validate generation request against provider capabilities.
        
        Args:
            request: Request to validate
            
        Returns:
            bool: True if request is valid
        """
        capabilities = await self.get_capabilities()
        
        # Check resolution
        if request.resolution not in capabilities.supported_resolutions:
            return False
        
        # Check duration
        if not (capabilities.min_duration <= request.duration <= capabilities.max_duration):
            return False
        
        # Check model
        if request.model and request.model not in capabilities.supported_models:
            return False
        
        return True
    
    async def format_prompt(
        self, 
        prompt: str, 
        request: GenerationRequest
    ) -> str:
        """
        Format prompt for provider-specific requirements.
        
        Override this method for provider-specific prompt formatting.
        
        Args:
            prompt: Original prompt
            request: Generation request
            
        Returns:
            str: Formatted prompt
        """
        return prompt
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(provider={self.provider_name})"
