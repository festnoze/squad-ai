"""W3 — the project CONSTITUTION: a global quality standard compiled to *executed* checks.

Philosophy: compile the standard into the existing gate
-------------------------------------------------------
A per-story acceptance test protects *one* story; nothing in the pipeline
protects the *project* — the cross-cutting invariants that must hold everywhere
(a security rule, a perf budget, an API-shape convention, a domain invariant).
The constitution fills that gap, and it does so with **zero new enforcement
machinery**. That is the whole design win.

A boss-tier call derives a small set of non-negotiable rules from the brief
(once, between SPEC and PLAN). Each rule is then *compiled* to something the
project already knows how to execute:

* ``kind=test``    → a self-contained pytest file seeded under
  ``tests/constitution/`` in the workspace. It rides the project's existing
  deterministic pytest gate, per-story worktrees and post-merge canary exactly
  like any hand-written test — no scheduler, no runner, no new gate. A
  constitution violation simply becomes a *red bar*.
* ``kind=command`` → a shell command expected to exit 0, run by whatever already
  runs the project's commands.

The advisory demotion valve
---------------------------
Not every rule can be made executable ("the UI should feel snappy"), and a rule
that *claims* to be a test but whose ``check_code`` is not real, runnable pytest
would poison the gate with an import/collection error — a wrong checker is worse
than no checker. So compilation has a safety valve: a ``kind=test`` rule whose
``check_code`` does not parse as pytest with at least one ``test_*`` function (or
``Test*`` class) is **demoted to advisory** rather than seeded as a broken test.
Advisory rules never touch the gate; they are prompt-injected into the relevant
agents as guidance only. Demotion is never silent — a demoted rule stays in the
compiled ``advisory`` bucket so callers can still surface it.

Immutability
------------
Compiled constitution test paths are handed to callers via
:func:`immutable_test_paths` so that W2 arbitration (``fix_test``) and W5
amendment never target them: the constitution is the floor under both
contestation mechanisms. It cannot be argued away by a worker or an amendment —
only re-derived deliberately.

This module only *derives* and *compiles*; it never writes files or runs
anything. Callers seed the returned ``(path, content)`` pairs into the workspace.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Callable, Optional

from ..agents.personas import persona
from . import schema as _schema

# --------------------------------------------------------------------------- #
# Rule schema
# --------------------------------------------------------------------------- #

#: schema.py-format spec for ONE constitution rule.
RULE_SCHEMA: dict = {
    "id": {"type": str, "required": True},
    "statement": {"type": str, "required": True},
    "kind": {"type": str, "required": True, "choices": ["test", "command", "advisory"]},
    "immutable": {"type": bool, "required": False},
    # pytest source for kind=test; shell command for kind=command.
    "check_code": {"type": str, "required": False},
    "check_cmd": {"type": str, "required": False},
}

# Defensive prompt budgets — a boss call reasons over the salient brief, not a novel.
_MAX_BRIEF = 6000


def _truncate(text: object, limit: int) -> str:
    """Clamp ``text`` to ``limit`` chars, marking the cut so the model knows."""
    if text is None:
        return ""
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [truncated, {len(text) - limit} more chars]"


# --------------------------------------------------------------------------- #
# Derivation (boss-tier)
# --------------------------------------------------------------------------- #

def build_prompt(*, brief: str, project_name: str = "", max_rules: int = 8) -> str:
    """Build a compact, evidence-first constitution-derivation prompt.

    Lays out the brief and asks the ``constitution`` persona for a small set of
    non-negotiable, project-wide rules, each declared as a checkable JSON object,
    wrapped in a ``{"rules": [...]}`` envelope.
    """
    name = (project_name or "").strip()
    header = f"Project: {name}\n\n" if name else ""
    return (
        "Derive the CONSTITUTION for this project: a SMALL set of non-negotiable, "
        "project-wide quality rules grounded in the brief below — security, "
        "performance budgets, accessibility, API conventions, domain invariants. "
        "Only high-value, cross-cutting rules; do not restate per-story acceptance "
        "criteria.\n\n"
        f"{header}"
        f"## Brief\n{_truncate(brief, _MAX_BRIEF) or '(none provided)'}\n\n"
        f"## Rules\n"
        f"Produce AT MOST {max_rules} rules. Every rule must be CHECKABLE. Prefer to "
        "make each rule executable:\n"
        "  - kind=test: provide `check_code` = a self-contained, runnable pytest "
        "module (at least one `test_*` function or `Test*` class) that FAILS when "
        "the rule is violated. It must import only what it needs and run standalone.\n"
        "  - kind=command: provide `check_cmd` = a shell command that must exit 0 "
        "when the rule holds.\n"
        "  - kind=advisory: only when the rule genuinely cannot be made executable.\n"
        "Set `immutable: true` for rules that must never be weakened by later "
        "contestation.\n\n"
        "Each rule object: "
        '{"id": <short slug>, "statement": <one sentence>, '
        '"kind": "test"|"command"|"advisory", "immutable": <bool>, '
        '"check_code": <pytest source, for kind=test>, '
        '"check_cmd": <shell command, for kind=command>}.\n\n'
        'Reply with EXACTLY ONE JSON object: {"rules": [ <rule>, ... ]}. '
        "No prose outside the JSON."
    )


async def aderive_constitution(
    runner,
    *,
    brief: str,
    project_name: str = "",
    max_rules: int = 8,
    cwd: Optional[Path] = None,
    model: Optional[str] = None,
    emit: Optional[Callable[[str], None]] = None,
) -> list[dict]:
    """Derive the project constitution as a list of validated rule dicts.

    A boss-tier call using the ``constitution`` persona. The model returns a
    ``{"rules": [...]}`` envelope; each rule is coerced + validated against
    :data:`RULE_SCHEMA` individually. Invalid rules are **dropped** (never fatal),
    the surviving rules are capped at ``max_rules``. Returns ``[]`` if the model
    yields nothing usable rather than raising for ordinary content problems.
    """
    prompt = build_prompt(brief=brief, project_name=project_name, max_rules=max_rules)

    # arun_json validates a single object; we validate the inner rules ourselves,
    # so define a permissive envelope schema (just require the `rules` list).
    envelope_schema = {"rules": {"type": list, "required": True}}
    try:
        envelope = await _schema.arun_json(
            runner,
            prompt,
            persona("constitution"),
            envelope_schema,
            cwd=cwd,
            model=model,
            emit=emit,
        )
    except Exception:
        # A malformed envelope after retries is not fatal — no constitution.
        return []

    raw_rules = envelope.get("rules") or []
    if not isinstance(raw_rules, list):
        return []

    valid: list[dict] = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            continue
        coerced = _schema.coerce(raw, RULE_SCHEMA)
        ok, _errors = _schema.validate(coerced, RULE_SCHEMA)
        if ok:
            valid.append(coerced)
        if len(valid) >= max(0, max_rules):
            break

    return valid


# --------------------------------------------------------------------------- #
# Compilation to executed checks
# --------------------------------------------------------------------------- #

_TESTS_DIR = "tests/constitution"
_SANITIZE_RE = re.compile(r"[^a-z0-9]+")


def is_runnable_pytest(source: str) -> bool:
    """Whether ``source`` is real, runnable pytest.

    Requires the source to parse (no ``SyntaxError``) AND to contain at least one
    ``test_*`` function (module-level or nested in a class) or a ``Test*`` class.
    Empty / non-string / syntactically broken source → ``False``.
    """
    if not source or not isinstance(source, str) or not source.strip():
        return False
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            return True
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            return True
    return False


def _sanitize_id(rule_id: str) -> str:
    """Turn a rule id into a safe file stem, e.g. ``No SQL Injection!`` → ``no_sql_injection``."""
    slug = _SANITIZE_RE.sub("_", str(rule_id).strip().lower()).strip("_")
    return slug or "rule"


def _thirdparty_roots(source: str) -> list[str]:
    """Every imported root module of ``source`` that is neither stdlib nor
    ``pytest`` — wherever the import lives (top-level OR nested in a helper /
    fixture / test body: the agent often writes ``def _client(): from
    fastapi.testclient import TestClient`` and a nested import raises at RUN
    time instead of collection time — same red suite, same cascade).

    A constitution test is compiled right after SPEC, BEFORE any story has added
    its dependencies to the workspace ``pyproject.toml``. Every third-party root
    found gets a module-level ``pytest.importorskip`` guard: the whole invariant
    file SKIPS until the dependency lands, then activates automatically."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    stdlib = getattr(sys, "stdlib_module_names", frozenset())
    roots: list[str] = []
    for node in ast.walk(tree):  # ALL imports, nested included
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        else:
            continue
        for name in names:
            root = name.split(".")[0]
            if root and root not in stdlib and root != "pytest" and root not in roots:
                roots.append(root)
    return roots


def render_pytest_file(rule: dict) -> "tuple[str, str] | None":
    """Render a ``kind=test`` rule into a ``(path, content)`` seeded-test pair.

    ``path`` is ``tests/constitution/test_<sanitized_id>.py``; ``content`` is a
    header comment naming the rule id + statement followed by the rule's
    ``check_code``. Returns ``None`` when the rule is not a runnable pytest test
    (so the caller / :func:`compile_rules` can demote it to advisory).
    """
    if not isinstance(rule, dict) or rule.get("kind") != "test":
        return None
    check_code = rule.get("check_code")
    if not is_runnable_pytest(check_code):
        return None

    rule_id = str(rule.get("id", "rule"))
    statement = str(rule.get("statement", "")).replace("\n", " ").strip()
    path = f"{_TESTS_DIR}/test_{_sanitize_id(rule_id)}.py"
    header = (
        f"# Constitution rule: {rule_id}\n"
        f"# {statement}\n"
        "# Auto-compiled — immutable: do NOT edit or delete (W2/W5 protected).\n\n"
    )
    guard = ""
    roots = _thirdparty_roots(check_code)
    if roots:
        skips = "\n".join(f'pytest.importorskip("{root}")' for root in roots)
        guard = (
            "import pytest\n\n"
            "# Dépendances potentiellement pas encore livrées à ce stade du build :\n"
            "# SKIP propre (pas d'échec de collecte) — l'invariant s'active dès\n"
            "# qu'elles arrivent dans le pyproject du workspace.\n"
            f"{skips}\n\n"
        )
    content = header + guard + check_code.rstrip() + "\n"
    return path, content


def compile_rules(rules: list[dict]) -> dict:
    """Compile a list of rule dicts into executed checks + advisory guidance.

    Returns::

        {
            "tests":    [(path, content), ...],   # kind=test, runnable
            "commands": [(id, cmd), ...],          # kind=command with a check_cmd
            "advisory": [rule, ...],               # kind=advisory + DEMOTED tests
        }

    A ``kind=test`` rule whose ``check_code`` is not runnable pytest is **demoted**
    into ``advisory`` (kept, not silently dropped) — the demotion valve that keeps
    a broken checker out of the gate. A ``kind=command`` rule missing a usable
    ``check_cmd`` is likewise demoted to advisory.
    """
    tests: list[tuple[str, str]] = []
    commands: list[tuple[str, str]] = []
    advisory: list[dict] = []

    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        kind = rule.get("kind")

        if kind == "test":
            rendered = render_pytest_file(rule)
            if rendered is not None:
                tests.append(rendered)
            else:
                advisory.append(rule)  # demotion valve
        elif kind == "command":
            cmd = rule.get("check_cmd")
            if isinstance(cmd, str) and cmd.strip():
                commands.append((str(rule.get("id", "rule")), cmd))
            else:
                advisory.append(rule)  # command without a command → advisory
        else:
            # kind=advisory (and any unexpected kind) → advisory guidance.
            advisory.append(rule)

    return {"tests": tests, "commands": commands, "advisory": advisory}


def immutable_test_paths(compiled: dict) -> set[str]:
    """The set of compiled constitution test file paths.

    Callers use this so W2 ``fix_test`` and W5 amendment never target a
    constitution test — the compiled tests are the immutable floor under both.
    """
    return {path for path, _content in (compiled or {}).get("tests", [])}
