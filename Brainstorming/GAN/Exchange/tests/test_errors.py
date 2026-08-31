"""Tests for ``pxe.errors`` (owner A01, CONTRACTS section 2.4).

The error taxonomy is the one thing every one of the twenty-five workstreams
touches, and it is load bearing twice: ``code`` values become
``RejectReason`` members in the journal, and the CLI exit code (section 7.22)
is chosen from the exception family. So the codes have to be unique, stable
and machine readable, and the families have to be disjoint.
"""

from __future__ import annotations

import inspect

import pytest

from pxe import errors as errors_mod
from pxe.errors import (
    AccountingError,
    ConfigError,
    DeterminismError,
    EngineError,
    ExchangeError,
    GatewayError,
    InvalidConfigError,
    InvariantViolationError,
    NonCanonicalValueError,
    PxeError,
    StoreError,
    TournamentError,
    ValidationError,
)


def _all_error_classes() -> tuple[type[PxeError], ...]:
    """Every exported error class, in ``__all__`` order."""
    classes = []
    for name in errors_mod.__all__:
        obj = getattr(errors_mod, name)
        assert inspect.isclass(obj), f"{name} in __all__ is not a class"
        assert issubclass(obj, PxeError), f"{name} does not descend from PxeError"
        classes.append(obj)
    return tuple(classes)


def test_all_is_non_empty_and_every_name_resolves() -> None:
    classes = _all_error_classes()
    assert len(classes) >= 20, "the taxonomy of section 2.4 has at least twenty members"


def test_every_code_is_unique() -> None:
    seen: dict[str, str] = {}
    for cls in _all_error_classes():
        code = cls.code
        assert code not in seen or seen[code] == cls.__name__, (
            f"{cls.__name__} and {seen[code]} share the code {code!r}; "
            "codes become RejectReason members and must be unique"
        )
        seen[code] = cls.__name__
    assert len(seen) == len(_all_error_classes())


def test_every_code_is_screaming_snake_case() -> None:
    for cls in _all_error_classes():
        code = cls.code
        assert code, f"{cls.__name__} has an empty code"
        assert code == code.upper(), f"{cls.__name__}.code {code!r} is not upper case"
        assert code.replace("_", "").isalnum(), f"{cls.__name__}.code {code!r} is not snake case"


def test_the_six_families_are_disjoint() -> None:
    """A caught family decides the CLI exit code, so overlap is a wrong exit code."""
    families = (
        ConfigError,
        DeterminismError,
        ValidationError,
        ExchangeError,
        AccountingError,
        EngineError,
        GatewayError,
        StoreError,
        TournamentError,
    )
    for i, left in enumerate(families):
        for right in families[i + 1 :]:
            assert not issubclass(left, right), f"{left.__name__} is also a {right.__name__}"
            assert not issubclass(right, left), f"{right.__name__} is also a {left.__name__}"


def test_context_is_kept_and_rendered_sorted() -> None:
    error = InvalidConfigError("bad ticks", ticks=3, template_id="election")
    assert error.message == "bad ticks"
    assert error.context == {"ticks": 3, "template_id": "election"}
    rendered = str(error)
    assert rendered.startswith("[INVALID_CONFIG] bad ticks (")
    # Sorted by key so two processes render one error identically.
    assert rendered.index("template_id=") < rendered.index("ticks=3")
    assert str(InvalidConfigError("plain")) == "[INVALID_CONFIG] plain"


def test_invariant_violation_is_an_accounting_error_and_never_a_config_error() -> None:
    """Section 2.4 and R2 finding 18: an I4 breach is exit code 4, not 1."""
    assert issubclass(InvariantViolationError, AccountingError)
    assert not issubclass(InvariantViolationError, ConfigError)
    assert not issubclass(InvalidConfigError, AccountingError)


def test_non_canonical_value_is_a_determinism_error() -> None:
    """``canonical_json`` refusing a float is a determinism failure, not a validation one."""
    assert issubclass(NonCanonicalValueError, DeterminismError)


def test_raising_and_catching_by_root() -> None:
    with pytest.raises(PxeError) as caught:
        raise GatewayError("provider is down", agent_id="A3")
    assert caught.value.context["agent_id"] == "A3"


def test_no_error_class_is_missing_from_all() -> None:
    exported = set(errors_mod.__all__)
    for name, obj in vars(errors_mod).items():
        if inspect.isclass(obj) and issubclass(obj, PxeError) and obj.__module__ == errors_mod.__name__:
            assert name in exported, f"{name} is a public error class missing from __all__"
