from src.prompts import RICK_SYSTEM, GROUP_SYSTEM


def test_rick_system_has_auto_language():
    assert "языке собеседника" in RICK_SYSTEM
    assert "по-русски" not in RICK_SYSTEM


def test_group_system_exists():
    assert len(GROUP_SYSTEM) > 100
    assert "группов" in GROUP_SYSTEM.lower()
