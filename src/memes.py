"""Rick GIF reactions — search via Tavily/web, very rare."""
import random
import asyncio
import logging
from src.config import TAVILY_API_KEY

logger = logging.getLogger(__name__)

GIF_CHANCE = 0.05  # 5% chance — very rare

# Mood keywords in Rick's response → search query
MOOD_SEARCHES = {
    "facepalm": "facepalm meme gif",
    "genius": "genius big brain meme gif",
    "drunk": "drunk meme gif funny",
    "angry": "angry rage meme gif",
    "laugh": "laughing meme gif reaction",
    "whatever": "whatever bored meme gif",
    "science": "science meme gif nerd",
}

MOOD_KEYWORDS = {
    "facepalm": ["тупой", "идиот", "дебил", "stupid", "dumb", "джерри", "jerry"],
    "genius": ["гений", "genius", "умный", "smart", "очевидно", "obviously"],
    "drunk": ["ырп", "burp", "бурп", "пьян", "drunk"],
    "angry": ["бесит", "чёрт", "damn", "заткни", "shut up"],
    "laugh": ["ахах", "хаха", "lol", "смешно", "funny"],
    "whatever": ["пофиг", "whatever", "ладно", "fine"],
    "science": ["наука", "science", "физика", "квант", "портал"],
}

# Cache: mood → list of GIF URLs (filled on first search)
_gif_cache: dict[str, list[str]] = {}


def _detect_mood(text: str) -> str | None:
    text_lower = text.lower()
    for mood, keywords in MOOD_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return mood
    return None


def _search_gif_sync(query: str) -> list[str]:
    """Search for GIF URLs via Tavily."""
    import json
    import urllib.request

    if not TAVILY_API_KEY:
        return []

    payload = json.dumps({
        "api_key": TAVILY_API_KEY,
        "query": f"{query} gif tenor",
        "max_results": 5,
        "search_depth": "basic",
        "include_images": True,
    }).encode()

    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=payload, method="POST",
        headers={"Content-Type": "application/json"}
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        images = data.get("images", [])
        # Filter for actual GIF URLs
        gifs = [url for url in images if ".gif" in url.lower()]
        return gifs[:5]
    except Exception as e:
        logger.warning(f"GIF search error: {e}")
        return []


async def maybe_send_gif(response_text: str, bot, chat_id: int) -> bool:
    """Maybe send a relevant GIF. Returns True if sent."""
    if len(response_text) > 100:
        return False

    mood = _detect_mood(response_text)
    if not mood:
        return False

    if random.random() > GIF_CHANCE:
        return False

    # Check cache first
    if mood not in _gif_cache:
        query = MOOD_SEARCHES.get(mood, "rick and morty")
        loop = asyncio.get_event_loop()
        _gif_cache[mood] = await loop.run_in_executor(None, _search_gif_sync, query)

    gifs = _gif_cache.get(mood, [])
    if not gifs:
        return False

    gif_url = random.choice(gifs)
    try:
        await bot.send_animation(chat_id=chat_id, animation=gif_url)
        return True
    except Exception as e:
        logger.warning(f"GIF send error: {e}")
        return False
