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

    if provider_name == "snapgen-pool":
        # Multi-account pool backed by the Account Vault (~/.snapgen-vault)
        from app.providers.vault import AccountVault, PoolSnapGenProvider

        vault = AccountVault()
        if vault.authenticated_count() == 0:
            raise RuntimeError(
                "snapgen-pool: no authenticated accounts in vault. "
                "Run: aivf vault create-account + open-login + mark-logged-in"
            )
        return PoolSnapGenProvider(
            vault=vault,
            headless=provider_config.get("headless", True),
            daily_limit_per_account=provider_config.get("daily_limit_per_account", 10),
        )

    if provider_name == "google-flow":
        from app.providers.google_flow import BASE_URL, GoogleFlowProvider

        return GoogleFlowProvider(
            base_url=provider_config.get("base_url", BASE_URL),
            headless=provider_config.get("headless", False),
            cookie_jar=provider_config.get("cookie_jar"),
            firefox_cookie_db=provider_config.get("firefox_cookie_db"),
            download_dir=provider_config.get(
                "download_dir", "~/Data/gf-downloads"
            ),
            cdp_port=provider_config.get("cdp_port"),
            generation_timeout_seconds=provider_config.get(
                "generation_timeout_seconds", 300
            ),
        )

    if provider_name == "meta-vibes":
        from app.providers.meta_vibes import MetaVibesProvider

        return MetaVibesProvider(
            base_url=provider_config.get("base_url", "https://vibes.ai"),
            cookie_jar=provider_config.get("cookie_jar"),
            download_dir=provider_config.get(
                "download_dir", "~/Data/meta-vibes-downloads"
            ),
            generation_timeout_seconds=provider_config.get(
                "generation_timeout_seconds", 600
            ),
            poll_interval_seconds=provider_config.get(
                "poll_interval_seconds", 10
            ),
            user_agent=provider_config.get("user_agent"),
        )

    if provider_name == "meta-ai-browser":
        from app.providers.meta_ai_browser import MetaAIBrowserProvider

        return MetaAIBrowserProvider(
            download_dir=provider_config.get(
                "download_dir", "~/Data/meta-ai-downloads"
            ),
            cookie_jar_path=provider_config.get(
                "cookie_jar_path", "~/.meta-ai-cookies.json"
            ),
            cdp_port=provider_config.get("cdp_port", 9228),
        )

    raise ValueError(
        f"Unknown provider: '{provider_name}'. "
        "Use 'mock', 'snapgen', 'snapgen-pool', 'google-flow', 'meta-vibes', or 'meta-ai-browser'."
    )


# Late import for type hints (avoids circular import)
from app.providers.base import VideoGenerationProvider  # noqa: E402