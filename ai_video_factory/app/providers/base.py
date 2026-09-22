"""VideoGenerationProvider ABC — the provider abstraction interface.

Source: docs/PROVIDER_INTERFACE.md §2, Master Spec §18

All video providers (Mock, SnapGen, etc.) implement this interface.
The provider interface is the only seam between the generation pipeline
and the actual video generation service.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class GenerationStatus(Enum):
    """Status of a generation request."""
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass
class GenerationCapabilities:
    """Discovered capabilities of a video provider."""
    max_prompt_length: int
    supported_aspect_ratios: list[str]
    supported_resolutions: list[str]
    max_duration_seconds: float
    min_duration_seconds: float
    supports_narration: bool


@dataclass
class QuotaInfo:
    """Quota/usage information from a provider.

    All fields may be None if the provider does not expose quota data.
    """
    limit: Optional[int] = None
    used: Optional[int] = None
    remaining: Optional[int] = None
    reset_time: Optional[str] = None  # ISO timestamp


@dataclass
class GenerationResult:
    """Result of a submit_generation call."""
    success: bool
    result_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    download_url: Optional[str] = None
    estimated_wait_seconds: Optional[int] = None


class VideoGenerationProvider(ABC):
    """Abstract base class for video generation providers.

    All providers must implement this interface.
    Authentication, 2FA, and CAPTCHA must remain user-controlled (spec §2, §5).
    """

    PROVIDER_NAME: str = "abstract"

    @abstractmethod
    def authenticate(self, account_credentials: dict) -> bool:
        """Verify or establish an authenticated session.

        For automated use, loads stored session state and validates it.
        If session has expired, returns False — does NOT attempt interactive login
        (2FA/CAPTCHA require user action per spec §2 and §5).

        Returns: True if session is valid, False if re-authentication needed.
        """

    @abstractmethod
    def check_session(self) -> bool:
        """Check whether the current session is still valid and authenticated."""

    @abstractmethod
    def get_capabilities(self) -> GenerationCapabilities:
        """Discover provider capabilities."""

    @abstractmethod
    def get_quota(self) -> QuotaInfo:
        """Check current account quota/usage limits."""

    @abstractmethod
    def submit_generation(self, prompt: str, scene_metadata: dict) -> GenerationResult:
        """Submit a generation request."""

    @abstractmethod
    def get_generation_status(self, result_id: str) -> GenerationStatus:
        """Poll for the status of a submitted generation."""

    @abstractmethod
    def download_result(self, result_id: str) -> bytes:
        """Download a completed generation result (raw bytes)."""

    @abstractmethod
    def detect_error(self, result_id: str, raw_response: str) -> tuple[Optional[str], Optional[str]]:
        """Parse a raw response and extract error info.

        Returns: (error_code, error_message) or (None, None) if no error.
        """

    @abstractmethod
    def detect_quota_exhaustion(self, raw_response: str) -> bool:
        """Determine if the raw response indicates quota/rate-limit exhaustion."""

    @abstractmethod
    def close_session(self) -> None:
        """Cleanly close the provider session."""
