import pytest
from unittest.mock import AsyncMock, patch
from src.groups import maybe_respond_in_group


@pytest.mark.asyncio
@patch("src.groups.run_claude", new_callable=AsyncMock, return_value="Морти, ты тупой.")
async def test_responds_when_not_skip(mock_claude):
    result = await maybe_respond_in_group(123, "Kairat", "Рик, помоги")
    assert result is not None
    assert "тупой" in result


@pytest.mark.asyncio
@patch("src.groups.run_claude", new_callable=AsyncMock, return_value="SKIP")
async def test_skips_when_skip(mock_claude):
    result = await maybe_respond_in_group(123, "Kairat", "пойдём поедим")
    assert result is None


@pytest.mark.asyncio
@patch("src.groups.run_claude", new_callable=AsyncMock, return_value="")
async def test_skips_on_empty(mock_claude):
    result = await maybe_respond_in_group(123, "Kairat", "ок")
    assert result is None
