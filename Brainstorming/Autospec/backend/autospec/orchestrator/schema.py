"""Schema-validated decision outputs — the guardrail for agent DECISION calls.

Why this exists
---------------
``extract_json`` (in ``..agents.runner``) is deliberately *tolerant*: it scavenges
the first brace-balanced JSON object out of an agent reply, tolerating fences and
surrounding prose. That is the right behaviour for free-form content, but it is
dangerous for a **decision**: when the orchestrator asks a classifier for a
verdict, a judge for a score, or an arbiter for a ruling, a misparse silently
becomes a *wrong decision*. There is no exception — just a plausible-looking dict
with a missing key, a string where an int was expected, or a score of 999.

A silent misparse = a wrong decision. This module is the guardrail for the
classifier / arbiter / judge calls in Waves 1–2 of the swarm upgrade: it validates
the extracted dict against a lightweight, dependency-free schema and, for the
agentic path (:func:`arun_json`), re-prompts the agent once (by default) with the
concrete validation errors appended, so a recoverable formatting slip is fixed
instead of poisoning a downstream decision.

Schema format
-------------
A schema is a ``dict`` mapping field name -> spec. A spec is either:

* a bare Python type — one of ``int``, ``str``, ``bool``, ``float``, ``list``,
  ``dict`` — meaning "this key is required and must be of that type"; or
* a ``dict`` with any of these keys::

      {
          "type": int,          # a Python type (as above); optional
          "required": True,     # default True
          "choices": [1, 2, 3], # allowed values (enum); optional
          "min": 0,             # numeric lower bound (inclusive); optional
          "max": 100,           # numeric upper bound (inclusive); optional
      }

Type rules (see :func:`validate`):

* ``float`` is lenient: an ``int`` *is* a valid ``float``.
* ``bool`` is **not** a valid ``int`` (and an ``int`` is not a valid ``bool``) —
  Python makes ``bool`` a subclass of ``int``, but a decision that expects a
  numeric score must not silently accept ``True``.
* ``choices`` / ``min`` / ``max`` are only checked when the key is present.

Nothing here raises for ordinary validation problems: :func:`validate` returns
``(ok, errors)`` and :func:`coerce` returns a best-effort new dict. Only
:func:`arun_json` raises, and only :class:`AgentError`, after retries are spent.
"""

from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable, Optional

from ..agents.runner import AgentError, AgentResult, extract_json

# The set of Python types the schema format understands.
_ALLOWED_TYPES = (int, str, bool, float, list, dict)

_TYPE_NAMES = {
    int: "int",
    str: "str",
    bool: "bool",
    float: "float",
    list: "list",
    dict: "dict",
}


def _normalize_spec(spec: object) -> dict:
    """Turn a bare-type or dict spec into a canonical dict spec.

    A bare type ``int`` becomes ``{"type": int, "required": True}``.
    """
    if isinstance(spec, type):
        return {"type": spec, "required": True}
    if isinstance(spec, dict):
        return dict(spec)
    # Unknown spec shape: treat as an unconstrained required field.
    return {"required": True}


def _type_matches(value: object, expected: type) -> bool:
    """Whether ``value`` satisfies ``expected`` under the schema's type rules."""
    if expected is bool:
        # bool must be exactly a bool (not the int 0/1).
        return isinstance(value, bool)
    if expected is int:
        # A bool is NOT a valid int (bool subclasses int in Python).
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is float:
        # Lenient: an int is a valid float. A bool is not.
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected in (str, list, dict):
        return isinstance(value, expected)
    # Unknown expected type — be permissive rather than raise.
    return True


def validate(data: dict, schema: dict) -> tuple[bool, list[str]]:
    """Validate ``data`` against ``schema``. Returns ``(ok, errors)``; never raises.

    Checks, per field: required-key presence, type match (see module docstring
    for the int/float/bool rules), ``choices`` membership, and numeric
    ``min`` / ``max`` bounds. Unknown keys in ``data`` are ignored.
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return False, [f"expected a JSON object, got {type(data).__name__}"]

    for field, raw_spec in schema.items():
        spec = _normalize_spec(raw_spec)
        required = spec.get("required", True)
        present = field in data

        if not present:
            if required:
                errors.append(f"missing required field '{field}'")
            continue

        value = data[field]
        expected = spec.get("type")
        if isinstance(expected, type) and not _type_matches(value, expected):
            errors.append(
                f"field '{field}' expected type {_TYPE_NAMES.get(expected, expected)}, "
                f"got {type(value).__name__}"
            )
            # Type is wrong: skip choices/min/max (they would be noise).
            continue

        choices = spec.get("choices")
        if choices is not None and value not in choices:
            errors.append(f"field '{field}' value {value!r} not in choices {list(choices)!r}")

        lo = spec.get("min")
        hi = spec.get("max")
        if (lo is not None or hi is not None) and isinstance(value, (int, float)) and not isinstance(value, bool):
            if lo is not None and value < lo:
                errors.append(f"field '{field}' value {value} below min {lo}")
            if hi is not None and value > hi:
                errors.append(f"field '{field}' value {value} above max {hi}")

    return (not errors), errors


def _coerce_value(value: object, expected: type) -> object:
    """Best-effort coercion of a single value toward ``expected``. On failure
    the original value is returned unchanged (validation reports the mismatch)."""
    if expected is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            low = value.strip().lower()
            if low in ("true", "yes", "1"):
                return True
            if low in ("false", "no", "0"):
                return False
        return value
    if expected is int:
        if isinstance(value, bool):
            return value  # never silently turn True into 1
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                return value
        return value
    if expected is float:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return value
        return value
    if expected is str:
        # Only coerce scalars to str; leave containers alone.
        if isinstance(value, (int, float, bool)):
            return str(value)
        return value
    return value


def coerce(data: dict, schema: dict) -> dict:
    """Return a NEW dict with each schema field best-effort coerced to its type.

    Examples: ``"80"`` -> ``80`` for an ``int`` field; ``"true"`` / ``"false"``
    -> ``bool``. Values that cannot be coerced are left as-is (so :func:`validate`
    still reports the real mismatch). Fields absent from ``data`` are not added,
    and keys not mentioned by ``schema`` are copied through untouched.
    """
    if not isinstance(data, dict):
        return data
    result = dict(data)
    for field, raw_spec in schema.items():
        if field not in result:
            continue
        spec = _normalize_spec(raw_spec)
        expected = spec.get("type")
        if isinstance(expected, type):
            result[field] = _coerce_value(result[field], expected)
    return result


def describe_schema(schema: dict) -> str:
    """A compact human/agent-readable description of ``schema`` for a prompt.

    Produces one line per field, e.g.::

        - score: int, required, min 0, max 100
        - verdict: str, required, one of ['pass', 'fail']
        - notes: str, optional
    """
    lines: list[str] = []
    for field, raw_spec in schema.items():
        spec = _normalize_spec(raw_spec)
        parts: list[str] = []
        expected = spec.get("type")
        if isinstance(expected, type):
            parts.append(_TYPE_NAMES.get(expected, getattr(expected, "__name__", str(expected))))
        parts.append("required" if spec.get("required", True) else "optional")
        choices = spec.get("choices")
        if choices is not None:
            parts.append(f"one of {list(choices)!r}")
        if spec.get("min") is not None:
            parts.append(f"min {spec['min']}")
        if spec.get("max") is not None:
            parts.append(f"max {spec['max']}")
        lines.append(f"- {field}: {', '.join(parts)}")
    return "\n".join(lines)


async def arun_json(
    runner: "AgentRunnerLike",
    prompt: str,
    system_prompt: str,
    schema: dict,
    *,
    cwd: Optional[Path] = None,
    model: Optional[str] = None,
    retries: int = 1,
    emit: Optional[Callable[[str], None]] = None,
) -> dict:
    """Run an agent and return a schema-valid decision dict.

    Calls ``runner.arun(...)``, extracts the first JSON object with
    :func:`extract_json`, :func:`coerce`\\ s it toward the schema, then
    :func:`validate`\\ s it. On failure it re-prompts the agent up to ``retries``
    additional times, appending the concrete validation errors and the schema
    description to the prompt so the model can self-correct. Raises
    :class:`AgentError` if the reply is still invalid after all retries (or if
    ``extract_json`` finds no JSON at all).

    ``emit`` — if given — is called with short human-readable progress strings
    (e.g. a retry notice); it must not raise.
    """
    base_prompt = prompt
    last_errors: list[str] = []
    # 1 initial attempt + `retries` retries.
    attempts = max(0, retries) + 1

    for attempt in range(attempts):
        if attempt == 0:
            this_prompt = base_prompt
        else:
            this_prompt = (
                f"{base_prompt}\n\n"
                f"Your previous reply was invalid: {'; '.join(last_errors)}. "
                f"Return ONLY a JSON object matching:\n{describe_schema(schema)}"
            )
            if emit is not None:
                try:
                    emit(f"decision output invalid, retrying ({attempt}/{retries}): {'; '.join(last_errors)}")
                except Exception:
                    pass

        result: AgentResult = await runner.arun(
            this_prompt, system_prompt, cwd=cwd, model=model
        )

        try:
            raw = extract_json(result.text)
        except AgentError as exc:
            last_errors = [str(exc)]
            continue

        coerced = coerce(raw, schema)
        ok, errors = validate(coerced, schema)
        if ok:
            return coerced
        last_errors = errors

    raise AgentError(
        "agent decision failed schema validation after "
        f"{attempts} attempt(s): {'; '.join(last_errors) or 'unknown error'}"
    )


# Structural alias for the runner Protocol; avoids importing the Protocol type
# just for an annotation while keeping the intent clear.
AgentRunnerLike = Callable[..., Awaitable[AgentResult]]
