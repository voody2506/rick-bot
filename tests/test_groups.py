import pytest
from unittest.mock import AsyncMock, patch
from src.groups import should_respond_in_group


@pytest.mark.asyncio
@patch("src.groups.run_claude", new_callable=AsyncMock, return_value="ДА")
async def test_responds_when_claude_says_yes(mock_claude):
    assert await should_respond_in_group("Рик, помоги", reply_to_bot=False) is True
    mock_claude.assert_called_once()


@pytest.mark.asyncio
@patch("src.groups.run_claude", new_callable=AsyncMock, return_value="НЕТ")
async def test_ignores_when_claude_says_no(mock_claude):
    assert await should_respond_in_group("пойдём поедим", reply_to_bot=False) is False


@pytest.mark.asyncio
@patch("src.groups.run_claude", new_callable=AsyncMock, return_value="ДА")
async def test_reply_includes_context(mock_claude):
    assert await should_respond_in_group("спасибо", reply_to_bot=True) is True
    # Check that "(This is a direct reply to Rick)" was passed
    call_args = mock_claude.call_args[0][0]
    assert "direct reply" in call_args
