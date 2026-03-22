"""Daily news — Rick shares science/tech news in chats."""
import json
import logging
from src.config import MEMORY_DIR, TAVILY_API_KEY
from src.claude import run_claude
from src.media import _tavily_search_sync

logger = logging.getLogger(__name__)

NEWS_CONFIG_FILE = MEMORY_DIR / "news_config.json"


def load_news_config() -> dict:
    """Load news config: {chat_id: {"time": "14:30", "topic": "AI"}}"""
    if NEWS_CONFIG_FILE.exists():
        try: return json.loads(NEWS_CONFIG_FILE.read_text())
        except: pass
    return {}


def save_news_config(config: dict):
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    NEWS_CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2))


async def send_daily_news(bot, chat_id: int, topic: str = "science technology AI"):
    """Search for news and send Rick's commentary."""
    try:
        if not TAVILY_API_KEY:
            return

        results = _tavily_search_sync(f"latest {topic} news today", max_results=3)
        if not results:
            return

        prompt = (
            f"You are Rick Sanchez. Here are today's news:\n\n{results[:2000]}\n\n"
            f"Pick the most interesting one and comment on it in Rick's style. "
            f"Be short, sarcastic, include a Rick-like take on why this matters (or doesn't). "
            f"Write in the language appropriate for the chat."
        )

        response = await run_claude(prompt, timeout=30)
        if response:
            await bot.send_message(chat_id=int(chat_id), text=response)
            logger.info(f"Daily news sent to chat {chat_id}")
    except Exception as e:
        logger.error(f"Daily news error for chat {chat_id}: {e}")
