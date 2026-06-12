import pytest

from autospec.agents.runner import AgentError, extract_json


def test_extract_json_plain():
    assert extract_json('{"type": "brief", "n": 1}') == {"type": "brief", "n": 1}


def test_extract_json_with_prose_around():
    text = 'Voici ma réponse :\n{"type": "question", "message": "Pourquoi ?"}\nMerci.'
    assert extract_json(text)["type"] == "question"


def test_extract_json_fenced():
    text = 'Bla\n```json\n{"status": "green", "files": []}\n```'
    assert extract_json(text)["status"] == "green"


def test_extract_json_nested_objects():
    text = '{"epics": [{"id": "E1", "stories": [{"id": "US-1"}]}]}'
    assert extract_json(text)["epics"][0]["stories"][0]["id"] == "US-1"


def test_extract_json_braces_inside_strings():
    text = '{"a": "contient } et { dedans", "b": 1}'
    assert extract_json(text) == {"a": "contient } et { dedans", "b": 1}


def test_extract_json_escaped_quote_inside_string():
    text = '{"g": "a \\"quote\\" and }", "n": 2}'
    assert extract_json(text) == {"g": 'a "quote" and }', "n": 2}


def test_extract_json_missing_raises():
    with pytest.raises(AgentError):
        extract_json("pas de json ici")
