#!/usr/bin/env python3
"""Skill-activation hook (the `skills.sh` equivalent), cross-platform.

Reads ``skill-rules.json`` next to this file and, given a prompt on stdin (or as
argv), prints the skills whose keyword/intent triggers match — so an agent (or a
Claude Code ``UserPromptSubmit`` hook) can surface the right `.claude/skills/<name>/SKILL.md`
on the fly instead of loading everything up front (progressive disclosure).

Usage:
  echo "add a column to the user entity" | python skill-activation.py
  python skill-activation.py "create an endpoint that exposes the total"
Exit code is always 0; matched skills (most-relevant first) go to stdout, one per line.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_PRIORITY = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _rules() -> dict:
    path = Path(__file__).with_name("skill-rules.json")
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("skills", {})
    except (OSError, json.JSONDecodeError):
        return {}


def match(prompt: str) -> list[str]:
    text = prompt.lower()
    hits: list[tuple[int, int, str]] = []
    for name, rule in _rules().items():
        triggers = rule.get("promptTriggers", {})
        score = sum(1 for kw in triggers.get("keywords", []) if kw.lower() in text)
        for pat in triggers.get("intentPatterns", []):
            try:
                if re.search(pat, text, re.IGNORECASE):
                    score += 2
            except re.error:
                continue
        if score:
            hits.append((_PRIORITY.get(rule.get("priority", "medium"), 2), -score, name))
    return [name for _, _, name in sorted(hits)]


def main() -> int:
    prompt = " ".join(sys.argv[1:]).strip() or sys.stdin.read()
    for name in match(prompt):
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
