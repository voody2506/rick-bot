"""Quiet mode — Rick only responds when directly mentioned."""
import json
import logging
from pathlib import Path
from src.config import BASE_DIR

logger = logging.getLogger(__name__)

_QUIET_FILE = BASE_DIR / "quiet_chats.json"
_quiet_chats: set[int] = set()


def _load():
    global _quiet_chats
    if _QUIET_FILE.exists():
        try:
            _quiet_chats = set(json.loads(_QUIET_FILE.read_text()))
        except Exception:
            _quiet_chats = set()


def _save():
    _QUIET_FILE.write_text(json.dumps(list(_quiet_chats)))


def is_quiet(chat_id: int) -> bool:
    return chat_id in _quiet_chats


def toggle_quiet(chat_id: int) -> bool:
    """Toggle quiet mode. Returns True if now quiet, False if back to normal."""
    if chat_id in _quiet_chats:
        _quiet_chats.discard(chat_id)
        _save()
        return False
    else:
        _quiet_chats.add(chat_id)
        _save()
        return True


_load()
