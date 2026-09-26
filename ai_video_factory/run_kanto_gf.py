"""Resume Pinoy Kanto series video generation via Google Flow."""
import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("kanto")

BASE_DIR = Path("/home/limar01/Projects/workspace/project/ai_video_factory")
PROMPTS_FILE = BASE_DIR / "pinoy_demo" / "prompts.json"
DOWNLOAD_DIR = Path("/home/limar01/Data/gf-downloads")
CDP_PORT = 9228


def set_video_defaults(page) -> bool:
    """Set 9:16, x1, Veo 3.1 Lite via settings drawer."""
    try:
        page.locator('button[aria-label="Settings"]').first.click(timeout=8000)
    except Exception:
        return False
    page.wait_for_timeout(2000)

    secs = page.locator(".settings-section")
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

    for label in ("9:16", "x1"):
        try:
            t = video_sec.locator(f'.mat-button-toggle-button:has-text("{label}")')
            if t.count() > 0:
                t.first.click(timeout=5000)
                page.wait_for_timeout(400)
        except Exception:
            pass

    try:
        trig = video_sec.locator(".mat-mdc-menu-trigger")
        if trig.count() > 0 and "Veo 3.1 - Lite" not in trig.first.inner_text(timeout=2000):
            trig.first.click(timeout=5000)
            page.wait_for_timeout(1200)
            lite = page.locator('.mat-mdc-menu-item:has-text("Veo 3.1 - Lite"), [role="menuitem"]:has-text("Veo 3.1 - Lite")')
            if lite.count() > 0:
                lite.first.click(timeout=5000)
                page.wait_for_timeout(800)
    except Exception:
        pass

    try:
        save = page.locator(".settings-save-button, button:has-text('Save')")
        if save.count() > 0:
            save.first.click(timeout=5000)
            page.wait_for_timeout(1000)
    except Exception:
        pass
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    logger.info("Video defaults set")
    return True


def submit_prompt(page, prompt: str) -> bool:
    """Type prompt into ProseMirror and click generate."""
    pm = page.locator(".ProseMirror")
    if pm.count() == 0:
        logger.error("No ProseMirror")
        return False
    pm.first.click(timeout=3000)
    page.wait_for_timeout(500)

    # Focus via JS and type directly
    page.evaluate("""() => {
        const pm = document.querySelector('.ProseMirror');
        if (pm) {
            pm.focus();
            const sel = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(pm);
            sel.removeAllRanges();
            sel.addRange(range);
        }
    }""")
    page.wait_for_timeout(300)

    # Type character by character (reliable for contenteditable)
    for ch in prompt:
        page.keyboard.type(ch, delay=5)
    page.wait_for_timeout(1000)

    content = page.evaluate("""() => {
        const pm = document.querySelector('.ProseMirror');
        return pm ? (pm.innerText || pm.textContent || '').trim() : '';
    }""")
    if not content:
        logger.error("ProseMirror empty after typing")
        return False
    if len(content) < len(prompt) * 0.5:
        logger.warning("ProseMirror content short: %d vs %d", len(content), len(prompt))
    logger.info("Typed %d chars", len(content))

    gen = page.locator(".generate-icon-button, button[aria-label='Start generation']")
    if gen.count() == 0:
        gen = page.locator(".base-prompt-box .bottom-controls button")
    if gen.count() == 0:
        logger.error("No generate button")
        return False

    deadline = time.time() + 15000
    while time.time() < deadline:
        try:
            if not gen.first.evaluate("el => el.disabled"):
                break
        except Exception:
            pass
        page.wait_for_timeout(500)

    gen.first.click(timeout=5000)
    page.wait_for_timeout(1000)
    logger.info("Generate clicked")
    return True


def wait_for_generation(page, want: str = "vids", timeout_s: int = 300) -> bool:
    """Wait for media tiles to appear and finish."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        page.wait_for_timeout(4000)
        tiles_key = "flow-image-tile" if want == "imgs" else "flow-video-tile"
        count = page.locator(tiles_key).count()
        if count > 0:
            body = page.inner_text("body").lower()
            if "stop" not in body and "%" not in body:
                logger.info("%s ready", want)
                return True
    return False


def approve_if_needed(page, timeout_s: int = 90) -> bool:
    """Click Approve / Always approve."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        page.wait_for_timeout(2000)
        try:
            target = page.evaluate("""() => {
                const rows = [...document.querySelectorAll('.option-row')];
                const always = rows.find(r => /always approve/i.test(r.textContent || ''));
                const once = rows.find(r => /^approve$/i.test((r.textContent || '').trim()));
                const row = always || once;
                if (row) {
                    const r = row.getBoundingClientRect();
                    return {x: r.x + r.width/2, y: r.y + r.height/2};
                }
                return null;
            }""")
            if target:
                page.mouse.click(target["x"], target["y"])
                logger.info("Approved")
                return True
        except Exception:
            pass
        body = page.inner_text("body").lower()
        if "would you like" not in body and "generating" in body:
            return True
    return False


def download_720p(page, timeout_s: int = 120) -> str:
    """Download 720p from latest video tile."""
    before = set(os.listdir(str(DOWNLOAD_DIR)))

    vids = page.locator("flow-video-tile")
    if vids.count() == 0:
        return None
    tile = vids.last
    info = tile.evaluate("el => { const r = el.getBoundingClientRect(); return {x: r.x + r.width/2, y: r.y + r.height/2}; }")
    page.mouse.click(info["x"], info["y"])
    page.wait_for_timeout(4000)

    dl = page.locator('button[aria-label="Download media"]')
    for _ in range(30):
        if dl.count() > 0:
            try:
                if not dl.first.get_attribute("disabled"):
                    break
            except Exception:
                pass
        page.wait_for_timeout(2000)

    try:
        dl.first.click(timeout=5000)
    except Exception:
        return None
    page.wait_for_timeout(2000)

    target = page.evaluate("""(optText) => {
        const panes = document.querySelectorAll('.cdk-overlay-pane');
        for (const p of panes) {
            if (p.getBoundingClientRect().width <= 0) continue;
            const b = [...p.querySelectorAll('button')]
                .find(x => (x.textContent || '').includes(optText));
            if (b) { const r = b.getBoundingClientRect(); return {x: r.x + r.width/2, y: r.y + r.height/2}; }
        }
        return null;
    }""", "720p")
    if not target:
        return None
    page.mouse.click(target["x"], target["y"])

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        page.wait_for_timeout(1000)
        new_files = set(os.listdir(str(DOWNLOAD_DIR))) - before
        for f in sorted(new_files):
            if not f.endswith(".crdownload"):
                return str(DOWNLOAD_DIR / f)
    return None


def generate_scene(page, scene: dict, project_url: str) -> str:
    """Run full two-stage pipeline for one scene."""
    sn = scene["scene_number"]
    prompt = scene["prompt_text"]
    logger.info("=== Scene %d ===", sn)

    page.goto(project_url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(4000)

    # Stage 1: reference image
    try:
        page.locator(".settings-trigger-button").first.click(timeout=8000)
        page.wait_for_timeout(2000)
        toggle = page.locator('mat-button-toggle:has-text("crop_9_16")')
        if toggle.count() > 0:
            toggle.first.click(timeout=5000)
            page.wait_for_timeout(500)
        page.keyboard.press("Escape")
    except Exception as exc:
        logger.warning("Image aspect ratio: %s", exc)

    if not submit_prompt(page, prompt):
        logger.error("Scene %d: image submit failed", sn)
        return None

    if not wait_for_generation(page, "imgs", timeout_s=240):
        logger.error("Scene %d: image timeout", sn)
        return None

    # Stage 2: video with image attached
    try:
        imgs = page.locator("flow-image-tile")
        if imgs.count() > 0:
            tile = imgs.last
            info = tile.evaluate("el => { const r = el.getBoundingClientRect(); return {x: r.x + r.width/2, y: r.y + r.height/2}; }")
            page.mouse.click(info["x"], info["y"])
            page.wait_for_timeout(3500)

            add_btn = page.locator('button[aria-label="Add ingredients to the prompt box"]')
            if add_btn.count() > 0:
                add_btn.first.click(timeout=5000)
                page.wait_for_timeout(2000)
                asset = page.locator(".cdk-overlay-pane .asset-item")
                if asset.count() > 0:
                    asset.first.click(timeout=5000)
                    page.wait_for_timeout(1500)
                back = page.locator('button[aria-label*="Back"]')
                if back.count() > 0:
                    back.first.click(timeout=5000)
                    page.wait_for_timeout(2000)
    except Exception as exc:
        logger.warning("Image attach: %s", exc)

    set_video_defaults(page)

    if not submit_prompt(page, prompt):
        logger.error("Scene %d: video submit failed", sn)
        return None

    approve_if_needed(page)

    if not wait_for_generation(page, "vids", timeout_s=420):
        logger.error("Scene %d: video timeout", sn)
        return None

    mp4 = download_720p(page)
    if mp4:
        logger.info("Scene %d downloaded: %s", sn, mp4)
    else:
        logger.error("Scene %d: download failed", sn)
    return mp4


def main():
    from playwright.sync_api import sync_playwright

    with open(PROMPTS_FILE) as f:
        scenes = json.load(f)
    logger.info("Loaded %d scenes", len(scenes))

    existing = sorted(DOWNLOAD_DIR.glob("Aling_Nena_Kiko_*.mp4"))
    logger.info("Existing kanto videos: %d", len(existing))
    for v in existing:
        logger.info("  %s (%d bytes)", v.name, v.stat().st_size)

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}", timeout=15000)
    context = browser.contexts[0]
    page = context.pages[0] if context.pages else context.new_page()

    cdp = context.new_cdp_session(page)
    cdp.send("Emulation.setDeviceMetricsOverride", {"width": 1920, "height": 1080, "deviceScaleFactor": 1, "mobile": False})
    cdp.send("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(DOWNLOAD_DIR), "eventsEnabled": True})

    # Ensure session
    page.goto("https://flow.google.com", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    if "accounts.google.com" in page.url:
        logger.error("Session invalid — log in manually in Chrome, then re-run")
        pw.stop()
        return
    logger.info("Session OK")

    # Create project
    page.goto("https://flow.google.com/about", timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    btn = page.locator('button:has-text("Create with Google Flow")')
    if btn.count() > 0:
        btn.first.click(timeout=10000)
        page.wait_for_timeout(3000)

    np_btn = page.locator('button:has-text("New project")')
    if np_btn.count() > 0:
        np_btn.first.click(timeout=10000)
        page.wait_for_timeout(5000)

    # Wait for project URL
    deadline = time.time() + 30
    project_url = None
    while time.time() < deadline:
        page.wait_for_timeout(1000)
        if "/project/" in page.url:
            project_url = page.url
            break
        if page.locator(".base-prompt-box").count() > 0 and "/project/" in page.url:
            project_url = page.url
            break

    if not project_url:
        if page.locator(".base-prompt-box").count() > 0:
            project_url = page.url
        else:
            logger.error("Project creation failed")
            pw.stop()
            return
    logger.info("Project: %s", project_url)

    # Generate each scene
    results = []
    for i, scene in enumerate(scenes):
        sn = scene["scene_number"]
        logger.info("[%d/%d] Scene %d", i + 1, len(scenes), sn)
        try:
            mp4 = generate_scene(page, scene, project_url)
            results.append({"scene": sn, "path": mp4, "success": mp4 is not None})
            if mp4:
                logger.info("Scene %d OK", sn)
            else:
                logger.error("Scene %d FAILED", sn)
        except Exception as exc:
            logger.error("Scene %d exception: %s", sn, exc)
            results.append({"scene": sn, "path": None, "success": False, "error": str(exc)})

        if i < len(scenes) - 1:
            logger.info("Pause 15s...")
            time.sleep(15)

    ok = sum(1 for r in results if r.get("success"))
    logger.info("=== DONE: %d/%d OK ===", ok, len(scenes))
    for r in results:
        logger.info("  Scene %d: %s %s", r["scene"], "OK" if r.get("success") else "FAIL", r.get("path", ""))

    out = BASE_DIR / "pinoy_demo" / "gf_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    logger.info("Results: %s", out)

    input("Press Enter to exit...")
    browser.close()
    pw.stop()


if __name__ == "__main__":
    main()