"""Rick's science challenges — occasional riddles for users."""
import time
import random

CHALLENGE_CHANCE = 0.08  # 8% chance per message
CHALLENGE_TIMEOUT = 600  # 10 minutes to answer

_pending: dict[int, dict] = {}  # chat_id -> {"ts": float}


def maybe_start_challenge(chat_id: int) -> bool:
    """Decide if Rick should throw a challenge. Returns True if yes."""
    if chat_id in _pending:
        if time.time() - _pending[chat_id]["ts"] < CHALLENGE_TIMEOUT:
            return False
        del _pending[chat_id]

    if random.random() > CHALLENGE_CHANCE:
        return False

    _pending[chat_id] = {"ts": time.time()}
    return True


def has_pending_challenge(chat_id: int) -> bool:
    """Check if there's an active challenge waiting for answer."""
    if chat_id not in _pending:
        return False
    if time.time() - _pending[chat_id]["ts"] > CHALLENGE_TIMEOUT:
        del _pending[chat_id]
        return False
    return True


def resolve_challenge(chat_id: int):
    """Mark challenge as resolved."""
    _pending.pop(chat_id, None)
