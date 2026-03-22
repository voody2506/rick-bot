"""Shared mood detection from text keywords."""

MOOD_KEYWORDS = {
    "facepalm": ["тупой", "идиот", "дебил", "stupid", "dumb", "джерри", "jerry", "серьёзно"],
    "angry": ["бесит", "злит", "чёрт", "damn", "заткни", "shut up", "ненавижу"],
    "genius": ["гений", "genius", "умный", "smart", "легко", "очевидно", "obviously", "элементарно"],
    "drunk": ["ырп", "burp", "бурп", "пьян", "выпь", "flask", "пиво", "водк", "drunk"],
    "thinking": ["хмм", "hmm", "подумать", "интересно", "interesting", "вопрос"],
    "laugh": ["ахах", "хаха", "lol", "смешно", "funny", "ржу"],
    "evil": ["план", "scheme", "мухаха", "evil", "отлично", "excellent"],
    "cool": ["круто", "cool", "класс", "nice", "неплохо", "not bad"],
    "scared": ["опасно", "danger", "бежим", "run", "помогите"],
    "pickle": ["огурец", "pickle", "огурчик"],
    "party": ["празднуем", "celebrate", "вечеринка", "party", "ура", "yay"],
    "whatever": ["пофиг", "whatever"],
    "science": ["наука", "science", "физика", "квант", "портал"],
}


def detect_mood(text: str) -> str | None:
    """Detect mood from text keywords. Returns mood string or None."""
    text_lower = text.lower()
    for mood, keywords in MOOD_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return mood
    return None
