"""Provider registry — the only place that imports concrete providers.

Source: docs/PROVIDER_INTERFACE.md §5, docs/ARCHITECTURE.md §5.4
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_provider(name: str, cls: type) -> None:
    """Register a custom provider implementation (for extensibility)."""
    # Providers are created via factory; this exists for plugin registration
    pass


def create_provider(
    provider_name: str,
    provider_config: dict | None = None,
) -> "VideoGenerationProvider":  # type: ignore[name-defined]
    """Factory: create a provider instance by name.

    This is the single seam — all downstream code calls this factory,
    never importing concrete providers directly.
    """
    provider_config = provider_config or {}

    if provider_name == "mock":
        from app.providers.mock import MockVideoProvider
        return MockVideoProvider(
            quota_limit=provider_config.get("quota_limit", 10000),
            fail_on_call=provider_config.get("fail_on_call"),
            fail_with_error=provider_config.get("fail_with_error", "SIMULATED_ERROR"),
            output_dir=provider_config.get("output_dir"),
            min_duration=provider_config.get("min_duration", 2.0),
            max_duration=provider_config.get("max_duration", 5.0),
        )

    if provider_name == "snapgen":
        # Isolated under app/providers/snapgen/ — only imported on explicit config
        from app.providers.snapgen import SnapGenProvider
        return SnapGenProvider(
            base_url=provider_config.get("base_url", "https://snapgen.ai"),
            session_timeout_minutes=provider_config.get("session_timeout_minutes", 30),
            generation_timeout_minutes=provider_config.get("generation_timeout_minutes", 15),
            polling_interval_seconds=provider_config.get("polling_interval_seconds", 10),
        )

    raise ValueError(
        f"Unknown provider: '{provider_name}'. Use 'mock' or 'snapgen'."
    )


# Late import for type hints (avoids circular import)
from app.providers.base import VideoGenerationProvider  # noqa: E402
