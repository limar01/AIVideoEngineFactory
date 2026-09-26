"""Google Flow production driver — persistent headed Chrome on workspace 8 via CDP.

Single browser, reused session, no new spawns. Full pipeline:
  login check → project → video defaults (9:16, x1, Veo 3.1 Lite)
  → stage 1: reference image (free) → stage 2: video w/ image attached (10cr)
  → approve → wait → download MP4
"""
import json
import logging
import os
import re
import sqlite3
import time
from typing import Any, Optional

from app.providers.generation_config import GenerationConfig

from playwright.sync_api import Page, sync_playwright

logger = logging.getLogger(__name__)

BASE_URL = "https://flow.google.com"
DL_DIR = "/home/limar01/Data/gf-downloads"
FIREFOX_COOKIE_DB = os.path.expanduser("~/.firefox-google-flow-profile/cookies.sqlite")
CDP_PORT = 9228


def load_ff_cookies() -> list[dict[str, Any]]:
    conn = sqlite3.connect(FIREFOX_COOKIE_DB)
    c = conn.cursor()
    c.execute("SELECT host, path, name, value, expiry, isSecure, sameSite FROM moz_cookies")
    rows = c.fetchall()
    conn.close()
    seen: set[tuple[str, str]] = set()
    cookies: list[dict[str, Any]] = []
    for host, path, name, value, expiry, is_secure, same_site in rows:
        domain = host[1:] if host.startswith(".") else host
        key = (name, domain)
        if key in seen:
            continue
        seen.add(key)
        ss = "Lax"
        if same_site in (0, 6):
            ss = "None"
        elif same_site == 1:
            ss = "Strict"
        cookies.append({
            "name": name, "value": value, "domain": domain, "path": path,
            "expires": max(1, min(int(expiry), 9999999999)) if expiry and expiry > 0 else -1,
            "secure": bool(is_secure), "httpOnly": False, "sameSite": ss,
        })
    return cookies


class GoogleFlowDriver:
    """Drives the persistent workspace-8 Chrome via CDP."""

    def __init__(self, cdp_port: int = CDP_PORT, download_dir: str = DL_DIR,
                 page=None, cdp=None, config: GenerationConfig | None = None):
        self.cdp_port = cdp_port
        self.download_dir = download_dir
        self.config = config or GenerationConfig.pinoy_kanto_defaults()
        os.makedirs(self.download_dir, exist_ok=True)
        self._pw = None
        self._browser = None
        self._page: Optional[Page] = page
        self._cdp = cdp

    # -- lifecycle ---------------------------------------------------------
    def connect(self) -> bool:
        """Connect to the persistent Chrome. Returns False if not running.
        If page and cdp are already provided (reusing provider's session),
        skip the Playwright connect and just verify the page is valid.
        """
        if self._page is not None and self._cdp is not None:
            # Reusing provider's existing Playwright session — just verify page
            try:
                self._page.evaluate("1 + 1")
                return True
            except Exception as exc:
                logger.error("page verification failed: %s", exc)
                return False
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.connect_over_cdp(
                f"http://localhost:{self.cdp_port}", timeout=15000
            )
            ctx = self._browser.contexts[0]
            self._page = ctx.pages[0] if ctx.pages else ctx.new_page()
            self._cdp = ctx.new_cdp_session(self._page)
            self._cdp.send("Browser.setDownloadBehavior", {
                "behavior": "allow", "downloadPath": self.download_dir, "eventsEnabled": True,
            })
            self._cdp.send("Emulation.setDeviceMetricsOverride", {
                "width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False,
            })
            return True
        except Exception as exc:
            logger.error("connect failed: %s", exc)
            return False

    def close(self) -> None:
        # Don't tear down the shared Playwright session when reusing provider's page
        if self._pw is None and self._browser is None:
            return
        try:
            if self._browser and self._page is None:
                # Only close browser if we created it fresh (page is None means we didn't reuse)
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw and self._page is None:
                self._pw.stop()
        except Exception:
            pass
        self._page = None
        self._cdp = None

    # -- helpers -----------------------------------------------------------
    def _wait(self, ms: int) -> None:
        assert self._page
        self._page.wait_for_timeout(ms)

    def _url(self) -> str:
        return self._page.url if self._page else ""

    def _tiles(self) -> dict:
        return self._page.evaluate(
            "() => ({imgs: document.querySelectorAll('flow-image-tile').length,"
            " vids: document.querySelectorAll('flow-video-tile').length})"
        )

    def _click_text_button(self, text: str) -> bool:
        try:
            loc = self._page.locator(f'button:has-text("{text}")')
            if loc.count() == 0:
                return False
            loc.first.click(timeout=8000)
            return True
        except Exception:
            return False

    # -- session -----------------------------------------------------------
    def ensure_session(self) -> bool:
        """Navigate into the app. Handles account-chooser if it appears."""
        assert self._page
        self._page.goto(f"{BASE_URL}/about", timeout=30000, wait_until="domcontentloaded")
        self._wait(3000)
        self._click_text_button("Create with Google Flow")
        self._wait(3000)
        if "accounts.google.com" in self._url():
            # try clicking the saved account
            for sel in ('div[data-identifier="poyxxx11@gmail.com"]',
                        'div[role="link"]:has-text("poyxxx11")'):
                try:
                    acc = self._page.locator(sel)
                    if acc.count() > 0:
                        acc.first.click(timeout=8000)
                        self._wait(5000)
                        break
                except Exception:
                    continue
        if "accounts.google.com" in self._url():
            logger.error("session invalid — manual login needed in ws8 Chrome")
            return False
        return True

    def new_project(self) -> Optional[str]:
        assert self._page
        if not self._click_text_button("New project"):
            return None
        deadline = time.time() + 30
        while time.time() < deadline:
            self._wait(1000)
            if "/project/" in self._url() and self._page.locator(".base-prompt-box").count() > 0:
                return self._url()
        return None

    # -- settings ----------------------------------------------------------
    def set_video_defaults(self, aspect: str | None = None, count: str | None = None,
                           model: str | None = None) -> bool:
        """Set persistent Video generation defaults via the tune (Agent settings) drawer.

        Uses self.config values as defaults. Explicit args override the config.
        """
        cfg = self.config
        if aspect is None:
            aspect = cfg.aspect_ratio
        if count is None:
            count = f"x{cfg.output_count}"
        if model is None:
            model = cfg.model
        assert self._page
        try:
            self._page.locator('button[aria-label="Settings"]').first.click(timeout=8000)
        except Exception:
            return False
        self._wait(2000)
        secs = self._page.locator(".settings-section")
        video_sec = None
        for i in range(secs.count()):
            try:
                if "Video generation default" in secs.nth(i).inner_text(timeout=2000):
                    video_sec = secs.nth(i)
                    break
            except Exception:
                continue
        if video_sec is None:
            return False
        for label in (aspect, count):
            try:
                t = video_sec.locator(f'.mat-button-toggle-button:has-text("{label}")')
                if t.count() > 0:
                    t.first.click(timeout=5000)
                    self._wait(400)
            except Exception:
                pass
        try:
            trig = video_sec.locator(".mat-mdc-menu-trigger")
            if trig.count() > 0 and model not in trig.first.inner_text(timeout=2000):
                trig.first.click(timeout=5000)
                self._wait(1200)
                lite = self._page.locator(
                    '.mat-mdc-menu-item:has-text("Veo 3.1 - Lite"), [role="menuitem"]:has-text("Veo 3.1 - Lite")'
                )
                if lite.count() > 0:
                    lite.first.click(timeout=5000)
                    self._wait(800)
        except Exception:
            pass
        try:
            save = self._page.locator(".settings-save-button, button:has-text('Save')")
            if save.count() > 0:
                save.first.click(timeout=5000)
                self._wait(1000)
        except Exception:
            pass
        self._page.keyboard.press("Escape")
        self._wait(500)
        return True

    # -- generation --------------------------------------------------------
    def _submit_prompt(self, prompt: str) -> bool:
        """Type prompt into the ProseMirror contenteditable div and click generate.

        The prompt input is a contenteditable DIV (.ProseMirror) inside
        .base-prompt-box. The generate button is the arrow_forward icon
        inside .base-prompt-box > bottom-controls.
        """
        assert self._page

        # Helper: focus a contenteditable div and type into it
        def _type_into_prosemirror(text: str) -> bool:
            try:
                pm = self._page.locator(".ProseMirror")
                if pm.count() == 0:
                    return False
                # Click to focus
                pm.first.click(timeout=3000)
                self._wait(500)
                # Force focus via JS
                self._page.evaluate("""() => {
                    const pm = document.querySelector('.ProseMirror');
                    if (pm) {
                        pm.focus();
                        // Ensure we're in edit mode
                        document.execCommand('selectAll', false, null);
                    }
                }""")
                self._wait(300)
                # Use clipboard paste — most reliable for contenteditable divs
                # Write text to clipboard, then paste into the focused div
                self._page.evaluate("""(text) => {
                    const ta = document.createElement('textarea');
                    ta.value = text;
                    ta.style.position = 'fixed';
                    ta.style.opacity = '0';
                    document.body.appendChild(ta);
                    ta.select();
                    document.execCommand('copy');
                    document.body.removeChild(ta);
                }""", text)
                self._wait(300)
                # Paste into the focused ProseMirror
                try:
                    self._page.keyboard.press("Control+V")
                    self._wait(1000)
                except Exception:
                    pass
                # Fallback: type character by character if clipboard paste failed
                content = self._page.evaluate("""() => {
                    const pm = document.querySelector('.ProseMirror');
                    return pm ? (pm.innerText || pm.textContent || '').trim() : '';
                }""")
                if not content:
                    for ch in text:
                        self._page.keyboard.type(ch, delay=5)
                        self._wait(10)
                    self._wait(500)
                return True
            except Exception as exc:
                logger.error("_submit_prompt: failed to type into ProseMirror: %s", exc)
                return False

        # Type into the ProseMirror contenteditable div
        if not _type_into_prosemirror(prompt):
            logger.error("_submit_prompt: could not type into prompt input")
            return False

        # Verify textarea-like content was entered
        content = self._page.evaluate("""() => {
            const pm = document.querySelector('.ProseMirror');
            return pm ? (pm.innerText || pm.textContent || '').trim() : '';
        }""")
        if not content:
            logger.error("_submit_prompt: ProseMirror is empty after typing")
            return False
        logger.info("_submit_prompt: typed %d chars into prompt", len(content))

        # Find and click the generate button (arrow_forward inside bottom-controls)
        gen = self._page.locator(".base-prompt-box .bottom-controls .generate-icon-button, "
                                 ".base-prompt-box .bottom-controls button[aria-label=\"Start generation\"]")
        if gen.count() == 0:
            # Fallback: find any generate icon button
            gen = self._page.locator(".generate-icon-button")
        if gen.count() == 0:
            logger.error("_submit_prompt: no generate button found")
            return False

        # Wait for it to become enabled
        deadline = time.time() + 15000
        while time.time() < deadline:
            disabled = gen.first.evaluate("el => el.disabled")
            if not disabled:
                break
            self._wait(500)

        if gen.first.evaluate("el => el.disabled"):
            logger.error("_submit_prompt: generate button still disabled")
            return False

        logger.info("_submit_prompt: clicking generate button")
        gen.first.click(timeout=5000)
        self._wait(1000)
        return True

    def _approve_if_asked(self, timeout_s: int = 90) -> bool:
        """Click Approve/Always approve when the agent asks for confirmation.

        The approval UI uses .option-row divs (not buttons). Prefers
        'Always approve' so subsequent generations run unattended.
        Returns True if approved (or no approval was needed).
        """
        assert self._page
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            self._wait(2000)
            try:
                target = self._page.evaluate(
                    """() => {
                        const rows = [...document.querySelectorAll('.option-row')];
                        const always = rows.find(r => /always approve/i.test(r.textContent || ''));
                        const once = rows.find(r => /^approve$/i.test((r.textContent || '').trim()));
                        const row = always || once;
                        if (row) {
                            const r = row.getBoundingClientRect();
                            return {x: r.x + r.width/2, y: r.y + r.height/2};
                        }
                        return null;
                    }"""
                )
                if target:
                    self._page.mouse.click(target["x"], target["y"])
                    logger.info("approved (%s)", "always" if target else "once")
                    return True
            except Exception:
                pass
            body = self._page.inner_text("body").lower()
            if "would you like" not in body and "generating" in body:
                return True  # already running, no approval needed
        return False

    def _wait_media(self, want: str, timeout_s: int = 360) -> dict:
        """Wait for media tiles to APPEAR and FINISH generating.

        Tiles render as progress cards while generating; complete media has no
        'stop' button and no percent text. want: 'imgs' or 'vids'.
        """
        assert self._page
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            self._wait(4000)
            tiles = self._tiles()
            if tiles.get(want, 0) > 0:
                # check generation actually finished
                state = self._page.evaluate(
                    """() => {
                        const stopBtn = [...document.querySelectorAll('button')]
                            .some(b => (b.getAttribute('aria-label') || '').toLowerCase() === 'stop'
                                   || (b.textContent || '').trim() === 'stop');
                        const body = document.body.innerText || '';
                        const pct = /\\b\\d{1,3}%\\b/.test(body);
                        return {running: stopBtn || pct};
                    }"""
                )
                if not state.get("running"):
                    return tiles
        return self._tiles()

    def _download_media(self, option_text: str, timeout_s: int = 120) -> Optional[str]:
        """Open the latest tile in the editor and download with the given option."""
        assert self._page
        before = set(os.listdir(self.download_dir))
        tag = "flow-video-tile" if "720p" in option_text else "flow-image-tile"
        tile_sel = f"{tag}, flow-image-tile, flow-video-tile"
        info = self._page.evaluate(
            f"""() => {{
                const tiles = [...document.querySelectorAll('{tag}')];
                const tile = tiles.length ? tiles[tiles.length - 1]
                    : document.querySelector('flow-image-tile, flow-video-tile');
                if (!tile) return null;
                const r = tile.getBoundingClientRect();
                return {{x: r.x + r.width/2, y: r.y + r.height/2}};
            }}"""
        )
        if not info:
            return None
        self._page.mouse.click(info["x"], info["y"])
        self._wait(4000)
        # wait for Download media enabled
        dl = self._page.locator('button[aria-label="Download media"]')
        for _ in range(30):
            if dl.count() > 0 and not dl.first.get_attribute("disabled"):
                break
            self._wait(2000)
        try:
            dl.first.click(timeout=5000)
        except Exception:
            return None
        self._wait(2000)
        target = self._page.evaluate(
            """(optText) => {
                const panes = document.querySelectorAll('.cdk-overlay-pane');
                for (const p of panes) {
                    if (p.getBoundingClientRect().width <= 0) continue;
                    const b = [...p.querySelectorAll('button')]
                        .find(x => (x.textContent || '').includes(optText));
                    if (b) {
                        const r = b.getBoundingClientRect();
                        return {x: r.x + r.width/2, y: r.y + r.height/2};
                    }
                }
                return null;
            }""",
            option_text,
        )
        if not target:
            return None
        self._page.mouse.click(target["x"], target["y"])
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            self._wait(1000)
            new = set(os.listdir(self.download_dir)) - before
            if new:
                f = sorted(new)[0]
                if not f.endswith(".crdownload"):
                    return os.path.join(self.download_dir, f)
        return None

    # -- public pipeline -----------------------------------------------------
    def generate_image(self, prompt: str, project_url: Optional[str] = None,
                       config: GenerationConfig | None = None) -> Optional[str]:
        """Stage 1: generate a reference image. Returns downloaded file path.

        Uses config.image_aspect_ratio to set the image generation aspect ratio.
        """
        cfg = config or self.config
        if project_url:
            assert self._page
            self._page.goto(project_url, timeout=30000, wait_until="domcontentloaded")
            self._wait(4000)
        else:
            if not self.ensure_session():
                return None
            project_url = self.new_project()
            if not project_url:
                return None
        # Set image aspect ratio from config (default: 9:16)
        self._set_image_aspect_ratio(cfg.image_aspect_ratio)
        if not self._submit_prompt(prompt):
            return None
        self._wait_media("imgs", timeout_s=240)
        return self._download_media("Original size")

    def _set_image_aspect_ratio(self, aspect: str = "9:16") -> bool:
        """Set image generation aspect ratio via the settings drawer toggle.

        Maps: '9:16' -> crop_9_16, '16:9' -> crop_16_9, '1:1' -> crop_square, etc.
        """
        assert self._page
        # Click the settings trigger (Nano Banana 2 chip)
        try:
            self._page.locator(".settings-trigger-button").first.click(timeout=8000)
        except Exception:
            return False
        self._wait(2000)
        # Find and click the matching aspect ratio toggle
        aspect_map = {
            "9:16": "crop_9_16",
            "16:9": "crop_16_9",
            "1:1": "crop_square",
            "4:3": "crop_landscape",
            "3:4": "crop_portrait",
        }
        toggle_id = aspect_map.get(aspect, f"crop_{aspect.replace(':', '_')}")
        try:
            toggle = self._page.locator(f'mat-button-toggle:has-text("{toggle_id}")')
            if toggle.count() > 0:
                toggle.first.click(timeout=5000)
                self._wait(500)
                logger.info("Set image aspect ratio to %s", aspect)
                return True
        except Exception as exc:
            logger.warning("Failed to set image aspect ratio: %s", exc)
        return False

    def generate_video(self, prompt: str, project_url: Optional[str] = None,
                       attach_last_image: bool = True) -> Optional[str]:
        """Stage 2: video generation (Veo 3.1 Lite, 10 credits). Returns MP4 path.

        If attach_last_image and an image tile exists, attaches it as ingredient.
        """
        if project_url:
            assert self._page
            self._page.goto(project_url, timeout=30000, wait_until="domcontentloaded")
            self._wait(4000)
        elif "/project/" not in self._url():
            if not self.ensure_session():
                return None
            if not self.new_project():
                return None
        self.set_video_defaults()

        # attach reference image if present
        if attach_last_image and self._tiles().get("imgs", 0) > 0:
            try:
                info = self._page.evaluate(
                    """() => {
                        const tiles = [...document.querySelectorAll('flow-image-tile')];
                        const tile = tiles[tiles.length - 1];
                        if (!tile) return null;
                        const r = tile.getBoundingClientRect();
                        return {x: r.x + r.width/2, y: r.y + r.height/2};
                    }"""
                )
                if info:
                    self._page.mouse.click(info["x"], info["y"])
                    self._wait(3500)
                    # editor: add ingredients → select asset
                    self._page.locator(
                        'button[aria-label="Add ingredients to the prompt box"]'
                    ).first.click(timeout=5000)
                    self._wait(2000)
                    asset = self._page.locator(".cdk-overlay-pane .asset-item")
                    if asset.count() > 0:
                        asset.first.click(timeout=5000)
                        self._wait(1500)
                    # back to workspace
                    back = self._page.locator('button[aria-label*="Back"]')
                    if back.count() > 0:
                        back.first.click(timeout=5000)
                        self._wait(2000)
            except Exception as exc:
                logger.warning("image attach failed (continuing without): %s", exc)

        if not self._submit_prompt(prompt):
            return None
        if not self._approve_if_asked():
            logger.error("approval failed/timed out")
            return None
        self._wait_media("vids", timeout_s=420)
        return self._download_media("720p")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["image", "video", "pipeline"])
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--project", default=None)
    args = ap.parse_args()

    d = GoogleFlowDriver()
    if not d.connect():
        print("ERROR: ws8 Chrome not running on :9228 — launch it first")
        raise SystemExit(1)
    try:
        if args.mode == "image":
            path = d.generate_image(args.prompt, args.project)
        elif args.mode == "video":
            path = d.generate_video(args.prompt, args.project)
        else:  # pipeline: image then video
            img = d.generate_image(args.prompt, args.project)
            print("image:", img)
            path = d.generate_video(args.prompt, args.project) if img else None
        print("RESULT:", path or "FAILED")
    finally:
        d.close()