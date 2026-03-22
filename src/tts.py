"""Text-to-Speech via Fish Audio API."""
import asyncio
import io
import json
import logging
import random
import urllib.request
from src.config import TTS_ENABLED, FISH_AUDIO_API_KEY, FISH_AUDIO_VOICE_ID

logger = logging.getLogger(__name__)

MAX_TTS_LENGTH = 200  # only short responses get voice

# Emotional markers — Rick sends voice when he's fired up
VOICE_MARKERS = [
    "ырп", "burp", "морти", "morty", "тупой", "идиот", "гений", "genius",
    "дебил", "кретин", "джерри", "jerry", "wubba", "боже", "чёрт", "блин",
    "очевидно", "seriously", "damn", "jesus", "stupid", "dumb",
]


VOICE_CHANCE = 0.07  # 7% chance on short messages


def should_voice(text: str) -> bool:
    """Decide if Rick should send a voice message — short + 7% random."""
    if len(text) > MAX_TTS_LENGTH:
        return False
    return random.random() < VOICE_CHANCE


def _generate_sync(text: str) -> bytes | None:
    """Generate TTS audio synchronously. Returns MP3 bytes or None."""
    if not FISH_AUDIO_API_KEY:
        return None

    # Truncate long texts
    if len(text) > MAX_TTS_LENGTH:
        text = text[:MAX_TTS_LENGTH]

    url = "https://api.fish.audio/v1/tts"
    payload = json.dumps({
        "text": text,
        "reference_id": FISH_AUDIO_VOICE_ID,
        "format": "mp3"
    }).encode()

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {FISH_AUDIO_API_KEY}")
    req.add_header("Content-Type", "application/json")

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.read()
    except Exception as e:
        logger.warning(f"TTS error: {e}")
        return None


async def generate_voice(text: str) -> io.BytesIO | None:
    """Generate TTS audio async. Returns BytesIO with MP3 or None."""
    if not TTS_ENABLED or not FISH_AUDIO_API_KEY:
        return None
    if not should_voice(text):
        return None

    loop = asyncio.get_event_loop()
    audio_bytes = await loop.run_in_executor(None, _generate_sync, text)

    if not audio_bytes:
        return None

    buf = io.BytesIO(audio_bytes)
    buf.name = "rick_voice.mp3"
    return buf
