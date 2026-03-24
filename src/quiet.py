"""Quiet modes — off / listen / silent.

- off: normal behavior
- listen: reads context, but only responds when mentioned
- silent: fully off, no context, no responses unless mentioned
"""
import json
import logging
from src.config import BASE_DIR

logger = logging.getLogger(__name__)

MODE_OFF = "off"
MODE_LISTEN = "listen"
MODE_SILENT = "silent"
_CYCLE = [MODE_OFF, MODE_LISTEN, MODE_SILENT]

_QUIET_FILE = BASE_DIR / "quiet_modes.json"
_modes: dict[str, str] = {}


def _load():
    global _modes
    if _QUIET_FILE.exists():
        try:
            _modes = json.loads(_QUIET_FILE.read_text())
        except Exception:
            _modes = {}


def _save():
    _QUIET_FILE.write_text(json.dumps(_modes))


def get_mode(chat_id: int) -> str:
    return _modes.get(str(chat_id), MODE_OFF)


def is_quiet(chat_id: int) -> bool:
    """Any non-off mode = quiet (don't respond unless mentioned)."""
    return get_mode(chat_id) != MODE_OFF


def is_silent(chat_id: int) -> bool:
    """Silent = don't even read context."""
    return get_mode(chat_id) == MODE_SILENT


def cycle_mode(chat_id: int) -> str:
    """Cycle: off → listen → silent → off. Returns new mode."""
    current = get_mode(chat_id)
    idx = _CYCLE.index(current) if current in _CYCLE else 0
    new_mode = _CYCLE[(idx + 1) % len(_CYCLE)]
    if new_mode == MODE_OFF:
        _modes.pop(str(chat_id), None)
    else:
        _modes[str(chat_id)] = new_mode
    _save()
    return new_mode


_load()
