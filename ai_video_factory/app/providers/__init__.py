"""Video generation providers package.

Source: docs/ARCHITECTURE.md §3 (Module Map), docs/PROVIDER_INTERFACE.md
"""
from app.providers.base import (
    GenerationCapabilities,
    GenerationResult,
    GenerationStatus,
    QuotaInfo,
    VideoGenerationProvider,
)

__all__ = [
    "VideoGenerationProvider",
    "GenerationCapabilities",
    "GenerationResult",
    "GenerationStatus",
    "QuotaInfo",
]
