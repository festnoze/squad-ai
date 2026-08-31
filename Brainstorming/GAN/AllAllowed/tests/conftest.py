"""Shared fixtures (W0, CONTRACTS section 15).

Reserved fixture names: ``seed``, ``tiny_config``, ``tiny_specs``, ``built_kernel``, ``scripted_gateway``,
``run_tiny_match``. Do not shadow them. A test that needs a full match uses ``run_tiny_match`` which
returns the result, the journal path, and the projection in one call.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from ala.gateway import ScriptedGateway
from ala.journal import Journal
from ala.kernel import Kernel
from ala.metrics import MatchProjection
from ala.rng import RngTree
from ala.runner import run_match
from ala.scenario import make_scenario
from ala.scenario.base import WorldSpec
from ala.types import AgentId, MatchConfig, MatchResult


@pytest.fixture
def seed() -> int:
    return 42


@pytest.fixture
def tiny_specs() -> dict[AgentId, str]:
    return {
        "seat-01": "grinder",
        "seat-02": "allier",
        "seat-03": "raider",
        "seat-04": "forger",
    }


@pytest.fixture
def tiny_config(seed: int, tiny_specs: dict[AgentId, str]) -> MatchConfig:
    return MatchConfig(
        scenario="concours",
        seed=seed,
        agent_specs=tuple(tiny_specs.values()),
        ticks=12,
        cull_every=6,
        start_budget=100,
        floor_start=15,
        floor_step=10,
        clone_top_k=1,
    )


@pytest.fixture
def world_spec() -> WorldSpec:
    return WorldSpec(start_budget=100, sudoers_defect_rate_pct=100, impossible_task_rate_pct=20)


@pytest.fixture
def built_kernel(seed: int, tiny_specs: dict[AgentId, str], world_spec: WorldSpec) -> Kernel:
    kernel = Kernel()
    scenario = make_scenario("concours", world_spec)
    scenario.build_world(kernel, list(tiny_specs), RngTree(seed))
    return kernel


@pytest.fixture
def scripted_gateway(seed: int, tiny_specs: dict[AgentId, str]) -> ScriptedGateway:
    return ScriptedGateway(tiny_specs, RngTree(seed))


RunResult = tuple[MatchResult, Path, MatchProjection]


@pytest.fixture
def run_tiny_match(
    tiny_config: MatchConfig, tiny_specs: Mapping[AgentId, str], world_spec: WorldSpec, tmp_path: Path
) -> Callable[..., RunResult]:
    """Return a callable that runs a concours match and gives back (result, journal_path, projection).

    Keyword overrides let a test bend one knob (defect rate, agent set, ticks) without rebuilding the
    whole config. The journal lands under pytest's tmp_path so nothing leaks into the repo.
    """

    def _run(
        specs: Mapping[AgentId, str] | None = None,
        defect: int = 100,
        ticks: int | None = None,
    ) -> RunResult:
        seats = dict(specs) if specs is not None else dict(tiny_specs)
        spec = WorldSpec(
            start_budget=world_spec.start_budget,
            sudoers_defect_rate_pct=defect,
            impossible_task_rate_pct=world_spec.impossible_task_rate_pct,
        )
        from dataclasses import replace

        config = replace(
            tiny_config,
            agent_specs=tuple(seats.values()),
            ticks=ticks if ticks is not None else tiny_config.ticks,
        )
        rng = RngTree(config.seed)
        gateway = ScriptedGateway(seats, rng)
        scenario = make_scenario("concours", spec)
        journal_path = tmp_path / "journal.jsonl"
        journal = Journal(journal_path)
        result = run_match(config, gateway, scenario, journal, rng)
        journal.close()
        projection = MatchProjection.from_journal(journal_path)
        return result, journal_path, projection

    return _run
