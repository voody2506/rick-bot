"""Browser automation via Playwright — screenshots and page reading."""
import io
import logging

logger = logging.getLogger(__name__)


async def browse_url(url: str, full_page: bool = False) -> tuple[io.BytesIO | None, str]:
    """Navigate to URL, take screenshot, extract text. Returns (screenshot_bytes, page_text)."""
    from playwright.async_api import async_playwright

    screenshot_buf = None
    page_text = ""

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
            )
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)  # let JS render

            # Screenshot
            screenshot_bytes = await page.screenshot(full_page=full_page)
            screenshot_buf = io.BytesIO(screenshot_bytes)
            screenshot_buf.name = "screenshot.png"

            # Extract text
            page_text = await page.inner_text("body")
            page_text = page_text[:3000]  # limit

            await browser.close()
    except Exception as e:
        logger.error(f"Browser error: {e}")
        page_text = f"Browser error: {e}"

    return screenshot_buf, page_text


async def take_screenshot(url: str) -> io.BytesIO | None:
    """Just take a screenshot of a URL."""
    screenshot, _ = await browse_url(url)
    return screenshot


async def get_page_content(url: str) -> str:
    """Get text content of a page."""
    _, text = await browse_url(url)
    return text
