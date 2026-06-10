"""Tests for the confrontation mode: NEAT camp vs GD camp with a gd_ratio split."""

from __future__ import annotations

import numpy as np

from nfl.config import Mode, Sensor, SimConfig, TeacherScope
from nfl.engine.runner import Runner
from nfl.neat.population import Population


def _config(**overrides) -> SimConfig:
    base = dict(
        mode=Mode.confrontation,
        pop_size=20,
        gd_ratio=0.5,
        seed=3,
        active_sensors=[Sensor.dy_gap, Sensor.dx_pipe, Sensor.vy],
        max_ticks_per_gen=120,
        gd_steps=2,
        gd_batch_size=8,
    )
    base.update(overrides)
    return SimConfig(**base)


def _topology_signature(genome) -> tuple:
    """Structure-only fingerprint: node ids/types + enabled (in, out) edges."""
    nodes = tuple(sorted((nid, n.type.value) for nid, n in genome.nodes.items()))
    conns = tuple(sorted((c.in_node, c.out_node) for c in genome.enabled_connections()))
    return (nodes, conns)


def test_assign_camps_respects_gd_ratio():
    config = _config(pop_size=20, gd_ratio=0.25)
    pop = Population(config, np.random.default_rng(0))
    pop.assign_camps(config.gd_ratio)
    camps = [g.camp for g in pop.genomes]
    assert camps.count("gd") == 5
    assert camps.count("neat") == 15
    # Stable layout: NEAT first, GD after.
    assert all(c == "neat" for c in camps[:15])


def test_runner_assigns_camps_in_confrontation_mode():
    runner = Runner(_config(pop_size=10, gd_ratio=0.5))
    camps = [g.camp for g in runner.population.genomes]
    assert camps.count("gd") == 5
    assert camps.count("neat") == 5


def test_generation_keeps_camp_sizes_and_freezes_gd_topology():
    runner = Runner(_config(pop_size=16, gd_ratio=0.5))
    gd_before = [g for g in runner.population.genomes if g.camp == "gd"]
    signatures_before = {id(g): _topology_signature(g) for g in gd_before}

    for _ in range(3):
        runner.step_generation()

    genomes = runner.population.genomes
    camps = [g.camp for g in genomes]
    assert len(genomes) == 16
    assert camps.count("gd") == 8
    assert camps.count("neat") == 8

    # The GD camp must be the SAME genome objects with an unchanged topology
    # (only weights may move, via gradient descent).
    gd_after = [g for g in genomes if g.camp == "gd"]
    assert {id(g) for g in gd_after} == set(signatures_before)
    for g in gd_after:
        assert _topology_signature(g) == signatures_before[id(g)]


def test_stats_expose_per_camp_aggregates_and_winner():
    runner = Runner(_config(pop_size=12, gd_ratio=0.5))
    stats = runner.step_generation()

    assert set(stats["camps"]) == {"neat", "gd"}
    for camp_stats in stats["camps"].values():
        assert camp_stats["count"] == 6
        assert camp_stats["fitnessMax"] >= camp_stats["fitnessMean"]
    assert stats["winnerCamp"] in ("neat", "gd")
    best = max(stats["camps"].values(), key=lambda c: c["fitnessMax"])
    assert stats["camps"][stats["winnerCamp"]] == best
    # Every leaderboard row is tagged with its camp.
    assert all(entry["camp"] in ("neat", "gd") for entry in stats["leaderboard"])


def test_camp_teacher_scope_only_uses_gd_champions():
    runner = Runner(_config(pop_size=12, gd_ratio=0.5, teacher_k=3))
    runner.step_generation()
    # With scope=camp every teacher comes from the GD camp.
    assert runner.config.gd_teacher_scope == TeacherScope.camp
    assert runner.teacher_genomes
    assert all(t.camp == "gd" for t in runner.teacher_genomes)


def test_extreme_ratios_degenerate_gracefully():
    # All-NEAT (ratio 0) and all-GD (ratio 1) must still run.
    for ratio in (0.0, 1.0):
        runner = Runner(_config(pop_size=8, gd_ratio=ratio))
        stats = runner.step_generation()
        expected = "gd" if ratio == 1.0 else "neat"
        assert set(stats["camps"]) == {expected}
        assert len(runner.population.genomes) == 8
