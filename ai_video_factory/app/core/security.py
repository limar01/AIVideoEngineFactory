"""Security primitives: credential encryption, password hashing, session tokens.

Design
------
* **Credential encryption** — symmetric at-rest encryption with Fernet
  (``cryptography`` library: AES-128-CBC + HMAC-SHA256). Credentials and
  session blobs are encrypted before they are written to the SQLite
  ``account`` table.
* **Encryption key management** — the key is resolved from (in priority order):
    1. the ``VAF_ENCRYPTION_KEY`` environment variable (a Fernet urlsafe-base64
       32-byte key), or
    2. ``config/secrets.yaml`` -> ``security.encryption_key``.

  The key is **user-managed** and set up once. ``get_fernet()`` raises a clear
  :class:`KeyResolutionError` if no key is present so misconfiguration fails
  loudly instead of silently generating an insecure ephemeral key.
  Use :func:`ensure_encryption_key` for first-run bootstrap.
* **Password hashing** — PBKDF2-HMAC-SHA256 via the standard library
  (OWASP-recommended iteration count). No external dependency required.
* **Session tokens** — :mod:`secrets` (CSPRNG) via :func:`generate_session_token`.

No external secrets service is used; everything is local.

References: Master Spec §2 (authorization), §18.2 (security model);
``docs/ARCHITECTURE.md`` §7.2; ``docs/DB_SCHEMA.md`` §3.4 (Account table).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any

import yaml
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# OWASP 2023 recommendation for PBKDF2-HMAC-SHA256.
PBKDF2_ITERATIONS = 390_000
_PBKDF2_ALGO = "pbkdf2_sha256"
_SALT_BYTES = 16
_HASH_BYTES = 32  # SHA-256 output length

# Session token entropy (bytes of CSPRNG output -> 43 url-safe base64 chars).
SESSION_TOKEN_BYTES = 32

# Key resolution
ENCRYPTION_KEY_ENV = "VAF_ENCRYPTION_KEY"
SECRETS_CONFIG_PATH = "config/secrets.yaml"
SECRETS_CONFIG_KEY = ("security", "encryption_key")

# A value safe to embed in logs: never reveals the secret.
REDACTED = "***REDACTED***"


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class SecurityError(Exception):
    """Base class for security-layer errors."""


class KeyResolutionError(SecurityError):
    """Raised when no encryption key can be resolved from the environment."""


class DecryptionError(SecurityError):
    """Raised when a value cannot be decrypted (bad key, corrupt data, etc.)."""


# --------------------------------------------------------------------------- #
# Secrets-file / key resolution helpers
# --------------------------------------------------------------------------- #


def _project_root() -> Path:
    """Best-effort project root.

    A ``config/`` directory at the repo root or an ancestor ``app`` package
    signals the root. Falls back to the current working directory.
    """
    candidate = Path.cwd()
    for parent in (candidate, *candidate.parents):
        if (parent / "config").is_dir() and (parent / "app").is_dir():
            return parent
    return candidate


def resolve_secrets_path(path: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the secrets.yaml path.

    * If *path* is given, it is used as-is (relative to CWD if not absolute).
    * Otherwise ``config/secrets.yaml`` under the project root is used.
    """
    if path is None:
        return _project_root() / SECRETS_CONFIG_PATH
    p = Path(path)
    return p if p.is_absolute() else Path.cwd() / p


def load_secrets(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Load ``secrets.yaml`` into a plain dict. Returns ``{}`` if absent."""
    p = resolve_secrets_path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def _walk_config(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
    node: Any = data
    for k in keys:
        if isinstance(node, dict) and k in node:
            node = node[k]
        else:
            return None
    return node


def _validate_fernet_key(key: str) -> str:
    """Validate that *key* is a usable Fernet key; return it stripped."""
    key = key.strip()
    try:
        Fernet(key.encode("ascii"))
    except (ValueError, TypeError) as exc:
        raise KeyResolutionError(f"Invalid Fernet encryption key: {exc}") from exc
    return key


def get_encryption_key() -> str:
    """Resolve the Fernet key string from env or config.

    Raises :class:`KeyResolutionError` if no key is configured.
    """
    env_key = os.environ.get(ENCRYPTION_KEY_ENV)
    if env_key:
        return _validate_fernet_key(env_key)
    cfg = load_secrets()
    key = _walk_config(cfg, SECRETS_CONFIG_KEY)
    if isinstance(key, str) and key.strip():
        return _validate_fernet_key(key)
    raise KeyResolutionError(
        f"No encryption key configured. Set the {ENCRYPTION_KEY_ENV} environment "
        f"variable, or add '{'.'.join(SECRETS_CONFIG_KEY)}' to {resolve_secrets_path()}. "
        f"Run first-time bootstrap (e.g. `aivf security bootstrap-key`)."
    )


def ensure_encryption_key(
    path: str | os.PathLike[str] | None = None,
    write: bool = True,
) -> str:
    """Return a valid Fernet key, bootstrapping one on first run.

    The key is resolved from env/config first. If none exists, a new Fernet
    key is generated. When *write* is ``True`` (default) and the key did not
    come from the environment, it is persisted to ``secrets.yaml`` so it is
    stable across restarts ("user sets up once").

    Returns the key as an ASCII ``str`` (urlsafe-base64, Fernet format).
    """
    env_key = os.environ.get(ENCRYPTION_KEY_ENV)
    if env_key:
        return _validate_fernet_key(env_key)
    try:
        return get_encryption_key()
    except KeyResolutionError:
        pass

    new_key = Fernet.generate_key().decode("ascii")
    if not write:
        return new_key
    p = resolve_secrets_path(path)
    data = load_secrets(p)
    node: dict[str, Any] = data
    for k in SECRETS_CONFIG_KEY[:-1]:
        node = node.setdefault(k, {})
        if not isinstance(node, dict):
            node = {}
            data[SECRETS_CONFIG_KEY[0]] = node  # pragma: no cover - defensive
    node[SECRETS_CONFIG_KEY[-1]] = new_key
    _write_secrets(p, data)
    logger.info("Bootstrapped new encryption key into %s", p)
    return new_key


def _write_secrets(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)
    # Restrictive permissions on the secrets file.
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def get_fernet() -> Fernet:
    """Return a :class:`~cryptography.fernet.Fernet` bound to the configured key."""
    return Fernet(get_encryption_key().encode("ascii"))


# --------------------------------------------------------------------------- #
# Value encryption / decryption (credentials, session blobs)
# --------------------------------------------------------------------------- #


def _encode_text(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


def encrypt_value(value: str | bytes | dict | list | None) -> str:
    """Encrypt an arbitrary JSON-serialisable value (or raw str/bytes).

    Dicts/lists are JSON-serialised before encryption so the stored blob is
    deterministic-ish and never leaks plaintext. Returns a Fernet token
    (ASCII ``str``) safe to persist.
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    else:
        payload = _encode_text(value)
    return get_fernet().encrypt(payload).decode("ascii")


def decrypt_value(token: str | None) -> str:
    """Decrypt a Fernet token back to the original text (``str``)."""
    if not token:
        return ""
    try:
        return get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptionError(
            "Failed to decrypt value: the encryption key may have changed or "
            "the data is corrupted."
        ) from exc


def decrypt_json(token: str | None) -> Any:
    """Decrypt a Fernet token and parse it as JSON."""
    text = decrypt_value(token)
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DecryptionError(f"Decrypted payload was not valid JSON: {exc}") from exc


def encrypt_dict(data: dict[str, Any] | None) -> str:
    """Encrypt a dict (JSON-serialised) — convenience alias for ``encrypt_value``."""
    return encrypt_value(data)


def decrypt_dict(token: str | None) -> dict[str, Any]:
    """Decrypt a Fernet token into a dict (empty dict for empty/missing tokens)."""
    if not token:
        return {}
    result = decrypt_json(token)
    if not isinstance(result, dict):
        raise DecryptionError("Decrypted credentials payload was not a JSON object.")
    return result


# --------------------------------------------------------------------------- #
# Password hashing (PBKDF2-HMAC-SHA256, stdlib only)
# --------------------------------------------------------------------------- #


def hash_password(password: str) -> str:
    """Return a self-describing PBKDF2 password hash string.

    Format: ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>``
    """
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, _HASH_BYTES
    )
    return _PBKDF2_ALGO + "${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time verification of *password* against a stored hash."""
    if not password or not stored_hash:
        return False
    try:
        algo, iters_s, salt_b64, hash_b64 = stored_hash.split("$")
    except ValueError:
        return False
    if algo != _PBKDF2_ALGO:
        return False
    try:
        iterations = int(iters_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, base64.binascii.Error):
        return False
    if not iterations > 0:
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, len(expected))
    return hmac.compare_digest(derived, expected)


# --------------------------------------------------------------------------- #
# Session tokens (CSPRNG)
# --------------------------------------------------------------------------- #


def generate_session_token() -> str:
    """Generate a cryptographically-secure URL-safe session token."""
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def constant_time_equal(a: str, b: str) -> bool:
    """Constant-time string comparison (wraps :func:`hmac.compare_digest`)."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
