"""
AI Video Factory - Providers Module

Provider abstraction layer for video generation services.
"""
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from app.providers.base.provider import (
    VideoGenerationProvider,
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
    QuotaInfo,
)
from app.providers.mock.mock_provider import (
    MockVideoProvider,
    create_mock_provider,
)
from app.providers.snapgen.snapgen_provider import SnapGenVideoProvider


def _providers_config_path() -> Path:
    """Return the app-level providers config file path."""
    return Path(__file__).resolve().parent.parent.parent / "config" / "providers.yaml"


def get_provider_config(provider_name: str) -> Dict[str, Any]:
    """Load and return provider config for a named provider."""
    config_path = _providers_config_path()
    if not config_path.exists():
        return {}

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    return data.get(provider_name, {}) or {}


def create_provider(
    provider_name: str,
    config: Optional[Dict[str, Any]] = None,
) -> VideoGenerationProvider:
    """Instantiate a provider instance by name using the config file as defaults."""
    normalized_name = (provider_name or "").lower().strip()
    provider_config = get_provider_config(normalized_name)
    if config:
        provider_config = {**provider_config, **config}

    if normalized_name == "mock":
        return create_mock_provider(provider_config)
    if normalized_name == "snapgen":
        return SnapGenVideoProvider(provider_config)

    raise ValueError(f"Unsupported provider: {provider_name}")


__all__ = [
    "VideoGenerationProvider",
    "GenerationRequest",
    "GenerationResult",
    "ProviderCapabilities",
    "QuotaInfo",
    "MockVideoProvider",
    "SnapGenVideoProvider",
    "create_mock_provider",
    "create_provider",
    "get_provider_config",
]
