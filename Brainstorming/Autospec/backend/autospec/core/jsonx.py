"""Extract the JSON object an agent was asked to end its answer with."""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class JsonNotFound(ValueError):
    pass


def extract_json(text: str) -> dict:
    """Return the LAST top-level JSON object found in ``text``.

    Fenced ```json blocks win over bare objects; agents often explain first and
    conclude with the requested object.
    """
    if not isinstance(text, str) or not text.strip():
        raise JsonNotFound("empty agent answer")
    for block in reversed(_FENCE.findall(text)):
        try:
            value = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    decoder = json.JSONDecoder()
    found: dict | None = None
    index = 0
    while True:
        start = text.find("{", index)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(value, dict):
            found = value
        index = end
    if found is None:
        raise JsonNotFound("no JSON object in agent answer")
    return found
