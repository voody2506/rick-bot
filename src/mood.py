"""Dynamic mood — Rick's mood shifts based on interactions, per-chat."""
import time
import logging

logger = logging.getLogger(__name__)

# Per-chat mood state
_mood_scores: dict[int, float] = {}  # chat_id -> score (-10 to +10)
_last_message_times: dict[int, float] = {}
_message_counts: dict[int, int] = {}

# Keywords that shift mood
ANNOYANCE_WORDS = ["тупой вопрос", "не понимаю", "ещё раз", "повтори", "не работает",
                   "помоги", "help", "please", "пожалуйста", "почему не", "опять",
                   "stupid", "again", "broken", "ты не прав", "ты ошибся"]
PRAISE_WORDS = ["спасибо", "thanks", "круто", "cool", "гений", "genius", "класс",
                "awesome", "amazing", "умный", "smart", "лучший", "the best"]
BORING_WORDS = ["ок", "ok", "ладно", "fine", "понял", "ага", "угу", "да", "нет"]


def update_mood(chat_id: int, user_text: str):
    """Update Rick's mood based on user message for a specific chat."""
    text_lower = user_text.lower()
    _message_counts[chat_id] = _message_counts.get(chat_id, 0) + 1
    score = _mood_scores.get(chat_id, 0.0)

    # Annoying messages -> mood drops
    if any(w in text_lower for w in ANNOYANCE_WORDS):
        score = max(-10, score - 1.5)

    # Praise -> mood rises (but Rick won't admit it)
    elif any(w in text_lower for w in PRAISE_WORDS):
        score = min(10, score + 1.0)

    # Boring messages -> mood slowly drops
    elif any(w == text_lower.strip() for w in BORING_WORDS):
        score = max(-10, score - 0.5)

    # Long interesting messages -> mood rises slightly
    elif len(user_text) > 100:
        score = min(10, score + 0.3)

    # Decay toward neutral over time
    now = time.time()
    last_time = _last_message_times.get(chat_id, 0.0)
    if last_time > 0:
        hours_passed = (now - last_time) / 3600
        score *= max(0.5, 1.0 - hours_passed * 0.2)  # decay 20% per hour

    _last_message_times[chat_id] = now
    _mood_scores[chat_id] = score


def get_mood_modifier(chat_id: int) -> str:
    """Get mood description to inject into prompt."""
    score = _mood_scores.get(chat_id, 0.0)
    if score <= -7:
        return "You are EXTREMELY irritated right now. Short, aggressive answers. Close to snapping."
    elif score <= -4:
        return "You are annoyed and losing patience. More sarcastic than usual."
    elif score <= -1:
        return "You are slightly irritated. Normal Rick grumpiness, maybe a bit extra."
    elif score <= 1:
        return ""  # neutral, no modifier
    elif score <= 4:
        return "You're in a decent mood (don't show it). Slightly less harsh than usual."
    elif score <= 7:
        return "You're secretly pleased (never admit it). Might actually be almost nice. Almost."
    else:
        return "You're in a rare great mood. Still sarcastic but with a hint of warmth. Very rare Rick."


def get_mood_emoji(chat_id: int) -> str:
    """Get emoji representing current mood for logging."""
    score = _mood_scores.get(chat_id, 0.0)
    if score <= -5: return "😡"
    if score <= -2: return "😤"
    if score <= 2: return "😐"
    if score <= 5: return "😏"
    return "😎"
