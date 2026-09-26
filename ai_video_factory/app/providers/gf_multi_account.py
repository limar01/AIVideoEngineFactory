"""Multi-account Google Flow generation orchestrator.

Picks an authenticated account, generates a video via its Chrome profile,
marks the account as used (10 credits), and rotates to the next account
when the daily limit (50 credits = 5 videos) is reached.

Flow:
    orchestrator = GFMultiAccountOrchestrator()
    result = orchestrator.generate_one(prompt, scene_metadata)
    # result has success/failure, which account was used, download path
"""

import logging
import os
import time
from typing import Any, Optional

from app.providers.google_flow import GoogleFlowProvider, GenerationResult
from app.providers.google_flow_driver import GoogleFlowDriver
from app.providers.gf_profile_manager import GFProfileManager

logger = logging.getLogger(__name__)

CREDITS_PER_VIDEO = 10
DAILY_LIMIT = 50


class GFMultiAccountOrchestrator:
    """Generates videos using the pool of authenticated Google Flow accounts.

    Each account has its own Chrome profile (user-data-dir) with its own
    cookies/session. The orchestrator picks the account with the most
    remaining credits, generates via its CDP port, and marks it as used.
    """

    def __init__(self, profile_manager: GFProfileManager):
        self.manager = profile_manager
        self._provider_cache: dict[str, GoogleFlowProvider] = {}

    def _get_provider_for_account(self, account_id: str) -> GoogleFlowProvider:
        """Get or create a GoogleFlowProvider for a specific account's profile."""
        if account_id in self._provider_cache:
            return self._provider_cache[account_id]

        info = self.manager.get_account_info(account_id)
        cdp_port = self.manager.read_cdp_port(account_id)
        if not cdp_port:
            raise RuntimeError(f"No CDP port assigned for {account_id}")

        udd = str(self.manager.get_user_data_dir(account_id))

        provider = GoogleFlowProvider(
            cdp_port=cdp_port,
            download_dir=os.path.expanduser("~/Data/gf-downloads"),
            firefox_cookie_db=None,  # Not using Firefox cookies — using Chrome profile
        )
        # The provider's _launch_browser will connect to the existing Chrome
        # via CDP. We need to set the page manually since Chrome is already running.
        # Actually, the provider will call _launch_browser which connects over CDP.
        # But we need to authenticate first (verify session).
        self._provider_cache[account_id] = provider
        return provider

    def _authenticate_provider(self, provider: GoogleFlowProvider, account_id: str) -> bool:
        """Authenticate a provider against its account's Chrome profile.

        Since the Chrome profile is already logged in (user logged in manually),
        we connect via CDP and verify the session is on flow.google.com (not
        accounts.google.com sign-in).
        """
        try:
            provider._launch_browser()
            if not provider._page:
                logger.error("No page after _launch_browser for %s", account_id)
                return False

            # Check if we're on the gallery (authenticated) or sign-in (not)
            url = provider._page.url or ""
            if "accounts.google.com" in url:
                logger.warning("Account %s is at sign-in page — needs re-login", account_id)
                return False

            # We're on flow.google.com — session is valid
            # Navigate to landing to confirm no redirect to sign-in
            provider._goto_landing()
            new_url = provider._page.url or ""
            if "accounts.google.com" in new_url:
                logger.warning("Account %s redirected to sign-in after landing", account_id)
                return False

            provider._open_projects_gallery()
            provider._authenticated = True
            logger.info("Account %s session verified (gallery reached)", account_id)
            return True
        except Exception as exc:
            logger.error("Auth failed for %s: %s", account_id, exc)
            return False

    def _pick_best_account(self) -> Optional[dict]:
        """Pick the authenticated account with the most remaining credits."""
        candidates = []
        for profile in self.manager.get_authenticated_profiles():
            acc_id = profile["account_id"]
            credits_file = self.manager.get_profile_path(acc_id) / "credits_used"
            used = int(credits_file.read_text().strip()) if credits_file.exists() else 0
            remaining = max(0, DAILY_LIMIT - used)
            if remaining >= CREDITS_PER_VIDEO:
                candidates.append((remaining, profile))

        if not candidates:
            logger.info("No accounts with enough credits remaining")
            return None

        candidates.sort(key=lambda x: -x[0])  # Most credits first
        return candidates[0][1]

    def generate_one(self, prompt: str, scene_metadata: dict) -> dict:
        """Generate one video using the best available account.

        Returns a dict with:
            success: bool
            account_id: str
            email: str
            download_path: str or None
            error: str or None
        """
        account = self._pick_best_account()
        if not account:
            return {
                "success": False,
                "account_id": None,
                "email": None,
                "download_path": None,
                "error": "No accounts with sufficient credits",
            }

        acc_id = account["account_id"]
        email = account["email"]
        cdp_port = account["cdp_port"]

        logger.info("Generating with account %s (%s) on CDP %d",
                     acc_id, email, cdp_port)

        try:
            # Get provider and authenticate
            provider = self._get_provider_for_account(acc_id)
            if not self._authenticate_provider(provider, acc_id):
                return {
                    "success": False,
                    "account_id": acc_id,
                    "email": email,
                    "download_path": None,
                    "error": "Session verification failed — may need re-login",
                }

            # Use the driver directly for generation (reuse provider's page)
            from app.providers.google_flow_driver import GoogleFlowDriver
            driver = GoogleFlowDriver(
                cdp_port=cdp_port,
                download_dir=os.path.expanduser("~/Data/gf-downloads"),
                page=provider._page,
                cdp=provider._cdp,
            )

            if not driver.connect():
                return {
                    "success": False,
                    "account_id": acc_id,
                    "email": email,
                    "download_path": None,
                    "error": "Could not connect to Chrome on CDP " + str(cdp_port),
                }

            try:
                if not driver.ensure_session():
                    return {
                        "success": False,
                        "account_id": acc_id,
                        "email": email,
                        "download_path": None,
                        "error": "Session expired — needs re-login",
                    }

                # Stage 1: reference image
                project_url = driver.new_project()
                if not project_url:
                    return {
                        "success": False,
                        "account_id": acc_id,
                        "email": email,
                        "download_path": None,
                        "error": "Failed to create project",
                    }

                driver.set_video_defaults()

                img_path = driver.generate_image(
                    scene_metadata.get("reference_prompt", prompt),
                    project_url,
                )
                if not img_path:
                    logger.warning("Reference image failed — generating video without it")

                # Stage 2: video
                video_path = driver.generate_video(prompt, project_url)
                if not video_path:
                    return {
                        "success": False,
                        "account_id": acc_id,
                        "email": email,
                        "download_path": None,
                        "error": "Video generation failed",
                    }

                # Mark account as used
                self.manager.mark_account_used(acc_id)

                result_id = f"gf-{acc_id}-{os.path.basename(video_path)}"
                return {
                    "success": True,
                    "account_id": acc_id,
                    "email": email,
                    "download_path": video_path,
                    "result_id": result_id,
                    "error": None,
                }
            finally:
                driver.close()
        except Exception as exc:
            logger.error("Generation failed for %s: %s", acc_id, exc)
            return {
                "success": False,
                "account_id": acc_id,
                "email": email,
                "download_path": None,
                "error": str(exc),
            }

    def get_account_status(self) -> list[dict]:
        """Get status of all accounts (credits remaining, etc.)."""
        result = []
        for profile in self.manager.get_authenticated_profiles():
            acc_id = profile["account_id"]
            credits_file = self.manager.get_profile_path(acc_id) / "credits_used"
            used = int(credits_file.read_text().strip()) if credits_file.exists() else 0
            remaining = max(0, DAILY_LIMIT - used)
            result.append({
                "account_id": acc_id,
                "email": profile["email"],
                "label": profile.get("label", acc_id),
                "cdp_port": profile["cdp_port"],
                "credits_used": used,
                "credits_remaining": remaining,
                "videos_today": used // CREDITS_PER_VIDEO,
            })
        return result

    def get_pending_accounts(self) -> list[dict]:
        """Get accounts that need auth (pending_auth or expired)."""
        result = []
        for acc in self.manager.load_accounts():
            status = self.manager.read_status(acc["id"])
            if status in ("pending_auth", "expired"):
                result.append({
                    "account_id": acc["id"],
                    "email": acc.get("email", ""),
                    "label": acc.get("label", acc["id"]),
                    "status": status,
                    "password": acc.get("password", ""),
                })
        return result
