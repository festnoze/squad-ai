"""Anchor tests for :mod:`pxe.types` (A01).

These guard the two contract rules that, when broken, stop every other
workstream on day one: the match configuration must be journal encodable, and
the canonical account order must have exactly one implementation.
"""

import dataclasses
import typing

import pytest

from pxe.errors import InvalidConfigError
from pxe.events import canonical_json
from pxe.types import (
    MatchConfig,
    bps_ratio,
    config_from_journal_dict,
    config_to_journal_dict,
    max_taker_fee_cents,
    sorted_account_ids,
    sorted_ids,
    taker_fee_cents,
)


# --------------------------------------------------------------------------
# Section 2.6: MatchConfig is journal encodable, and float free
# --------------------------------------------------------------------------
@pytest.mark.determinism
def test_match_config_is_journal_encodable() -> None:
    """MatchStarted is seq 1 of every match. It must not raise."""
    config = MatchConfig()
    as_dict = dataclasses.asdict(config)
    assert canonical_json(as_dict)  # would raise NonCanonicalValueError on a float
    encoded = config_to_journal_dict(config)
    assert canonical_json(encoded)
    assert encoded["seed"] == 0
    assert encoded["mm_initial_cash_cents"] == 10_000_000


@pytest.mark.determinism
def test_match_config_has_no_float_field() -> None:
    """A float anywhere in MatchConfig crashes canonical_json (section 2.6)."""
    hints = typing.get_type_hints(MatchConfig)
    floats = [name for name, hint in hints.items() if hint is float]
    assert floats == [], f"MatchConfig must be float free, found {floats}"

    def walk(value: object, path: str) -> list[str]:
        found: list[str] = []
        if isinstance(value, float):
            found.append(path)
        elif isinstance(value, dict):
            for key, item in value.items():
                found.extend(walk(item, f"{path}.{key}"))
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                found.extend(walk(item, f"{path}[{index}]"))
        return found

    assert walk(dataclasses.asdict(MatchConfig()), "$") == []


def test_config_journal_round_trip() -> None:
    """FR-5.1.3: replay_journal needs the inverse of the encoder."""
    config = MatchConfig(seed=7, ticks_total=24, n_agents=4, taker_fee_bps=25)
    assert config_from_journal_dict(config_to_journal_dict(config)) == config


def test_mm_cash_must_cover_an_agent() -> None:
    with pytest.raises(InvalidConfigError):
        MatchConfig(initial_cash_cents=1_000_000, mm_initial_cash_cents=1_000)


# --------------------------------------------------------------------------
# Section 2.3: one canonical account order
# --------------------------------------------------------------------------
@pytest.mark.determinism
def test_canonical_account_order() -> None:
    """Ranked agents ascending, then MM, then FEES. Nothing else."""
    assert sorted_account_ids(["FEES", "A10", "MM", "A2", "A1"]) == ("A1", "A2", "A10", "MM", "FEES")
    assert sorted_account_ids(["MM", "FEES"]) == ("MM", "FEES")
    assert sorted_account_ids([]) == ()


@pytest.mark.determinism
def test_sorted_ids_refuses_account_ids() -> None:
    """The helper must be unable to produce the non canonical order."""
    assert sorted_ids(["A10", "A2", "A1"]) == ("A1", "A2", "A10")
    assert sorted_ids(["M10", "M2", "M1"]) == ("M1", "M2", "M10")
    for bad in (["A1", "MM"], ["A1", "FEES"]):
        with pytest.raises(InvalidConfigError):
            sorted_ids(bad)


def test_sorted_account_ids_rejects_unknown_ids() -> None:
    with pytest.raises(InvalidConfigError):
        sorted_account_ids(["A1", "M1"])


# --------------------------------------------------------------------------
# Section 2.1: signed ratios and fee arithmetic
# --------------------------------------------------------------------------
def test_bps_ratio_is_symmetric_around_zero() -> None:
    """Floor division would report -1 for the loss and 0 for the gain."""
    assert bps_ratio(1, 1_000_000) == 0
    assert bps_ratio(-1, 1_000_000) == 0
    assert bps_ratio(51, 1_000_000) == 1
    assert bps_ratio(-51, 1_000_000) == -1
    for cents in (0, 1, 49, 50, 51, 1234, 999_999, 1_000_000):
        assert bps_ratio(cents, 1_000_000) == -bps_ratio(-cents, 1_000_000)


def test_bps_ratio_rejects_a_null_denominator() -> None:
    with pytest.raises(InvalidConfigError):
        bps_ratio(100, 0)


def test_fee_reserve_is_never_under_the_realised_fees() -> None:
    """Partial fills must never cost more than what was reserved (section 6.1)."""
    bps = 200
    for qty in (1, 3, 7, 25, 100):
        reserved = max_taker_fee_cents(bps, qty)
        for split in range(1, qty + 1):
            first, second = split, qty - split
            realised = taker_fee_cents(bps, 99, first) + taker_fee_cents(bps, 99, second)
            assert realised <= reserved
