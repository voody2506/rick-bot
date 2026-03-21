"""ClawHub skills system and external service integration."""
import os
import io
import re
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
            return f"Ничего не найдено по запросу «{query}»"
        lines = [f"🔍 Найдено {len(results)} skills по «{query}»:\n"]
        for r in results[:8]:
            lines.append(f"• `{r['slug']}` — _{r['displayName']}_\n  {r.get('summary','')[:120]}")
        lines.append("\nУстановить: `/skill install <slug>`")
        return "\n".join(lines)
    except Exception as e:
        return f"Ошибка поиска ClawHub: {e}"

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
            return f"Ошибка: сервер вернул не ZIP (slug «{slug}» существует?)"
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
        return f"✅ Skill `{slug}` установлен в {dest}\n{len(files)} файлов.\n{desc}"
    except Exception as e:
        return f"Ошибка установки «{slug}»: {e}"

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
        await update.message.reply_text(f"ырп, сейчас поставлю skill для {service}...")
        await install_clawhub_skill(config["clawhub_slug"], chat_id)

    # Проверить токен
    token_path = TOKENS_DIR / str(user_id) / config["token_file"]
    if not token_path.exists():
        if config.get("oauth_url"):
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [[InlineKeyboardButton(
                f"Авторизоваться в {service.title()}", url=config["oauth_url"]
            )]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"Морти, чтобы работать с {service.title()} мне нужен доступ. "
                f"Жми кнопку, дай разрешение, потом повтори запрос.",
                reply_markup=reply_markup
            )
            return True
        # Нет OAuth URL — даём конкретную инструкцию по подключению
        if service == "notion":
            await update.message.reply_text(
                "ырп Морти, у меня нет телепатического доступа к твоему Notion. "
                "Сделай так: зайди на notion.so/my-integrations, создай новую интеграцию, "
                "скопируй Internal Integration Token и скинь мне командой:\n"
                "/notion_token <твой_токен>\n"
                "Это займёт 2 минуты. Даже ты справишься."
            )
            return True
        elif service == "gmail":
            await update.message.reply_text(
                "ырп Gmail пока не подключён, Морти. "
                "Скажи владельцу бота настроить Gmail API — нужны client_id и client_secret. "
                "Без этого я не могу лезть в чужую почту. Это не каприз, это OAuth."
            )
            return True
        elif service == "github":
            await update.message.reply_text(
                "ырп GitHub не подключён. Создай токен на github.com/settings/tokens, "
                "выбери нужные права (repo, read:user) и скинь мне:\n"
                "/github_token <твой_токен>\n"
                "Дальше я разберусь сам."
            )
            return True
        elif service == "google_drive":
            await update.message.reply_text(
                "ырп Google Drive тоже не настроен, Морти. "
                "Нужен OAuth от Google — скажи владельцу бота добавить credentials."
            )
            return True
        return False

    return False  # Токен есть, всё готово — продолжать нормально
