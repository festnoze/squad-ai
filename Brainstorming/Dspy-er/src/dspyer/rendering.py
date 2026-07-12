from __future__ import annotations

import json
import re
from typing import Any

VARIABLE_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def render_messages(prompt_text: str, item_input: Any) -> list[dict[str, str]]:
    """Build chat messages from a prompt template and a dataset item input.

    - dict input: fill {{variables}} in the template; leftover keys (or all keys if the
      template has no variables) become the user message.
    - scalar/list input: template is the system prompt, input is the user message.
    """
    if isinstance(item_input, dict):
        used: set[str] = set()

        def _substitute(match: re.Match[str]) -> str:
            key = match.group(1)
            if key in item_input:
                used.add(key)
                return as_text(item_input[key])
            return match.group(0)

        system = VARIABLE_RE.sub(_substitute, prompt_text)
        leftover = {k: v for k, v in item_input.items() if k not in used}
        user = as_text(leftover) if leftover else "Follow the instructions above."
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]

    return [
        {"role": "system", "content": prompt_text},
        {"role": "user", "content": as_text(item_input)},
    ]
