"""A20 acceptance tests for the sealed held-out bank (PRD 8, AC-P5, T3.5).

Two claims, and they are the two the PRD makes:

* ``test_access_is_logged_and_sealed`` - every access leaves an entry, granted or
  refused, on disk and in memory. There is no accessor that hands out a sealed
  seed without logging, which is what makes the seal structural.
* ``test_sealed_seeds_are_never_drawn_for_training`` - a draw whose purpose is
  not an evaluation purpose raises, returns nothing, and is itself logged. "Jamais
  vus pendant l'iteration" is enforced, not documented.

Anti vacuous rule (CONTRACTS section 10). This module reads no journal, so the
equivalent guard is applied to what it does produce: every test asserts that the
bank actually sealed seeds and that the access log file has lines before it makes
any claim about their content, and ``test_a_sealed_seed_generates_a_real_world``
plays a sealed seed through ``generate_world`` so the bank is proven to hold
usable scenario seeds rather than arbitrary integers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pxe.errors import HeldoutAccessError, InvalidConfigError, StoreError
from pxe.events import JOURNAL_ENCODING
from pxe.tournament.heldout import (
    EVALUATION_PURPOSES,
    HELDOUT_BANK_VERSION,
    HELDOUT_SUBSTREAM,
    HeldoutBank,
)
from pxe.types import SEED_SPACE
from pxe.world.generator import generate_world

BASE_SEED = 20260827
REQUESTER = "pxe tournament run"
PURPOSE = "evaluation"


def bank_of(tmp_path: Path) -> HeldoutBank:
    """Open a bank on a fresh temporary directory."""
    return HeldoutBank(path=tmp_path / "heldout.json", access_log=tmp_path / "heldout_access.jsonl")


def log_lines(tmp_path: Path) -> list[dict[str, object]]:
    """Read the access log file back, one parsed object per line."""
    path = tmp_path / "heldout_access.jsonl"
    assert path.exists(), "the access log file was never written"
    raw = path.read_bytes()
    assert b"\r" not in raw, "the access log must use LF endings (section 4.2)"
    lines = path.read_text(encoding=JOURNAL_ENCODING).splitlines()
    assert lines, "the access log is empty, so every claim about it would be vacuous"
    return [json.loads(line) for line in lines]


# ---------------------------------------------------------------------------
# Reserving: sealing material is not an access
# ---------------------------------------------------------------------------
def test_reserve_seals_distinct_seeds_deterministically(tmp_path: Path) -> None:
    """The same (template, base seed) seals the same set on any machine."""
    first = bank_of(tmp_path).reserve(template_id="election", count=5, base_seed=BASE_SEED)
    assert len(first) == 5, "nothing was sealed"
    assert len(set(first)) == 5, "a seed was sealed twice"
    assert list(first) == sorted(first), "reserve returns its seeds ascending"
    assert all(0 <= seed < SEED_SPACE for seed in first)

    other_dir = tmp_path / "again"
    other_dir.mkdir()
    again = bank_of(other_dir).reserve(template_id="election", count=5, base_seed=BASE_SEED)
    assert again == first, "the sealed set is not a function of (template, base seed)"

    harvest = bank_of(tmp_path / "again").reserve(template_id="harvest", count=5, base_seed=BASE_SEED)
    assert not set(harvest) & set(first), "two templates sealed from one base seed shared a seed"


def test_every_sealed_seed_survives_the_store(tmp_path: Path) -> None:
    """AC-P5 regression: a sealed seed the store cannot hold is a lost held-out run.

    ``match_task.seed`` and ``scenario_instance.seed`` are ``BigInteger``, which
    is signed on SQLite and on Postgres. A bank that drew over the whole
    unsigned 64 bit space produced an unstorable seed roughly every other draw,
    so the run that used it died on the first ``save_task``. Sixty-four seeds is
    enough that the old bound would have failed here with probability above
    ``1 - 2**-64``.
    """
    from pxe.store.db import Store
    from pxe.types import InfoProfileKind, MatchTask

    seeds = bank_of(tmp_path).reserve(template_id="election", count=64, base_seed=BASE_SEED)
    assert len(seeds) == 64, "nothing was sealed, so the store would be handed nothing"
    with Store(runs_dir=tmp_path / "runs") as store:
        store.init_schema()
        for index, seed in enumerate(seeds):
            store.save_task(
                MatchTask(
                    task_id=f"T-sealed-0001#{index:04d}",
                    match_id=f"m-election-{seed}-01",
                    template_id="election",
                    seed=seed,
                    agent_ids=("A1", "A2"),
                    harness_keys=("h-a@1+00000000", "h-b@1+00000000"),
                    profile_assignment=(("A1", InfoProfileKind.GENERALIST), ("A2", InfoProfileKind.DELAYED)),
                    held_out=True,
                ),
                status="pending",
            )
        stored = {task.seed for task in store.pending_tasks("T-sealed-0001")}
    assert stored == set(seeds), "a sealed seed did not survive the round trip"


def test_reserve_extends_an_existing_bank_and_persists_it(tmp_path: Path) -> None:
    """A bank is a file: a second process sees what the first one sealed."""
    bank = bank_of(tmp_path)
    first = bank.reserve(template_id="election", count=3, base_seed=BASE_SEED)
    second = bank.reserve(template_id="election", count=2, base_seed=BASE_SEED + 1)
    assert not set(first) & set(second), "the extension re-sealed a known seed"

    payload = json.loads((tmp_path / "heldout.json").read_text(encoding=JOURNAL_ENCODING))
    assert payload["version"] == HELDOUT_BANK_VERSION
    assert sorted(payload["templates"]["election"]) == sorted(first + second)

    reopened = bank_of(tmp_path)
    drawn = reopened.draw(template_id="election", count=5, requester=REQUESTER, purpose=PURPOSE)
    assert set(drawn) == set(first + second), "the reopened bank lost what was sealed"


def test_reserving_writes_no_access_entry(tmp_path: Path) -> None:
    """Creating sealed material reveals nothing, so it is not an access."""
    bank = bank_of(tmp_path)
    bank.reserve(template_id="election", count=3, base_seed=BASE_SEED)
    assert bank.access_log_entries() == ()
    assert not (tmp_path / "heldout_access.jsonl").exists()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"template_id": "", "count": 1, "base_seed": BASE_SEED},
        {"template_id": "election", "count": 0, "base_seed": BASE_SEED},
        {"template_id": "election", "count": 1, "base_seed": -1},
        {"template_id": "election", "count": 1, "base_seed": 2**64},
    ],
)
def test_reserve_refuses_an_impossible_reservation(tmp_path: Path, kwargs: dict[str, object]) -> None:
    """A reservation that cannot be replayed is a configuration error."""
    with pytest.raises(InvalidConfigError):
        bank_of(tmp_path).reserve(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC-P5 / T3.5: the seal and its log
# ---------------------------------------------------------------------------
def test_access_is_logged_and_sealed(tmp_path: Path) -> None:
    """Every access to the bank leaves an entry, and there is no other way in (AC-P5)."""
    bank = bank_of(tmp_path)
    sealed = bank.reserve(template_id="election", count=4, base_seed=BASE_SEED)
    assert sealed, "nothing was sealed, so nothing could leak"

    drawn = bank.draw(template_id="election", count=2, requester=REQUESTER, purpose=PURPOSE)
    assert drawn == tuple(sorted(sealed)[:2]), "a draw must be repeatable on the same sealed set"
    assert bank.draw(template_id="election", count=2, requester=REQUESTER, purpose=PURPOSE) == drawn

    entries = bank.access_log_entries()
    assert len(entries) == 2, "two draws must leave two entries"
    first = entries[0]
    assert first["access_index"] == 1
    assert first["template_id"] == "election"
    assert first["requester"] == REQUESTER
    assert first["purpose"] == PURPOSE
    assert first["count"] == 2
    assert first["granted"] is True
    assert first["reason"] == ""
    assert list(first["seeds"]) == list(drawn), "the log must say what was handed out"
    with pytest.raises(TypeError):
        first["requester"] = "someone else"  # type: ignore[index]

    on_disk = log_lines(tmp_path)
    assert len(on_disk) == 2
    assert on_disk[0] == dict(first), "the in memory log and the file disagree"
    assert [entry["access_index"] for entry in on_disk] == [1, 2]

    # The seal is structural: no public accessor returns a sealed seed, so the
    # only names that can hand one out are the two that log.
    handing_out = {
        name for name in dir(bank) if not name.startswith("_") and name not in ("reserve", "draw", "access_log_entries")
    }
    assert handing_out == set(), f"an unlogged accessor appeared on the bank: {sorted(handing_out)}"

    reopened = bank_of(tmp_path)
    assert len(reopened.access_log_entries()) == 2, "the log must survive a reopen"
    reopened.draw(template_id="election", count=1, requester="pxe evolve run", purpose="ab_test")
    assert [entry["access_index"] for entry in reopened.access_log_entries()] == [1, 2, 3]
    assert len(log_lines(tmp_path)) == 3


def test_sealed_seeds_are_never_drawn_for_training(tmp_path: Path) -> None:
    """A non evaluation purpose is refused, returns nothing, and is logged (T3.5)."""
    bank = bank_of(tmp_path)
    sealed = bank.reserve(template_id="election", count=3, base_seed=BASE_SEED)
    assert sealed, "nothing was sealed"
    assert "training" not in EVALUATION_PURPOSES

    for purpose in ("training", "iteration", "tuning", "mutation", ""):
        with pytest.raises(HeldoutAccessError):
            bank.draw(template_id="election", count=1, requester=REQUESTER, purpose=purpose)

    entries = bank.access_log_entries()
    assert len(entries) == 5, "a refused access must still be logged"
    for entry in entries:
        assert entry["granted"] is False
        assert entry["reason"] == "NOT_AN_EVALUATION"
        assert list(entry["seeds"]) == [], "a refused access must hand out nothing"
    assert len(log_lines(tmp_path)) == 5

    granted = bank.draw(template_id="election", count=1, requester=REQUESTER, purpose=PURPOSE)
    assert set(granted) <= set(sealed)
    assert bank.access_log_entries()[-1]["granted"] is True


def test_an_anonymous_or_starved_access_is_refused_and_logged(tmp_path: Path) -> None:
    """No requester, no template, or not enough sealed seeds: all refused, all logged."""
    bank = bank_of(tmp_path)
    bank.reserve(template_id="election", count=2, base_seed=BASE_SEED)

    with pytest.raises(HeldoutAccessError):
        bank.draw(template_id="election", count=1, requester="", purpose=PURPOSE)
    with pytest.raises(HeldoutAccessError):
        bank.draw(template_id="harvest", count=1, requester=REQUESTER, purpose=PURPOSE)
    with pytest.raises(HeldoutAccessError):
        bank.draw(template_id="election", count=99, requester=REQUESTER, purpose=PURPOSE)

    reasons = [entry["reason"] for entry in bank.access_log_entries()]
    assert reasons == ["NO_REQUESTER", "NOT_ENOUGH_SEEDS", "NOT_ENOUGH_SEEDS"]
    assert all(entry["granted"] is False for entry in bank.access_log_entries())
    assert len(log_lines(tmp_path)) == 3


def test_a_draw_of_zero_is_a_caller_bug_not_an_access(tmp_path: Path) -> None:
    """Asking for no seed accesses nothing, so it raises without logging."""
    bank = bank_of(tmp_path)
    bank.reserve(template_id="election", count=2, base_seed=BASE_SEED)
    with pytest.raises(InvalidConfigError):
        bank.draw(template_id="election", count=0, requester=REQUESTER, purpose=PURPOSE)
    assert bank.access_log_entries() == ()


def test_every_evaluation_purpose_is_accepted(tmp_path: Path) -> None:
    """The allow list is the whole contract of the seal, so it is exercised."""
    bank = bank_of(tmp_path)
    bank.reserve(template_id="election", count=1, base_seed=BASE_SEED)
    assert EVALUATION_PURPOSES, "an empty allow list would seal the bank shut"
    for purpose in sorted(EVALUATION_PURPOSES):
        assert bank.draw(template_id="election", count=1, requester=REQUESTER, purpose=purpose)
    assert len(bank.access_log_entries()) == len(EVALUATION_PURPOSES)
    assert all(entry["granted"] is True for entry in bank.access_log_entries())


# ---------------------------------------------------------------------------
# The bank holds real scenario seeds, and refuses a corrupt file
# ---------------------------------------------------------------------------
def test_a_sealed_seed_generates_a_real_world(tmp_path: Path) -> None:
    """A sealed seed is a scenario seed: the same templates, reserved seeds (PRD 8)."""
    bank = bank_of(tmp_path)
    bank.reserve(template_id="election", count=1, base_seed=BASE_SEED)
    seed = bank.draw(template_id="election", count=1, requester=REQUESTER, purpose=PURPOSE)[0]
    world = generate_world(template_id="election", seed=seed % 2**64, ticks_total=24, n_markets=2)
    assert world.scenario.markets, "a sealed seed produced a world with no market"
    assert len(world.scenario.markets) == 2
    assert world.scenario.seed == seed % 2**64


def test_the_substream_is_the_registered_one() -> None:
    """Section 3.3: sealed seeds come from ``tournament.heldout`` and nowhere else."""
    from pxe.rng import is_registered_substream

    assert HELDOUT_SUBSTREAM == "tournament.heldout"
    assert is_registered_substream(HELDOUT_SUBSTREAM)


def test_a_corrupt_bank_is_refused_rather_than_reinterpreted(tmp_path: Path) -> None:
    """A sealed set that cannot be read is an error, never an empty bank."""
    path = tmp_path / "heldout.json"
    log = tmp_path / "heldout_access.jsonl"
    path.write_text("not json", encoding=JOURNAL_ENCODING)
    with pytest.raises(StoreError):
        HeldoutBank(path=path, access_log=log)

    path.write_text('{"version": 999, "templates": {}}', encoding=JOURNAL_ENCODING)
    with pytest.raises(StoreError):
        HeldoutBank(path=path, access_log=log)

    path.write_text(f'{{"version": {HELDOUT_BANK_VERSION}}}', encoding=JOURNAL_ENCODING)
    with pytest.raises(StoreError):
        HeldoutBank(path=path, access_log=log)

    path.write_text(
        f'{{"version": {HELDOUT_BANK_VERSION}, "templates": {{"election": ["nope"]}}}}',
        encoding=JOURNAL_ENCODING,
    )
    with pytest.raises(StoreError):
        HeldoutBank(path=path, access_log=log)


def test_a_corrupt_access_log_is_refused(tmp_path: Path) -> None:
    """An audit trail that cannot be read is not silently replaced by an empty one."""
    log = tmp_path / "heldout_access.jsonl"
    log.write_text("[1, 2, 3]\n", encoding=JOURNAL_ENCODING)
    with pytest.raises(StoreError):
        HeldoutBank(path=tmp_path / "heldout.json", access_log=log)
    log.write_text("{oops\n", encoding=JOURNAL_ENCODING)
    with pytest.raises(StoreError):
        HeldoutBank(path=tmp_path / "heldout.json", access_log=log)


def test_a_missing_bank_is_an_empty_bank(tmp_path: Path) -> None:
    """Opening a bank must not create files: sealing does."""
    bank = bank_of(tmp_path)
    assert bank.access_log_entries() == ()
    assert not (tmp_path / "heldout.json").exists()
    with pytest.raises(HeldoutAccessError):
        bank.draw(template_id="election", count=1, requester=REQUESTER, purpose=PURPOSE)
