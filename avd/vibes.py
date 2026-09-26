#!/usr/bin/env python3
"""vibes.py — drive the emulator's Chrome from the PC over Chrome DevTools Protocol.

The emulator's Chrome exposes @chrome_devtools_remote; we forward it to 127.0.0.1:9222
(`adb forward tcp:9222 localabstract:chrome_devtools_remote`) and speak CDP through it.
Playwright's connect_over_cdp gives us navigation, DOM queries, typing, clicking,
screenshots and JS evaluation against the REAL logged-in browser.

Usage:
  python3 vibes.py status                 # list tabs (url + title)
  python3 vibes.py open URL               # open URL in a new tab, waits for load
  python3 vibes.py text                   # innerText of the active page
  python3 vibes.py html                   # outerHTML (truncated)
  python3 vibes.py eval "JS expression"   # run JS in the page, print result
  python3 vibes.py shot FILE.png          # screenshot the active page
  python3 vibes.py click SELECTOR         # click a CSS selector (or text=... pseudo)
  python3 vibes.py fill SELECTOR TEXT     # fill an input
  python3 vibes.py press SELECTOR KEY     # press a key in an element
  python3 vibes.py ua "STRING"            # override the User-Agent for the page (the "app trick")
  python3 vibes.py wait SECONDS
"""
import sys
import json
import time
from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:9222"


def active(ctx):
    pages = [p for p in ctx.pages if p.url and p.url.startswith("http")]
    return pages[-1] if pages else ctx.new_page()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    arg = sys.argv[2] if len(sys.argv) > 2 else ""
    arg2 = sys.argv[3] if len(sys.argv) > 3 else ""

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP)
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = active(ctx)

        if cmd == "status":
            for i, p in enumerate(ctx.pages):
                try:
                    title = p.title()
                except Exception:
                    title = "?"
                print(f"[{i}] {p.url[:110]}  |  {title[:60]}")
        elif cmd == "open":
            page = ctx.new_page()
            page.goto(arg, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            print("url:", page.url)
            print("text:", (page.inner_text("body") or "")[:600].replace("\n", " | "))
        elif cmd == "text":
            print((page.inner_text("body") or "")[:2500])
        elif cmd == "html":
            print((page.content() or "")[:3000])
        elif cmd == "eval":
            print(json.dumps(page.evaluate(arg), ensure_ascii=False)[:2500])
        elif cmd == "shot":
            path = arg or "/tmp/vibes_shot.png"
            page.screenshot(path=path)
            print("saved", path)
        elif cmd == "click":
            page.click(arg, timeout=15000)
            time.sleep(2)
            print("clicked", arg)
            print("url:", page.url)
        elif cmd == "fill":
            page.fill(arg, arg2, timeout=15000)
            print("filled", arg)
        elif cmd == "press":
            page.press(arg, arg2 or "Enter", timeout=15000)
            time.sleep(2)
            print("pressed", arg2 or "Enter", "in", arg)
        elif cmd == "ua":
            ctx.add_init_script("")
            page.set_extra_http_headers({})
            cdp = ctx.new_cdp_session(page)
            cdp.send("Network.setUserAgentOverride", {"userAgent": arg})
            print("UA overridden for this page:", arg[:80])
        elif cmd == "wait":
            time.sleep(float(arg or 3))
            print("waited", arg)
        else:
            print("unknown command", cmd)
            return 2
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
