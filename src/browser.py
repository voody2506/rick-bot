"""Browser sessions via Playwright — persistent browsing with screenshots."""
import io
import time
import logging

logger = logging.getLogger(__name__)

SESSION_TIMEOUT = 300  # 5 min — auto-close inactive sessions

# Active browser sessions: chat_id → {"browser", "page", "last_used", "url"}
_sessions: dict[int, dict] = {}


async def _get_or_create_session(chat_id: int):
    """Get existing session or create new one."""
    from playwright.async_api import async_playwright

    session = _sessions.get(chat_id)
    if session and time.time() - session["last_used"] < SESSION_TIMEOUT:
        session["last_used"] = time.time()
        return session

    # Close old session if exists
    await close_session(chat_id)

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
    )
    page = await browser.new_page(viewport={"width": 1280, "height": 720})

    _sessions[chat_id] = {
        "pw": pw,
        "browser": browser,
        "page": page,
        "last_used": time.time(),
        "url": "",
    }
    return _sessions[chat_id]


async def close_session(chat_id: int):
    """Close browser session for a chat."""
    session = _sessions.pop(chat_id, None)
    if session:
        try:
            await session["browser"].close()
            await session["pw"].stop()
        except Exception:
            pass


async def navigate(chat_id: int, url: str) -> tuple[io.BytesIO | None, str]:
    """Navigate to URL, screenshot, extract text."""
    try:
        session = await _get_or_create_session(chat_id)
        page = session["page"]
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        session["url"] = url

        screenshot = await page.screenshot()
        text = await page.inner_text("body")
        text = text[:3000]

        buf = io.BytesIO(screenshot)
        buf.name = "screenshot.png"
        return buf, text
    except Exception as e:
        logger.error(f"Navigate error: {e}")
        return None, f"Error: {e}"


async def click(chat_id: int, target: str) -> tuple[io.BytesIO | None, str]:
    """Click on element by text/selector, screenshot after."""
    session = _sessions.get(chat_id)
    if not session:
        return None, "No active browser session."
    try:
        page = session["page"]
        session["last_used"] = time.time()

        # Try clicking by text first, then by selector
        try:
            await page.get_by_text(target, exact=False).first.click(timeout=5000)
        except Exception:
            try:
                await page.click(target, timeout=5000)
            except Exception:
                return None, f"Can't find '{target}' on the page."

        await page.wait_for_timeout(2000)
        session["url"] = page.url

        screenshot = await page.screenshot()
        text = await page.inner_text("body")
        text = text[:3000]

        buf = io.BytesIO(screenshot)
        buf.name = "screenshot.png"
        return buf, text
    except Exception as e:
        logger.error(f"Click error: {e}")
        return None, f"Error: {e}"


async def scroll(chat_id: int, direction: str = "down") -> tuple[io.BytesIO | None, str]:
    """Scroll page, screenshot after."""
    session = _sessions.get(chat_id)
    if not session:
        return None, "No active browser session."
    try:
        page = session["page"]
        session["last_used"] = time.time()

        delta = 600 if direction == "down" else -600
        await page.mouse.wheel(0, delta)
        await page.wait_for_timeout(1000)

        screenshot = await page.screenshot()
        text = await page.inner_text("body")
        text = text[:3000]

        buf = io.BytesIO(screenshot)
        buf.name = "screenshot.png"
        return buf, text
    except Exception as e:
        logger.error(f"Scroll error: {e}")
        return None, f"Error: {e}"


async def fill_form(chat_id: int, selector: str, value: str) -> tuple[io.BytesIO | None, str]:
    """Fill a form field, screenshot after."""
    session = _sessions.get(chat_id)
    if not session:
        return None, "No active browser session."
    try:
        page = session["page"]
        session["last_used"] = time.time()

        await page.fill(selector, value, timeout=5000)
        await page.wait_for_timeout(500)

        screenshot = await page.screenshot()
        buf = io.BytesIO(screenshot)
        buf.name = "screenshot.png"
        return buf, "Filled."
    except Exception as e:
        logger.error(f"Fill error: {e}")
        return None, f"Error: {e}"


def has_active_session(chat_id: int) -> bool:
    session = _sessions.get(chat_id)
    return session is not None and time.time() - session["last_used"] < SESSION_TIMEOUT


async def cleanup_stale_sessions():
    """Close sessions idle for too long."""
    now = time.time()
    stale = [cid for cid, s in _sessions.items() if now - s["last_used"] > SESSION_TIMEOUT]
    for cid in stale:
        await close_session(cid)
