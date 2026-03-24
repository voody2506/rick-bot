"""Rick sticker responses — sends stickers by mood from curated packs."""
import random
import logging
from src.mood_detect import detect_mood

logger = logging.getLogger(__name__)

STICKER_CHANCE = 0.10  # 10% chance

# Sticker file_ids grouped by mood (from RickAndMorty, MrPoopy, Meeseeks packs)
STICKERS = {
    "facepalm": [
        "CAACAgIAAxUAAWm_Rb1yVPUwGzmd4107kQABYjRiAQACuA4AAlEOOUsuTuauZpwKkjoE",
        "CAACAgIAAxUAAWm_RbxfY3fzSuxkmxjom0jAbtJVAAI3AwACtXHaBqSAkerG-Gh2OgQ",
    ],
    "angry": [
        "CAACAgIAAxUAAWm_Rbxg4kG4c9yYcNCv0JQgKumhAAI1EQACNtrYSVlSKqh1OH1COgQ",
        "CAACAgIAAxUAAWm_Rbz1cG9TSULlA2U2oow8sCBvAAI6AwACtXHaBiDulSPzkEA2OgQ",
        "CAACAgIAAxUAAWm_RbwPMFNpfu6PTMKBhv3g3p3UAAIoAwACtXHaBpB6SodelUpuOgQ",
    ],
    "genius": [
        "CAACAgIAAxUAAWm_RbyGhEVesnS5WCmvB2tB_Yy0AAI5AwACtXHaBmh9wyozEKYCOgQ",
        "CAACAgIAAxUAAWm_Rbxlycr4EItn7oobAgzGaggoAAIxAwACtXHaBqKdXuJ4Jm7mOgQ",
        "CAACAgIAAxUAAWm_RbxpHbbSweTwRi7QcfPUd9-pAAItAwACtXHaBl JdSDo4DpaAOgQ",
    ],
    "drunk": [
        "CAACAgIAAxUAAWm_RbyAFei24g9oBS_o_IuSbiIdAAIvAwACtXHaBu0FMEu2Y03ROgQ",
        "CAACAgIAAxUAAWm_RbxjFwXUe9QVf7ozbo78eAKXAAIsAwACtXHaBotgl-Dh0B91OgQ",
    ],
    "thinking": [
        "CAACAgIAAxUAAWm_RbxWwHwbIzdCVkRfInyROeYWAAI5AwACtXHaBiNQZme8RjitOgQ",
        "CAACAgIAAxUAAWm_Rb3Wqh-_9U4-HhSy3TLoRvpVAAKhDAACQVqJSXJ2toezBbLYOgQ",
    ],
    "laugh": [
        "CAACAgIAAxUAAWm_RbzMW2BJoSdA7Q2aYi2EfpK-AAIkAwACtXHaBp-KKzzkUc-9OgQ",
        "CAACAgIAAxUAAWm_RbyMNRXHdF_z7zymvNlULynNAAKmDAACdC9pS6F6_R8I6ZuOOgQ",
        "CAACAgIAAxUAAWm_Rb1r1di00k8kOUAWEfqG8FURAALoDwACf8YQSryPZWQ6eOTpOgQ",
    ],
    "evil": [
        "CAACAgIAAxUAAWm_Rby01FkGt7Eyf9aHkk-_p8QBAAI_AwACtXHaBpmD7Hp6-DRVOgQ",
        "CAACAgIAAxUAAWm_RbzOXBpMJgmeBw-VbA8Njd7mAAI7AwACtXHaBhhLBtJVU8tEOgQ",
    ],
    "cool": [
        "CAACAgIAAxUAAWm_Rb3fsdVrdFSyMxWRsXtpf51lAAJ4DwACQSVISwABxSLmQfOYhjoE",
        "CAACAgIAAxUAAWm_RbyikCb9aiS-hJGUtXigPYUjAAIpAwACtXHaBt0xkieb3sQBOgQ",
    ],
    "scared": [
        "CAACAgIAAxUAAWm_Rbxgqfb9PX7AYu8i5-65sxfQAAIlAwACtXHaBnybn1XbRS4yOgQ",
        "CAACAgIAAxUAAWm_Rbyg0zRWoQSA7BBXmPVJ2347AAL4DAAC-1iZStKMdFGWqXFVOgQ",
    ],
    "pickle": [
        "CAACAgIAAxUAAWm_Rbw3uc9XtyMTIZbUpcQFffLQAAI4AwACtXHaBsLy3lrP6g0VOgQ",
    ],
    "party": [
        "CAACAgIAAxUAAWm_RbxQTdzAK5_WnzZxpW-TbS93AAI-EAAC5M5hSe4qrVGogMfnOgQ",
        "CAACAgIAAxUAAWm_Rb03q6Gq0yJJuDZYtOKD8EFAAAJVEQACj5nhSiIeHICga4P0OgQ",
    ],
}


def pick_sticker(response_text: str) -> str | None:
    """Pick a sticker for Rick's response, or None."""
    if random.random() > STICKER_CHANCE:
        return None

    mood = detect_mood(response_text)
    if mood:
        stickers = STICKERS.get(mood, [])
        if stickers:
            return random.choice(stickers)

    return None
