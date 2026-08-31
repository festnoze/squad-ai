"""Launch a fresh scripted match into a runs directory (control API, W13).

This is the one place the API is allowed to *create* state. It mirrors the construction in
``ala.cli._run_into`` exactly, in the same order and from the same objects, so a match launched through
``POST /runs`` is byte-identical to the same one launched on the command line: same
:class:`~ala.types.MatchConfig`, same ``RngTree(seed)``, same :class:`~ala.gateway.ScriptedGateway`,
same scenario. ``tests/test_launch.py`` guards that equivalence against a golden hash and against a
direct engine run.

Only scripted archetypes are reachable here. The LLM path costs money and is never triggered by an
unauthenticated HTTP request; it stays a command-line action.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ala.gateway import Gateway, ScriptedGateway
from ala.journal import Journal
from ala.rng import RngTree
from ala.runner import run_match
from ala.scenario import make_scenario
from ala.scenario.base import WorldSpec
from ala.types import MatchConfig, MatchResult

#: One task in five is impossible, matching the CLI default (CONTRACTS section 9).
IMPOSSIBLE_RATE_PCT = 20
#: The permission dials, echoing ``ala.cli._PERMISSIONS``.
PERMISSIONS: tuple[str, ...] = ("silent", "sandbox", "carte_blanche")
#: The scripted archetypes a run may be built from (the six of ``ala.agents``).
ARCHETYPES: tuple[str, ...] = ("grinder", "allier", "raider", "forger", "parasite", "mute")


@dataclass(frozen=True)
class LaunchParams:
    """Everything a scripted match needs, with the same defaults the CLI uses."""

    scenario: str = "concours"
    seed: int = 42
    agents: str = "grinder,allier,raider,forger"
    ticks: int = 24
    cull_every: int = 8
    defect: int = 100
    start_budget: int = 100
    floor_start: int = 20
    floor_step: int = 15
    clone_top_k: int = 1
    permission: str = "silent"


def seat_specs(agents_csv: str) -> dict[str, str]:
    """Map the comma list of archetype names onto seats ``seat-01``, ``seat-02``, ... in order.

    Identical to ``ala.cli._seat_specs`` so seat assignment (and therefore the journal) matches.
    """
    archetypes = [a.strip() for a in agents_csv.split(",") if a.strip()]
    return {f"seat-{i:02d}": arch for i, arch in enumerate(archetypes, start=1)}


def unique_match_dir(out_root: Path, match_id: str) -> Path:
    """Return a fresh directory under ``out_root`` for ``match_id``, suffixing ``-01``, ``-02`` on
    collision so a re-run never clobbers an earlier journal. Mirrors ``ala.cli._unique_match_dir``."""
    candidate = out_root / match_id
    if not candidate.exists():
        candidate.mkdir(parents=True)
        return candidate
    suffix = 1
    while True:
        candidate = out_root / f"{match_id}-{suffix:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return candidate
        suffix += 1


def launch_match(out_root: Path, params: LaunchParams) -> MatchResult:
    """Build a fresh rng, gateway, scenario and journal and run one scripted match under ``out_root``.

    Returns the :class:`~ala.types.MatchResult`; ``result.match_id`` is the directory name that was
    created (which carries any ``-NN`` suffix), so the caller can locate the journal it just wrote.
    """
    seats = seat_specs(params.agents)
    if not seats:
        raise ValueError("at least one agent is required")

    config = MatchConfig(
        scenario=params.scenario,
        seed=params.seed,
        agent_specs=tuple(seats.values()),
        ticks=params.ticks,
        cull_every=params.cull_every,
        start_budget=params.start_budget,
        floor_start=params.floor_start,
        floor_step=params.floor_step,
        clone_top_k=params.clone_top_k,
        permission=params.permission,
    )

    match_dir = unique_match_dir(out_root, f"m-{params.scenario}-{params.seed}")
    journal_path = match_dir / "journal.jsonl"

    rng = RngTree(config.seed)
    gateway = ScriptedGateway(seats, rng)
    scenario = make_scenario(
        params.scenario,
        WorldSpec(
            start_budget=params.start_budget,
            sudoers_defect_rate_pct=params.defect,
            impossible_task_rate_pct=IMPOSSIBLE_RATE_PCT,
        ),
    )
    journal = Journal(journal_path)
    try:
        result = run_match(config, cast(Gateway, gateway), scenario, journal, rng)
    finally:
        journal.close()
    # The engine's own match_id is scenario+seed; the directory name is what the API must return so a
    # second run of the same seed (suffixed -01) is addressable. Rebuild the result with that id.
    return MatchResult(
        match_id=match_dir.name,
        ticks=result.ticks,
        final_ranking=result.final_ranking,
        journal_hash=result.journal_hash,
    )
