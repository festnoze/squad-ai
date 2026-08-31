"""The headline determinism guard (AC-1, CONTRACTS section 3).

Why this is the most important test in the suite: the entire value of the engine is that a seed plus a
scripted agent set replays bit-for-bit. If two runs of the same seed ever diverged, every metric,
detector, and golden journal downstream would be untrustworthy. So we assert not only equal hashes but
byte-identical journal files, and that a different seed actually moves the world.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ala.gateway import ScriptedGateway
from ala.journal import Journal, hash_file
from ala.rng import RngTree
from ala.runner import run_match
from ala.scenario import make_scenario
from ala.scenario.base import WorldSpec
from ala.types import AgentId, MatchConfig

_SPECS: dict[AgentId, str] = {
    "seat-01": "grinder",
    "seat-02": "allier",
    "seat-03": "raider",
    "seat-04": "forger",
}


def _run(seed: int, path: Path, specs: Mapping[AgentId, str] | None = None) -> str:
    """Run one full concours match into ``path`` and return the journal hash. Everything the run touches
    (rng, gateway, scenario, journal) is freshly constructed, so two calls share no hidden state."""
    seats = dict(specs) if specs is not None else dict(_SPECS)
    config = MatchConfig(
        scenario="concours",
        seed=seed,
        agent_specs=tuple(seats.values()),
        ticks=12,
        cull_every=6,
        start_budget=100,
        floor_start=15,
        floor_step=10,
        clone_top_k=1,
    )
    world = WorldSpec(start_budget=100, sudoers_defect_rate_pct=100, impossible_task_rate_pct=20)
    rng = RngTree(seed)
    gateway = ScriptedGateway(seats, rng)
    scenario = make_scenario("concours", world)
    journal = Journal(path)
    result = run_match(config, gateway, scenario, journal, rng)
    journal.close()
    # The result hash and the recomputed file hash must agree: the fingerprint is over the real bytes.
    assert result.journal_hash == hash_file(path)
    return result.journal_hash


def test_same_seed_gives_identical_hash(tmp_path: Path) -> None:
    h1 = _run(42, tmp_path / "run_a.jsonl")
    h2 = _run(42, tmp_path / "run_b.jsonl")
    assert h1 == h2


def test_same_seed_gives_byte_identical_journal(tmp_path: Path) -> None:
    a = tmp_path / "run_a.jsonl"
    b = tmp_path / "run_b.jsonl"
    _run(42, a)
    _run(42, b)
    assert a.read_bytes() == b.read_bytes()


def test_different_seeds_give_different_hashes(tmp_path: Path) -> None:
    h_a = _run(42, tmp_path / "seed42.jsonl")
    h_b = _run(43, tmp_path / "seed43.jsonl")
    assert h_a != h_b


def test_determinism_holds_for_a_second_seed(tmp_path: Path) -> None:
    # Reproducibility is a property of the machine, not of one lucky seed.
    assert _run(7, tmp_path / "a.jsonl") == _run(7, tmp_path / "b.jsonl")
