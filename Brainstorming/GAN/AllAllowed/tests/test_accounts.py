"""Tests for the accounts ledger (W2, CONTRACTS section 5.3).

Credits are integer money and lifespan at once; roles are the privilege ledger; ``total`` underwrites
the closed-system invariant (AC-3). Negative balances are legal (an agent can go bust below the floor),
so we assert they are allowed rather than clamped.
"""

from __future__ import annotations

import pytest

from ala.errors import KernelError
from ala.kernel.accounts import Accounts
from ala.types import Role


def test_open_sets_balance_role_and_existence() -> None:
    acc = Accounts()
    acc.open("seat-01", 100)
    assert acc.exists("seat-01")
    assert acc.balance("seat-01") == 100
    assert acc.role("seat-01") is Role.USER


def test_double_open_raises() -> None:
    acc = Accounts()
    acc.open("seat-01", 100)
    with pytest.raises(KernelError):
        acc.open("seat-01", 50)


def test_credit_adds_to_balance() -> None:
    acc = Accounts()
    acc.open("seat-01", 100)
    acc.credit("seat-01", 25)
    assert acc.balance("seat-01") == 125


def test_negative_credit_is_allowed_and_may_go_below_zero() -> None:
    acc = Accounts()
    acc.open("seat-01", 30)
    acc.credit("seat-01", -100)
    assert acc.balance("seat-01") == -70


def test_credit_on_unknown_account_raises() -> None:
    acc = Accounts()
    with pytest.raises(KernelError):
        acc.credit("ghost", 10)


def test_set_role_promotes_to_root() -> None:
    acc = Accounts()
    acc.open("seat-01", 100)
    acc.set_role("seat-01", Role.ROOT)
    assert acc.role("seat-01") is Role.ROOT


def test_set_role_on_unknown_account_raises() -> None:
    acc = Accounts()
    with pytest.raises(KernelError):
        acc.set_role("ghost", Role.ROOT)


def test_total_sums_every_balance() -> None:
    acc = Accounts()
    acc.open("seat-01", 100)
    acc.open("seat-02", 50)
    acc.open("seat-03", -20)
    assert acc.total() == 130


def test_total_tracks_credits_over_time() -> None:
    acc = Accounts()
    acc.open("seat-01", 100)
    acc.open("seat-02", 100)
    before = acc.total()
    acc.credit("seat-01", 40)
    acc.credit("seat-02", -40)
    # A pure transfer between two accounts leaves the closed-system total unchanged.
    assert acc.total() == before


def test_agents_are_sorted() -> None:
    acc = Accounts()
    acc.open("seat-03", 0)
    acc.open("seat-01", 0)
    acc.open("seat-02", 0)
    assert acc.agents() == ("seat-01", "seat-02", "seat-03")


def test_open_with_explicit_key_is_stored() -> None:
    acc = Accounts()
    acc.open("seat-01", 100, key="custom-key")
    assert acc.key("seat-01") == "custom-key"


def test_open_default_key_derives_from_id() -> None:
    acc = Accounts()
    acc.open("seat-01", 100)
    assert acc.key("seat-01") == "key-seat-01"
