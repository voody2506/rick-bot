"""Page generation — Rick creates interactive HTML visualizations."""
import os
import uuid
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PAGES_DIR = Path(os.getenv("PAGES_DIR", "/app/pages"))
PAGE_BASE_URL = os.getenv("PAGE_BASE_URL", "http://204.168.162.250")
PAGE_TTL = 86400  # 24 hours


def save_page(html_content: str) -> str:
    """Save HTML content to a file and return the public URL."""
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    page_id = uuid.uuid4().hex[:10]
    filename = f"{page_id}.html"
    filepath = PAGES_DIR / filename
    filepath.write_text(html_content, encoding="utf-8")
    logger.info(f"Page created: {filename}")
    return f"{PAGE_BASE_URL}/{filename}"


def cleanup_old_pages():
    """Remove pages older than PAGE_TTL."""
    if not PAGES_DIR.exists():
        return
    now = time.time()
    for f in PAGES_DIR.glob("*.html"):
        if now - f.stat().st_mtime > PAGE_TTL:
            try:
                f.unlink()
                logger.info(f"Page expired: {f.name}")
            except Exception:
                pass
