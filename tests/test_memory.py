from collections import deque
from unittest.mock import patch
from src.memory import load_history, save_history, load_facts, save_facts


def test_save_and_load_history(tmp_path):
    with patch("src.memory.MEMORY_DIR", tmp_path):
        h = deque(["hello", "world"], maxlen=40)
        save_history(123, h)
        loaded = load_history(123)
        assert list(loaded) == ["hello", "world"]


def test_load_history_empty(tmp_path):
    with patch("src.memory.MEMORY_DIR", tmp_path):
        loaded = load_history(999)
        assert len(loaded) == 0


def test_load_history_corrupted(tmp_path):
    with patch("src.memory.MEMORY_DIR", tmp_path):
        d = tmp_path / "999"
        d.mkdir()
        (d / "history.json").write_text("NOT JSON")
        loaded = load_history(999)
        assert len(loaded) == 0


def test_save_and_load_facts(tmp_path):
    with patch("src.memory.MEMORY_DIR", tmp_path):
        save_facts(123, ["fact1", "fact2"])
        loaded = load_facts(123)
        assert loaded == ["fact1", "fact2"]


def test_load_facts_empty(tmp_path):
    with patch("src.memory.MEMORY_DIR", tmp_path):
        assert load_facts(999) == []
