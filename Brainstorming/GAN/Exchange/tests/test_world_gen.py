"""World generation tests (A03, CONTRACTS sections 7.5 and 11).

Anti-vacuous rule (section 10): a world is A03's "journal", so every test below
first asserts that the object under test is non empty (markets, latent rows,
outcomes, news slots) before it claims anything about its content. A test that
would pass on an empty world does not count.
"""

from __future__ import annotations

import inspect
import statistics

import pytest

from pxe.errors import InvalidConfigError
from pxe.events import canonical_json
from pxe.rng import RngTree
from pxe.types import (
    RE_MARKET_ID,
    LiquidityProfileName,
    MarketStatus,
    MatchConfig,
    NewsImpact,
    Outcome,
    make_market_id,
    market_spec_from_dict,
    market_spec_to_dict,
    scenario_from_journal_dict,
    scenario_to_journal_dict,
    sorted_ids,
)
from pxe.world.generator import (
    DEFAULT_TICKS_TOTAL,
    World,
    generate_world,
    get_template,
    list_templates,
    outcome_frequency,
)
from pxe.world.latent import (
    LatentProcess,
    milli_from_probability_ppm,
    probability_ppm_from_milli,
)

TEMPLATE_IDS = ("election", "harvest", "league")
SEED = 20260827


def _world(template_id: str, *, seed: int = SEED, n_markets: int | None = None, ticks_total: int = 48) -> World:
    """Build one world, defaulting the market count to the template's own."""
    template = get_template(template_id)
    return generate_world(
        template_id=template_id,
        seed=seed,
        ticks_total=ticks_total,
        n_markets=template.default_markets if n_markets is None else n_markets,
    )


def _increments(world: World, latent_key: str) -> list[float]:
    """Return the per tick latent increments of one key, as floats."""
    row = world.latent.values_milli[world.latent.keys.index(latent_key)]
    return [float(row[tick] - row[tick - 1]) for tick in range(1, len(row))]


def _assert_non_empty(world: World) -> None:
    """The anti-vacuous guard every test in this file runs first."""
    assert world.scenario.markets, "world has no market"
    assert world.latent.keys, "world has no latent key"
    assert world.latent.values_milli[0], "latent path is empty"
    assert world.outcomes, "world has no outcome"
    assert world.news_plan, "world has no news slot"


# ---------------------------------------------------------------------------
# The registry and the literal signatures of section 7.5
# ---------------------------------------------------------------------------
def test_registry_lists_the_three_templates() -> None:
    assert list_templates() == TEMPLATE_IDS
    for template_id in TEMPLATE_IDS:
        template = get_template(template_id)
        assert template.template_id == template_id
        assert template.template_version
        assert template.default_ticks >= 24
        assert template.min_markets >= 2
        assert template.max_markets <= 8
        assert template.min_markets <= template.default_markets <= template.max_markets


def test_unknown_template_raises() -> None:
    with pytest.raises(InvalidConfigError):
        get_template("no_such_template")
    with pytest.raises(InvalidConfigError):
        generate_world(template_id="no_such_template", seed=1)


def test_signatures_are_the_contracted_ones() -> None:
    """Section 13.1 point 1: the literal signature, argument names included."""
    parameters = inspect.signature(generate_world).parameters
    assert list(parameters) == [
        "template_id",
        "seed",
        "ticks_total",
        "n_markets",
        "liquidity",
        "talking_mode",
        "held_out",
    ]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())
    assert parameters["ticks_total"].default == 48
    assert parameters["n_markets"].default == 5
    assert parameters["liquidity"].default is LiquidityProfileName.STANDARD
    assert parameters["talking_mode"].default is False
    assert parameters["held_out"].default is False

    frequency = inspect.signature(outcome_frequency).parameters
    assert list(frequency) == ["template_id", "draws", "base_seed", "n_markets"]
    assert frequency["template_id"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert frequency["draws"].default == 10_000
    assert frequency["base_seed"].default == 0
    assert frequency["n_markets"].default == 5

    build = inspect.signature(get_template("election").build).parameters
    assert list(build) == ["seed", "ticks_total", "n_markets", "rng"]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in build.values())


# ---------------------------------------------------------------------------
# FR-5.2.1: the market count is a parameter, and markets are correlated
# ---------------------------------------------------------------------------
def test_market_count_is_a_parameter() -> None:
    """FR-5.2.1 and decision 36: 2 to 8, refused (never clamped) outside a template's range."""
    seen_success = 0
    seen_refusal = 0
    for template_id in TEMPLATE_IDS:
        template = get_template(template_id)
        for n_markets in range(2, 9):
            if template.min_markets <= n_markets <= template.max_markets:
                world = _world(template_id, n_markets=n_markets)
                _assert_non_empty(world)
                assert len(world.scenario.markets) == n_markets
                assert world.market_ids() == tuple(make_market_id(i + 1) for i in range(n_markets))
                # The third of the three places the count appears (section 7.5).
                assert MatchConfig(seed=SEED, n_markets=n_markets).n_markets == len(world.scenario.markets)
                seen_success += 1
            else:
                with pytest.raises(InvalidConfigError):
                    _world(template_id, n_markets=n_markets)
                seen_refusal += 1
    assert seen_success >= 3 * 4, "the sweep built almost nothing"
    assert seen_refusal >= 1, "no template exercised its own range check"


def test_market_count_out_of_range_raises() -> None:
    for template_id in TEMPLATE_IDS:
        for n_markets in (1, 9):
            with pytest.raises(InvalidConfigError):
                _world(template_id, n_markets=n_markets)


def test_market_count_and_correlations() -> None:
    """FR-5.2.1: whatever the count, at least one correlated pair exists."""
    for template_id in TEMPLATE_IDS:
        template = get_template(template_id)
        for n_markets in range(template.min_markets, template.max_markets + 1):
            world = _world(template_id, n_markets=n_markets)
            _assert_non_empty(world)
            correlations = world.scenario.correlations
            assert correlations, f"{template_id} with {n_markets} markets has no correlated pair"
            known = set(world.market_ids())
            for left, right, rho_milli in correlations:
                assert left in known and right in known
                assert int(left[1:]) < int(right[1:]), "a pair is ordered"
                assert 1 <= rho_milli < 1000, "rho is a real correlation, not 0 and not 1"
            keys = [(int(left[1:]), int(right[1:])) for left, right, _rho in correlations]
            assert keys == sorted(keys), "correlations are sorted by (market_a, market_b)"
            # Two markets of the same group share a correlation_group tag.
            grouped = [m for m in world.scenario.markets if m.correlation_group]
            assert len(grouped) >= 2
            tags = {m.correlation_group for m in grouped}
            for tag in sorted(tags):
                assert sum(1 for m in grouped if m.correlation_group == tag) >= 2


def test_correlated_latent_paths_move_together_inside_one_world() -> None:
    """The shared factor is in the shocks, so a group's paths co-move within a match."""
    world = _world("election", n_markets=5)
    _assert_non_empty(world)
    by_market = {m.market_id: m for m in world.scenario.markets}
    left, right, rho_milli = world.scenario.correlations[0]
    assert rho_milli > 0
    head_group = by_market[left].correlation_group
    outside = [m.market_id for m in world.scenario.markets if m.correlation_group != head_group]
    assert outside, "the fixture needs an out of group market"

    grouped = statistics.correlation(
        _increments(world, by_market[left].latent_key),
        _increments(world, by_market[right].latent_key),
    )
    crossed = statistics.correlation(
        _increments(world, by_market[left].latent_key),
        _increments(world, by_market[outside[0]].latent_key),
    )
    # Tolerance: 48 increments is a small sample, so only the ordering and a
    # loose floor are asserted. The tight check is the statistical test in
    # test_world_statistics.py.
    assert grouped > 0.25, f"grouped shocks are not correlated: {grouped}"
    assert grouped > crossed, f"grouped {grouped} is not above crossed {crossed}"


# ---------------------------------------------------------------------------
# FR-5.1.4 and O1: a world is a pure function of its seed
# ---------------------------------------------------------------------------
def test_world_is_a_function_of_the_seed() -> None:
    """O1: same arguments, equal worlds; different seed, different world."""
    for template_id in TEMPLATE_IDS:
        first = _world(template_id)
        second = _world(template_id)
        _assert_non_empty(first)
        assert first == second, f"{template_id} is not a function of its seed"
        assert first.latent == second.latent
        assert first.outcomes == second.outcomes
        assert first.news_plan == second.news_plan
        other = _world(template_id, seed=SEED + 1)
        assert other.latent != first.latent, "two seeds produced the same latent process"


def test_world_generation_touches_no_ambient_state() -> None:
    """Generating a world twice with an interleaved third seed changes nothing."""
    first = _world("league")
    _world("league", seed=1)
    again = _world("league")
    assert first == again


def test_metadata_arguments_do_not_move_a_draw() -> None:
    """liquidity, talking_mode and held_out are scenario metadata, not draws."""
    plain = generate_world(template_id="harvest", seed=SEED, ticks_total=48, n_markets=4)
    flagged = generate_world(
        template_id="harvest",
        seed=SEED,
        ticks_total=48,
        n_markets=4,
        liquidity=LiquidityProfileName.ILLIQUID,
        talking_mode=True,
        held_out=True,
    )
    _assert_non_empty(flagged)
    assert flagged.latent == plain.latent
    assert flagged.outcomes == plain.outcomes
    assert flagged.news_plan == plain.news_plan
    assert flagged.scenario.markets == plain.scenario.markets
    assert flagged.scenario.liquidity_profile_name is LiquidityProfileName.ILLIQUID
    assert flagged.scenario.talking_mode is True
    assert flagged.scenario.held_out is True
    assert plain.scenario.liquidity_profile_name is LiquidityProfileName.STANDARD
    assert plain.scenario.talking_mode is False
    assert plain.scenario.held_out is False


def test_generate_world_rejects_a_bad_seed_or_horizon() -> None:
    with pytest.raises(InvalidConfigError):
        generate_world(template_id="election", seed=-1)
    with pytest.raises(InvalidConfigError):
        generate_world(template_id="election", seed=2**64)
    with pytest.raises(InvalidConfigError):
        generate_world(template_id="election", seed=1, ticks_total=1)


# ---------------------------------------------------------------------------
# FR-5.2.3 resolution ticks, FR-5.2.4 public priors
# ---------------------------------------------------------------------------
def test_scenario_is_journal_shaped() -> None:
    for template_id in TEMPLATE_IDS:
        world = _world(template_id)
        _assert_non_empty(world)
        scenario = world.scenario
        assert scenario.template_id == template_id
        assert scenario.template_version
        assert scenario.seed == SEED
        assert scenario.ticks_total == 48
        assert scenario.notes
        assert scenario.cancellations == ()
        ids = [m.market_id for m in scenario.markets]
        assert ids == list(sorted_ids(ids))
        assert all(RE_MARKET_ID.match(market_id) for market_id in ids)
        assert len({m.latent_key for m in scenario.markets}) == len(ids)
        assert tuple(mid for mid, _outcome in world.outcomes) == tuple(ids)
        for market in scenario.markets:
            assert 1 <= market.prior_price <= 99
            assert 1 <= market.resolution_tick <= scenario.ticks_total
            assert market.question.endswith("?")
            assert market.tags
            assert market.latent_key in world.latent.keys
            assert world.outcome(market.market_id) in (Outcome.YES, Outcome.NO)
        assert MarketStatus.OPEN.is_tradable  # markets start tradable, A05 owns the rest


def test_scenario_is_journal_encodable_and_round_trips() -> None:
    """A09 journals these specs inside ``MatchStarted``, so they must encode.

    ``canonical_json`` rejects floats structurally (section 4.2): a single float
    reaching a ``MarketSpec`` would crash the first event of every match, and it
    would crash it in A09's code rather than here.
    """
    for template_id in TEMPLATE_IDS:
        world = _world(template_id)
        _assert_non_empty(world)
        payload = scenario_to_journal_dict(world.scenario)
        assert canonical_json(payload)
        assert scenario_from_journal_dict(payload) == world.scenario
        for market in world.scenario.markets:
            encoded = market_spec_to_dict(market)
            assert canonical_json(encoded)
            assert market_spec_from_dict(encoded) == market


def test_at_least_one_market_resolves_at_the_last_tick() -> None:
    """A match must always have something to settle at finalisation (section 5)."""
    for template_id in TEMPLATE_IDS:
        for seed in range(SEED, SEED + 12):
            world = _world(template_id, seed=seed)
            _assert_non_empty(world)
            ticks = [m.resolution_tick for m in world.scenario.markets]
            assert max(ticks) == world.scenario.ticks_total, f"{template_id} seed {seed} never reaches T"


def test_election_resolves_every_market_at_the_last_tick() -> None:
    """The PRD default of FR-5.2.3, which section 5's finalisation claim relies on."""
    for seed in range(SEED, SEED + 8):
        world = _world("election", seed=seed)
        _assert_non_empty(world)
        assert all(m.resolution_tick == world.scenario.ticks_total for m in world.scenario.markets)


def test_harvest_and_league_produce_early_resolutions() -> None:
    """FR-5.2.3: a market that matures mid match exists, or the oracle path is dead code."""
    for template_id in ("harvest", "league"):
        early = 0
        for seed in range(SEED, SEED + 12):
            world = _world(template_id, seed=seed)
            _assert_non_empty(world)
            early += sum(1 for m in world.scenario.markets if m.resolution_tick < world.scenario.ticks_total)
        assert early > 0, f"{template_id} never resolves a market early"


def test_prior_is_a_public_and_plausible_opening_price() -> None:
    """FR-5.2.4: the prior is the template's honest probability, off by a few cents at most."""
    for template_id in TEMPLATE_IDS:
        world = _world(template_id)
        _assert_non_empty(world)
        for market in world.scenario.markets:
            implied = world.latent.probability_ppm(market.latent_key, 0)
            assert abs(market.prior_price * 10_000 - implied) <= 40_000, (
                f"{template_id} {market.market_id}: prior {market.prior_price} is far from {implied} ppm"
            )


def test_priors_are_not_all_the_same_price() -> None:
    """A world of eight identical 50 cent markets would make every metric degenerate."""
    world = _world("election", n_markets=8)
    _assert_non_empty(world)
    assert len({m.prior_price for m in world.scenario.markets}) >= 4


# ---------------------------------------------------------------------------
# The news calendar, the A03 to A04 handover
# ---------------------------------------------------------------------------
def test_news_plan_is_sorted_and_well_formed() -> None:
    for template_id in TEMPLATE_IDS:
        world = _world(template_id)
        _assert_non_empty(world)
        known = set(world.market_ids())
        keys = [(item.tick, item.market_ids) for item in world.news_plan]
        assert keys == sorted(keys), "news_plan is sorted by (tick, market_ids)"
        for item in world.news_plan:
            assert 1 <= item.tick <= world.scenario.ticks_total
            assert list(item.market_ids) == sorted(item.market_ids)
            assert all(market_id in known for market_id in item.market_ids)
            assert item.impact in (NewsImpact.LOW, NewsImpact.MEDIUM, NewsImpact.HIGH)
        impacts = {item.impact for item in world.news_plan}
        assert NewsImpact.HIGH in impacts, "no high impact slot: FR-5.8.4 widening never fires"
        assert any(len(item.market_ids) > 1 for item in world.news_plan), "no slot carries a correlated group"
        assert any(item.is_noise for item in world.news_plan), "no noise slot"
        assert any(not item.is_noise for item in world.news_plan), "every slot is noise"


def test_news_plan_covers_the_horizon() -> None:
    world = _world("election")
    _assert_non_empty(world)
    ticks = [item.tick for item in world.news_plan]
    assert min(ticks) <= 6
    assert max(ticks) >= world.scenario.ticks_total - 6
    assert len(world.news_plan) >= world.scenario.ticks_total // 4


# ---------------------------------------------------------------------------
# The latent process itself
# ---------------------------------------------------------------------------
def test_latent_process_shape_and_accessors() -> None:
    world = _world("league")
    _assert_non_empty(world)
    latent = world.latent
    assert len(latent.keys) == len(world.scenario.markets)
    assert all(len(row) == world.scenario.ticks_total + 1 for row in latent.values_milli)
    key = latent.keys[0]
    assert latent.value_milli(key, 0) == latent.values_milli[0][0]
    assert latent.probability_ppm(key, 0) == probability_ppm_from_milli(latent.values_milli[0][0])
    assert latent.final_probability_ppm(key) == probability_ppm_from_milli(latent.values_milli[0][-1])
    # A caller resolving at the virtual tick T + 1 (finalisation) reads the
    # terminal value instead of crashing.
    assert latent.value_milli(key, world.scenario.ticks_total + 1) == latent.values_milli[0][-1]
    with pytest.raises(InvalidConfigError):
        latent.value_milli(key, -1)
    with pytest.raises(InvalidConfigError):
        latent.value_milli("no.such.key", 0)
    with pytest.raises(InvalidConfigError):
        latent.probability_ppm("no.such.key", 0)
    with pytest.raises(InvalidConfigError):
        latent.final_probability_ppm("no.such.key")


def test_latent_process_rejects_a_broken_shape() -> None:
    with pytest.raises(InvalidConfigError):
        LatentProcess(keys=(), values_milli=())
    with pytest.raises(InvalidConfigError):
        LatentProcess(keys=("a", "a"), values_milli=((0,), (0,)))
    with pytest.raises(InvalidConfigError):
        LatentProcess(keys=("a", "b"), values_milli=((0,),))
    with pytest.raises(InvalidConfigError):
        LatentProcess(keys=("a", "b"), values_milli=((0,), (0, 1)))
    with pytest.raises(InvalidConfigError):
        LatentProcess(keys=("a",), values_milli=((),))


def test_probability_map_is_monotone_symmetric_and_integer_only() -> None:
    values = list(range(-4000, 4001, 7))
    probabilities = [probability_ppm_from_milli(value) for value in values]
    assert probabilities, "the sweep produced nothing"
    assert all(isinstance(p, int) for p in probabilities)
    assert probabilities == sorted(probabilities), "the map is not monotone"
    assert probability_ppm_from_milli(0) == 500_000
    for value in (1, 250, 1000, 3210):
        assert probability_ppm_from_milli(value) + probability_ppm_from_milli(-value) == 1_000_000
    # v = s / sqrt(3) = 577 is the 75 % point of the algebraic sigmoid and
    # v = s is its 85.36 % point. Both are pinned exactly: the map is integer
    # arithmetic, so a platform may not shift it by even one ppm.
    assert probability_ppm_from_milli(577) == 749_886
    assert probability_ppm_from_milli(1000) == 853_553
    assert min(probabilities) >= 0
    assert max(probabilities) <= 1_000_000


def test_probability_map_round_trips() -> None:
    for ppm in (1_000, 100_000, 250_000, 499_999, 500_000, 620_000, 900_000, 999_000):
        value = milli_from_probability_ppm(ppm)
        # Tolerance: the latent value is quantised to whole thousandths and one
        # thousandth is worth about 500 ppm of probability, so a round trip can
        # only be exact to half of that.
        assert abs(probability_ppm_from_milli(value) - ppm) <= 300, ppm
    with pytest.raises(InvalidConfigError):
        milli_from_probability_ppm(0)
    with pytest.raises(InvalidConfigError):
        milli_from_probability_ppm(1_000_000)


def test_latent_path_actually_moves() -> None:
    """A frozen latent process would make every signal worthless and every Brier flat."""
    world = _world("election")
    _assert_non_empty(world)
    for row in world.latent.values_milli:
        assert len(set(row)) > 5, "a latent path barely moves"
        assert max(row) - min(row) >= 100, "a latent path is almost constant"


def test_outcomes_follow_the_latent_probability_in_the_extremes() -> None:
    """A world whose outcome ignored the latent process would pass every shape test."""
    high_yes = high_total = 0
    low_yes = low_total = 0
    for seed in range(400):
        world = generate_world(template_id="election", seed=seed, n_markets=5)
        for market in world.scenario.markets:
            probability = world.latent.probability_ppm(market.latent_key, market.resolution_tick)
            resolved_yes = world.outcome(market.market_id) is Outcome.YES
            if probability >= 750_000:
                high_total += 1
                high_yes += int(resolved_yes)
            if probability <= 250_000:
                low_total += 1
                low_yes += int(resolved_yes)
    assert high_total >= 40, f"not enough confident markets to judge ({high_total})"
    assert low_total >= 40, f"not enough unlikely markets to judge ({low_total})"
    # Tolerance: with p >= 0.75 the YES share must sit well above one half, and
    # the mirror below it. A generator flipping a fair coin lands near 0.5 on
    # both and fails here, which is the point of the two sided check.
    assert high_yes / high_total >= 0.70, f"confident markets resolved YES {high_yes}/{high_total}"
    assert low_yes / low_total <= 0.30, f"unlikely markets resolved YES {low_yes}/{low_total}"


# ---------------------------------------------------------------------------
# outcome_frequency argument handling (the statistics live in the other file)
# ---------------------------------------------------------------------------
def test_outcome_frequency_shape_and_validation() -> None:
    frequency = outcome_frequency("election", draws=40, base_seed=7, n_markets=3)
    assert frequency, "outcome_frequency returned nothing"
    assert list(frequency) == ["M1", "M2", "M3"]
    assert all(0 <= value <= 1_000_000 for value in frequency.values())
    assert outcome_frequency("election", draws=40, base_seed=7, n_markets=3) == frequency
    with pytest.raises(InvalidConfigError):
        outcome_frequency("election", draws=0)
    with pytest.raises(InvalidConfigError):
        outcome_frequency("nope", draws=2)


def test_default_horizon_matches_the_match_config_default() -> None:
    assert MatchConfig().ticks_total == DEFAULT_TICKS_TOTAL


# ---------------------------------------------------------------------------
# The fixture other workstreams build on (section 10)
# ---------------------------------------------------------------------------
def test_tiny_world_fixture_pairs_with_a_legal_config(tiny_world: World) -> None:
    _assert_non_empty(tiny_world)
    config = MatchConfig(seed=tiny_world.scenario.seed, ticks_total=24, n_markets=2)
    assert config.ticks_total == tiny_world.scenario.ticks_total
    assert config.n_markets == len(tiny_world.scenario.markets)
    assert config.talking_mode == tiny_world.scenario.talking_mode
    assert config.liquidity_profile_name == tiny_world.scenario.liquidity_profile_name
    assert tiny_world.scenario.correlations, "even a two market world is correlated"


def test_the_world_tree_is_the_runner_child_tree() -> None:
    """Section 3.1: RngTree(seed).child("world") is what generate_world uses."""
    seed = 4242
    expected = RngTree(seed).child("world")
    assert expected.seed_for("world.latent") == RngTree(seed).child("world").seed_for("world.latent")
    template = get_template("election")
    direct = template.build(seed=seed, ticks_total=32, n_markets=4, rng=expected)
    through = generate_world(template_id="election", seed=seed, ticks_total=32, n_markets=4)
    _assert_non_empty(direct)
    assert direct == through
    # The same tree object twice: every draw comes from fresh_substream, so a
    # reused tree cannot silently produce a second, different world (section 3.1).
    assert template.build(seed=seed, ticks_total=32, n_markets=4, rng=expected) == direct
