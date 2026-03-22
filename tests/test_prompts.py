from src.prompts import RICK_SYSTEM, GROUP_SYSTEM


def test_rick_system_has_auto_language():
    assert "user's language" in RICK_SYSTEM
    assert "Rick Sanchez" in RICK_SYSTEM


def test_group_system_exists():
    assert len(GROUP_SYSTEM) > 100
    assert "group chat" in GROUP_SYSTEM.lower()
