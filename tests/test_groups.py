import unittest.mock
from src.groups import should_respond_in_group


def test_responds_to_direct_mention():
    assert should_respond_in_group("Рик, помоги", reply_to_bot=False) is True


def test_responds_to_english_name():
    assert should_respond_in_group("hey rick what do you think", reply_to_bot=False) is True


def test_responds_to_reply():
    assert should_respond_in_group("что думаешь?", reply_to_bot=True) is True


def test_ignores_short_messages():
    with unittest.mock.patch("src.groups.random") as mock_random:
        mock_random.random.return_value = 1.0
        assert should_respond_in_group("ок", reply_to_bot=False) is False


def test_responds_to_rick_topic_question():
    assert should_respond_in_group("Как работает квантовая физика?", reply_to_bot=False) is True


def test_ignores_irrelevant():
    with unittest.mock.patch("src.groups.random") as mock_random:
        mock_random.random.return_value = 1.0
        assert should_respond_in_group("пойдём поедим пиццу вечером", reply_to_bot=False) is False
