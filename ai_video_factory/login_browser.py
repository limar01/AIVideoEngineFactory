#!/usr/bin/env python
"""Open vault login browser for one account, keep alive until user closes it."""
import sys
import time

sys.path.insert(0, "/home/limar01/Projects/workspace/project/ai_video_factory")

from app.providers.vault import AccountVault

account_id = sys.argv[1]
vault = AccountVault()
session = vault.open_login_browser(account_id, visible=True)
print(f"BROWSER OPEN for {account_id} — log in with Google, then just leave it or close it.")
print("When done, run: mark-logged-in for this account.", flush=True)

# Keep process alive so the browser window stays open
try:
    while True:
        time.sleep(5)
        try:
            session.page.evaluate("1+1")
        except Exception:
            print("Browser closed by user.", flush=True)
            break
except KeyboardInterrupt:
    pass
finally:
    vault.close_account_session(account_id)
    print("Session closed.", flush=True)
