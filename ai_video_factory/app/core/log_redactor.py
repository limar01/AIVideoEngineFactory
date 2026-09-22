"""Log redaction middleware/filter — strips sensitive data from log output.

Source: Master Spec §2 (free-tier), SECURITY-001
"""
from __future__ import annotations

import logging
import re
from typing import Any

# Patterns for sensitive data that must never appear in logs
_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # API keys
    (re.compile(r"(?i)(api[_-]?key|token|secret)([\"':\s=]+)([A-Za-z0-9_\-]{20,})"),
     r"\1\2***REDACTED***"),
    # Bearer tokens
    (re.compile(r"(?i)(Bearer\s+)([A-Za-z0-9_\-\.]+)"), r"\1***REDACTED***"),
    # Session cookies
    (re.compile(r"(session[_-]?cookie|cookies?)=\{[^}]*\}", re.IGNORECASE),
     r"\1={***REDACTED***}"),
    # Password fields in JSON
    (re.compile(r'"(password|credentials|session_state)"\s*:\s*"[^"]*"', re.IGNORECASE),
     r'"\1":"***REDACTED***"'),
    # Google OAuth tokens
    (re.compile(r"(access[_-]?token|refresh[_-]?token)[\"'=: ]+([A-Za-z0-9_\-\.]+)"),
     r"\1=***REDACTED***"),
    # Credit card numbers (basic pattern)
    (re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"), "***REDACTED***"),
]

# Fields that should always be redacted if they appear in a dict/log line
_SENSITIVE_KEYS = frozenset({
    "password", "api_key", "apikey", "token", "secret",
    "credentials", "session_state", "session_cookie",
    "access_token", "refresh_token", "encryption_key",
    "private_key", "password_hash",
})


class RedactingFilter(logging.Filter):
    """Logging filter that redacts sensitive data from log records.

    Usage:
        logger = logging.getLogger("myapp")
        logger.addFilter(RedactingFilter())
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(str(record.msg))
        if record.args:
            record.args = tuple(
                self._redact(str(a)) if isinstance(a, str) else a
                for a in record.args
            )
        # Redact the formatted message
        if hasattr(record, "getMessage"):
            record.message = self._redact(record.getMessage())  # type: ignore[attr-defined]
        return True

    @staticmethod
    def _redact(text: str) -> str:
        """Apply all redaction patterns to a text string."""
        for pattern, replacement in _REDACT_PATTERNS:
            text = pattern.sub(replacement, text)
        return text


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *data* with sensitive keys replaced by '***REDACTED***'."""
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS:
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = redact_dict(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_dict(v) if isinstance(v, dict) else v
                for v in value
            ]
        else:
            redacted[key] = value
    return redacted


def redact_text(text: str) -> str:
    """Redact sensitive data from arbitrary text (for log lines)."""
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
