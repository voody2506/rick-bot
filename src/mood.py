"""Dynamic mood — Rick's mood shifts based on interactions."""
import time
import logging

logger = logging.getLogger(__name__)

# Global mood modifiers (affect all chats)
_mood_score = 0.0  # -10 (furious) to +10 (smug/happy)
_last_message_time = 0.0
_message_count = 0

# Keywords that shift mood
ANNOYANCE_WORDS = ["тупой вопрос", "не понимаю", "ещё раз", "повтори", "не работает",
                   "помоги", "help", "please", "пожалуйста", "почему не", "опять",
                   "stupid", "again", "broken", "ты не прав", "ты ошибся"]
PRAISE_WORDS = ["спасибо", "thanks", "круто", "cool", "гений", "genius", "класс",
                "awesome", "amazing", "умный", "smart", "лучший", "the best"]
BORING_WORDS = ["ок", "ok", "ладно", "fine", "понял", "ага", "угу", "да", "нет"]


def update_mood(user_text: str):
    """Update Rick's mood based on user message."""
    global _mood_score, _last_message_time, _message_count

    text_lower = user_text.lower()
    _message_count += 1

    # Annoying messages → mood drops
    if any(w in text_lower for w in ANNOYANCE_WORDS):
        _mood_score = max(-10, _mood_score - 1.5)

    # Praise → mood rises (but Rick won't admit it)
    elif any(w in text_lower for w in PRAISE_WORDS):
        _mood_score = min(10, _mood_score + 1.0)

    # Boring messages → mood slowly drops
    elif any(w == text_lower.strip() for w in BORING_WORDS):
        _mood_score = max(-10, _mood_score - 0.5)

    # Long interesting messages → mood rises slightly
    elif len(user_text) > 100:
        _mood_score = min(10, _mood_score + 0.3)

    # Decay toward neutral over time
    now = time.time()
    if _last_message_time > 0:
        hours_passed = (now - _last_message_time) / 3600
        _mood_score *= max(0.5, 1.0 - hours_passed * 0.2)  # decay 20% per hour

    _last_message_time = now


def get_mood_modifier() -> str:
    """Get mood description to inject into prompt."""
    if _mood_score <= -7:
        return "You are EXTREMELY irritated right now. Short, aggressive answers. Close to snapping."
    elif _mood_score <= -4:
        return "You are annoyed and losing patience. More sarcastic than usual."
    elif _mood_score <= -1:
        return "You are slightly irritated. Normal Rick grumpiness, maybe a bit extra."
    elif _mood_score <= 1:
        return ""  # neutral, no modifier
    elif _mood_score <= 4:
        return "You're in a decent mood (don't show it). Slightly less harsh than usual."
    elif _mood_score <= 7:
        return "You're secretly pleased (never admit it). Might actually be almost nice. Almost."
    else:
        return "You're in a rare great mood. Still sarcastic but with a hint of warmth. Very rare Rick."


def get_mood_emoji() -> str:
    """Get emoji representing current mood for logging."""
    if _mood_score <= -5: return "😡"
    if _mood_score <= -2: return "😤"
    if _mood_score <= 2: return "😐"
    if _mood_score <= 5: return "😏"
    return "😎"
