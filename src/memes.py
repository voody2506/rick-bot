"""Rick GIF reactions — search via Tavily/web, very rare."""
import random
import asyncio
import logging
from src.config import TAVILY_API_KEY
from src.mood_detect import detect_mood

logger = logging.getLogger(__name__)

GIF_CHANCE = 0.12  # 12% chance

# Mood -> Rick and Morty themed GIF searches
MOOD_SEARCHES = {
    "facepalm": "rick and morty facepalm gif",
    "genius": "rick sanchez genius gif",
    "drunk": "rick sanchez drinking gif",
    "angry": "rick sanchez angry gif",
    "laugh": "rick and morty laughing gif",
    "whatever": "rick sanchez bored gif",
    "science": "rick sanchez science gif",
    "evil": "rick sanchez evil gif",
    "cool": "rick sanchez cool gif",
    "scared": "rick and morty scared gif",
    "pickle": "pickle rick gif",
    "party": "rick and morty party gif",
}

# Cache: mood -> list of GIF URLs (filled on first search)
_gif_cache: dict[str, list[str]] = {}


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
    mood = detect_mood(response_text)
    if not mood:
        return False

    if random.random() > GIF_CHANCE:
        return False

    # Check cache first
    if mood not in _gif_cache:
        query = MOOD_SEARCHES.get(mood, "rick and morty")
        loop = asyncio.get_running_loop()
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
