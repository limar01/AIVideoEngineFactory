"""Account Vault — persistent per-account browser profiles for SnapGen.

Each account gets:
  - A unique Chromium user-data-dir profile (cookies, localStorage, session)
  - A BrowserSession for manual login
  - A SnapGenProvider for automated generation using the same profile

First login per account is manual (Google OAuth). After that, the profile
persists and is reused automatically.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page

from app.providers.base import (
    VideoGenerationProvider,
    GenerationStatus,
    GenerationCapabilities,
    QuotaInfo,
    GenerationResult,
)
from app.providers.snapgen import (
    SnapGenProvider,
    BASE_URL,
    APP_URL,
    HISTORY_URL,
    MODEL_BUTTON_TEXT,
    DURATION_OPTIONS,
    ASPECT_RATIO_OPTIONS,
    RESOLUTION_OPTIONS,
    AUDIO_TOGGLE_TEXT,
    GENERATE_BUTTON_SELECTOR,
    TEXTAREA_SELECTOR,
)
from app.providers.browser_session import BrowserSession

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Account data model
# ---------------------------------------------------------------------------


class AccountRecord:
    """Immutable snapshot of one account's state."""

    __slots__ = (
        "id",
        "label",
        "profile_dir",
        "created_at",
        "last_used_at",
        "login_status",
        "generation_count_today",
        "count_date",
    )

    def __init__(
        self,
        id: str,
        label: str,
        profile_dir: Path,
        created_at: datetime,
        last_used_at: datetime | None = None,
        login_status: str = "needs_login",
        generation_count_today: int = 0,
        count_date: str | None = None,
    ) -> None:
        self.id = id
        self.label = label
        self.profile_dir = profile_dir
        self.created_at = created_at
        self.last_used_at = last_used_at
        self.login_status = login_status
        self.generation_count_today = generation_count_today
        self.count_date = count_date  # ISO date the count belongs to

    @property
    def effective_count_today(self) -> int:
        """Generation count, reset to 0 if the stored count is from a previous day."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.count_date != today:
            return 0
        return self.generation_count_today

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "profile_dir": str(self.profile_dir),
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "login_status": self.login_status,
            "generation_count_today": self.generation_count_today,
            "count_date": self.count_date,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AccountRecord:
        return cls(
            id=data["id"],
            label=data["label"],
            profile_dir=Path(data["profile_dir"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_used_at=(
                datetime.fromisoformat(data["last_used_at"])
                if data.get("last_used_at")
                else None
            ),
            login_status=data.get("login_status", "needs_login"),
            generation_count_today=data.get("generation_count_today", 0),
            count_date=data.get("count_date"),
        )


# ---------------------------------------------------------------------------
# Account Store (persistence)
# ---------------------------------------------------------------------------


class AccountStore:
    """Persists account records to disk."""

    def __init__(self, store_path: Path) -> None:
        self.store_path = store_path
        self._records: dict[str, AccountRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.store_path.exists():
            self._records = {}
            return
        try:
            data = json.loads(self.store_path.read_text())
            self._records = {
                acc_id: AccountRecord.from_dict(acc_data)
                for acc_id, acc_data in data.items()
            }
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("AccountStore._load — corrupt store: %s", exc)
            self._records = {}

    def _save(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        data = {acc_id: rec.to_dict() for acc_id, rec in self._records.items()}
        self.store_path.write_text(json.dumps(data, indent=2))

    def list(self) -> list[AccountRecord]:
        return sorted(self._records.values(), key=lambda r: r.created_at)

    def get(self, account_id: str) -> AccountRecord | None:
        return self._records.get(account_id)

    def add(self, label: str, profile_dir: Path) -> AccountRecord:
        account_id = f"acc-{secrets.token_hex(4)}"
        now = datetime.now(timezone.utc)
        rec = AccountRecord(
            id=account_id,
            label=label,
            profile_dir=profile_dir,
            created_at=now,
            login_status="needs_login",
        )
        self._records[account_id] = rec
        self._save()
        logger.info("AccountStore.add — created %s (%s)", account_id, label)
        return rec

    def update(self, account_id: str, **kwargs: Any) -> AccountRecord | None:
        rec = self._records.get(account_id)
        if rec is None:
            return None
        for key, value in kwargs.items():
            if hasattr(rec, key):
                setattr(rec, key, value)
        self._save()
        return rec

    def remove(self, account_id: str) -> bool:
        if account_id not in self._records:
            return False
        del self._records[account_id]
        self._save()
        logger.info("AccountStore.remove — removed %s", account_id)
        return True


# ---------------------------------------------------------------------------
# Account Vault — browser profile manager
# ---------------------------------------------------------------------------


class AccountVault:
    """Manages browser profiles and login state for multiple SnapGen accounts.

    First login per account is manual (Google OAuth). Subsequent uses load the
    persistent profile automatically — no re-login needed.
    """

    def __init__(
        self,
        vault_dir: Path | str | None = None,
        store_path: Path | str | None = None,
    ) -> None:
        self.vault_dir = (
            Path(vault_dir).expanduser() if vault_dir
            else Path.home() / ".snapgen-vault"
        )
        self.store_path = (
            Path(store_path).expanduser() if store_path
            else self.vault_dir / "accounts.json"
        )
        self._store = AccountStore(self.store_path)
        self._sessions: dict[str, BrowserSession] = {}

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    def create_account(self, label: str) -> AccountRecord:
        profile_dir = self.vault_dir / f"profile-{secrets.token_hex(4)}"
        profile_dir.mkdir(parents=True, exist_ok=True)
        return self._store.add(label=label, profile_dir=profile_dir)

    def list_accounts(self) -> list[dict]:
        return [rec.to_dict() for rec in self._store.list()]

    def get_account(self, account_id: str) -> AccountRecord | None:
        return self._store.get(account_id)

    def remove_account(self, account_id: str) -> bool:
        self.close_account_session(account_id)
        rec = self._store.get(account_id)
        if rec and rec.profile_dir.exists():
            import shutil
            shutil.rmtree(rec.profile_dir, ignore_errors=True)
        return self._store.remove(account_id)

    def account_count(self) -> int:
        return len(self._store._records)

    def authenticated_count(self) -> int:
        return sum(
            1 for r in self._store._records.values()
            if r.login_status == "authenticated"
        )

    # ------------------------------------------------------------------
    # Login lifecycle
    # ------------------------------------------------------------------

    def open_login_browser(
        self,
        account_id: str,
        visible: bool = True,
        viewport: tuple[int, int] = (1280, 960),
    ) -> BrowserSession:
        """Open a visible browser for manual Google OAuth login."""
        rec = self._store.get(account_id)
        if rec is None:
            raise ValueError(f"Account not found: {account_id}")

        session = BrowserSession(
            headless=not visible,
            user_data_dir=str(rec.profile_dir),
            viewport=viewport,
        )
        session.start()
        try:
            session.navigate(APP_URL, wait_until="domcontentloaded")
            session.wait_for_network_idle(timeout=15000)
        except Exception as exc:
            logger.warning("AccountVault.open_login_browser: %s", exc)

        self._sessions[account_id] = session
        logger.info(
            "AccountVault.open_login_browser — %s (visible=%s, profile=%s)",
            account_id, visible, rec.profile_dir
        )
        return session

    def mark_logged_in(self, account_id: str) -> AccountRecord:
        """Mark account as authenticated after user closes login browser."""
        rec = self._store.get(account_id)
        if rec is None:
            raise ValueError(f"Account not found: {account_id}")
        now = datetime.now(timezone.utc)
        updated = self._store.update(
            account_id,
            login_status="authenticated",
            last_used_at=now,
        )
        self.close_account_session(account_id)
        logger.info("AccountVault.mark_logged_in — %s authenticated", account_id)
        return updated

    def close_account_session(self, account_id: str) -> None:
        session = self._sessions.pop(account_id, None)
        if session is not None:
            session.close()

    def close_all(self) -> None:
        for account_id in list(self._sessions.keys()):
            self.close_account_session(account_id)

    def get_or_create_session(
        self,
        account_id: str,
        headless: bool = True,
    ) -> BrowserSession:
        """Get existing session or create new one for an authenticated account."""
        rec = self._store.get(account_id)
        if rec is None:
            raise ValueError(f"Account not found: {account_id}")
        if rec.login_status != "authenticated":
            raise RuntimeError(
                f"AccountVault.get_or_create_session — {account_id} not authenticated "
                f"(status={rec.login_status})"
            )

        existing = self._sessions.get(account_id)
        if existing is not None:
            return existing

        session = BrowserSession(
            headless=headless,
            user_data_dir=str(rec.profile_dir),
        )
        session.start()
        self._sessions[account_id] = session
        logger.info("AccountVault.get_or_create_session — %s", account_id)
        return session

    def verify_session(self, account_id: str) -> bool:
        """Check if account's saved session is still valid."""
        rec = self._store.get(account_id)
        if rec is None or rec.login_status != "authenticated":
            return False

        session = BrowserSession(
            headless=True,
            user_data_dir=str(rec.profile_dir),
            viewport=(1280, 960),
        )
        try:
            session.start()
            session.navigate(APP_URL, wait_until="domcontentloaded", timeout=15000)
            login_visible = session.page.locator('text=Login').count() > 0
            signup_visible = session.page.locator('text=Sign Up').count() > 0
            is_logged_in = not (login_visible and signup_visible)
            return is_logged_in
        except Exception as exc:
            logger.warning("AccountVault.verify_session — %s: %s", account_id, exc)
            return False
        finally:
            session.close()


# ---------------------------------------------------------------------------
# PoolSnapGenProvider — accounts rotation wrapper
# ---------------------------------------------------------------------------


class PoolSnapGenProvider(VideoGenerationProvider):
    """SnapGen provider that rotates through an AccountVault.

    Picks the next available authenticated account for each generation.
    If an account's session expires, the pool marks it expired and tries next.
    """

    PROVIDER_NAME: str = "snapgen-pool"

    def __init__(
        self,
        vault: AccountVault,
        base_url: str = BASE_URL,
        session_timeout_minutes: int = 30,
        generation_timeout_minutes: int = 15,
        polling_interval_seconds: int = 10,
        headless: bool = True,
        round_robin: bool = True,
        daily_limit_per_account: int = 10,
    ) -> None:
        self.vault = vault
        self._base_url = base_url
        self._session_timeout_minutes = session_timeout_minutes
        self._generation_timeout_minutes = generation_timeout_minutes
        self._polling_interval_seconds = polling_interval_seconds
        self._headless = headless
        self._round_robin = round_robin
        self._daily_limit_per_account = daily_limit_per_account
        self._current_index = 0
        self._account_providers: dict[str, SnapGenProvider] = {}
        self._account_sessions: dict[str, BrowserSession] = {}
        self._account_gen_counts: dict[str, int] = {}

    # ------------------------------------------------------------------
    # VideoGenerationProvider ABC
    # ------------------------------------------------------------------

    def authenticate(self, account_credentials: dict) -> bool:
        """Validate vault — returns True if at least one account is authenticated."""
        auth_count = self.vault.authenticated_count()
        if auth_count == 0:
            logger.error(
                "PoolSnapGenProvider.authenticate — no authenticated accounts"
            )
            return False
        logger.info(
            "PoolSnapGenProvider.authenticate — %d/%d accounts authenticated",
            auth_count, self.vault.account_count()
        )
        return True

    def check_session(self) -> bool:
        """Check if at least one account has a valid session."""
        return self.vault.authenticated_count() > 0

    def get_capabilities(self) -> GenerationCapabilities:
        return GenerationCapabilities(
            max_prompt_length=5000,
            supported_aspect_ratios=["16:9", "9:16"],
            supported_resolutions=["720p", "1080p"],
            max_duration_seconds=8.0,
            min_duration_seconds=4.0,
            supports_narration=True,
        )

    def get_quota(self) -> QuotaInfo:
        """Aggregate quota across all authenticated accounts (local daily tracking)."""
        total_limit = 0
        total_remaining = 0
        for rec in self.vault._store.list():
            if rec.login_status == "authenticated":
                total_limit += self._daily_limit_per_account
                total_remaining += max(
                    0, self._daily_limit_per_account - rec.effective_count_today
                )
        return QuotaInfo(
            limit=total_limit or None,
            used=(total_limit - total_remaining) if total_limit else None,
            remaining=total_remaining if total_limit else None,
            reset_time=None,
        )

    def submit_generation(
        self,
        prompt: str,
        scene_metadata: dict,
    ) -> GenerationResult:
        """Submit to next available account."""
        account_id = self._pick_account()
        if account_id is None:
            return GenerationResult(
                success=False,
                result_id=None,
                error_code="NO_AVAILABLE_ACCOUNTS",
                error_message="No authenticated accounts available.",
            )

        provider = self._get_provider(account_id)
        result = provider.submit_generation(prompt, scene_metadata)

        if result.success:
            rec = self.vault._store.get(account_id)
            new_count = (rec.effective_count_today if rec else 0) + 1
            self._account_gen_counts[account_id] = new_count
            self.vault._store.update(
                account_id,
                last_used_at=datetime.now(timezone.utc),
                generation_count_today=new_count,
                count_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )
            logger.info(
                "PoolSnapGenProvider.submit_generation — %s via %s (%d/%d today)",
                result.result_id[:8] if result.result_id else "unknown",
                account_id,
                new_count,
                self._daily_limit_per_account,
            )

        return result

    def get_generation_status(self, result_id: str) -> GenerationStatus:
        """Poll status from the account that owns this result."""
        for account_id, provider in self._account_providers.items():
            status = provider.get_generation_status(result_id)
            if status != GenerationStatus.UNKNOWN:
                return status
        return GenerationStatus.UNKNOWN

    def download_result(self, result_id: str) -> bytes:
        """Download from the account that owns this result."""
        for account_id, provider in self._account_providers.items():
            try:
                data = provider.download_result(result_id)
                if data:
                    return data
            except Exception:
                continue
        raise RuntimeError(f"Result {result_id[:8]} not found in any account.")

    def health_check(self) -> bool:
        """Check if vault has at least one authenticated account."""
        return self.vault.authenticated_count() > 0

    def cancel_generation(self, result_id: str) -> bool:
        """Cancel not supported at SnapGen (browser-only provider)."""
        return False

    def detect_error(self, result_id: str, raw_response: str) -> tuple[str | None, str | None]:
        """Delegate error detection to the underlying provider."""
        # Find which provider owns this result
        for account_id, provider in self._account_providers.items():
            try:
                code, msg = provider.detect_error(result_id, raw_response)
                if code is not None:
                    return code, msg
            except Exception:
                continue
        return None, None

    def detect_quota_exhaustion(self, raw_response: str) -> bool:
        """Check if any account shows quota/rate-limit exhaustion."""
        for account_id, provider in self._account_providers.items():
            try:
                if provider.detect_quota_exhaustion(raw_response):
                    return True
            except Exception:
                continue
        return False

    def close_session(self) -> None:
        """Close all account providers and sessions."""
        for provider in self._account_providers.values():
            provider._page = None
            provider._context = None
            provider._browser = None
            provider._authenticated = False
        self._account_providers.clear()
        for session in self._account_sessions.values():
            try:
                session.close()
            except Exception:
                pass
        self._account_sessions.clear()
        # Stop the shared Playwright driver — pool is done
        from app.providers.browser_session import BrowserSession
        BrowserSession.shutdown_shared_playwright()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pick_account(self) -> str | None:
        """Pick next available authenticated account with quota left today."""
        accounts = self.vault._store.list()
        auth_accounts = [a for a in accounts if a.login_status == "authenticated"]
        if not auth_accounts:
            return None

        # Filter out accounts that hit the daily limit
        available = [
            a for a in auth_accounts
            if a.effective_count_today < self._daily_limit_per_account
        ]
        if not available:
            logger.warning(
                "PoolSnapGenProvider._pick_account — all %d accounts hit the "
                "daily limit of %d generations",
                len(auth_accounts), self._daily_limit_per_account,
            )
            return None

        if self._round_robin and len(available) > 1:
            start = self._current_index % len(available)
            for i in range(len(available)):
                idx = (start + i) % len(available)
                acc = available[idx]
                if self._is_account_available(acc.id):
                    self._current_index = (idx + 1) % len(available)
                    return acc.id
            # All tried, try the first one
            acc = available[0]
            if self._is_account_available(acc.id):
                self._current_index = 1 % len(available)
                return acc.id
            return None

        # Non-round-robin: return first available
        for acc in available:
            if self._is_account_available(acc.id):
                return acc.id
        return None

    def _is_account_available(self, account_id: str) -> bool:
        """Check if account's session is still valid.

        NOTE: infrastructure errors (browser launch failures, Playwright
        issues) do NOT mark the account as needs_login — the saved profile
        may still be perfectly valid; only a real page-load check may.
        """
        rec = self.vault._store.get(account_id)
        if rec is None or rec.login_status != "authenticated":
            return False

        session = self._account_sessions.get(account_id)
        if session is not None:
            # Session exists, check if it's still alive
            try:
                session.page.evaluate("1 + 1")
                return True
            except Exception:
                # Session died — clean up but do NOT touch login_status;
                # a fresh session can be recreated from the same profile.
                session.close()
                del self._account_sessions[account_id]
                if account_id in self._account_providers:
                    self._account_providers[account_id]._page = None
                    self._account_providers[account_id]._context = None
                    self._account_providers[account_id]._authenticated = False
                    del self._account_providers[account_id]
                return False

        # No session — create one
        try:
            session = BrowserSession(
                headless=self._headless,
                user_data_dir=str(rec.profile_dir),
            )
            session.start()
            self._account_sessions[account_id] = session
            logger.info("PoolSnapGenProvider._is_account_available — created session for %s", account_id)
            return True
        except Exception as exc:
            # Infrastructure failure — do NOT mark needs_login
            logger.warning("PoolSnapGenProvider._is_account_available — failed for %s: %s", account_id, exc)
            return False

    def _get_provider(self, account_id: str) -> SnapGenProvider:
        """Get or create SnapGenProvider for an account.

        The provider attaches to the ALREADY-RUNNING BrowserSession's page
        (owned by this pool) instead of launching its own browser — two
        Chromium instances cannot share one user-data-dir (profile lock).
        """
        if account_id not in self._account_providers:
            rec = self.vault._store.get(account_id)
            if rec is None:
                raise RuntimeError(f"Account not found: {account_id}")

            # Ensure a live session exists (creates it if needed)
            if not self._is_account_available(account_id):
                raise RuntimeError(f"Account {account_id} has no live browser session")

            session = self._account_sessions[account_id]

            provider = SnapGenProvider(
                base_url=self._base_url,
                session_timeout_minutes=self._session_timeout_minutes,
                generation_timeout_minutes=self._generation_timeout_minutes,
                polling_interval_seconds=self._polling_interval_seconds,
                headless=self._headless,
                user_data_dir=str(rec.profile_dir),
            )
            # Attach to the shared session's page — provider must NOT
            # launch its own browser on the same profile.
            provider._page = session.page
            provider._context = session.context
            provider._browser = None
            provider._authenticated = True
            provider._session_start = time.time()
            self._account_providers[account_id] = provider
            logger.info("PoolSnapGenProvider._get_provider — created provider for %s", account_id)

        return self._account_providers[account_id]