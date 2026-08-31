"""Read only access to the two versioned agent interface schemas (A11).

``schemas/observation.v1.json`` and ``schemas/action.v1.json`` are owned by A01
and are **inputs** to this package: they are loaded once, cached, and never
patched at runtime (CONTRACTS section 8.2, "a mutated schema is a different
schema and the provider caches it"). Two guarantees follow from that sentence
and are implemented here:

* :func:`load_schema` returns a **deep copy** of the cached document, so a
  caller that mutates what it got back cannot corrupt the copy the validator
  and the provider CLI use.
* the cache is keyed by name only. There is no reload hook, no environment
  variable and no argument that could make two calls in one process see two
  different schemas (CONTRACTS section 2.6: no module reads a file path from
  the environment).

The schemas directory is found by walking up from this module until a directory
holding ``action.v1.json`` appears, which works both from a source checkout and
from an editable install. Nothing here reads a clock, a socket or ``sys.argv``.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped, unused-ignore]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped, unused-ignore]

from pxe.errors import InvalidConfigError, SchemaValidationError

__all__ = ["action_schema", "load_schema", "observation_schema", "validator_for"]

#: The two schema names this registry knows, in the order of CONTRACTS section 8.
_SCHEMA_NAMES: tuple[str, ...] = ("observation.v1", "action.v1")

#: File that must exist for a directory to be recognised as the schemas root.
_ANCHOR_FILE = "action.v1.json"


@lru_cache(maxsize=1)
def _schemas_dir() -> Path:
    """Locate the repository ``schemas/`` directory.

    Returns:
        Absolute path of the directory holding the versioned schemas.

    Raises:
        SchemaValidationError: If no ancestor directory holds ``schemas/``.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "schemas"
        if (candidate / _ANCHOR_FILE).is_file():
            return candidate
    raise SchemaValidationError("schemas directory not found", searched_from=str(here))


@lru_cache(maxsize=len(_SCHEMA_NAMES))
def _cached_schema(name: str) -> dict[str, Any]:
    """Parse one schema file once per process.

    The returned mapping is the cache itself and is therefore private: every
    public accessor hands out a deep copy.

    Args:
        name: One of ``"observation.v1"`` or ``"action.v1"``.

    Returns:
        The parsed schema document.

    Raises:
        InvalidConfigError: If ``name`` is not a known schema name. This is a
            caller bug, not agent input.
        SchemaValidationError: If the file is missing, unreadable, not JSON, or
            not a JSON object.
    """
    if name not in _SCHEMA_NAMES:
        raise InvalidConfigError("unknown schema name", name=name, known=list(_SCHEMA_NAMES))
    path = _schemas_dir() / f"{name}.json"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SchemaValidationError("schema file cannot be read", name=name, path=str(path)) from exc
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError("schema file is not valid JSON", name=name, path=str(path)) from exc
    if not isinstance(parsed, dict):
        raise SchemaValidationError("schema document is not an object", name=name, path=str(path))
    return parsed


def load_schema(name: str) -> dict[str, Any]:
    """Return one versioned schema document by name.

    Args:
        name: ``"observation.v1"`` or ``"action.v1"``.

    Returns:
        A deep copy of the parsed schema, safe for the caller to mutate.

    Raises:
        InvalidConfigError: If ``name`` is unknown.
        SchemaValidationError: If the file is missing or malformed.
    """
    return copy.deepcopy(_cached_schema(name))


def action_schema() -> dict[str, Any]:
    """Return ``schemas/action.v1.json`` (CONTRACTS section 8.2).

    Returns:
        A deep copy of the action schema.
    """
    return load_schema("action.v1")


def observation_schema() -> dict[str, Any]:
    """Return ``schemas/observation.v1.json`` (CONTRACTS section 8.1).

    Returns:
        A deep copy of the observation schema.
    """
    return load_schema("observation.v1")


@lru_cache(maxsize=len(_SCHEMA_NAMES))
def validator_for(name: str) -> Draft202012Validator:
    """Return the cached Draft 2020-12 validator for one schema.

    The validator is built over a private deep copy, so mutating
    ``load_schema(name)`` afterwards cannot change what it enforces. The schema
    itself is checked against its meta schema on first use: a malformed schema
    is a packaging bug and must fail loudly rather than validate nothing.

    Args:
        name: ``"observation.v1"`` or ``"action.v1"``.

    Returns:
        A validator instance, shared between callers and never reconfigured.

    Raises:
        InvalidConfigError: If ``name`` is unknown.
        SchemaValidationError: If the file is missing, malformed, or is not a
            valid Draft 2020-12 schema.
    """
    schema = load_schema(name)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise SchemaValidationError("schema is not a valid Draft 2020-12 document", name=name) from exc
    validator: Draft202012Validator = Draft202012Validator(schema)
    return validator
