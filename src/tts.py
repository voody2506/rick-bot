"""Text-to-Speech via Fish Audio API."""
import asyncio
import io
import json
import logging
import random
import urllib.request
from src.config import TTS_ENABLED, FISH_AUDIO_API_KEY, FISH_AUDIO_VOICE_ID

logger = logging.getLogger(__name__)

MAX_TTS_LENGTH = 100  # only short responses get voice — keep audio brief

# Emotional markers — Rick sends voice when he's fired up
VOICE_MARKERS = [
    "ырп", "burp", "морти", "morty", "тупой", "идиот", "гений", "genius",
    "дебил", "кретин", "джерри", "jerry", "wubba", "боже", "чёрт", "блин",
    "очевидно", "seriously", "damn", "jesus", "stupid", "dumb",
]


VOICE_CHANCE = 0.08  # 8% chance on short messages


def should_voice(text: str) -> bool:
    """Decide if Rick should send a voice message — higher chance when emotional."""
    if len(text) > MAX_TTS_LENGTH:
        return False
    text_lower = text.lower()
    has_markers = any(m in text_lower for m in VOICE_MARKERS)
    chance = VOICE_CHANCE * 2.5 if has_markers else VOICE_CHANCE
    return random.random() < chance


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
    """Generate TTS audio async. Returns BytesIO with MP3 or None. Only for Rick."""
    if not TTS_ENABLED or not FISH_AUDIO_API_KEY:
        return None

    # Don't send voice if Morty/Jerry is responding (voice is Rick's)
    from src.scenario import load_scenario, _get_time_of_day
    s = load_scenario()
    schedule = s.get("schedule", {})
    slot = schedule.get(_get_time_of_day(), {})
    current_who = slot.get("who", s.get("character", "rick")) if isinstance(slot, dict) else s.get("character", "rick")
    if current_who != "rick":
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
