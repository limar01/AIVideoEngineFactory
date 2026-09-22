"""Application configuration — loads YAML config + resolves env overrides.

Source: docs/CONFIG_SPEC.md §2–§8
All config is loaded from YAML files under ``config/``.  Environment
variables override sensitive values (API keys, encryption key).
"""
from __future__ import annotations

import os
import re
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _project_root() -> Path:
    """Find the project root by looking for config/ + app/ + pyproject.toml."""
    candidate = Path.cwd()
    for parent in (candidate, *candidate.parents):
        if (parent / "config").is_dir() and (parent / "pyproject.toml").exists():
            return parent
    return candidate


PROJECT_ROOT = _project_root()
CONFIG_DIR = PROJECT_ROOT / "config"


def _load_yaml(name: str) -> dict[str, Any]:
    """Load a YAML config file, returning {} if it doesn't exist."""
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


_ENV_PATTERN = re.compile(r"^VAF_")


def _resolve_env(value: str) -> str:
    """Resolve environment-variable references like ${VAR_NAME}."""
    if not isinstance(value, str):
        return value
    match = re.match(r"^\$\{(\w+)\}$", value)
    if match:
        env_var = match.group(1)
        resolved = os.environ.get(env_var)
        if resolved:
            return resolved
    return value


def _deep_resolve(obj: Any) -> Any:
    """Recursively resolve ${ENV_VAR} references in a config tree."""
    if isinstance(obj, str):
        return _resolve_env(obj)
    if isinstance(obj, dict):
        return {k: _deep_resolve(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_resolve(v) for v in obj]
    return obj


# --------------------------------------------------------------------------- #
# Pydantic-settings — env overrides
# --------------------------------------------------------------------------- #

class AppSettings(BaseSettings):
    """Settings resolved from ``config/factory.yaml`` and environment variables."""

    model_config = {
        "env_prefix": "VAF_",
        "extra": "ignore",
        "yaml_file": None,  # we load YAML manually
    }

    # From config/factory.yaml
    app_name: str = "AI Video Factory"
    environment: str = "development"
    log_level: str = "INFO"

    # Paths (resolved relative to project root)
    projects_dir: Path = Field(default_factory=lambda: _project_root() / "projects")
    database_path: Path = Field(default_factory=lambda: _project_root() / "database" / "factory.db")
    logs_dir: Path = Field(default_factory=lambda: _project_root() / "logs")

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8890

    # Pipeline
    default_clip_seconds: int = 8
    max_concurrent_jobs: int = 1
    default_niche: str = "horror"
    default_target_seconds: int = 600

    @computed_field
    @property
    def api_key(self) -> str:
        return os.environ.get("VAF_API_KEY", "")

    @computed_field
    @property
    def encryption_key(self) -> str:
        return os.environ.get("VAF_ENCRYPTION_KEY", "")

    @computed_field
    @property
    def provider_name(self) -> str:
        providers = _load_yaml("providers.yaml")
        return providers.get("provider", "mock")

    @computed_field
    @property
    def story_engine(self) -> str:
        story_cfg = _load_yaml("story.yaml")
        return story_cfg.get("engine", "hermes")

    @computed_field
    @property
    def audio_provider(self) -> str:
        audio_cfg = _load_yaml("audio.yaml")
        return audio_cfg.get("provider", "silent")


# --------------------------------------------------------------------------- #
# Config accessor (loaded once, cached)
# --------------------------------------------------------------------------- #

_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    """Return the singleton app settings."""
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings


def reload_settings() -> AppSettings:
    """Force a reload of settings (for testing / config changes)."""
    global _settings
    _settings = AppSettings()
    return _settings


def get_config(section: str, key: str, default: Any = None) -> Any:
    """Read a value from a config YAML file.

    Examples:
        get_config("providers", "provider")  # from providers.yaml
        get_config("quota", "policy.fallback_daily_limit")  # nested
    """
    data = _deep_resolve(_load_yaml(f"{section}.yaml"))
    node: Any = data
    for part in key.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


def get_quota_config() -> dict[str, Any]:
    """Return the quota policy config."""
    return _load_yaml("quota.yaml").get("policy", {})
