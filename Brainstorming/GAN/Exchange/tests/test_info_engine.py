"""A04 acceptance tests for ``pxe.info``: the calendar, the tags, the signals.

Anti-vacuous rule (CONTRACTS section 10): there is no journal at this level, so
every test below first asserts that the stream it is about to reason over is non
empty. ``test_the_reference_world_actually_carries_information`` is the guard
for the whole file: if the fixtures ever stop producing news and signals, it
fails loudly instead of letting eighteen tests pass on empty tuples.
"""

from __future__ import annotations

import pytest

from pxe.errors import InvalidConfigError
from pxe.info.engine import (
    NEWS_MAX_PER_TICK,
    InfoEngine,
)
from pxe.info.noise import (
    MILLI_PROBABILITY_ONE,
    THRESHOLD_STEP_MILLI,
    precision_ppm_for_sigma,
    sigma_milli_for_precision,
)
from pxe.info.profiles import (
    DELAYED_DELAY_TICKS,
    SIGNALS_MAX_PER_TICK,
    build_profile,
    default_profile_kinds,
)
from pxe.rng import RngTree
from pxe.types import (
    PPM_ONE,
    InfoProfileKind,
    NewsImpact,
    Outcome,
    SignalKind,
    make_agent_id,
    make_news_id,
    make_signal_id,
    sorted_ids,
)
from pxe.world.generator import generate_world

TICKS = 24
MARKETS = 4
SEATS = 6
SEED = 20260827


def build_world(*, seed: int = SEED, ticks: int = TICKS, markets: int = MARKETS, template: str = "election"):
    return generate_world(template_id=template, seed=seed, ticks_total=ticks, n_markets=markets)


def build_profiles(world, *, seats: int = SEATS):
    market_ids = world.market_ids()
    kinds = default_profile_kinds(seats)
    out = {}
    for index, kind in enumerate(kinds, start=1):
        agent_id = make_agent_id(index)
        focus = market_ids[(index - 1) % len(market_ids)] if kind is InfoProfileKind.SPECIALIST else None
        out[agent_id] = build_profile(kind, market_ids=market_ids, focus_market_id=focus)
    return out


def build_engine(*, seed: int = SEED, ticks: int = TICKS, markets: int = MARKETS, seats: int = SEATS):
    world = build_world(seed=seed, ticks=ticks, markets=markets)
    profiles = build_profiles(world, seats=seats)
    engine = InfoEngine(
        world=world,
        profiles=profiles,
        rng=RngTree(seed).child("info"),
        ticks_total=ticks,
    )
    return world, profiles, engine


def all_news(engine, ticks: int = TICKS):
    return [item for tick in range(1, ticks + 1) for item in engine.news_for_tick(tick)]


def all_signals(engine, ticks: int = TICKS):
    return [signal for tick in range(1, ticks + 1) for signal in engine.signals_for_tick(tick)]


# ---------------------------------------------------------------------------
# The anti-vacuous guard for the whole file
# ---------------------------------------------------------------------------
def test_the_reference_world_actually_carries_information():
    _, _, engine = build_engine()
    news = all_news(engine)
    signals = all_signals(engine)
    assert news, "the reference world published no news: every other test here would pass vacuously"
    assert signals, "the reference world delivered no signal: every other test here would pass vacuously"
    assert any(item.impact is NewsImpact.HIGH for item in news)
    assert any(item.is_noise for item in news), "no pure noise item: the FR-5.3.1 control has nothing to control"
    assert any(not item.is_noise for item in news)
    kinds = {signal.kind for signal in signals}
    assert kinds == set(SignalKind), f"not every signal shape was drawn: {sorted(k.value for k in kinds)}"


# ---------------------------------------------------------------------------
# Purity and determinism
# ---------------------------------------------------------------------------
def test_two_engines_from_the_same_inputs_agree_on_every_tick():
    world = build_world()
    profiles = build_profiles(world)
    left = InfoEngine(world=world, profiles=profiles, rng=RngTree(SEED).child("info"), ticks_total=TICKS)
    right = InfoEngine(world=world, profiles=profiles, rng=RngTree(SEED).child("info"), ticks_total=TICKS)
    assert all_news(left), "vacuous"
    for tick in range(1, TICKS + 1):
        assert left.news_for_tick(tick) == right.news_for_tick(tick)
        assert left.signals_for_tick(tick) == right.signals_for_tick(tick)


def test_call_order_does_not_change_an_answer():
    _, _, engine = build_engine()
    forward = {tick: (engine.news_for_tick(tick), engine.signals_for_tick(tick)) for tick in range(1, TICKS + 1)}
    assert any(news for news, _ in forward.values()), "vacuous"
    _, _, fresh = build_engine()
    for tick in reversed(range(1, TICKS + 1)):
        # Same tick, opposite traversal order, and both methods called twice.
        assert fresh.signals_for_tick(tick) == forward[tick][1]
        assert fresh.news_for_tick(tick) == forward[tick][0]
        assert fresh.news_for_tick(tick) == forward[tick][0]


def test_a_different_seed_changes_the_stream():
    _, _, left = build_engine(seed=SEED)
    _, _, right = build_engine(seed=SEED + 1)
    left_signals = all_signals(left)
    right_signals = all_signals(right)
    assert left_signals and right_signals, "vacuous"
    assert [s.value_milli for s in left_signals] != [s.value_milli for s in right_signals]


def test_impact_tags_are_deterministic():
    """T1.6: the FR-5.8.4 widening is reproducible, so the tags must be too."""
    _, _, first = build_engine()
    _, _, second = build_engine()
    tagged = [(tick, first.news_for_tick(tick)) for tick in range(1, TICKS + 1)]
    assert any(items for _, items in tagged), "vacuous"
    assert any(item.impact is NewsImpact.HIGH for _, items in tagged for item in items)
    for tick, items in tagged:
        assert [item.impact for item in items] == [item.impact for item in second.news_for_tick(tick)]
        assert first.high_impact_market_ids(tick) == second.high_impact_market_ids(tick)


def test_high_impact_market_ids_matches_the_published_items():
    _, _, engine = build_engine()
    seen_any = False
    for tick in range(1, TICKS + 1):
        expected: list[str] = []
        for item in engine.news_for_tick(tick):
            if item.impact is NewsImpact.HIGH:
                expected.extend(market_id for market_id in item.market_ids if market_id not in expected)
        if expected:
            seen_any = True
        assert engine.high_impact_market_ids(tick) == sorted_ids(expected)
    assert seen_any, "no high impact tick in the reference world: the assertion above proved nothing"


# ---------------------------------------------------------------------------
# Section 2.3: the profiles mapping is iterated through sorted_ids
# ---------------------------------------------------------------------------
def test_profile_mapping_insertion_order_does_not_change_the_signals():
    world = build_world()
    profiles = build_profiles(world)
    reversed_profiles = {agent_id: profiles[agent_id] for agent_id in reversed(list(profiles))}
    assert list(reversed_profiles) != list(profiles), "the two mappings must differ in insertion order"
    ordered = InfoEngine(world=world, profiles=profiles, rng=RngTree(SEED).child("info"), ticks_total=TICKS)
    shuffled = InfoEngine(world=world, profiles=reversed_profiles, rng=RngTree(SEED).child("info"), ticks_total=TICKS)
    assert all_signals(ordered), "vacuous"
    for tick in range(1, TICKS + 1):
        assert ordered.signals_for_tick(tick) == shuffled.signals_for_tick(tick)


def test_signals_are_sorted_by_agent_then_signal_id():
    _, _, engine = build_engine()
    for tick in range(1, TICKS + 1):
        signals = engine.signals_for_tick(tick)
        keys = [(signal.agent_id, signal.signal_id) for signal in signals]
        assert keys == sorted(keys)
    assert all_signals(engine), "vacuous"


# ---------------------------------------------------------------------------
# The runner side drop (P1 step 3, decision 37) and its engine side twin
# ---------------------------------------------------------------------------
def tradable_market_ids(world, tick: int) -> tuple[str, ...]:
    """Mirror ``TickStarted.open_market_ids`` (CONTRACTS section 5.0).

    A market whose ``resolution_tick`` is ``r`` is tradable for the whole of
    tick ``r`` and resolved in P1 of ``r + 1``. The production copy of this rule
    lives in ``runner/match_runner.py`` (A09); this is the same predicate,
    written against the world alone so the filter can be tested before the
    runner exists.
    """
    return sorted_ids([m.market_id for m in world.scenario.markets if tick <= m.resolution_tick])


def test_no_signal_for_a_resolved_market():
    """PRD 5.3 + FR-5.2.3: the runner drops a signal naming an untradable market."""
    dropped = 0
    kept = 0
    for seed in range(SEED, SEED + 8):
        # harvest and league allow an early resolution_tick, which is what makes
        # this filter fire at all; election resolves everything at T.
        world = build_world(seed=seed, template="harvest", markets=5)
        profiles = build_profiles(world)
        engine = InfoEngine(world=world, profiles=profiles, rng=RngTree(seed).child("info"), ticks_total=TICKS)
        for tick in range(1, TICKS + 1):
            open_ids = tradable_market_ids(world, tick)
            for signal in engine.signals_for_tick(tick):
                if signal.market_id in open_ids:
                    kept += 1
                else:
                    dropped += 1
    assert kept > 0, "no signal survived the filter at all: the test proved nothing"
    assert dropped > 0, (
        "no signal was ever dropped, so the filter was never exercised; "
        "a template with an early resolution_tick and a delayed profile must produce one"
    )


def test_signal_draw_is_independent_of_resolutions():
    """Engine side of decision 37: the draw never sees market status."""
    world = build_world(template="harvest", markets=5)
    profiles = build_profiles(world)
    engine = InfoEngine(world=world, profiles=profiles, rng=RngTree(SEED).child("info"), ticks_total=TICKS)
    signals = all_signals(engine)
    assert signals, "vacuous"
    # A signal is drawn for markets that are already past their resolution tick,
    # which is the observable proof that the engine was not told about them.
    late = [signal for signal in signals if signal.market_id not in tradable_market_ids(world, signal.tick)]
    assert late, "the engine filtered by status, which is the runner's job (decision 37)"
    # And re-running with the same seed consumes exactly the same draws.
    repeat = InfoEngine(world=world, profiles=profiles, rng=RngTree(SEED).child("info"), ticks_total=TICKS)
    assert all_signals(repeat) == signals


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------
def test_default_profile_kinds_cycles_in_declaration_order():
    kinds = tuple(InfoProfileKind)
    assert default_profile_kinds(6) == tuple(kinds[i % len(kinds)] for i in range(6))
    assert default_profile_kinds(1) == (kinds[0],)
    assert default_profile_kinds(8)[:3] == kinds
    with pytest.raises(InvalidConfigError):
        default_profile_kinds(0)


def test_build_profile_shapes_the_three_kinds():
    market_ids = ("M1", "M2", "M3")
    generalist = build_profile(InfoProfileKind.GENERALIST, market_ids=market_ids)
    specialist = build_profile(InfoProfileKind.SPECIALIST, market_ids=market_ids, focus_market_id="M2")
    delayed = build_profile(InfoProfileKind.DELAYED, market_ids=market_ids)
    assert generalist.focus_market_ids == ()
    assert generalist.delay_ticks == 0
    assert specialist.focus_market_ids == ("M2",)
    assert specialist.signals_min == 1
    assert delayed.delay_ticks == DELAYED_DELAY_TICKS
    assert delayed.noise_scale_ppm < PPM_ONE
    for profile in (generalist, specialist, delayed):
        assert profile.signals_max == SIGNALS_MAX_PER_TICK


def test_build_profile_defaults_the_specialist_focus_to_the_first_market():
    profile = build_profile(InfoProfileKind.SPECIALIST, market_ids=("M3", "M1", "M2"))
    assert profile.focus_market_ids == ("M1",)


def test_build_profile_rejects_a_bad_focus():
    with pytest.raises(InvalidConfigError):
        build_profile(InfoProfileKind.SPECIALIST, market_ids=("M1", "M2"), focus_market_id="M7")
    with pytest.raises(InvalidConfigError):
        build_profile(InfoProfileKind.GENERALIST, market_ids=("M1", "M2"), focus_market_id="M1")
    with pytest.raises(InvalidConfigError):
        build_profile(InfoProfileKind.GENERALIST, market_ids=())


def test_engine_rejects_a_profile_focusing_on_an_unknown_market():
    world = build_world()
    profiles = {"A1": build_profile(InfoProfileKind.SPECIALIST, market_ids=("M1", "M7"), focus_market_id="M7")}
    with pytest.raises(InvalidConfigError):
        InfoEngine(world=world, profiles=profiles, rng=RngTree(SEED).child("info"), ticks_total=TICKS)


def test_engine_rejects_a_null_horizon():
    world = build_world()
    with pytest.raises(InvalidConfigError):
        InfoEngine(world=world, profiles={}, rng=RngTree(SEED).child("info"), ticks_total=0)


def test_engine_rejects_a_tick_below_one():
    _, _, engine = build_engine()
    for bad in (0, -1):
        with pytest.raises(InvalidConfigError):
            engine.news_for_tick(bad)
        with pytest.raises(InvalidConfigError):
            engine.signals_for_tick(bad)
        with pytest.raises(InvalidConfigError):
            engine.high_impact_market_ids(bad)


# ---------------------------------------------------------------------------
# Signal shape and profile effects
# ---------------------------------------------------------------------------
def test_signal_count_stays_inside_the_profile_bounds():
    _, profiles, engine = build_engine()
    total = 0
    for tick in range(1, TICKS + 1):
        per_agent: dict[str, int] = {}
        for signal in engine.signals_for_tick(tick):
            per_agent[signal.agent_id] = per_agent.get(signal.agent_id, 0) + 1
        for agent_id in sorted_ids(list(profiles)):
            profile = profiles[agent_id]
            count = per_agent.get(agent_id, 0)
            assert profile.signals_min <= count <= profile.signals_max
            assert count <= SIGNALS_MAX_PER_TICK
            total += count
    assert total > 0, "vacuous"


def test_signal_ids_and_news_ids_follow_the_contract_format():
    _, _, engine = build_engine()
    news = all_news(engine)
    signals = all_signals(engine)
    assert news and signals, "vacuous"
    for tick in range(1, TICKS + 1):
        for index, item in enumerate(engine.news_for_tick(tick)):
            assert item.news_id == make_news_id(tick, index)
            assert item.tick == tick
            assert len(item.headline) <= 120
            assert len(item.body) <= 400
        counters: dict[str, int] = {}
        for signal in engine.signals_for_tick(tick):
            index = counters.get(signal.agent_id, 0)
            assert signal.signal_id == make_signal_id(tick, signal.agent_id, index)
            counters[signal.agent_id] = index + 1


def test_news_per_tick_never_exceeds_the_engine_cap():
    for seed in range(SEED, SEED + 6):
        for template in ("election", "harvest", "league"):
            world = build_world(seed=seed, template=template, markets=5)
            engine = InfoEngine(
                world=world,
                profiles=build_profiles(world),
                rng=RngTree(seed).child("info"),
                ticks_total=TICKS,
            )
            assert all_news(engine), "vacuous"
            for tick in range(1, TICKS + 1):
                assert len(engine.news_for_tick(tick)) <= NEWS_MAX_PER_TICK


def test_signal_values_stay_in_the_documented_range():
    _, _, engine = build_engine()
    signals = all_signals(engine)
    assert signals, "vacuous"
    for signal in signals:
        assert 0 <= signal.precision_ppm <= PPM_ONE
        if signal.kind is SignalKind.POINT_ESTIMATE:
            assert 0 <= signal.value_milli <= MILLI_PROBABILITY_ONE
        elif signal.kind is SignalKind.DIRECTION:
            assert signal.value_milli in (-MILLI_PROBABILITY_ONE, MILLI_PROBABILITY_ONE)
        else:
            magnitude = abs(signal.value_milli)
            assert THRESHOLD_STEP_MILLI <= magnitude <= MILLI_PROBABILITY_ONE - THRESHOLD_STEP_MILLI
            assert magnitude % THRESHOLD_STEP_MILLI == 0


def test_precision_is_the_exact_inverse_of_the_sigma_it_publishes():
    for sigma in (20, 60, 104, 260, 338, 1000):
        precision = precision_ppm_for_sigma(sigma)
        assert abs(sigma_milli_for_precision(precision) - sigma) <= 1


def test_a_specialist_is_sharper_and_more_focused_than_a_generalist():
    world = build_world(markets=4)
    market_ids = world.market_ids()
    focus = market_ids[1]
    profiles = {
        "A1": build_profile(InfoProfileKind.GENERALIST, market_ids=market_ids),
        "A2": build_profile(InfoProfileKind.SPECIALIST, market_ids=market_ids, focus_market_id=focus),
    }
    engine = InfoEngine(world=world, profiles=profiles, rng=RngTree(SEED).child("info"), ticks_total=TICKS)
    signals = all_signals(engine)
    assert signals, "vacuous"
    specialist = [s for s in signals if s.agent_id == "A2"]
    generalist = [s for s in signals if s.agent_id == "A1"]
    assert specialist and generalist
    on_focus = [s for s in specialist if s.market_id == focus]
    assert len(on_focus) / len(specialist) > 0.5, "a specialist must mostly hear about its own event"
    generalist_focus_share = len([s for s in generalist if s.market_id == focus]) / len(generalist)
    assert generalist_focus_share < len(on_focus) / len(specialist)
    best_focus_precision = max(s.precision_ppm for s in on_focus)
    assert best_focus_precision > max(s.precision_ppm for s in generalist)
    off_focus = [s for s in specialist if s.market_id != focus]
    if off_focus:
        assert min(s.precision_ppm for s in off_focus) < best_focus_precision


@pytest.mark.statistical
def test_a_delayed_profile_reports_a_stale_observation():
    """Fixed seeds: over 200 readings the delayed seat tracks tick ``t - 2``, not ``t``.

    Tolerance: the mean absolute error against the stale latent must be
    strictly smaller than against the current one. Both errors are dominated by
    the observation noise, so the gap is small; the assertion is on the sign of
    the difference and never on its size.
    """
    stale_error = 0
    fresh_error = 0
    samples = 0
    moved = 0
    for seed in range(7000, 7060):
        world = build_world(seed=seed, markets=3)
        market_ids = world.market_ids()
        profiles = {
            "A1": build_profile(InfoProfileKind.GENERALIST, market_ids=market_ids),
            "A2": build_profile(InfoProfileKind.DELAYED, market_ids=market_ids),
        }
        engine = InfoEngine(world=world, profiles=profiles, rng=RngTree(seed).child("info"), ticks_total=TICKS)
        key_of = {m.market_id: m.latent_key for m in world.scenario.markets}
        for tick in range(DELAYED_DELAY_TICKS + 1, TICKS + 1):
            for signal in engine.signals_for_tick(tick):
                if signal.agent_id != "A2" or signal.kind is not SignalKind.POINT_ESTIMATE:
                    continue
                key = key_of[signal.market_id]
                stale = world.latent.probability_ppm(key, tick - DELAYED_DELAY_TICKS)
                fresh = world.latent.probability_ppm(key, tick)
                if abs(stale - fresh) >= 20_000:
                    moved += 1
                observed = signal.value_milli * 1_000
                stale_error += abs(observed - stale)
                fresh_error += abs(observed - fresh)
                samples += 1
    assert samples >= 200, f"only {samples} delayed point estimates: vacuous"
    assert moved >= 50, "the latent never moved between t-2 and t: the comparison below is meaningless"
    assert stale_error < fresh_error, (
        f"the delayed seat tracked the current latent, not the stale one "
        f"(stale error {stale_error}, fresh error {fresh_error})"
    )


# ---------------------------------------------------------------------------
# The two runner facing factories
# ---------------------------------------------------------------------------
def test_resolution_news_is_high_impact_and_names_the_outcome():
    world = build_world()
    _, _, engine = build_engine()
    market_id = world.market_ids()[0]
    item = engine.resolution_news(tick=TICKS + 1, market_id=market_id, outcome=Outcome.YES, index=3)
    assert item.impact is NewsImpact.HIGH
    assert item.is_noise is False
    assert item.news_id == make_news_id(TICKS + 1, 3)
    assert item.market_ids == (market_id,)
    assert "yes" in item.body.lower()
    assert len(item.headline) <= 120
    assert len(item.body) <= 400
    same = engine.resolution_news(tick=TICKS + 1, market_id=market_id, outcome=Outcome.YES, index=3)
    assert same == item
    other = engine.resolution_news(tick=TICKS + 1, market_id=market_id, outcome=Outcome.NO, index=3)
    assert other != item


def test_cancellation_news_is_high_impact_and_echoes_the_reason():
    world = build_world()
    _, _, engine = build_engine()
    market_id = world.market_ids()[1]
    item = engine.cancellation_news(tick=7, market_id=market_id, reason="regulator halted the event", index=0)
    assert item.impact is NewsImpact.HIGH
    assert item.is_noise is False
    assert item.news_id == make_news_id(7, 0)
    assert "regulator halted the event" in item.body
    assert len(item.body) <= 400
    assert item == engine.cancellation_news(tick=7, market_id=market_id, reason="regulator halted the event", index=0)


def test_the_two_factories_reject_bad_arguments():
    world = build_world()
    _, _, engine = build_engine()
    market_id = world.market_ids()[0]
    with pytest.raises(InvalidConfigError):
        engine.resolution_news(tick=0, market_id=market_id, outcome=Outcome.YES, index=0)
    with pytest.raises(InvalidConfigError):
        engine.resolution_news(tick=1, market_id=market_id, outcome=Outcome.YES, index=-1)
    with pytest.raises(InvalidConfigError):
        engine.resolution_news(tick=1, market_id="M9", outcome=Outcome.YES, index=0)
    with pytest.raises(InvalidConfigError):
        engine.cancellation_news(tick=1, market_id="M9", reason="x", index=0)


# ---------------------------------------------------------------------------
# Noise items carry no information
# ---------------------------------------------------------------------------
@pytest.mark.statistical
def test_a_pure_noise_item_is_uncorrelated_with_the_latent_state():
    """Fixed seeds, explicit tolerance: |correlation| under 0.15 over 300 items."""
    noise_pairs: list[tuple[float, float]] = []
    real_pairs: list[tuple[float, float]] = []
    for seed in range(4000, 4120):
        world = build_world(seed=seed, markets=5)
        engine = InfoEngine(
            world=world,
            profiles=build_profiles(world),
            rng=RngTree(seed).child("info"),
            ticks_total=TICKS,
        )
        key_of = {m.market_id: m.latent_key for m in world.scenario.markets}
        for tick in range(1, TICKS + 1):
            for item in engine.news_for_tick(tick):
                if not item.market_ids:
                    continue
                truth = world.latent.probability_ppm(key_of[item.market_ids[0]], tick) / PPM_ONE
                digits = [int(part) for part in item.headline.split() if part.isdigit()]
                if not digits:
                    continue
                published = digits[-1] / 100.0
                (noise_pairs if item.is_noise else real_pairs).append((truth, published))
    assert len(noise_pairs) >= 300, f"only {len(noise_pairs)} noise items: vacuous"
    assert len(real_pairs) >= 300, f"only {len(real_pairs)} genuine items: vacuous"
    assert abs(_correlation(noise_pairs)) < 0.15
    assert _correlation(real_pairs) > 0.45


def _correlation(pairs: list[tuple[float, float]]) -> float:
    n = len(pairs)
    mean_x = sum(x for x, _ in pairs) / n
    mean_y = sum(y for _, y in pairs) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    var_x = sum((x - mean_x) ** 2 for x, _ in pairs)
    var_y = sum((y - mean_y) ** 2 for _, y in pairs)
    if var_x <= 0.0 or var_y <= 0.0:
        return 0.0
    return cov / (var_x**0.5 * var_y**0.5)
