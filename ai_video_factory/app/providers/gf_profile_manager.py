#!/usr/bin/env python3
"""Multi-account Chrome profile manager for Google Flow production.

Each Google account gets its own Chrome user-data-dir profile.
When a profile is "authenticated", the account is logged in and
ready for generation. The production pipeline picks an account,
launches its Chrome profile on a specific CDP port, and generates.

Profile layout:
    ~/.google-flow-profiles/<account_id>/
        user_data_dir/   # Chrome user data (created on first launch)
        status           # pending_auth | authenticating | authenticated | expired
        email            # account email
        label            # human-readable label
        last_used        # ISO timestamp of last generation
        credits_used     # credits used today (reset at midnight UTC)
        cdp_port         # CDP port this profile's Chrome listens on

Usage:
    manager = GFProfileManager()
    manager.launch_profile("gf-acc-001")  # starts Chrome with that profile on assigned CDP port
    manager.wait_for_auth("gf-acc-001")   # waits until status=authenticated
    # ... use the profile's cdp_port for generation ...
    manager.stop_profile("gf-acc-001")    # kills the Chrome process
"""

import json
import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

PROFILES_DIR = Path.home() / ".google-flow-profiles"
CHROME_BIN = "/home/limar01/.local/opt/google-chrome/opt/google/chrome/google-chrome"
BASE_CDP_PORT = 9228
PORTS_PER_PROFILE = 2  # CDP + 1 extra for safety


class GFProfileManager:
    """Manages Chrome profiles for multiple Google Flow accounts."""

    def __init__(self, profiles_dir: Path = PROFILES_DIR):
        self.profiles_dir = profiles_dir
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self._processes: dict[str, subprocess.Popen] = {}  # account_id -> process
        self._cdp_ports: dict[str, int] = {}  # account_id -> cdp_port

    # ------------------------------------------------------------------
    # Account loading
    # ------------------------------------------------------------------

    def load_accounts(self) -> list[dict]:
        """Load account config from the vault."""
        vault_path = Path.home() / ".snapgen-vault" / "google_flow_accounts.json"
        if not vault_path.exists():
            return []
        with open(vault_path) as f:
            data = json.load(f)
        return data.get("accounts", [])

    # ------------------------------------------------------------------
    # Profile discovery
    # ------------------------------------------------------------------

    def get_profile_path(self, account_id: str) -> Path:
        return self.profiles_dir / account_id

    def get_user_data_dir(self, account_id: str) -> Path:
        """Chrome user-data-dir for this account's profile."""
        return self.get_profile_path(account_id) / "user_data_dir"

    def get_status_file(self, account_id: str) -> Path:
        return self.get_profile_path(account_id) / "status"

    def get_cdp_port_file(self, account_id: str) -> Path:
        return self.get_profile_path(account_id) / "cdp_port"

    def read_status(self, account_id: str) -> str:
        sf = self.get_status_file(account_id)
        if sf.exists():
            return sf.read_text().strip()
        return "pending_auth"

    def write_status(self, account_id: str, status: str) -> None:
        sf = self.get_status_file(account_id)
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(status)

    def read_cdp_port(self, account_id: str) -> Optional[int]:
        pf = self.get_cdp_port_file(account_id)
        if pf.exists():
            return int(pf.read_text().strip())
        return None

    def write_cdp_port(self, account_id: str, port: int) -> None:
        pf = self.get_cdp_port_file(account_id)
        pf.parent.mkdir(parents=True, exist_ok=True)
        pf.write_text(str(port))

    def get_account_info(self, account_id: str) -> dict:
        """Get account info from vault by account ID."""
        for acc in self.load_accounts():
            if acc["id"] == account_id:
                return acc
        return {}

    # ------------------------------------------------------------------
    # Profile lifecycle
    # ------------------------------------------------------------------

    def prepare_profile(self, account_id: str) -> Path:
        """Create the profile directory and user-data-dir if needed."""
        pp = self.get_profile_path(account_id)
        pp.mkdir(parents=True, exist_ok=True)
        udd = self.get_user_data_dir(account_id)
        udd.mkdir(parents=True, exist_ok=True)
        # Write account info
        info = self.get_account_info(account_id)
        if info:
            (pp / "email").write_text(info.get("email", ""))
            (pp / "label").write_text(info.get("label", account_id))
        return udd

    def assign_cdp_port(self, account_id: str) -> int:
        """Assign a CDP port for this profile, avoiding conflicts."""
        used_ports = set(self._cdp_ports.values())
        for offset in range(10):
            port = BASE_CDP_PORT + offset * PORTS_PER_PROFILE
            if port not in used_ports and not self._port_in_use(port):
                self._cdp_ports[account_id] = port
                self.write_cdp_port(account_id, port)
                return port
        raise RuntimeError(f"Cannot assign free CDP port for {account_id}")

    def _port_in_use(self, port: int) -> bool:
        """Check if a TCP port is in use."""
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except (ConnectionRefusedError, OSError):
            return False

    def launch_profile(self, account_id: str, headless: bool = False) -> int:
        """Launch Chrome with this account's profile on an assigned CDP port.

        Returns the CDP port. The caller must wait for auth before using it.
        """
        if account_id in self._processes:
            logger.warning("Profile %s already launched (port %d)", account_id, self._cdp_ports.get(account_id, "?"))
            return self._cdp_ports[account_id]

        udd = self.prepare_profile(account_id)
        port = self.assign_cdp_port(account_id)
        self.write_status(account_id, "authenticating")

        # Build Chrome args
        args = [
            CHROME_BIN,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={udd}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--window-size=1280,900",
            "--window-position=100,100",
            f"--app=https://flow.google.com",
        ]
        if headless:
            args.append("--headless=new")

        logger.info("Launching Chrome profile %s (email: %s) on CDP port %d",
                    account_id, self.get_account_info(account_id).get("email", "?"), port)

        # Launch in background
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # detach from our process group
        )
        self._processes[account_id] = proc
        return port

    def wait_for_auth(self, account_id: str, timeout: int = 300) -> bool:
        """Wait until the profile's status becomes 'authenticated'.

        In practice, the user logs in manually. This polls the status file.
        For automated auth, cookies could be injected here.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.read_status(account_id)
            if status == "authenticated":
                logger.info("Profile %s authenticated", account_id)
                return True
            if status == "expired":
                logger.warning("Profile %s expired", account_id)
                return False
            time.sleep(5)
        logger.warning("Timeout waiting for profile %s auth", account_id)
        return False

    def stop_profile(self, account_id: str) -> None:
        """Kill the Chrome process for this profile."""
        proc = self._processes.pop(account_id, None)
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        # Clean up port tracking
        self._cdp_ports.pop(account_id, None)
        # Don't delete the profile — keep cookies/session for reuse
        logger.info("Stopped profile %s", account_id)

    def stop_all(self) -> None:
        """Kill all running Chrome profiles."""
        for acc_id in list(self._processes.keys()):
            self.stop_profile(acc_id)

    def get_authenticated_profiles(self) -> list[dict]:
        """Return list of accounts with authenticated profiles."""
        result = []
        for acc in self.load_accounts():
            acc_id = acc["id"]
            if self.read_status(acc_id) == "authenticated":
                cdp_port = self.read_cdp_port(acc_id)
                if cdp_port:
                    result.append({
                        "account_id": acc_id,
                        "email": acc.get("email", ""),
                        "label": acc.get("label", acc_id),
                        "cdp_port": cdp_port,
                        "user_data_dir": str(self.get_user_data_dir(acc_id)),
                    })
        return result

    def get_next_account(self) -> Optional[dict]:
        """Get the next account that needs auth (pending_auth status)."""
        for acc in self.load_accounts():
            if self.read_status(acc["id"]) in ("pending_auth", "expired"):
                return acc
        return None

    def mark_account_used(self, account_id: str) -> None:
        """Update last_used and credits after a generation."""
        pp = self.get_profile_path(account_id)
        pp.mkdir(parents=True, exist_ok=True)
        (pp / "last_used").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ"))

        # Increment credits
        credits_file = pp / "credits_used"
        current = int(credits_file.read_text().strip()) if credits_file.exists() else 0
        credits_file.write_text(str(current + 10))  # 10 credits per video

    def reset_daily_credits(self) -> None:
        """Reset credits_used for all profiles (call at UTC midnight)."""
        today = time.strftime("%Y-%m-%d")
        for acc in self.load_accounts():
            acc_id = acc["id"]
            pp = self.get_profile_path(acc_id)
            credits_file = pp / "credits_used"
            last_used_file = pp / "last_used"
            # Reset if last_used is on a different day
            if last_used_file.exists():
                last_used_day = last_used_file.read_text().strip()[:10]
                if last_used_day != today:
                    credits_file.write_text("0")
                    logger.info("Reset credits for %s", acc_id)
            else:
                credits_file.write_text("0")


# ------------------------------------------------------------------
# CLI helpers
# ------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    manager = GFProfileManager()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "list":
        print("=== Google Flow Profiles ===")
        for acc in manager.load_accounts():
            acc_id = acc["id"]
            status = manager.read_status(acc_id)
            port = manager.read_cdp_port(acc_id) or "not assigned"
            print(f"  {acc['label']} ({acc['email']})")
            print(f"    Status: {status} | CDP port: {port}")
        print()
        print("=== Authenticated profiles ===")
        for p in manager.get_authenticated_profiles():
            print(f"  {p['label']} — CDP {p['cdp_port']} — {p['email']}")

    elif cmd == "launch":
        acc_id = sys.argv[2] if len(sys.argv) > 2 else "gf-acc-001"
        port = manager.launch_profile(acc_id)
        print(f"Launched {acc_id} on CDP port {port}")
        print(f"Profile dir: {manager.get_user_data_dir(acc_id)}")
        print("Log in manually, then the production pipeline will detect auth.")

    elif cmd == "stop":
        acc_id = sys.argv[2] if len(sys.argv) > 2 else "all"
        if acc_id == "all":
            manager.stop_all()
            print("Stopped all profiles")
        else:
            manager.stop_profile(acc_id)
            print(f"Stopped {acc_id}")

    elif cmd == "auth-status":
        acc_id = sys.argv[2] if len(sys.argv) > 2 else "all"
        if acc_id == "all":
            for acc in manager.load_accounts():
                print(f"{acc['label']}: {manager.read_status(acc['id'])}")
        else:
            print(f"{acc_id}: {manager.read_status(acc_id)}")

    elif cmd == "mark-auth":
        acc_id = sys.argv[2]
        manager.write_status(acc_id, "authenticated")
        print(f"Marked {acc_id} as authenticated")
