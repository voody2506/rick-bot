"""Page generation — Rick creates interactive HTML visualizations from templates."""
import os
import uuid
import time
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PAGES_DIR = Path(os.getenv("PAGES_DIR", "/app/pages"))
PAGE_BASE_URL = os.getenv("PAGE_BASE_URL", "http://204.168.162.250")
PAGE_TTL = 86400  # 24 hours
TEMPLATES_DIR = Path(__file__).parent / "page_templates"


def get_template(template_type: str) -> str | None:
    """Load HTML template by type (cards, compare, chart)."""
    path = TEMPLATES_DIR / f"{template_type}.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def render_template(template_type: str, title: str, subtitle: str, data_json: str, extra: dict = None) -> str | None:
    """Render a template with data."""
    template = get_template(template_type)
    if not template:
        return None
    html = template.replace("{{title}}", title)
    html = html.replace("{{subtitle}}", subtitle)
    html = html.replace("{{data}}", data_json)
    if extra:
        for key, value in extra.items():
            html = html.replace("{{" + key + "}}", value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))
    return html


def save_page(html_content: str) -> str:
    """Save HTML content to a file and return the public URL."""
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    page_id = uuid.uuid4().hex[:10]
    filename = f"{page_id}.html"
    filepath = PAGES_DIR / filename
    filepath.write_text(html_content, encoding="utf-8")
    logger.info(f"Page created: {filename}")
    return f"{PAGE_BASE_URL}/{filename}"


def available_templates() -> str:
    """Return list of available templates for the prompt."""
    return "cards (list with images/tags/prices), compare (side-by-side comparison), chart (graphs/stats)"


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
