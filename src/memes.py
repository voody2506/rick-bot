"""Rick meme/GIF reactions — curated collection by mood."""
import random
import asyncio
import logging
import urllib.request
import io

logger = logging.getLogger(__name__)

# Curated Rick and Morty GIF URLs by mood
RICK_GIFS = {
    "facepalm": [
        "https://media.giphy.com/media/gKsJUddjnpPG0/giphy.gif",
        "https://media.giphy.com/media/3o7btZ1Gm7ZL25pLMs/giphy.gif",
    ],
    "genius": [
        "https://media.giphy.com/media/l41YkEYRBagaFcXTO/giphy.gif",
        "https://media.giphy.com/media/dYPFRrezMNkmEYUsdT/giphy.gif",
    ],
    "drunk": [
        "https://media.giphy.com/media/joeRYmOkLaj2U6hwdj/giphy.gif",
        "https://media.giphy.com/media/l0HlSFaQ0JBYMPVvi/giphy.gif",
    ],
    "angry": [
        "https://media.giphy.com/media/3oriO5t2QB1dk1BReE/giphy.gif",
        "https://media.giphy.com/media/liBsVeLILcyaY/giphy.gif",
    ],
    "whatever": [
        "https://media.giphy.com/media/Oj7yTCLSZjlsraNMtF/giphy.gif",
        "https://media.giphy.com/media/xT0GqssRweIhlz209i/giphy.gif",
    ],
    "science": [
        "https://media.giphy.com/media/KI9oNS4JBemyI/giphy.gif",
        "https://media.giphy.com/media/3oEjHGr1Fhz0kyv8Ig/giphy.gif",
    ],
}

# Keywords that map to moods
MOOD_KEYWORDS = {
    "facepalm": ["тупой", "идиот", "дебил", "кретин", "stupid", "dumb", "джерри", "jerry", "серьёзно", "seriously"],
    "genius": ["гений", "genius", "умный", "smart", "легко", "easy", "очевидно", "obviously"],
    "drunk": ["ырп", "burp", "бурп", "пьян", "drunk", "выпь", "flask"],
    "angry": ["бесит", "злит", "чёрт", "damn", "hell", "shut up", "заткни"],
    "whatever": ["пофиг", "whatever", "неважно", "ладно", "fine", "окей", "мне всё равно"],
    "science": ["наука", "science", "физика", "квант", "формул", "теори", "atom"],
}

MEME_CHANCE = 0.12  # 12% chance on short messages


def detect_mood(text: str) -> str | None:
    text_lower = text.lower()
    for mood, keywords in MOOD_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return mood
    return None


def _download_gif_sync(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.read()
    except Exception as e:
        logger.warning(f"GIF download error: {e}")
        return None


async def maybe_get_meme(response_text: str) -> tuple[io.BytesIO, str] | None:
    """Maybe return a meme GIF based on Rick's response. Returns (BytesIO, mood) or None."""
    if len(response_text) > 100:
        return None

    mood = detect_mood(response_text)
    if not mood:
        return None

    if random.random() > MEME_CHANCE:
        return None

    gif_urls = RICK_GIFS.get(mood, [])
    if not gif_urls:
        return None

    url = random.choice(gif_urls)
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, _download_gif_sync, url)

    if not data:
        return None

    buf = io.BytesIO(data)
    buf.name = f"rick_{mood}.gif"
    return buf, mood
