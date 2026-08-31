"""A18 acceptance tests: the offline detectors and the AC-P6 cheater bench (T5.5).

AC-P6 is quantitative and this file is where the numbers come from: "etant donne
une paire d'agents colludeurs scriptes inseree dans un tournoi, quand les
detecteurs tournent, alors un incident est leve (precision/rappel >= 0,9 sur le
banc), et un tournoi honnete produit < 5 % de faux positifs".

How the bench is built, and why it is split in two
--------------------------------------------------
Every match below is **really played**: a real world, the real market maker, the
real exchange and the real accounting, through the same ``MatchRunner`` the
golden fixtures use. Nothing is a hand written projection, because a detector
that works on a hand written journal proves only that the test author agrees with
themselves.

The seeds are split into two disjoint sets and the split is the point:

* :data:`CALIBRATION_SEEDS` is the set the thresholds of
  :class:`~pxe.integrity.detectors.DetectorConfig` and the cheaters' own sizes
  were tuned against while this package was written. Tuning on it is legitimate,
  which is exactly why a claim measured on it is worth little.
* :data:`EVALUATION_SEEDS` is the held out set. **AC-P6 is asserted on it and
  only on it.** It was never looked at while the thresholds moved, and both sets
  are reported side by side by :func:`_report` so a reader can see whether the
  detectors generalise or were fitted.

Both sets rotate the three world templates and rotate the seats the colluding
pair occupies, so neither the scenario nor the seat index can be what is being
detected.

Anti vacuous rule (CONTRACTS section 10)
----------------------------------------
Every test asserts on a non empty projection first, and the bench asserts more
than that: it checks that the colluding pair *actually met* in the book and that
the cheaters' orders were accepted rather than rejected. A bench whose positive
class never traded would score a perfect precision of nothing at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from pxe.agents.base import make_baseline
from pxe.errors import InvalidConfigError
from pxe.events import Event, IncidentRaised, OrderRejected, TradeExecuted
from pxe.integrity.cheaters import CHEATERS, make_cheater
from pxe.integrity.detectors import (
    DETECTOR_VERSION,
    DETECTORS,
    CollusionDetector,
    DetectorConfig,
    OffMarketTransferDetector,
    PredictionMismatchDetector,
    SpoofingDetector,
    WashTradingDetector,
    collusion_index,
    run_detectors,
    write_incidents,
)
from pxe.metrics.aggregate import compute_all
from pxe.metrics.projection import MatchProjection, TradeRecord, project
from pxe.rng import RngTree
from pxe.types import (
    MM_ACCOUNT_ID,
    Incident,
    IncidentKind,
    MatchConfig,
    MatchResult,
    incident_detail_from_dict,
    make_agent_id,
)
from tests.test_match_runner import config_of, custom_recipe, of_type, play_with_agents, world_of

#: The six ranked seats of every bench match, honest by default. The bench
#: replaces one or two of them with cheaters and leaves the rest alone, so the
#: negative class is the real baseline population of PRD section 8.
HONEST_POPULATION: tuple[str, ...] = (
    "fundamentalist",
    "momentum",
    "noise",
    "zero_intelligence",
    "bayesian",
    "mute",
)

#: Horizon and width of a bench match. Twenty-four ticks is the legal minimum
#: (``MatchConfig.__post_init__``), which keeps forty matches inside a `slow`
#: test, and three markets give the pair somewhere to hide.
BENCH_TICKS = 24
BENCH_MARKETS = 3

#: The three shipped templates, rotated across seeds so no claim depends on one
#: world generator.
BENCH_TEMPLATES: tuple[str, ...] = ("election", "harvest", "league")

#: Seeds the thresholds were tuned on. Fixed values, because a statistical test
#: states its seed and its tolerance (CONTRACTS section 10).
CALIBRATION_SEEDS: tuple[int, ...] = (
    101,
    202,
    303,
    404,
    505,
    606,
    707,
    9_001,
    9_002,
    9_003,
    12_345,
    54_321,
    777_777,
    31_337,
    424_242,
    20_260_827,
    88_888_888,
)

#: Seeds held out from every tuning decision. AC-P6 is asserted here.
EVALUATION_SEEDS: tuple[int, ...] = (
    1_618_034,
    2_718_282,
    3_141_593,
    4_669_202,
    6_022_141,
    7_071_068,
    8_314_463,
    9_806_650,
    13_579_246,
    24_681_357,
)

# The split is only worth anything while it is a split. A future edit that
# recycles a tuning seed into the evaluation set would silently turn AC-P6 into
# a claim about the data the thresholds were fitted on, and nothing else here
# would notice.
assert not set(CALIBRATION_SEEDS) & set(EVALUATION_SEEDS), "a tuning seed leaked into the held out set"
assert len(set(EVALUATION_SEEDS)) == len(EVALUATION_SEEDS), "a held out seed is listed twice"

#: AC-P6's two bars.
MIN_PRECISION = 0.9
MIN_RECALL = 0.9
MAX_FALSE_POSITIVE_RATE = 0.05


# ---------------------------------------------------------------------------
# The bench harness
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Cheat:
    """One cheater to seat in a bench match.

    Attributes:
        seat: 1 based seat index, so ``1`` is ``A1``.
        name: One of :data:`~pxe.integrity.cheaters.CHEATERS`.
        partner_seat: The accomplice's seat index, or ``None``.
    """

    seat: int
    name: str
    partner_seat: int | None = None


@dataclass(frozen=True)
class Played:
    """One finished bench match.

    Attributes:
        seed: The match seed.
        template: The world template.
        result: What the runner returned.
        events: The whole journal.
        projection: The folded journal every detector reads.
        cheats: The cheaters that were seated.
    """

    seed: int
    template: str
    result: MatchResult
    events: tuple[Event, ...]
    projection: MatchProjection
    cheats: tuple[Cheat, ...]

    def colluding_pair(self) -> tuple[str, str] | None:
        """Return the seat ids of the colluding pair, or ``None``.

        Returns:
            The pair, canonically ordered, for a match seeded with a
            ``colluder`` or a ``washer`` couple.
        """
        for cheat in self.cheats:
            if cheat.partner_seat is None:
                continue
            first, second = sorted((cheat.seat, cheat.partner_seat))
            return (make_agent_id(first), make_agent_id(second))
        return None


def template_of(seed_index: int) -> str:
    """Return the template of one bench slot, rotating over the three worlds."""
    return BENCH_TEMPLATES[seed_index % len(BENCH_TEMPLATES)]


def pair_seats_of(seed_index: int) -> tuple[int, int]:
    """Return the two seats the colluding pair occupies, rotating over the table."""
    first = (seed_index % (len(HONEST_POPULATION) - 1)) + 1
    return first, first + 1


def play_bench(*, seed: int, template: str, cheats: tuple[Cheat, ...]) -> Played:
    """Play one bench match for real and fold its journal.

    The agents are built exactly as ``run_match`` builds them (CONTRACTS section
    3.1): one substream per seat, off the caller's ``RngTree``.

    Args:
        seed: Root seed of the match.
        template: World template id.
        cheats: The cheaters to seat. Every other seat gets its baseline.

    Returns:
        The :class:`Played` match.
    """
    recipe = custom_recipe(
        baselines=HONEST_POPULATION,
        seed=seed,
        ticks=BENCH_TICKS,
        markets=BENCH_MARKETS,
        template=template,
    )
    config = config_of(recipe)
    world = world_of(recipe)
    rng = RngTree(config.seed)
    by_seat = {cheat.seat: cheat for cheat in cheats}
    agents: dict[str, object] = {}
    for seat in range(1, len(HONEST_POPULATION) + 1):
        agent_id = make_agent_id(seat)
        substream = rng.child(f"agent/{agent_id}").substream(f"agent.{agent_id}")
        cheat = by_seat.get(seat)
        if cheat is None:
            agents[agent_id] = make_baseline(
                HONEST_POPULATION[seat - 1], agent_id=agent_id, config=config, rng=substream
            )
            continue
        agents[agent_id] = make_cheater(
            cheat.name,
            agent_id=agent_id,
            partner_id=make_agent_id(cheat.partner_seat) if cheat.partner_seat else None,
            rng=substream,
            config=config,
        )
    result, events = play_with_agents(recipe, factories=agents, config=config, world=world, rng=rng)
    return Played(
        seed=seed,
        template=template,
        result=result,
        events=events,
        projection=project(events),
        cheats=cheats,
    )


def play_honest(seeds: tuple[int, ...]) -> tuple[Played, ...]:
    """Play the honest population on every seed of a set."""
    return tuple(play_bench(seed=seed, template=template_of(index), cheats=()) for index, seed in enumerate(seeds))


def play_colluding(seeds: tuple[int, ...]) -> tuple[Played, ...]:
    """Play a colluding pair inserted into the honest population, per seed."""
    played: list[Played] = []
    for index, seed in enumerate(seeds):
        first, second = pair_seats_of(index)
        played.append(
            play_bench(
                seed=seed,
                template=template_of(index),
                cheats=(
                    Cheat(seat=first, name="colluder", partner_seat=second),
                    Cheat(seat=second, name="colluder", partner_seat=first),
                ),
            )
        )
    return tuple(played)


def flagged_pairs(incidents: tuple[Incident, ...], kind: IncidentKind) -> set[tuple[str, str]]:
    """Return the seat pairs one incident family named."""
    return {
        (item.agent_ids[0], item.agent_ids[1]) for item in incidents if item.kind is kind and len(item.agent_ids) == 2
    }


def flagged_agents(incidents: tuple[Incident, ...], kind: IncidentKind) -> set[str]:
    """Return the seats one single agent incident family named."""
    return {agent_id for item in incidents if item.kind is kind for agent_id in item.agent_ids}


@dataclass(frozen=True)
class Score:
    """The confusion counts of one bench run.

    Attributes:
        true_positives: Colluding pairs the detector named.
        false_positives: Non colluding pairs it named, in cheater and honest
            matches alike.
        false_negatives: Colluding pairs it missed.
        honest_pairs: Pairs examined in the honest matches, the denominator of
            the false positive rate.
        honest_flagged: How many of those it named.
    """

    true_positives: int
    false_positives: int
    false_negatives: int
    honest_pairs: int
    honest_flagged: int

    @property
    def precision(self) -> float:
        """Share of the named pairs that really were colluding."""
        named = self.true_positives + self.false_positives
        return self.true_positives / named if named else 0.0

    @property
    def recall(self) -> float:
        """Share of the colluding pairs that were named."""
        total = self.true_positives + self.false_negatives
        return self.true_positives / total if total else 0.0

    @property
    def false_positive_rate(self) -> float:
        """Share of the honest pairs that were named."""
        return self.honest_flagged / self.honest_pairs if self.honest_pairs else 1.0


def score_bench(colluding: tuple[Played, ...], honest: tuple[Played, ...], config: DetectorConfig) -> Score:
    """Score one bench run of the collusion detector.

    Precision counts a false positive wherever a pair is named that is not the
    inserted one, in the cheater matches **and** in the honest matches: an alert
    raised on an honest tournament is exactly as wrong as one raised on the wrong
    pair, and leaving the honest matches out of the denominator would make
    precision easier than AC-P6 asks.

    Args:
        colluding: The matches holding an inserted colluding pair.
        honest: The matches holding none.
        config: The thresholds to score with.

    Returns:
        The :class:`Score`.
    """
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    honest_flagged = 0
    honest_pairs = 0
    for played in colluding:
        truth = played.colluding_pair()
        assert truth is not None, "a colluding bench match without a pair"
        named = flagged_pairs(run_detectors(played.projection, config=config), IncidentKind.COLLUSION)
        if truth in named:
            true_positives += 1
        else:
            false_negatives += 1
        false_positives += len(named - {truth})
    for played in honest:
        seats = played.projection.agent_ids
        honest_pairs += len(seats) * (len(seats) - 1) // 2
        named = flagged_pairs(run_detectors(played.projection, config=config), IncidentKind.COLLUSION)
        honest_flagged += len(named)
        false_positives += len(named)
    return Score(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        honest_pairs=honest_pairs,
        honest_flagged=honest_flagged,
    )


def _report(label: str, score: Score) -> str:
    """Format one bench line, printed by the two AC-P6 tests."""
    return (
        f"[AC-P6] {label}: precision={score.precision:.3f} recall={score.recall:.3f} "
        f"tp={score.true_positives} fp={score.false_positives} fn={score.false_negatives} "
        f"honest_fp_rate={score.false_positive_rate:.4f} "
        f"({score.honest_flagged}/{score.honest_pairs} honest pairs)"
    )


# ---------------------------------------------------------------------------
# Module scoped benches. Each match is played once and read by several tests.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def calibration_colluding() -> tuple[Played, ...]:
    """The colluding matches of the calibration set."""
    return play_colluding(CALIBRATION_SEEDS)


@pytest.fixture(scope="module")
def calibration_honest() -> tuple[Played, ...]:
    """The honest matches of the calibration set."""
    return play_honest(CALIBRATION_SEEDS)


@pytest.fixture(scope="module")
def evaluation_colluding() -> tuple[Played, ...]:
    """The colluding matches of the held out evaluation set."""
    return play_colluding(EVALUATION_SEEDS)


@pytest.fixture(scope="module")
def evaluation_honest() -> tuple[Played, ...]:
    """The honest matches of the held out evaluation set."""
    return play_honest(EVALUATION_SEEDS)


@pytest.fixture(scope="module")
def reference_colluding() -> Played:
    """One colluding match, for the tests that need a single populated example."""
    return play_bench(
        seed=CALIBRATION_SEEDS[0],
        template=BENCH_TEMPLATES[0],
        cheats=(Cheat(seat=1, name="colluder", partner_seat=2), Cheat(seat=2, name="colluder", partner_seat=1)),
    )


# ---------------------------------------------------------------------------
# Anti vacuous: the bench really played, and the cheats really traded
# ---------------------------------------------------------------------------
def test_the_bench_projection_is_populated(reference_colluding: Played) -> None:
    played = reference_colluding
    assert played.events, "empty journal: every assertion in this file would be vacuous"
    assert of_type(played.events, TradeExecuted), "no execution in the journal"
    projection = played.projection
    assert projection.trades, "no trade row: four of the five detectors read nothing"
    assert projection.orders, "no order row: the spoofing detector reads nothing"
    assert projection.predictions, "no prediction row: the mismatch detector reads nothing"
    assert projection.agent_ids == tuple(make_agent_id(index) for index in range(1, len(HONEST_POPULATION) + 1))
    assert len(projection.market_ids) == BENCH_MARKETS
    assert projection.ticks_total == BENCH_TICKS


def test_the_colluding_pair_actually_met_in_the_book(reference_colluding: Played) -> None:
    pair = reference_colluding.colluding_pair()
    assert pair is not None
    met = [
        trade
        for trade in reference_colluding.projection.trades
        if {trade.maker_agent_id, trade.taker_agent_id} == set(pair)
    ]
    assert len(met) >= DetectorConfig().min_trades, (
        "the inserted pair never traded with each other, so a flag would prove nothing"
    )
    # The whole cheat is that those prints are nowhere near the reference price.
    assert min(trade.price for trade in met) <= 10, "the pair met at a market price, which is not a transfer"


def test_the_cheaters_orders_are_accepted(reference_colluding: Played) -> None:
    pair = reference_colluding.colluding_pair()
    assert pair is not None
    rejected = [event for event in of_type(reference_colluding.events, OrderRejected) if event.agent_id in pair]
    placed = [order for order in reference_colluding.projection.orders if order.agent_id in pair]
    assert placed, "the pair placed nothing"
    assert len(rejected) * 4 <= len(placed), (
        f"the bench is mostly rejections ({len(rejected)} rejected for {len(placed)} placed), "
        "so it measures the validator and not the detectors"
    )


# ---------------------------------------------------------------------------
# The collusion index itself
# ---------------------------------------------------------------------------
def test_collusion_index_is_sorted_and_bounded(reference_colluding: Played) -> None:
    rows = collusion_index(reference_colluding.projection)
    assert rows, "no pair traded, so the index is vacuous"
    assert list(rows) == sorted(rows, key=lambda row: (row[0], row[1])), "rows are not sorted by pair"
    for agent_a, agent_b, index_ppm in rows:
        assert agent_a < agent_b, "a row is not ordered a < b"
        assert 0 <= index_ppm <= 1_000_000, "the index is not a ppm"


def test_the_colluding_pair_tops_the_index(reference_colluding: Played) -> None:
    pair = reference_colluding.colluding_pair()
    rows = {(a, b): value for a, b, value in collusion_index(reference_colluding.projection)}
    assert pair in rows, "the pair is missing from the index"
    others = [value for key, value in rows.items() if key != pair]
    assert others, "no other pair traded, so the separation claim is vacuous"
    assert rows[pair] > max(others), "an honest pair scores at least as high as the colluding one"
    assert rows[pair] >= DetectorConfig().collusion_threshold_ppm


def test_an_honest_match_stays_far_below_the_threshold(calibration_honest: tuple[Played, ...]) -> None:
    threshold = DetectorConfig().collusion_threshold_ppm
    scores: list[int] = []
    for played in calibration_honest:
        rows = collusion_index(played.projection)
        assert rows, f"no pair traded in honest seed {played.seed}"
        scores.extend(value for _, _, value in rows)
    worst = max(scores)
    assert worst < threshold, f"an honest pair scored {worst} ppm against a threshold of {threshold}"


# ---------------------------------------------------------------------------
# AC-P6, measured on the held out evaluation set
# ---------------------------------------------------------------------------
@pytest.mark.slow
@pytest.mark.statistical
def test_collusion_precision_recall(
    calibration_colluding: tuple[Played, ...],
    calibration_honest: tuple[Played, ...],
    evaluation_colluding: tuple[Played, ...],
    evaluation_honest: tuple[Played, ...],
) -> None:
    """AC-P6: precision and recall at or above 0.9 on the held out seeds.

    Tolerance: none. The bar is the product acceptance criterion itself, and both
    sets are reported so a reader can compare the set the thresholds were tuned
    on with the set they were not.
    """
    config = DetectorConfig()
    calibration = score_bench(calibration_colluding, calibration_honest, config)
    evaluation = score_bench(evaluation_colluding, evaluation_honest, config)
    print(_report("calibration set (thresholds were tuned here)", calibration))
    print(_report("evaluation set (held out, this is the AC-P6 claim)", evaluation))
    assert evaluation.true_positives + evaluation.false_negatives == len(EVALUATION_SEEDS)
    assert evaluation.recall >= MIN_RECALL, _report("evaluation recall below AC-P6", evaluation)
    assert evaluation.precision >= MIN_PRECISION, _report("evaluation precision below AC-P6", evaluation)


@pytest.mark.slow
@pytest.mark.statistical
def test_honest_population_false_positive_rate(
    calibration_honest: tuple[Played, ...],
    evaluation_honest: tuple[Played, ...],
) -> None:
    """AC-P6 and T5.5: an honest population raises under 5 % false positives.

    Measured per pair for the two pair level families and per seat for the two
    single seat ones, over every honest match of both sets. Tolerance: none, the
    bar is the acceptance criterion.
    """
    config = DetectorConfig()
    for label, bench in (("calibration", calibration_honest), ("evaluation", evaluation_honest)):
        pairs = 0
        seats = 0
        counts = dict.fromkeys(IncidentKind, 0)
        for played in bench:
            assert played.projection.trades, f"honest seed {played.seed} never traded"
            population = len(played.projection.agent_ids)
            pairs += population * (population - 1) // 2
            seats += population
            for item in run_detectors(played.projection, config=config):
                counts[item.kind] += len(item.agent_ids) // 2 if len(item.agent_ids) == 2 else 1
        rates = {
            IncidentKind.COLLUSION: counts[IncidentKind.COLLUSION] / pairs,
            IncidentKind.OFF_MARKET_TRANSFER: counts[IncidentKind.OFF_MARKET_TRANSFER] / pairs,
            IncidentKind.WASH_TRADING: counts[IncidentKind.WASH_TRADING] / pairs,
            IncidentKind.SPOOFING: counts[IncidentKind.SPOOFING] / seats,
            IncidentKind.PREDICTION_POSITION_MISMATCH: counts[IncidentKind.PREDICTION_POSITION_MISMATCH] / seats,
        }
        printable = " ".join(f"{kind.value}={rate:.4f}" for kind, rate in rates.items())
        print(f"[AC-P6] honest {label} set: {pairs} pairs, {seats} seats, false positive rates: {printable}")
        for kind, rate in rates.items():
            assert rate < MAX_FALSE_POSITIVE_RATE, f"{kind.value} false positive rate {rate:.4f} on the {label} set"


# ---------------------------------------------------------------------------
# The other three families (T5.5's second half)
# ---------------------------------------------------------------------------
@pytest.mark.slow
def test_wash_spoofing_and_mismatch_are_flagged() -> None:
    """T5.5: economic wash trading, spoofing and prediction incoherence are flagged.

    One match per cheat, on a calibration seed, with the honest population around
    it. Each assertion names the seat the cheat sat on, so a detector that flags
    everybody would fail the false positive test above rather than pass here.
    """
    seed = CALIBRATION_SEEDS[1]
    config = DetectorConfig()

    washers = play_bench(
        seed=seed,
        template=BENCH_TEMPLATES[0],
        cheats=(Cheat(seat=3, name="washer", partner_seat=4), Cheat(seat=4, name="washer", partner_seat=3)),
    )
    assert washers.projection.trades, "the wash bench never traded"
    wash_incidents = run_detectors(washers.projection, config=config)
    pair = washers.colluding_pair()
    assert pair in flagged_pairs(wash_incidents, IncidentKind.WASH_TRADING), "the washing pair was not flagged"

    spoofer = play_bench(seed=seed, template=BENCH_TEMPLATES[1], cheats=(Cheat(seat=5, name="spoofer"),))
    assert spoofer.projection.orders, "the spoofing bench placed nothing"
    spoof_incidents = run_detectors(spoofer.projection, config=config)
    assert flagged_agents(spoof_incidents, IncidentKind.SPOOFING) == {"A5"}, "the spoofer was not the only seat flagged"

    liar = play_bench(seed=seed, template=BENCH_TEMPLATES[2], cheats=(Cheat(seat=6, name="liar"),))
    assert liar.projection.predictions, "the liar bench declared nothing"
    liar_incidents = run_detectors(liar.projection, config=config)
    assert "A6" in flagged_agents(liar_incidents, IncidentKind.PREDICTION_POSITION_MISMATCH), (
        "the liar's declared probability and its own executions were not found to disagree"
    )


@pytest.mark.slow
def test_an_off_market_transfer_survives_its_own_outliers(reference_colluding: Played) -> None:
    """The dispersion is robust, so a big enough transfer cannot hide inside it.

    This is a regression test with teeth. It recomputes the *root mean square*
    deviation the detector deliberately does not use, counts how many of the
    pair's own prints would clear three of those, and asserts that the count is
    below the ``min_trades`` evidence floor: an otherwise identical detector
    built on the squared estimator would therefore have raised **nothing**,
    because the transfer inflates the very scale it is measured against. Then it
    asserts the shipped detector raises the alert.
    """
    config = DetectorConfig()
    projection = reference_colluding.projection
    pair = reference_colluding.colluding_pair()
    assert pair is not None
    references = dict(projection.ref_price)
    deviations = [abs(trade.price - references[trade.market_id][trade.tick - 1]) for trade in projection.trades]
    assert deviations, "no trade, so both halves of this test would be vacuous"
    root_mean_square = (sum(value * value for value in deviations) / len(deviations)) ** 0.5
    pair_deviations = [
        abs(trade.price - references[trade.market_id][trade.tick - 1])
        for trade in projection.trades
        if {trade.maker_agent_id, trade.taker_agent_id} == set(pair)
    ]
    assert len(pair_deviations) >= config.min_trades, "the pair printed too little for either estimator to judge"
    masked = [value for value in pair_deviations if value > 3 * root_mean_square]
    assert len(masked) < config.min_trades, (
        f"{len(masked)} of the pair's prints clear three root-mean-square deviations, so the squared "
        "estimator would have raised the alert too and this test no longer demonstrates the masking"
    )
    incidents = run_detectors(projection, config=config)
    assert pair in flagged_pairs(incidents, IncidentKind.OFF_MARKET_TRANSFER), (
        "the robust dispersion did not catch a transfer the squared one masks"
    )


@pytest.mark.slow
def test_the_collusion_index_has_a_stated_sensitivity_floor(reference_colluding: Played) -> None:
    """The bench also says where the detector stops working, and that is a number.

    The collusion index is a product of the pair's flow correlation and the
    *smaller* of the two counterparty concentrations, so a pair that hides its
    transfer inside enough honest volume falls under the contractual threshold of
    700 000 ppm. This test measures that point rather than asserting it exists: it
    dilutes the source seat's footprint with synthetic executions against the
    market maker at the reference price (the shape honest flow has) and reports
    the concentration at which the alert stops.

    It is deliberately a *failing* case for the detector, and it is the one
    sentence a reader needs about the operating point: the pair below that
    concentration is still visible in ``collusion_index`` and, for a transfer far
    from the reference price, still reported by the off market family.
    """
    config = DetectorConfig()
    projection = reference_colluding.projection
    pair = reference_colluding.colluding_pair()
    assert pair is not None
    source = pair[1]
    last_tick = projection.ticks_total
    market_id = projection.market_ids[0]
    reference_price = dict(projection.ref_price)[market_id][last_tick - 1]
    baseline = {(a, b): value for a, b, value in collusion_index(projection)}[pair]
    assert baseline >= config.collusion_threshold_ppm, "the undiluted pair is not flagged, so nothing is measured"

    def diluted(extra_qty: int) -> tuple[int, bool]:
        """Return the pair's index and whether it is still flagged, after dilution.

        The synthetic execution is the source buying ``extra_qty`` from the market
        maker at the reference price on the last tick, which is what honest flow
        looks like: on market, against the liquidity provider, and therefore
        invisible to every other detector.
        """
        padding = TradeRecord(
            trade_id="t-999999",
            tick=last_tick,
            market_id=market_id,
            price=reference_price,
            qty=extra_qty,
            maker_order_id="o-999999",
            maker_agent_id=MM_ACCOUNT_ID,
            maker_side="sell",
            taker_order_id="o-999998",
            taker_agent_id=source,
            taker_side="buy",
            taker_fee_cents=0,
            maker_cash_delta_cents=0,
            taker_cash_delta_cents=0,
        )
        padded = replace(projection, trades=(*projection.trades, padding))
        index_ppm = {(a, b): value for a, b, value in collusion_index(padded)}[pair]
        named = flagged_pairs(run_detectors(padded, config=config), IncidentKind.COLLUSION)
        return index_ppm, pair in named

    mutual_qty = sum(
        trade.qty for trade in projection.trades if {trade.maker_agent_id, trade.taker_agent_id} == set(pair)
    )
    floor: tuple[int, int] | None = None
    for extra_qty in (0, mutual_qty // 4, mutual_qty // 2, mutual_qty, 2 * mutual_qty):
        index_ppm, flagged = (baseline, True) if extra_qty == 0 else diluted(extra_qty)
        print(f"[AC-P6] dilution +{extra_qty} contracts of honest volume: index={index_ppm} flagged={flagged}")
        if not flagged and floor is None:
            floor = (extra_qty, index_ppm)
    assert floor is not None, (
        "the pair survived twice its own volume in honest dilution, so this test no longer measures a floor"
    )
    print(f"[AC-P6] sensitivity floor: lost at +{floor[0]} contracts of dilution, index {floor[1]} ppm")


# ---------------------------------------------------------------------------
# Contract surface
# ---------------------------------------------------------------------------
def test_detector_config_defaults_are_the_contracted_ones() -> None:
    config = DetectorConfig()
    assert config.collusion_threshold_ppm == 700_000
    assert config.off_market_sigma_milli == 3_000
    assert config.spoofing_cancel_ratio_ppm == 900_000
    assert config.mismatch_threshold_ppm == 300_000
    assert config.min_trades == 5


def test_the_suite_covers_every_alert_family_but_technical() -> None:
    assert len(DETECTORS) == 5
    assert [detector.name for detector in DETECTORS] == [
        CollusionDetector.name,
        OffMarketTransferDetector.name,
        WashTradingDetector.name,
        SpoofingDetector.name,
        PredictionMismatchDetector.name,
    ]
    for detector in DETECTORS:
        assert detector.version == DETECTOR_VERSION
    covered = {
        IncidentKind.COLLUSION,
        IncidentKind.OFF_MARKET_TRANSFER,
        IncidentKind.WASH_TRADING,
        IncidentKind.SPOOFING,
        IncidentKind.PREDICTION_POSITION_MISMATCH,
    }
    assert covered | {IncidentKind.TECHNICAL} == set(IncidentKind), (
        "an IncidentKind exists that no detector raises and that is not TECHNICAL"
    )


def test_run_detectors_renumbers_ids_and_is_deterministic(reference_colluding: Played) -> None:
    first = run_detectors(reference_colluding.projection)
    second = run_detectors(reference_colluding.projection, config=DetectorConfig())
    assert first, "no incident, so the renumbering claim is vacuous"
    assert first == second, "two runs over the same projection disagree"
    assert [item.incident_id for item in first] == [f"i-{index:04d}" for index in range(1, len(first) + 1)]
    for item in first:
        assert item.severity in ("low", "medium", "high")
        assert item.detector_version.endswith(f"@{DETECTOR_VERSION}")
        assert item.tick >= 1
        assert all(isinstance(value, int | str | bool) for _, value in item.detail)


def test_a_caller_can_run_one_detector_alone(reference_colluding: Played) -> None:
    only = run_detectors(reference_colluding.projection, detectors=(CollusionDetector(),))
    assert only, "the collusion detector found nothing on the colluding bench"
    assert {item.kind for item in only} == {IncidentKind.COLLUSION}
    assert run_detectors(reference_colluding.projection, detectors=()) == ()


def test_thresholds_are_honoured(reference_colluding: Played) -> None:
    impossible = DetectorConfig(
        collusion_threshold_ppm=1_000_001,
        off_market_sigma_milli=1_000_000,
        spoofing_cancel_ratio_ppm=1_000_001,
        mismatch_threshold_ppm=1_000_001,
    )
    assert run_detectors(reference_colluding.projection, config=impossible) == ()
    generous = DetectorConfig(collusion_threshold_ppm=1, min_trades=1)
    assert len(run_detectors(reference_colluding.projection, config=generous)) > len(
        run_detectors(reference_colluding.projection)
    )


def test_min_trades_is_an_evidence_floor(reference_colluding: Played) -> None:
    strict = DetectorConfig(min_trades=10_000)
    assert run_detectors(reference_colluding.projection, config=strict) == ()


# ---------------------------------------------------------------------------
# Detectors are offline and never touch a score (PRD section 7.2)
# ---------------------------------------------------------------------------
def test_no_incident_is_journalled(reference_colluding: Played) -> None:
    assert of_type(reference_colluding.events, IncidentRaised) == [], (
        "an integrity incident reached the journal, which would put a detector inside AC-P1"
    )


def test_running_the_detectors_changes_no_metric(reference_colluding: Played) -> None:
    before = compute_all(reference_colluding.projection)
    incidents = run_detectors(reference_colluding.projection)
    assert incidents, "no incident, so this test would prove nothing"
    after = compute_all(project(reference_colluding.events))
    assert before == after, "a metric moved when the detectors ran"
    assert reference_colluding.projection.highlights == project(reference_colluding.events).highlights


def test_incidents_become_highlights_only_when_the_caller_passes_them(reference_colluding: Played) -> None:
    """The A15 seam: ``project(events, incidents=...)`` is how an alert reaches the UI.

    Without the argument the projection is a pure function of the journal and
    carries no ``integrity_alert`` highlight, which is what keeps a detector
    version bump out of every metric (CONTRACTS section 7.17). With it, the
    alerts this package produced become highlights, and that is the only path
    between A18 and the replay UI.
    """
    incidents = run_detectors(reference_colluding.projection)
    assert incidents, "no incident, so both halves of this test would be vacuous"
    bare = project(reference_colluding.events)
    assert [highlight for highlight in bare.highlights if highlight.kind == "integrity_alert"] == []
    with_alerts = project(reference_colluding.events, incidents=incidents)
    alerts = [highlight for highlight in with_alerts.highlights if highlight.kind == "integrity_alert"]
    assert len(alerts) == len(incidents), "an incident did not become a highlight"
    assert all(highlight.label for highlight in alerts), "a highlight reached the UI without a label"


def test_a_detector_reads_the_projection_and_never_the_events() -> None:
    source = Path(__file__).resolve().parents[1] / "src" / "pxe" / "integrity" / "detectors.py"
    text = source.read_text(encoding="utf-8")
    assert "MatchProjection" in text, "the scan found the wrong file"
    for forbidden in ("from pxe.runner", "from pxe.exchange", "from pxe.world", "from pxe.info", "read_journal"):
        assert forbidden not in text, f"detectors.py reaches for {forbidden}"


# ---------------------------------------------------------------------------
# write_incidents
# ---------------------------------------------------------------------------
def test_write_incidents_round_trip(tmp_path: Path, reference_colluding: Played) -> None:
    incidents = run_detectors(reference_colluding.projection)
    assert incidents, "nothing to write, so this test would be vacuous"
    path = tmp_path / "runs" / "m-x" / "incidents.jsonl"
    write_incidents(path, incidents)
    raw = path.read_bytes()
    assert b"\r" not in raw, "a carriage return reached incidents.jsonl"
    lines = raw.decode("utf-8").splitlines()
    assert len(lines) == len(incidents)
    for line, item in zip(lines, incidents, strict=True):
        payload = json.loads(line)
        assert payload["incident_id"] == item.incident_id
        assert payload["kind"] == item.kind.value
        assert payload["severity"] == item.severity
        assert payload["tick"] == item.tick
        assert payload["agent_ids"] == list(item.agent_ids)
        assert payload["market_ids"] == list(item.market_ids)
        assert payload["score_ppm"] == item.score_ppm
        assert payload["detector_version"] == item.detector_version
        assert incident_detail_from_dict(payload["detail"]) == tuple(sorted(item.detail))
    assert sorted(json.loads(lines[0])) == list(json.loads(lines[0])), "keys are not canonically sorted"


def test_write_incidents_replaces_the_file(tmp_path: Path, reference_colluding: Played) -> None:
    incidents = run_detectors(reference_colluding.projection)
    path = tmp_path / "incidents.jsonl"
    write_incidents(path, incidents)
    write_incidents(path, incidents)
    assert len(path.read_text(encoding="utf-8").splitlines()) == len(incidents), (
        "a second run appended a second generation of ids to the same file"
    )
    write_incidents(path, ())
    assert path.read_text(encoding="utf-8") == "", "an empty run left the previous alerts behind"


# ---------------------------------------------------------------------------
# make_cheater
# ---------------------------------------------------------------------------
def test_make_cheater_builds_every_registered_name(standard_config: MatchConfig) -> None:
    rng = RngTree(standard_config.seed)
    assert CHEATERS == ("colluder", "washer", "spoofer", "liar")
    for name in CHEATERS:
        cheater = make_cheater(
            name,
            agent_id="A1",
            partner_id="A2",
            rng=rng.child("agent/A1").substream("agent.A1"),
            config=standard_config,
        )
        assert cheater.agent_id == "A1"
        assert cheater.name == name
        cheater.reset(config=standard_config, rng=rng.child("agent/A1").substream("agent.A1"))


def test_make_cheater_refuses_a_bad_configuration(standard_config: MatchConfig) -> None:
    rng = RngTree(standard_config.seed).child("agent/A1").substream("agent.A1")
    with pytest.raises(InvalidConfigError):
        make_cheater("saboteur", agent_id="A1", partner_id=None, rng=rng, config=standard_config)
    with pytest.raises(InvalidConfigError):
        make_cheater("colluder", agent_id="A1", partner_id=None, rng=rng, config=standard_config)
    with pytest.raises(InvalidConfigError):
        make_cheater("washer", agent_id="A1", partner_id="A1", rng=rng, config=standard_config)


def test_a_solo_cheat_needs_no_partner(standard_config: MatchConfig) -> None:
    rng = RngTree(standard_config.seed).child("agent/A3").substream("agent.A3")
    for name in ("spoofer", "liar"):
        assert make_cheater(name, agent_id="A3", partner_id=None, rng=rng, config=standard_config).agent_id == "A3"


@pytest.mark.determinism
def test_a_cheater_bench_match_replays_identically() -> None:
    """Two runs of the same bench seed produce the same journal.

    The cheaters are part of the scripted population, so AC-P1 covers them: a
    cheater that read a clock or drew outside its substream would break the
    determinism claim for every bench number in this file.
    """
    first = play_bench(
        seed=CALIBRATION_SEEDS[2],
        template=BENCH_TEMPLATES[0],
        cheats=(Cheat(seat=1, name="colluder", partner_seat=2), Cheat(seat=2, name="colluder", partner_seat=1)),
    )
    second = play_bench(
        seed=CALIBRATION_SEEDS[2],
        template=BENCH_TEMPLATES[0],
        cheats=(Cheat(seat=1, name="colluder", partner_seat=2), Cheat(seat=2, name="colluder", partner_seat=1)),
    )
    assert first.events, "empty journal"
    assert first.result.journal_hash == second.result.journal_hash
    assert run_detectors(first.projection) == run_detectors(second.projection)
