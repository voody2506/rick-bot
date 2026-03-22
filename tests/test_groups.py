import pytest
from src.groups import should_respond_in_group


@pytest.mark.asyncio
async def test_responds_to_direct_mention():
    assert await should_respond_in_group("Рик, помоги", reply_to_bot=False) is True


@pytest.mark.asyncio
async def test_responds_to_english_name():
    assert await should_respond_in_group("hey rick what do you think", reply_to_bot=False) is True


@pytest.mark.asyncio
async def test_responds_to_reply():
    assert await should_respond_in_group("что думаешь?", reply_to_bot=True) is True


@pytest.mark.asyncio
async def test_ignores_short_messages():
    assert await should_respond_in_group("ок", reply_to_bot=False) is False
