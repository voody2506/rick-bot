"""Rick's drink counter — gets drunker from trigger words, decays over time."""
import time

DRINK_TRIGGERS = ["тупой", "stupid", "помоги", "help", "спасибо", "thanks",
                  "пожалуйста", "please", "не понимаю", "объясни", "explain",
                  "ещё раз", "повтори", "repeat", "sorry", "извини"]

_drink_counts: dict[int, float] = {}  # chat_id -> drinks
_last_drink_times: dict[int, float] = {}

DECAY_PER_HOUR = 2.0


def take_drink(chat_id: int, user_text: str) -> bool:
    """Check if user's message triggers a drink. Returns True if Rick drank."""
    text_lower = user_text.lower()
    if not any(t in text_lower for t in DRINK_TRIGGERS):
        return False
    _decay(chat_id)
    _drink_counts[chat_id] = _drink_counts.get(chat_id, 0.0) + 1.0
    _last_drink_times[chat_id] = time.time()
    return True


def _decay(chat_id: int):
    last_time = _last_drink_times.get(chat_id, 0.0)
    if last_time <= 0:
        return
    hours = (time.time() - last_time) / 3600
    decay = hours * DECAY_PER_HOUR
    _drink_counts[chat_id] = max(0.0, _drink_counts.get(chat_id, 0.0) - decay)


def get_drunk_level(chat_id: int) -> str:
    """Get drunkenness modifier for prompt."""
    _decay(chat_id)
    drinks = _drink_counts.get(chat_id, 0.0)
    if drinks < 2:
        return ""
    elif drinks < 5:
        return "You've had a few drinks. Slightly looser, more tangents, occasional slurred word."
    elif drinks < 8:
        return "You're noticeably drunk. Slur words, mix up topics, start philosophizing mid-sentence. More emotional. Occasional typo."
    elif drinks < 12:
        return "You're WASTED. Heavy slurring, barely type straight. Random tangents about the universe. Very emotional. Many typos."
    else:
        return "You are BLACKOUT DRUNK. Barely coherent. Single words. Random letters. Might pass out mid-message. '...zzzz'."
