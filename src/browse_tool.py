#!/usr/bin/env python3
"""Browser CLI tool — called by Claude CLI via bash when it needs to browse."""
import sys
import json
import asyncio


async def main():
    from playwright.async_api import async_playwright

    if len(sys.argv) < 3:
        print("Usage: python -m src.browse_tool <action> <args>")
        print("Actions: open <url> | click <selector> | scroll <up|down> | text | screenshot <path> | close")
        sys.exit(1)

    action = sys.argv[1]
    arg = sys.argv[2] if len(sys.argv) > 2 else ""

    # State file for persistent session
    state_file = "/tmp/browser_state.json"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page(viewport={"width": 1280, "height": 720})

        # Load previous URL if exists
        try:
            with open(state_file) as f:
                state = json.load(f)
                if state.get("url") and action != "open":
                    await page.goto(state["url"], timeout=15000, wait_until="domcontentloaded")
                    await page.wait_for_timeout(1000)
        except Exception:
            state = {}

        if action == "open":
            url = arg
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            text = await page.inner_text("body")
            print(text[:5000])
            with open(state_file, "w") as f:
                json.dump({"url": page.url}, f)

        elif action == "click":
            try:
                await page.get_by_text(arg, exact=False).first.click(timeout=5000)
            except Exception:
                await page.click(arg, timeout=5000)
            await page.wait_for_timeout(2000)
            text = await page.inner_text("body")
            print(text[:5000])
            with open(state_file, "w") as f:
                json.dump({"url": page.url}, f)

        elif action == "scroll":
            delta = 600 if arg == "down" else -600
            await page.mouse.wheel(0, delta)
            await page.wait_for_timeout(1000)
            text = await page.inner_text("body")
            print(text[:5000])

        elif action == "text":
            text = await page.inner_text("body")
            print(text[:5000])

        elif action == "screenshot":
            path = arg or "/tmp/screenshot.png"
            await page.screenshot(path=path)
            print(f"Screenshot saved to {path}")

        elif action == "fill":
            # arg = "selector|||value"
            parts = arg.split("|||")
            if len(parts) == 2:
                await page.fill(parts[0], parts[1], timeout=5000)
                print("Filled.")

        elif action == "close":
            try:
                import os
                os.remove(state_file)
            except Exception:
                pass
            print("Browser closed.")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
