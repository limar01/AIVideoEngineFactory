"""Authorized Account Pool + session lifecycle management.

Source: docs/DB_SCHEMA.md §3.4 (Account), §3.5 (Quota)
        docs/CONFIG_SPEC.md §8 (accounts.yaml)
        Master Spec §2 (Authorized Account Pool), §17 (Quota Manager)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlmodel import select
from sqlmodel.orm.session import Session

from app.core.security import decrypt_dict, encrypt_dict
from app.core.models import Account, AccountStatus, Quota
from app.core.config import get_config

logger = logging.getLogger(__name__)


class AccountManager:
    """Manages provider accounts, session lifecycle, and quota tracking.

    Only user-authorized accounts are supported. No credential rotation to
    exceed limits (spec §2).
    """

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ #
    # Account CRUD
    # ------------------------------------------------------------------ #

    def add_account(
        self,
        provider: str,
        label: str | None = None,
        credentials: dict | None = None,
    ) -> Account:
        """Register a new authorized account.

        Args:
            provider: e.g. "snapgen"
            label: Human-friendly name
            credentials: dict of credentials to encrypt (e.g. {"session_cookies": {...}})
        """
        # Per spec §2: only one authorized account per provider at a time
        existing = self.session.exec(
            select(Account).where(
                Account.provider == provider,
                Account.status == AccountStatus.AUTHORIZED,
            )
        ).first()
        if existing:
            raise ValueError(
                f"Provider '{provider}' already has an authorized account ({existing.id}). "
                f"Deauthorize the existing account first (spec §2: no circumvention)."
            )

        encrypted_creds = encrypt_dict(credentials) if credentials else None

        account = Account(
            id=str(uuid4()),
            provider=provider,
            label=label or f"{provider} account",
            credentials_encrypted=encrypted_creds,
            status=AccountStatus.PENDING_AUTH,
        )
        self.session.add(account)
        self.session.commit()
        self.session.refresh(account)

        logger.info("Added account %s for provider '%s'", account.id, provider)
        return account

    def get_account(self, account_id: str) -> Account | None:
        return self.session.exec(
            select(Account).where(Account.id == account_id)
        ).first()

    def list_accounts(self, provider: str | None = None) -> list[Account]:
        """List all accounts, optionally filtered by provider."""
        query = select(Account)
        if provider:
            query = query.where(Account.provider == provider)
        return self.session.exec(query).all()

    def set_authorized(self, account_id: str, session_state: str | None = None,
                       session_expires: datetime | None = None,
                       quota_info: Quota | None = None) -> Account:
        """Mark an account as authorized after successful login."""
        account = self.get_account(account_id)
        if not account:
            raise ValueError(f"Account not found: {account_id}")

        account.status = AccountStatus.AUTHORIZED
        account.session_state = session_state
        account.session_expires = session_expires
        account.updated_at = datetime.utcnow()
        self.session.add(account)

        # Create or update quota row
        if quota_info:
            quota = self.session.exec(
                select(Quota).where(Quota.account_id == account_id)
            ).first()
            if quota:
                quota.daily_limit = quota_info.daily_limit
                quota.used_today = quota_info.used_today
                quota.remaining = quota_info.remaining
                quota.reset_time = quota_info.reset_time
                quota.last_check_at = datetime.utcnow()
                self.session.add(quota)
            else:
                self.session.add(quota_info)

        self.session.commit()
        self.session.refresh(account)
        logger.info("Account %s authorized for provider '%s'", account_id, account.provider)
        return account

    def deauthorize(self, account_id: str) -> Account:
        """Deauthorize an account (user-controlled, per spec §2)."""
        account = self.get_account(account_id)
        if not account:
            raise ValueError(f"Account not found: {account_id}")
        account.status = AccountStatus.DISABLED
        account.session_state = None
        account.session_expires = None
        self.session.add(account)
        self.session.commit()
        return account

    # ------------------------------------------------------------------ #
    # Session lifecycle
    # ------------------------------------------------------------------ #

    def check_session(self, account_id: str) -> bool:
        """Check if the account's session is still valid.

        Returns True if session is valid, False if it needs re-authentication.
        """
        account = self.get_account(account_id)
        if not account:
            return False
        if account.status != AccountStatus.AUTHORIZED:
            return False
        if account.session_expires and account.session_expires < datetime.utcnow():
            # Session expired
            account.status = AccountStatus.AUTH_EXPIRED
            self.session.add(account)
            self.session.commit()
            return False
        return True

    def refresh_session(self, account_id: str, session_state: str,
                        session_expires: datetime | None = None) -> Account:
        """Update session state after a successful renewal."""
        account = self.get_account(account_id)
        if not account:
            raise ValueError(f"Account not found: {account_id}")
        account.session_state = session_state
        account.session_expires = session_expires
        account.last_used_at = datetime.utcnow()
        self.session.add(account)
        self.session.commit()
        return account

    def get_authorized_account(self, provider: str) -> Account | None:
        """Return the single authorized account for a provider (if any).

        Per spec §2: multiple accounts only if provider explicitly permits.
        """
        return self.session.exec(
            select(Account).where(
                Account.provider == provider,
                Account.status == AccountStatus.AUTHORIZED,
            )
        ).first()

    # ------------------------------------------------------------------ #
    # Quota management
    # ------------------------------------------------------------------ #

    def update_quota(self, account_id: str, used_today: int, remaining: int,
                     reset_time: datetime, daily_limit: int | None = None) -> Quota:
        """Update the quota record for an account.

        Provider limits come from the provider's get_quota() — never hard-coded.
        """
        quota = self.session.exec(
            select(Quota).where(Quota.account_id == account_id)
        ).first()

        if quota is None:
            quota = Quota(
                id=str(uuid4()),
                account_id=account_id,
                provider=Account.provider,  # type: ignore
                daily_limit=daily_limit or 0,
                used_today=used_today,
                remaining=remaining,
                reset_time=reset_time,
            )
            self.session.add(quota)
        else:
            quota.used_today = used_today
            quota.remaining = remaining
            quota.reset_time = reset_time
            if daily_limit is not None:
                quota.daily_limit = daily_limit
            quota.last_check_at = datetime.utcnow()

        # Check if quota reset time has passed
        if quota.reset_time and quota.reset_time <= datetime.utcnow():
            # Quota resets
            quota.used_today = 0
            quota.remaining = quota.daily_limit
            quota.error_count = 0
            # Set next reset to tomorrow
            quota.reset_time = _next_reset_time(quota.reset_time)

        self.session.commit()
        self.session.refresh(quota)
        return quota

    def check_quota(self, provider: str) -> Quota | None:
        """Check if the authorized account for a provider has quota remaining.

        Returns the Quota object, or None if no authorized account.
        """
        account = self.get_authorized_account(provider)
        if not account:
            return None

        quota = self.session.exec(
            select(Quota).where(Quota.account_id == account.id)
        ).first()

        if quota and quota.reset_time and quota.reset_time <= datetime.utcnow():
            # Quota has reset since last check
            quota.used_today = 0
            quota.remaining = quota.daily_limit
            quota.error_count = 0
            self.session.add(quota)
            self.session.commit()

        return quota

    def decrement_quota(self, account_id: str) -> Quota:
        """Decrement the quota by 1 for a used generation."""
        quota = self.session.exec(
            select(Quota).where(Quota.account_id == account_id)
        ).first()
        if not quota:
            raise ValueError(f"No quota record for account {account_id}")
        quota.used_today += 1
        quota.remaining = max(0, quota.remaining - 1)
        quota.last_generation = datetime.utcnow()
        quota.last_check_at = datetime.utcnow()
        self.session.add(quota)
        self.session.commit()
        return quota


def _next_reset_time(current_reset: datetime) -> datetime:
    """Calculate next reset time (24 hours from current reset)."""
    return current_reset + timedelta(days=1)
