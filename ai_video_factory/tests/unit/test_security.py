"""Unit tests for configuration loading and security primitives."""
import os
from pathlib import Path

import pytest
import yaml

from app.core.config import get_config, get_settings, reload_settings
from app.core.security import (
    decrypt_dict,
    decrypt_value,
    encrypt_dict,
    encrypt_value,
    generate_session_token,
    hash_password,
    verify_password,
)


# --------------------------------------------------------------------------- #
# Config tests
# --------------------------------------------------------------------------- #

class TestConfig:
    def test_get_settings_loads_factory_yaml(self) -> None:
        settings = get_settings()
        assert settings.app_name == "AI Video Factory"
        assert settings.default_niche == "horror"
        assert settings.default_target_seconds == 600

    def test_provider_name_from_config(self) -> None:
        settings = get_settings()
        assert settings.provider_name == "mock"  # config/providers.yaml default

    def test_story_engine_from_config(self) -> None:
        settings = get_settings()
        assert settings.story_engine == "hermes"

    def test_get_config_nested_key(self) -> None:
        val = get_config("quota", "policy.fallback_daily_limit", 99)
        assert val == 5

    def test_get_config_missing_returns_default(self) -> None:
        val = get_config("quota", "nonexistent.key", 42)
        assert val == 42

    def test_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VAF_API_KEY", "test-secret-key")
        settings = reload_settings()
        assert settings.api_key == "test-secret-key"

    def test_env_var_overrides_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("VAF_API_PORT", "9999")
        settings = reload_settings()
        assert settings.api_port == 9999


# --------------------------------------------------------------------------- #
# Security tests
# --------------------------------------------------------------------------- #

class TestPasswordHashing:
    def test_hash_and_verify_password(self) -> None:
        password = "Pppp0000"
        hashed = hash_password(password)
        assert hashed != password
        assert hashed.startswith("pbkdf2_sha256$")
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self) -> None:
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_verify_empty_returns_false(self) -> None:
        hashed = hash_password("test")
        assert verify_password("", hashed) is False
        assert verify_password("test", "") is False

    def test_hash_is_randomized(self) -> None:
        """Same password should produce different hashes (salt)."""
        h1 = hash_password("samepass")
        h2 = hash_password("samepass")
        assert h1 != h2
        assert verify_password("samepass", h1) is True
        assert verify_password("samepass", h2) is True

    def test_hash_empty_password_raises(self) -> None:
        with pytest.raises(ValueError):
            hash_password("")


class TestEncryption:
    @pytest.fixture(autouse=True)
    def _set_encryption_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Ensure an encryption key is available for encryption tests."""
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        monkeypatch.setenv("VAF_ENCRYPTION_KEY", key)

    def test_encrypt_decrypt_value(self) -> None:

        original = "my_secret_cookie_value"
        encrypted = encrypt_value(original)
        assert encrypted != original
        assert decrypt_value(encrypted) == original

    def test_encrypt_decrypt_dict(self) -> None:
        original = {"key": "value", "nested": {"num": 42}}
        encrypted = encrypt_dict(original)
        assert encrypted != "value"
        decrypted = decrypt_dict(encrypted)
        assert decrypted == original

    def test_encrypt_empty_dict(self) -> None:
        encrypted = encrypt_dict({})
        decrypted = decrypt_dict(encrypted)
        assert decrypted == {}

    def test_decrypt_empty_returns_empty(self) -> None:
        assert decrypt_value("") == ""
        assert decrypt_dict("") == {}


class TestSessionTokens:
    def test_generate_session_token(self) -> None:
        token = generate_session_token()
        assert len(token) >= 32  # token_urlsafe(32) produces ~43 chars

    def test_tokens_are_unique(self) -> None:
        t1 = generate_session_token()
        t2 = generate_session_token()
        assert t1 != t2


class TestLogRedaction:
    def test_redact_dict_redacts_sensitive_keys(self) -> None:
        from app.core.log_redactor import redact_dict
        data = {"api_key": "secret123", "name": "public", "password": "hunter2"}
        redacted = redact_dict(data)
        assert redacted["api_key"] == "***REDACTED***"
        assert redacted["name"] == "public"
        assert redacted["password"] == "***REDACTED***"

    def test_redact_text_strips_api_keys(self) -> None:
        from app.core.log_redactor import redact_text
        text = "Using api_key=sk-abc123def456ghi789jkl to call the API"
        redacted = redact_text(text)
        assert "sk-abc123def456ghi789jkl" not in redacted
        assert "***REDACTED***" in redacted
