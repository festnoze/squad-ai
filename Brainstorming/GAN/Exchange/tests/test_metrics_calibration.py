"""A16 acceptance tests: the Brier score and the reliability curves (PRD 7.2).

Every test starts from a **non empty** projection and asserts that the
``PredictionRecorded`` rows it is about to measure exist before it claims
anything (CONTRACTS section 10's anti vacuous rule). The three frozen journals of
``tests/golden/`` are the primary input, because they are bytes rather than a
live engine run, so a calibration regression shows up as a number moving and not
as a flaky match.

The five claims this file exists for:

* ``n_terms`` is one term per ``PredictionRecorded`` event, so for a seat that
  played every tick of a fully resolved match
  ``n_terms == sum over markets of resolution_tick`` (section 9,
  ``test_n_terms_equals_resolution_tick``). That identity is the off-by-one
  detector: a market with ``resolution_tick == r`` counts on ticks ``1..r``
  inclusive, and the resolution tick term, the most informative one, is in.
* Carried values (FR-6.2.4) count, with the value that was carried, and they are
  reported separately as ``n_carried``.
* A market that never resolved contributes no term, because ``(p - y)^2`` has no
  ``y``, and a frozen agent stops accumulating at its freeze tick.
* The mean is exact: an agent that declares one constant probability scores
  exactly ``brier_term_ppm(that probability, the realised outcome)``.
* The reliability curve partitions exactly the same terms the Brier averages,
  bin by bin, with a fixed number of rows and truthful edges.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest

from pxe.errors import InvalidConfigError
from pxe.events import AgentFrozen, Event, MarketCancelled, MarketResolved, PredictionRecorded
from pxe.journal import read_journal
from pxe.metrics.calibration import (
    UNMEASURED_BRIER_PPM,
    CalibrationMetrics,
    brier_ppm_of,
    compute_calibration,
    counted_terms,
    reliability_curve,
)
from pxe.metrics.projection import MatchProjection, PredictionRow, project
from pxe.rng import RngTree
from pxe.types import (
    PPM_ONE,
    AgentAction,
    MatchConfig,
    Observation,
    Outcome,
    PredictionIntent,
    brier_term_ppm,
)
from tests.test_match_runner import (
    GOLDEN_DIR,
    REFERENCE,
    SMALL,
    WIDE,
    Recipe,
    Spendthrift,
    agents_of,
    config_of,
    custom_recipe,
    of_type,
    play,
    play_with_agents,
    world_of,
)

GOLDEN: tuple[Recipe, ...] = (REFERENCE, SMALL, WIDE)

#: The constant probability the :class:`Forecaster` below declares. Chosen off
#: the 500 000 default so a carried value cannot be confused with a default one,
#: and strictly inside a bin of the default ten (850 000 ppm is in ``(800 000,
#: 900 000)``) so the reliability curve puts every term of it in one bin.
FIXED_P_YES_PPM = 850_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def golden_events(recipe: Recipe) -> tuple[Event, ...]:
    """Read one frozen journal from ``tests/golden/``."""
    path = GOLDEN_DIR / f"{recipe.name}.journal.jsonl"
    assert path.exists(), f"missing golden journal for {recipe.name}"
    events = read_journal(path)
    assert events, "the golden journal read back empty, so every assertion below would be vacuous"
    return events


def golden_projection(recipe: Recipe) -> MatchProjection:
    """Project one frozen journal and refuse an empty prediction family."""
    projection = project(golden_events(recipe))
    assert projection.predictions, "no PredictionRecorded row, so every calibration assertion would be vacuous"
    return projection


def block_of(metrics: tuple[CalibrationMetrics, ...], agent_id: str) -> CalibrationMetrics:
    """Return the calibration block of one seat."""
    found = [row for row in metrics if row.agent_id == agent_id]
    assert len(found) == 1, f"expected exactly one calibration block for {agent_id}, got {len(found)}"
    return found[0]


class Forecaster:
    """Declares one constant probability, on every tick or only on the first.

    ``first_tick_only`` is how the FR-6.2.4 carry is reached through the real
    runner rather than by forging a ``PredictionRecorded``: after tick 1 this
    agent declares nothing at all, so every following row is a carried copy of
    what it said once. It never places an order, which keeps the two halves of
    AC-P4 visibly separate in the journal it produces.
    """

    def __init__(
        self,
        *,
        agent_id: str,
        config: MatchConfig,
        rng: object,
        p_yes_ppm: int = FIXED_P_YES_PPM,
        first_tick_only: bool = False,
    ) -> None:
        self.agent_id = agent_id
        self._config = config
        self._p_yes_ppm = p_yes_ppm
        self._first_tick_only = first_tick_only

    def reset(self, *, config: MatchConfig, rng: object) -> None:
        """Accept a new match without forgetting what this agent is for."""
        self._config = config

    def act(self, observation: Observation) -> AgentAction:
        """Declare the constant probability, or nothing at all after tick 1."""
        declare = observation.markets if not self._first_tick_only or observation.tick == 1 else ()
        return AgentAction(
            agent_id=self.agent_id,
            tick=observation.tick,
            action_version=self._config.action_version,
            predictions=tuple(
                PredictionIntent(market_id=block.market_id, p_yes_ppm=self._p_yes_ppm) for block in declare
            ),
        )


def play_small_with_forecaster(*, first_tick_only: bool) -> tuple[MatchProjection, MatchConfig]:
    """Play the small scenario with seat ``A1`` replaced by a constant forecaster."""
    config = config_of(SMALL)
    rng = RngTree(config.seed)
    seats = agents_of(SMALL, config, rng)
    seats["A1"] = Forecaster(
        agent_id="A1",
        config=config,
        rng=rng.child("agent/A1").substream("agent.A1"),
        first_tick_only=first_tick_only,
    )
    _result, events = play_with_agents(SMALL, factories=seats, config=config, rng=rng)
    assert of_type(events, PredictionRecorded), "the forecaster declared nothing, so this run proves nothing"
    projection = project(events)
    assert projection.predictions
    return projection, config


# ---------------------------------------------------------------------------
# n_terms: the resolution tick boundary (section 5.0 and section 9)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_n_terms_equals_resolution_tick(recipe: Recipe) -> None:
    """Section 9: ``n_terms == sum over markets of resolution_tick``.

    This is the test CONTRACTS sections 5.0 and 9 both name. It only holds for a
    seat that played every tick, so the absence of an ``AgentFrozen`` is asserted
    first: with a freeze in the journal the identity is expected to break and the
    test would be measuring the wrong thing.
    """
    events = golden_events(recipe)
    assert of_type(events, AgentFrozen) == [], "a seat was frozen, so this identity does not apply to this match"
    assert of_type(events, MarketCancelled) == [], "a market was cancelled, so it produces no term"
    projection = project(events)
    assert projection.predictions
    expected = sum(tick for _market_id, tick in projection.resolution_ticks)
    assert expected > 0
    for row in compute_calibration(projection):
        assert row.n_terms == expected, row.agent_id


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_one_event_one_term(recipe: Recipe) -> None:
    """Section 9: nothing is recomputed and nothing is inferred.

    ``n_terms`` is the number of ``PredictionRecorded`` events of that seat on a
    resolved market, counted from the journal, and never a tick range derived
    from ``resolution_ticks``.
    """
    events = golden_events(recipe)
    recorded = [event for event in of_type(events, PredictionRecorded) if isinstance(event, PredictionRecorded)]
    assert recorded
    resolved = {event.market_id for event in of_type(events, MarketResolved) if isinstance(event, MarketResolved)}
    assert resolved
    projection = project(events)
    for row in compute_calibration(projection):
        assert row.n_terms == sum(
            1 for event in recorded if event.agent_id == row.agent_id and event.market_id in resolved
        )


def test_the_resolution_tick_term_is_the_last_one_and_it_counts() -> None:
    """Section 5.0: a market with ``resolution_tick == r`` counts on ticks 1..r.

    ``league_wide`` resolves ``M4`` at tick 22 of 24, which is the only golden
    match where the boundary is not the end of the match, so it is the one that
    can tell the contract's rule apart from the off-by-one either side of it: a
    projection dropping the resolution tick term would stop at 21, and one
    counting the resolution event's own envelope tick would reach 23.
    """
    events = golden_events(WIDE)
    resolved = [event for event in of_type(events, MarketResolved) if isinstance(event, MarketResolved)]
    early = [event for event in resolved if event.resolution_tick < WIDE.ticks_total]
    assert early, "no market resolved mid match, so the boundary is untested here"
    target = early[0]
    # The envelope tick and the payload field differ by one on purpose.
    assert target.tick == target.resolution_tick + 1

    projection = project(events)
    ticks = sorted(row.tick for row in projection.predictions if row.market_id == target.market_id)
    assert ticks, f"no prediction row for {target.market_id}"
    per_agent = len(projection.agent_ids)
    assert min(ticks) == 1
    assert max(ticks) == target.resolution_tick, (
        f"the last term of {target.market_id} is at tick {max(ticks)}, not at its resolution tick "
        f"{target.resolution_tick}"
    )
    assert len(ticks) == target.resolution_tick * per_agent
    assert target.tick not in set(ticks), "a term was produced on the tick the market resolved on"


def test_a_frozen_seat_stops_accumulating_terms() -> None:
    """Section 9: a frozen agent's Brier is the mean over the ticks it played.

    The freeze is reached through real order flow, exactly as
    ``test_match_runner.py::test_bankruptcy_freezes_agent`` does, and never by
    forging a state: ``Spendthrift`` buys until its free cash is gone.
    """
    recipe = custom_recipe(
        baselines=("spendthrift", "fundamentalist", "momentum", "bayesian"),
        seed=11,
        ticks=24,
        markets=2,
        template="election",
    )
    config = config_of(recipe, initial_cash_cents=20_000, bankruptcy_free_cash_floor_cents=3_000)
    rng = RngTree(config.seed)
    seats = agents_of(
        replace(recipe, baselines=("fundamentalist", "fundamentalist", "momentum", "bayesian")),
        config,
        rng,
    )
    seats["A1"] = Spendthrift(agent_id="A1", config=config, rng=rng.child("agent/A1").substream("agent.A1"))
    _result, events = play_with_agents(recipe, factories=seats, config=config)

    frozen = [event for event in of_type(events, AgentFrozen) if isinstance(event, AgentFrozen)]
    assert frozen, "no agent was frozen, so this test would assert nothing about a freeze"
    freeze = frozen[0]
    projection = project(events)
    assert projection.predictions
    metrics = compute_calibration(projection)
    full = sum(tick for _market_id, tick in projection.resolution_ticks)

    stopped = block_of(metrics, freeze.agent_id)
    assert stopped.n_terms < full, "the frozen seat produced as many terms as a seat that played every tick"
    assert stopped.n_terms > 0, "the seat was frozen before it ever declared, so its Brier is not a mean"
    # The terms stop at the freeze tick: the freeze takes effect from tick + 1.
    ticks = [row.tick for row in projection.predictions if row.agent_id == freeze.agent_id]
    assert max(ticks) == freeze.tick
    for row in metrics:
        if row.agent_id != freeze.agent_id:
            assert row.n_terms == full, f"{row.agent_id} was not frozen and should have every term"


def test_a_cancelled_market_produces_no_term() -> None:
    """FR-5.4.5: without an outcome there is no ``y``, so there is no term.

    No shipped template scripts a cancellation, so this drives the same hand
    built ``ScenarioSpec`` as
    ``test_match_runner.py::test_a_cancelled_market_is_not_tradable_on_its_cancellation_tick``.
    The rows are really there, they are simply not counted, which is what the two
    assertions on ``projection.predictions`` below establish before the metric is
    read at all.
    """
    cancel_tick, cancelled_market = 8, "M2"
    config = config_of(SMALL, n_markets=3)
    base = world_of(SMALL)
    world = replace(
        base,
        scenario=replace(base.scenario, cancellations=((cancel_tick, cancelled_market, "scripted_probe"),)),
    )
    _result, events = play(SMALL, config=config, world=world)
    cancellations = [event for event in of_type(events, MarketCancelled) if isinstance(event, MarketCancelled)]
    assert [(event.tick, event.market_id) for event in cancellations] == [(cancel_tick, cancelled_market)], (
        "the scripted cancellation did not fire, so nothing below is being tested"
    )

    projection = project(events)
    on_cancelled = [row for row in projection.predictions if row.market_id == cancelled_market]
    assert on_cancelled, "no prediction was ever recorded on the cancelled market, so nothing is being excluded"
    assert max(row.tick for row in on_cancelled) == cancel_tick - 1
    assert cancelled_market not in dict(projection.outcomes)

    resolved_total = sum(
        tick for market_id, tick in projection.resolution_ticks if market_id in dict(projection.outcomes)
    )
    assert resolved_total > 0
    for row in compute_calibration(projection):
        assert row.n_terms == resolved_total
        assert all(term.market_id != cancelled_market for term, _outcome in counted_terms(projection, row.agent_id))


# ---------------------------------------------------------------------------
# brier_ppm: the uniform mean, exactly
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_brier_is_the_uniform_mean_of_its_terms(recipe: Recipe) -> None:
    """PRD section 7.2: a uniform mean, rounded half up, never a float.

    The expected value is stated as a property of the exact rational mean rather
    than as a second copy of the implementation: the reported integer is within
    half a ppm of ``total / n``, and a tie rounds up. Two implementations of the
    same rounding would agree even when both are wrong.
    """
    projection = golden_projection(recipe)
    resolved = dict(projection.outcomes)
    assert resolved
    for row in compute_calibration(projection):
        terms = [
            brier_term_ppm(prediction.p_yes_ppm, resolved[prediction.market_id])
            for prediction in projection.predictions
            if prediction.agent_id == row.agent_id and prediction.market_id in resolved
        ]
        assert len(terms) == row.n_terms > 0
        exact = Fraction(sum(terms), len(terms))
        assert Fraction(row.brier_ppm) - exact <= Fraction(1, 2)
        assert exact - Fraction(row.brier_ppm) < Fraction(1, 2)
        assert 0 <= row.brier_ppm <= PPM_ONE


def test_a_constant_forecaster_scores_exactly_its_own_term() -> None:
    """The mean of a constant is that constant, to the ppm.

    Every market of the small scenario resolves YES, so a seat declaring
    850 000 ppm on every open market scores exactly
    ``brier_term_ppm(850_000, YES)``, that is 22 500 ppm, and nothing else. This
    is the one assertion in the file that pins the arithmetic to a literal
    number, which is why it is worth reaching through a real match.
    """
    projection, _config = play_small_with_forecaster(first_tick_only=False)
    outcomes = dict(projection.outcomes)
    assert set(outcomes.values()) == {Outcome.YES}, "the small scenario no longer resolves every market YES"
    expected_term = brier_term_ppm(FIXED_P_YES_PPM, Outcome.YES)
    assert expected_term == 22_500

    block = block_of(compute_calibration(projection), "A1")
    assert block.n_terms == sum(tick for _market_id, tick in projection.resolution_ticks)
    assert block.n_carried == 0, "the forecaster declared on every tick, so nothing was carried"
    assert block.brier_ppm == expected_term


def test_carried_values_count_with_the_value_that_was_carried() -> None:
    """FR-6.2.4: the carried values count, and they count as what they carried.

    The same forecaster declares only on tick 1. Every later row is a carry of
    850 000 ppm, so the score is unchanged and ``n_carried`` is every term but
    the first tick's. A projection that dropped carried rows would report
    ``n_terms == n_markets``; one that scored them as the 500 000 default would
    report 250 000 ppm instead of 22 500.
    """
    projection, _config = play_small_with_forecaster(first_tick_only=True)
    assert set(dict(projection.outcomes).values()) == {Outcome.YES}
    carried_rows = [row for row in projection.predictions if row.agent_id == "A1" and row.carried]
    assert carried_rows, "nothing was carried, so FR-6.2.4 is not exercised here"
    assert all(row.p_yes_ppm == FIXED_P_YES_PPM for row in carried_rows)

    block = block_of(compute_calibration(projection), "A1")
    full = sum(tick for _market_id, tick in projection.resolution_ticks)
    assert block.n_terms == full
    assert block.n_carried == full - len(projection.market_ids)
    assert 0 < block.n_carried < block.n_terms
    assert block.brier_ppm == brier_term_ppm(FIXED_P_YES_PPM, Outcome.YES)


def test_an_agent_with_no_term_is_scored_as_uninformative() -> None:
    """``n_terms == 0`` reports the score of the FR-6.2.4 default, not zero.

    A zero would make silence the best possible Brier, which is a reward hacking
    vector (PRD section 7.5). The state is unreachable through a real match (a
    seat always faces at least one open market at tick 1), so it is reached by
    emptying the row family of a real projection.
    """
    projection = golden_projection(SMALL)
    silent = replace(projection, predictions=())
    metrics = compute_calibration(silent)
    assert metrics, "the projection has no ranked seat, so this test would assert nothing"
    assert UNMEASURED_BRIER_PPM == brier_term_ppm(500_000, Outcome.YES) == 250_000
    for row in metrics:
        assert row.n_terms == 0
        assert row.n_carried == 0
        assert row.brier_ppm == UNMEASURED_BRIER_PPM
    assert brier_ppm_of(()) == UNMEASURED_BRIER_PPM


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_one_block_per_seat_in_canonical_order(recipe: Recipe) -> None:
    """Section 2.3: ascending numeric suffix, which is ``agent_ids`` itself."""
    projection = golden_projection(recipe)
    metrics = compute_calibration(projection)
    assert [row.agent_id for row in metrics] == list(projection.agent_ids)
    assert all(isinstance(row, CalibrationMetrics) for row in metrics)
    assert all(0 <= row.n_carried <= row.n_terms for row in metrics)


def test_the_brier_is_not_inert_when_a_declaration_moves() -> None:
    """The mirror of the decoupling tests: calibration does depend on predictions."""
    events = golden_events(SMALL)
    recorded = [event for event in of_type(events, PredictionRecorded) if isinstance(event, PredictionRecorded)]
    assert recorded
    perfect = tuple(
        replace(event, p_yes_ppm=PPM_ONE) if isinstance(event, PredictionRecorded) and event.agent_id == "A1" else event
        for event in events
    )
    projection = project(perfect)
    assert set(dict(projection.outcomes).values()) == {Outcome.YES}
    metrics = compute_calibration(projection)
    assert block_of(metrics, "A1").brier_ppm == 0, "a declaration of 1.0 on a YES market is a perfect Brier"
    assert block_of(metrics, "A2").brier_ppm > 0, "only A1 was rewritten, so A2 must be unchanged"


# ---------------------------------------------------------------------------
# reliability_curve
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_the_curve_partitions_exactly_the_counted_terms(recipe: Recipe) -> None:
    """One row per bin, and the bins together hold every term and nothing else."""
    projection = golden_projection(recipe)
    metrics = {row.agent_id: row for row in compute_calibration(projection)}
    for agent_id in projection.agent_ids:
        curve = reliability_curve(projection, agent_id)
        assert len(curve) == 10, "the default is ten bins and every bin has a row, empty or not"
        uppers = [upper for upper, _count, _observed in curve]
        assert uppers == sorted(uppers) == [(index + 1) * 100_000 for index in range(10)]
        assert uppers[-1] == PPM_ONE
        assert sum(count for _upper, count, _observed in curve) == metrics[agent_id].n_terms
        assert all(0 <= observed <= PPM_ONE for _upper, _count, observed in curve)
        assert all(observed == 0 for _upper, count, observed in curve if count == 0)
        populated = [row for row in curve if row[1] > 0]
        assert populated, f"{agent_id} has terms but every bin is empty"


@pytest.mark.parametrize("n_bins", [1, 2, 3, 4, 7, 10, 20, 100])
def test_the_curve_honours_n_bins(n_bins: int) -> None:
    """Any strictly positive bin count works and the last edge is always 1.0."""
    projection = golden_projection(WIDE)
    total = block_of(compute_calibration(projection), "A1").n_terms
    curve = reliability_curve(projection, "A1", n_bins=n_bins)
    assert len(curve) == n_bins
    assert curve[-1][0] == PPM_ONE
    assert sum(count for _upper, count, _observed in curve) == total > 0


def test_the_bin_edges_are_exhaustive_and_disjoint() -> None:
    """Membership is ``p * n_bins // 1_000_000``, so an edge value moves up a bin.

    The probabilities are planted on and around the edges of the default ten bin
    grid, which no real match is guaranteed to produce, and the counts prove
    where each one landed: 100 000 ppm belongs to the second bin, not to the
    first, and 1 000 000 ppm belongs to the last bin rather than to a phantom
    eleventh one.
    """
    projection = golden_projection(SMALL)
    resolved = dict(projection.outcomes)
    market_id = projection.market_ids[0]
    assert market_id in resolved, "the first market did not resolve, so no term can be planted on it"
    planted = (0, 99_999, 100_000, 100_001, 999_999, PPM_ONE)
    seeded = replace(
        projection,
        predictions=tuple(
            PredictionRow(agent_id="A1", market_id=market_id, tick=index + 1, p_yes_ppm=value, carried=False)
            for index, value in enumerate(planted)
        ),
    )
    curve = reliability_curve(seeded, "A1")
    counts = [count for _upper, count, _observed in curve]
    assert sum(counts) == len(planted)
    assert counts == [2, 2, 0, 0, 0, 0, 0, 0, 0, 2]


def test_the_observed_frequency_is_the_realised_outcome() -> None:
    """``observed_yes_ppm`` is the YES rate of that bin, in ppm, half up.

    ``league_wide`` is the only golden match with both outcomes, so it is the one
    where the observed rate can be something other than 0 or 1 000 000.
    """
    projection = golden_projection(WIDE)
    resolved = dict(projection.outcomes)
    assert len(set(resolved.values())) == 2, "this match has a single outcome value, so the rate is degenerate"
    curve = reliability_curve(projection, "A1")
    for index, (upper, count, observed) in enumerate(curve):
        lower = 0 if index == 0 else curve[index - 1][0]
        rows = [
            row
            for row in projection.predictions
            if row.agent_id == "A1" and row.market_id in resolved and lower <= row.p_yes_ppm < upper
        ]
        if index == len(curve) - 1:
            rows = [row for row in projection.predictions if row.agent_id == "A1" and lower <= row.p_yes_ppm <= upper]
        assert count == len(rows), f"bin {index} counted {count} terms, the rows say {len(rows)}"
        if rows:
            yes = sum(1 for row in rows if resolved[row.market_id] is Outcome.YES)
            assert observed == (2 * yes * PPM_ONE + len(rows)) // (2 * len(rows))
    intermediate = [observed for _upper, count, observed in curve if count and 0 < observed < PPM_ONE]
    assert intermediate, "no bin mixes the two outcomes, so the rate is never actually measured here"


def test_a_perfect_forecaster_sits_in_one_bin_on_the_diagonal() -> None:
    """The curve pairs a declaration with the outcome of its own market."""
    projection, _config = play_small_with_forecaster(first_tick_only=False)
    curve = reliability_curve(projection, "A1")
    populated = [(upper, count, observed) for upper, count, observed in curve if count]
    assert len(populated) == 1, f"a constant forecaster should occupy exactly one bin, got {populated}"
    upper, count, observed = populated[0]
    assert upper == 900_000, "850 000 ppm sits in the ninth bin of ten, whose upper boundary is 900 000"
    assert count == block_of(compute_calibration(projection), "A1").n_terms
    assert observed == PPM_ONE, "every market resolved YES, so the observed rate is 1.0"


def test_the_curve_refuses_a_bad_argument() -> None:
    """A silently empty curve would be published as a measurement."""
    projection = golden_projection(SMALL)
    with pytest.raises(InvalidConfigError):
        reliability_curve(projection, "A1", n_bins=0)
    with pytest.raises(InvalidConfigError):
        reliability_curve(projection, "A1", n_bins=-3)
    with pytest.raises(InvalidConfigError):
        reliability_curve(projection, "A99")
    with pytest.raises(InvalidConfigError):
        counted_terms(projection, "MM")
