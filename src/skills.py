"""ClawHub skills system and external service integration."""
import io
import json
import asyncio
import zipfile
import logging
import urllib.request
import urllib.parse
from src.config import SKILLS_DIR, TOKENS_DIR, CLAWHUB_SEARCH_URL, CLAWHUB_DOWNLOAD_URL

logger = logging.getLogger(__name__)


def load_skills_for_chat(chat_id: int) -> str:
    """Загружает SKILL.md для конкретного чата из skills/{chat_id}/"""
    skills_dir = SKILLS_DIR / str(chat_id)
    if not skills_dir.exists():
        return ""
    parts = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            try:
                content = skill_file.read_text(encoding="utf-8")
                parts.append(f"## SKILL: {skill_dir.name}\n{content}")
            except Exception:
                pass
    return "\n\n".join(parts)

async def search_clawhub(query: str) -> str:
    """Ищет skills на ClawHub по запросу, возвращает форматированный список"""
    def _search():
        url = f"{CLAWHUB_SEARCH_URL}?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "RickBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _search)
        results = data.get("results", [])
        if not results:
            return f"Nothing found for '{query}'"
        lines = [f"🔍 Found {len(results)} skills for '{query}':\n"]
        for r in results[:8]:
            lines.append(f"• `{r['slug']}` — _{r['displayName']}_\n  {r.get('summary','')[:120]}")
        lines.append("\nInstall: `/skill install <slug>`")
        return "\n".join(lines)
    except Exception as e:
        return f"ClawHub search error: {e}"

async def install_clawhub_skill(slug: str, chat_id: int) -> str:
    """Скачивает и устанавливает skill из ClawHub (ZIP → SKILLS_DIR/<chat_id>/<slug>/)"""
    def _download():
        url = f"{CLAWHUB_DOWNLOAD_URL}?slug={urllib.parse.quote(slug)}"
        req = urllib.request.Request(url, headers={"User-Agent": "RickBot/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _download)
        if data[:2] != b'PK':
            return f"Error: server returned non-ZIP (does slug '{slug}' exist?)"
        dest = SKILLS_DIR / str(chat_id) / slug
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(dest)
        files = list(dest.rglob("*"))
        skill_md = dest / "SKILL.md"
        desc = ""
        if skill_md.exists():
            first_lines = skill_md.read_text(encoding="utf-8", errors="replace").split("\n")[:5]
            desc = " ".join(l for l in first_lines if l and not l.startswith("---")).strip()[:120]
        return f"✅ Skill `{slug}` installed to {dest}\n{len(files)} files.\n{desc}"
    except Exception as e:
        return f"Installation error '{slug}': {e}"

# ─── EXTERNAL SERVICES AUTO-FLOW ──────────────────────────

SERVICE_MAP = {
    "notion": {
        "keywords": ["notion", "нотион"],
        "clawhub_slug": "notion-api-skill",
        "oauth_url": None,
        "token_file": "notion.json"
    },
    "gmail": {
        "keywords": ["gmail", "почту", "письм", "email", "гмейл", "mail"],
        "clawhub_slug": "gmail",
        "oauth_url": None,
        "token_file": "gmail.json"
    },
    "github": {
        "keywords": ["github", "гитхаб", "репозитор", "коммит", "пул реквест"],
        "clawhub_slug": "github",
        "oauth_url": None,
        "token_file": "github.json"
    },
    "google_drive": {
        "keywords": ["google drive", "гугл диск", "диск", "drive"],
        "clawhub_slug": "google-drive",
        "oauth_url": None,
        "token_file": "gdrive.json"
    }
}


def detect_service(text: str):
    text_lower = text.lower()
    for service, config in SERVICE_MAP.items():
        if any(kw in text_lower for kw in config["keywords"]):
            return service
    return None


async def handle_service_request(update, context, user_id: int, chat_id: int, service: str, original_text: str) -> bool:
    """Возвращает True если обработал (нужен skill/auth), False если продолжать нормально"""
    config = SERVICE_MAP[service]

    # Проверить / установить skill
    skill_dir = SKILLS_DIR / str(chat_id) / config["clawhub_slug"]
    if not skill_dir.exists():
        await update.message.reply_text(f"burp, installing skill for {service}...")
        await install_clawhub_skill(config["clawhub_slug"], chat_id)

    # Проверить токен
    token_path = TOKENS_DIR / str(user_id) / config["token_file"]
    if not token_path.exists():
        if config.get("oauth_url"):
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [[InlineKeyboardButton(
                f"Authorize {service.title()}", url=config["oauth_url"]
            )]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"Morty, I need access to work with {service.title()}. "
                "Hit the button, grant permission, then try again.",
                reply_markup=reply_markup
            )
            return True
        # Нет OAuth URL — даём конкретную инструкцию по подключению
        if service == "notion":
            await update.message.reply_text(
                "burp Morty, I don't have telepathic access to your Notion. "
                "Here's what to do: go to notion.so/my-integrations, create a new integration, "
                "copy the Internal Integration Token and send it to me with:\n"
                "/notion_token <your_token>\n"
                "It takes 2 minutes. Even you can handle it."
            )
            return True
        elif service == "gmail":
            await update.message.reply_text(
                "burp Gmail isn't connected yet, Morty. "
                "Tell the bot owner to set up the Gmail API — client_id and client_secret are needed. "
                "Without that I can't dig through someone else's inbox. It's not a quirk, it's OAuth."
            )
            return True
        elif service == "github":
            await update.message.reply_text(
                "burp GitHub isn't connected. Create a token at github.com/settings/tokens, "
                "select the required scopes (repo, read:user) and send it to me:\n"
                "/github_token <your_token>\n"
                "I'll take it from there."
            )
            return True
        elif service == "google_drive":
            await update.message.reply_text(
                "burp Google Drive isn't set up either, Morty. "
                "Google OAuth is required — tell the bot owner to add credentials."
            )
            return True
        return False

    return False  # Токен есть, всё готово — продолжать нормально
