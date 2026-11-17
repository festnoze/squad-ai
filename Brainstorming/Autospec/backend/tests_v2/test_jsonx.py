import pytest

from autospec.core.jsonx import JsonNotFound, extract_json


def test_bare_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_last_object_wins_after_prose():
    text = 'I first considered {"draft": true} then decided.\n\n{"final": 1}'
    assert extract_json(text) == {"final": 1}


def test_fenced_block_wins_over_bare_objects():
    text = 'Here {"noise": 1}\n```json\n{"tests": [{"ac_id": "US-1.AC-1"}]}\n```\nDone {"x": 2}'
    assert extract_json(text) == {"tests": [{"ac_id": "US-1.AC-1"}]}


def test_braces_inside_strings_do_not_confuse_the_parser():
    assert extract_json('result: {"brief": "use {curly} braces"}') == {"brief": "use {curly} braces"}


@pytest.mark.parametrize("text", ["", "   ", "no json here", "[1, 2]", "{broken"])
def test_missing_object_raises(text):
    with pytest.raises(JsonNotFound):
        extract_json(text)
