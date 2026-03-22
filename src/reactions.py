"""Rick's emoji reactions on user messages."""
import random
import logging

logger = logging.getLogger(__name__)

REACTION_CHANCE = 0.20  # 20% chance to react

# User message keywords → emoji reaction
REACTION_MAP = {
    "stupid": ["🤮", "💩", "🤡"],
    "тупой": ["🤮", "💩", "🤡"],
    "помоги": ["👀", "🤔"],
    "help": ["👀", "🤔"],
    "спасибо": ["👍", "🙄"],
    "thanks": ["👍", "🙄"],
    "круто": ["🔥", "👍"],
    "cool": ["🔥", "👍"],
    "рик": ["⚡", "🧪"],
    "rick": ["⚡", "🧪"],
    "гений": ["🧠", "⚡"],
    "genius": ["🧠", "⚡"],
    "код": ["💻", "🧠"],
    "code": ["💻", "🧠"],
    "баг": ["🐛", "💩"],
    "bug": ["🐛", "💩"],
    "ахах": ["😂", "🤣"],
    "lol": ["😂", "🤣"],
    "хаха": ["😂", "🤣"],
    "?": ["🤔"],
    "!": ["👀"],
    "наука": ["🧪", "⚡"],
    "science": ["🧪", "⚡"],
    "люблю": ["🙄", "💅"],
    "love": ["🙄", "💅"],
}


def pick_reaction(user_text: str) -> str | None:
    """Pick an emoji reaction for the user's message, or None."""
    if random.random() > REACTION_CHANCE:
        return None

    text_lower = user_text.lower()
    candidates = []
    for keyword, emojis in REACTION_MAP.items():
        if keyword in text_lower:
            candidates.extend(emojis)

    if not candidates:
        return None

    return random.choice(candidates)


async def set_reaction(bot, chat_id: int, message_id: int, emoji: str):
    """Set emoji reaction on a message."""
    try:
        from telegram import ReactionTypeEmoji
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)]
        )
    except Exception as e:
        logger.debug(f"Reaction failed: {e}")
