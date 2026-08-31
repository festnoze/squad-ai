"""A17 acceptance tests: the six MAP-Elites descriptors (PRD 7.4, T5.1).

Every test starts from a **non empty** projection and asserts that the rows it is
about to measure exist, which is CONTRACTS section 10's anti vacuous rule: a
projection of five empty tuples satisfies every annotation
:mod:`pxe.metrics.behavioral` codes against, and a descriptor computed over
nothing would return six neutral constants and look plausible.

Five claims this file exists for:

* the six descriptors come from the journal alone, through a
  ``MatchProjection`` and nothing else;
* the ``reserved_cents`` and the per market positions the module rebuilds from
  the order and trade rows are **equal** to the ones ``PositionSnapshot``
  journalled, which is invariant I3 read as a metric: the reconstruction is the
  section 6.1 formula, so it must not merely approximate the ledger;
* the axes have reachable extremes, so a MAP-Elites grid over them is not one
  crowded cell: a pure taker sits at ``maker_ratio_ppm == 0``, a seat that never
  trades sits at the latency cap, a one market book sits at
  ``herfindahl_ppm == 1_000_000``;
* T5.1's inter seed stability: over five seeds of the same scenario, the
  correlation of each descriptor across the population exceeds 0.6, so a
  descriptor identifies the harness and not the seed;
* that stability bench **can fail**, which is demonstrated with a population of
  deliberately erratic agents whose descriptors are seed noise.
"""

from __future__ import annotations

import statistics

import pytest

from pxe.events import AgentFrozen, Event, PositionSnapshot
from pxe.journal import read_journal
from pxe.metrics import behavioral
from pxe.metrics.behavioral import (
    DESCRIPTOR_NAMES,
    BehavioralDescriptors,
    compute_descriptors,
)
from pxe.metrics.projection import MatchProjection, project
from pxe.rng import RngTree
from pxe.types import (
    MILLI_ONE,
    PPM_ONE,
    AgentAction,
    Incident,
    IncidentKind,
    MatchConfig,
    Observation,
    OrderIntent,
    OrderType,
    PredictionIntent,
    Side,
    make_incident_id,
)
from pxe.world.generator import generate_world
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
    play_with_agents,
)

GOLDEN: tuple[Recipe, ...] = (REFERENCE, SMALL, WIDE)

#: T5.1's threshold, quoted from the PRD WBS row: "stabilite inter-seeds
#: (correlation > 0,6 pour un meme harness)".
STABILITY_THRESHOLD = 0.6

#: The five seeds the stability bench replays the same scenario on. Fixed
#: values, because a `statistical` test states its seed and its tolerance
#: (section 10) and a randomly seeded stability claim is not a claim.
STABILITY_SEEDS: tuple[int, ...] = (11, 2222, 333333, 4444, 5555)

#: Horizon and width of the stability scenario. Twenty-four ticks is the legal
#: minimum, which keeps ten matches inside a fast test.
BENCH_TICKS = 24
BENCH_MARKETS = 3


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
    """Project one frozen journal and refuse an empty one."""
    projection = project(golden_events(recipe))
    assert projection.trades, "no trade row: every trading descriptor would be vacuous"
    assert projection.orders, "no order row: the reserved reconstruction would be vacuous"
    assert projection.signals, "no signal row: reaction latency would be vacuous"
    assert projection.agent_ids, "no ranked seat"
    return projection


def descriptors_by_agent(projection: MatchProjection) -> dict[str, BehavioralDescriptors]:
    """Index the descriptor blocks by seat."""
    rows = compute_descriptors(projection)
    assert rows, "compute_descriptors returned nothing"
    return {row.agent_id: row for row in rows}


@pytest.fixture(scope="module")
def reference() -> MatchProjection:
    """The projection of the reference golden match, built once."""
    return golden_projection(REFERENCE)


def correlation_or_none(left: list[int], right: list[int]) -> float | None:
    """Return Pearson's r, or ``None`` when either vector is constant.

    A constant vector has no correlation, and pretending it has one (say 1.0
    because both sides are constant) is exactly the vacuous pass section 10
    forbids: it would let a descriptor that is always zero look perfectly
    stable. The caller decides what ``None`` means for its claim.
    """
    if len(set(left)) < 2 or len(set(right)) < 2:
        return None
    return statistics.correlation(left, right)


def mean_inter_seed_correlation(per_seed: dict[int, dict[str, list[int]]], name: str) -> float | None:
    """Mean of Pearson's r over every unordered pair of seeds, for one descriptor."""
    seeds = sorted(per_seed)
    values: list[float] = []
    for index, left in enumerate(seeds):
        for right in seeds[index + 1 :]:
            cor = correlation_or_none(per_seed[left][name], per_seed[right][name])
            if cor is None:
                return None
            values.append(cor)
    assert values, "no seed pair to correlate"
    return statistics.fmean(values)


# ---------------------------------------------------------------------------
# Scripted agents with a deliberate style, so every axis has two ends
# ---------------------------------------------------------------------------
class Styled:
    """A seat with a fixed, seed independent trading style.

    Four knobs are enough to place a seat at a known end of each of the six
    axes: ``passive`` decides the maker ratio, ``one_market`` decides the
    Herfindahl, ``qty`` decides the leverage and ``message_every`` decides the
    communication intensity. Nothing here draws from the generator it is handed,
    which is the point: a style must be a property of the harness, not of the
    seed, or T5.1's stability claim is untestable.
    """

    def __init__(
        self,
        *,
        agent_id: str,
        config: MatchConfig,
        rng: object,
        passive: bool,
        one_market: bool,
        message_every: int,
        qty: int,
    ) -> None:
        self.agent_id = agent_id
        self._config = config
        self._passive = passive
        self._one_market = one_market
        self._message_every = message_every
        self._qty = qty

    def reset(self, *, config: MatchConfig, rng: object) -> None:
        self._config = config

    def act(self, observation: Observation) -> AgentAction:
        blocks = observation.markets[:1] if self._one_market else observation.markets
        orders: list[OrderIntent] = []
        for block in blocks:
            if self._passive:
                orders.extend(self._quote(block))
            else:
                orders.append(self._hit(block, observation.tick))
        message = None
        if self._message_every and observation.tick % self._message_every == 0:
            message = f"{self.agent_id} at tick {observation.tick}"
        return AgentAction(
            agent_id=self.agent_id,
            tick=observation.tick,
            action_version=self._config.action_version,
            predictions=tuple(
                PredictionIntent(market_id=block.market_id, p_yes_ppm=500_000) for block in observation.markets
            ),
            orders=tuple(orders),
            message_public=message,
        )

    def _quote(self, block: object) -> list[OrderIntent]:
        """Replace last tick's quotes with a new best bid and a new best ask."""
        out = [OrderIntent(op="cancel", order_id=order.order_id) for order in block.my_orders]  # type: ignore[attr-defined]
        bid, ask = block.best_bid, block.best_ask  # type: ignore[attr-defined]
        if bid is None or ask is None:
            return out
        buy = bid + 1 if bid + 1 < ask else bid
        sell = ask - 1 if ask - 1 > buy else ask
        for side, price in ((Side.BUY, buy), (Side.SELL, sell)):
            out.append(
                OrderIntent(
                    op="place",
                    market_id=block.market_id,  # type: ignore[attr-defined]
                    side=side,
                    order_type=OrderType.LIMIT,
                    price=price,
                    qty=self._qty,
                )
            )
        return out

    def _hit(self, block: object, tick: int) -> OrderIntent:
        """Cross the spread, two ticks out of three on the buy side.

        The bias matters: a seat that alternated evenly would be flat exactly
        half the time and its Herfindahl at the median tick would be a coin
        toss on the seed, which is a property of this test agent and not of the
        descriptor.
        """
        market_id: str = block.market_id  # type: ignore[attr-defined]
        side = Side.SELL if (tick + int(market_id[1:])) % 3 == 0 else Side.BUY
        return OrderIntent(op="place", market_id=market_id, side=side, order_type=OrderType.MARKET, qty=self._qty)


class Erratic:
    """A seat whose every choice comes from its seed derived generator.

    This is the control of the T5.1 bench. Its style is not a style: order type,
    side, size, market and message all move with the seed, so its descriptors
    carry no harness signal and the inter seed correlation collapses. Without it
    ``test_descriptors_stable_across_seeds`` could be passing on a bench that
    cannot fail.
    """

    def __init__(self, *, agent_id: str, config: MatchConfig, rng: object) -> None:
        self.agent_id = agent_id
        self._config = config
        self._rng = rng

    def reset(self, *, config: MatchConfig, rng: object) -> None:
        self._config = config
        self._rng = rng

    def act(self, observation: Observation) -> AgentAction:
        draw = self._rng.getrandbits  # type: ignore[attr-defined]
        orders: list[OrderIntent] = []
        for block in observation.markets:
            if draw(2) == 0:
                continue
            side = Side.BUY if draw(1) else Side.SELL
            if draw(1):
                orders.append(
                    OrderIntent(
                        op="place",
                        market_id=block.market_id,
                        side=side,
                        order_type=OrderType.MARKET,
                        qty=1 + draw(3),
                    )
                )
            else:
                orders.append(
                    OrderIntent(
                        op="place",
                        market_id=block.market_id,
                        side=side,
                        order_type=OrderType.LIMIT,
                        price=2 + draw(6) % 96,
                        qty=1 + draw(3),
                    )
                )
        message = f"{self.agent_id} says {draw(8)}" if draw(1) else None
        return AgentAction(
            agent_id=self.agent_id,
            tick=observation.tick,
            action_version=self._config.action_version,
            predictions=tuple(
                PredictionIntent(market_id=block.market_id, p_yes_ppm=500_000) for block in observation.markets
            ),
            orders=tuple(orders),
            message_public=message,
        )


#: The four styled seats of the bench, in seat order. Seats A5 and A6 are the
#: ``bayesian`` and ``mute`` baselines, so the population mixes real harnesses
#: with the two extremes each axis needs.
BENCH_STYLES: tuple[dict[str, object], ...] = (
    {"passive": False, "one_market": True, "message_every": 1, "qty": 5},
    {"passive": False, "one_market": False, "message_every": 2, "qty": 5},
    {"passive": True, "one_market": False, "message_every": 0, "qty": 10},
    {"passive": True, "one_market": True, "message_every": 3, "qty": 10},
)
BENCH_BASELINES: tuple[str, ...] = ("bayesian", "mute")


def play_bench(seed: int, *, erratic: bool) -> MatchProjection:
    """Play one bench match on one seed and project it.

    Args:
        seed: Root seed of the match, and of the world.
        erratic: True to seat six :class:`Erratic` agents instead of the styled
            population, which is the control run.

    Returns:
        The projection of that match.
    """
    from pxe.agents.base import make_baseline

    n_seats = len(BENCH_STYLES) + len(BENCH_BASELINES)
    recipe = custom_recipe(
        baselines=("fundamentalist",) * n_seats,
        seed=seed,
        ticks=BENCH_TICKS,
        markets=BENCH_MARKETS,
        template="election",
    )
    config = config_of(recipe, talking_mode=True)
    world = generate_world(
        template_id=recipe.template_id,
        seed=seed,
        ticks_total=BENCH_TICKS,
        n_markets=BENCH_MARKETS,
        talking_mode=True,
    )
    rng = RngTree(seed)
    factories: dict[str, object] = {}
    for index in range(1, n_seats + 1):
        agent_id = f"A{index}"
        substream = rng.child(f"agent/{agent_id}").substream(f"agent.{agent_id}")
        if erratic:
            factories[agent_id] = Erratic(agent_id=agent_id, config=config, rng=substream)
        elif index <= len(BENCH_STYLES):
            factories[agent_id] = Styled(
                agent_id=agent_id,
                config=config,
                rng=substream,
                **BENCH_STYLES[index - 1],  # type: ignore[arg-type]
            )
        else:
            factories[agent_id] = make_baseline(
                BENCH_BASELINES[index - 1 - len(BENCH_STYLES)],
                agent_id=agent_id,
                config=config,
                rng=substream,
            )
    _result, events = play_with_agents(recipe, factories=factories, config=config, world=world, rng=rng)
    projection = project(events)
    assert projection.trades, "the bench produced no trade: every descriptor would be a default"
    assert projection.messages, "the bench produced no message: message intensity would be vacuous"
    return projection


def bench_vectors(*, erratic: bool) -> dict[int, dict[str, list[int]]]:
    """Return, per seed, the population vector of each descriptor.

    A vector is indexed by seat, and a seat is one harness of the population, so
    correlating two seeds over that vector answers exactly T5.1's question: does
    the descriptor rank the harnesses the same way whatever the seed.
    """
    out: dict[int, dict[str, list[int]]] = {}
    for seed in STABILITY_SEEDS:
        rows = compute_descriptors(play_bench(seed, erratic=erratic))
        per_name: dict[str, list[int]] = {name: [] for name in DESCRIPTOR_NAMES}
        for row in rows:
            for index, name in enumerate(DESCRIPTOR_NAMES):
                per_name[name].append(row.as_tuple()[index])
        out[seed] = per_name
    return out


# ---------------------------------------------------------------------------
# The public shape
# ---------------------------------------------------------------------------
def test_descriptor_names_match_the_dataclass_and_as_tuple() -> None:
    """DESCRIPTOR_NAMES is the axis order A20 bins, so it is load bearing."""
    assert DESCRIPTOR_NAMES == (
        "maker_ratio_ppm",
        "reaction_latency_milli",
        "holding_horizon_milli",
        "herfindahl_ppm",
        "leverage_ppm",
        "message_intensity_ppm",
    )
    row = BehavioralDescriptors(
        agent_id="A1",
        maker_ratio_ppm=1,
        reaction_latency_milli=2,
        holding_horizon_milli=3,
        herfindahl_ppm=4,
        leverage_ppm=5,
        message_intensity_ppm=6,
    )
    assert row.as_tuple() == (1, 2, 3, 4, 5, 6)
    assert row.as_tuple() == tuple(getattr(row, name) for name in DESCRIPTOR_NAMES)
    assert len(DESCRIPTOR_NAMES) == len(row.as_tuple()) == 6


# ---------------------------------------------------------------------------
# The journal alone
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_six_descriptors_from_the_journal_alone(recipe: Recipe) -> None:
    """T5.1: the six descriptors are computed from the journal and nothing else.

    The input is a frozen journal read from disk, projected by A15's ``project``
    and handed to ``compute_descriptors``. No world, no info engine, no agent and
    no exchange is constructed anywhere in this test, which is the whole of PRD
    section 7.4's "calcules exclusivement depuis le journal".
    """
    projection = golden_projection(recipe)
    rows = compute_descriptors(projection)

    assert tuple(row.agent_id for row in rows) == projection.agent_ids, "not one block per seat in canonical order"
    horizon_milli = projection.ticks_total * MILLI_ONE
    for row in rows:
        assert 0 <= row.maker_ratio_ppm <= PPM_ONE
        assert 0 <= row.reaction_latency_milli <= horizon_milli
        assert 0 <= row.holding_horizon_milli <= horizon_milli
        assert 0 <= row.herfindahl_ppm <= PPM_ONE
        assert 0 <= row.leverage_ppm <= PPM_ONE, "I4 keeps reserved <= cash, so leverage cannot exceed one"
        assert 0 <= row.message_intensity_ppm <= PPM_ONE
    # Anti vacuous: at least one seat actually traded and therefore has a
    # descriptor that is not the "never played" default.
    traded = [row for row in rows if row.holding_horizon_milli > 0]
    assert traded, "no seat ever held a position, so five of the six axes are defaults"


def test_descriptors_are_a_pure_function_of_the_projection(reference: MatchProjection) -> None:
    """Two calls agree, and an incident file cannot move a descriptor.

    Incidents reach ``project`` only to build ``integrity_alert`` highlights
    (section 4.5, decision 10), so a detector version bump must be invisible
    here. This is the behavioral half of the AC-P4 style decoupling
    ``test_metrics_decoupling.py`` asserts for the two scores.
    """
    first = compute_descriptors(reference)
    assert first == compute_descriptors(reference)

    events = golden_events(REFERENCE)
    incident = Incident(
        incident_id=make_incident_id(1),
        kind=IncidentKind.COLLUSION,
        severity="high",
        tick=2,
        agent_ids=(reference.agent_ids[0],),
        market_ids=(reference.market_ids[0],),
        score_ppm=900_000,
        detail=(("source", "synthetic"),),
        detector_version="1.0.0",
    )
    with_incident = project(events, incidents=(incident,))
    assert any(row.kind == "integrity_alert" for row in with_incident.highlights), "the incident did not reach the fold"
    assert compute_descriptors(with_incident) == first


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_rebuilt_reserved_equals_the_journalled_snapshot(recipe: Recipe) -> None:
    """The reconstruction is the section 6.1 formula, so I3 makes it exact.

    ``leverage_ppm`` needs ``reserved_cents`` at the close of every tick and the
    projection carries no such series, so the module rebuilds it from the order
    and trade rows. Invariant I3 says that formula equals the ledger, so
    "approximately equal" is not good enough: every tick of every ranked seat
    must match the number ``PositionSnapshot`` journalled.
    """
    events = golden_events(recipe)
    projection = golden_projection(recipe)
    timeline = behavioral._build_timeline(projection)

    snapshots = [
        event
        for event in of_type(events, PositionSnapshot)
        if isinstance(event, PositionSnapshot)
        and event.account_id in projection.agent_ids
        and 1 <= event.tick <= projection.ticks_total
    ]
    assert snapshots, "no PositionSnapshot for a ranked seat: this test would compare nothing"
    assert any(event.reserved_cents > 0 for event in snapshots), "nobody ever locked collateral, so the check is blind"

    for event in snapshots:
        rebuilt = timeline.reserved[event.account_id][event.tick - 1]
        assert rebuilt == event.reserved_cents, f"{event.account_id} at tick {event.tick}"


@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_rebuilt_positions_equal_the_journalled_snapshot(recipe: Recipe) -> None:
    """The per tick position series is the one ``PositionSnapshot`` reports."""
    events = golden_events(recipe)
    projection = golden_projection(recipe)
    timeline = behavioral._build_timeline(projection)

    compared = 0
    non_flat = 0
    for event in of_type(events, PositionSnapshot):
        assert isinstance(event, PositionSnapshot)
        if event.account_id not in projection.agent_ids or not 1 <= event.tick <= projection.ticks_total:
            continue
        journalled = {str(row["market_id"]): int(row["qty"]) for row in event.positions}
        for market_id in projection.market_ids:
            rebuilt = timeline.positions.get((event.account_id, market_id), ())
            held = rebuilt[event.tick - 1] if rebuilt else 0
            assert held == journalled.get(market_id, 0), f"{event.account_id} {market_id} tick {event.tick}"
            compared += 1
            non_flat += 1 if held != 0 else 0
    assert compared, "no position was compared"
    assert non_flat, "every position was flat, so the reconstruction was never exercised"


# ---------------------------------------------------------------------------
# The extremes of each axis are reachable
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("recipe", GOLDEN, ids=lambda recipe: recipe.name)
def test_a_seat_that_never_trades_is_neutral_and_at_the_cap(recipe: Recipe) -> None:
    """The ``mute`` baseline (AC-P9) pins every "never played" default at once."""
    projection = golden_projection(recipe)
    rows = descriptors_by_agent(projection)
    silent = [
        agent_id
        for agent_id in projection.agent_ids
        if not any(agent_id in (trade.maker_agent_id, trade.taker_agent_id) for trade in projection.trades)
    ]
    assert silent, "every seat traded, so this golden match no longer holds a mute baseline"
    for agent_id in silent:
        row = rows[agent_id]
        assert row.maker_ratio_ppm == PPM_ONE // 2, "a seat with no execution is neither passive nor aggressive"
        assert row.reaction_latency_milli == projection.ticks_total * MILLI_ONE, "an unanswered signal costs the cap"
        assert row.holding_horizon_milli == 0
        assert row.herfindahl_ppm == 0
        assert row.leverage_ppm == 0
        assert row.message_intensity_ppm == 0


def test_taker_and_maker_styles_sit_at_opposite_ends() -> None:
    """A pure taker reaches 0 and a two sided quoter reaches the top of the axis."""
    projection = play_bench(STABILITY_SEEDS[0], erratic=False)
    rows = descriptors_by_agent(projection)

    assert rows["A1"].maker_ratio_ppm == 0, "a seat that only sends market orders is never the maker"
    assert rows["A2"].maker_ratio_ppm == 0
    assert rows["A3"].maker_ratio_ppm > 700_000, "a two sided quoter is mostly hit, not hitting"
    assert rows["A4"].maker_ratio_ppm > 700_000
    # A1 and A4 trade one market only, so their whole exposure is concentrated.
    assert rows["A1"].herfindahl_ppm == PPM_ONE
    assert rows["A4"].herfindahl_ppm == PPM_ONE
    assert rows["A2"].herfindahl_ppm < PPM_ONE, "a seat spread over three markets is not concentrated"
    # A1 hits its own market every tick, so it answers its signals immediately.
    assert rows["A1"].reaction_latency_milli > 0
    assert rows["A2"].reaction_latency_milli < rows["A1"].reaction_latency_milli, (
        "A1 also receives signals about the two markets it refuses to trade, which cost the cap"
    )


def test_message_intensity_counts_the_ticks_a_seat_spoke_on() -> None:
    """FR-5.6.1: the axis is the share of played ticks carrying a message."""
    projection = play_bench(STABILITY_SEEDS[0], erratic=False)
    rows = descriptors_by_agent(projection)
    assert rows["A1"].message_intensity_ppm == PPM_ONE, "A1 speaks on every tick"
    assert rows["A2"].message_intensity_ppm == PPM_ONE // 2, "A2 speaks every other tick"
    assert rows["A3"].message_intensity_ppm == 0, "A3 never speaks"
    assert rows["A4"].message_intensity_ppm == PPM_ONE // 3, "A4 speaks every third tick"


def test_message_intensity_is_zero_when_talking_mode_is_off() -> None:
    """Talking mode is off by default, so no journal carries a MessagePosted."""
    projection = golden_projection(REFERENCE)
    assert projection.messages == (), "the reference match now has messages, so this test measures nothing"
    for row in compute_descriptors(projection):
        assert row.message_intensity_ppm == 0


def test_a_frozen_seat_is_normalised_on_the_ticks_it_played() -> None:
    """FR-5.5.5: a bankruptcy at tick t normalises the axes over ticks 1..t.

    Section 9 already settles the principle for calibration ("its Brier is the
    mean over the ticks it actually played"). Without the same normalisation
    here, a seat frozen early reports a near zero leverage, which is the exact
    opposite of what emptied its account.
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
    tail = Recipe(
        name="tail",
        template_id=recipe.template_id,
        seed=recipe.seed,
        ticks_total=recipe.ticks_total,
        n_markets=recipe.n_markets,
        baselines=("fundamentalist", "fundamentalist", "momentum", "bayesian"),
    )
    seats = agents_of(tail, config, rng)
    seats["A1"] = Spendthrift(agent_id="A1", config=config, rng=rng.child("agent/A1").substream("agent.A1"))
    _result, events = play_with_agents(recipe, factories=seats, config=config)

    frozen = of_type(events, AgentFrozen)
    assert frozen, "no agent was frozen: the scenario no longer exhausts free cash"
    freeze = frozen[0]
    assert isinstance(freeze, AgentFrozen)
    assert freeze.tick < recipe.ticks_total, "a freeze on the last tick would make played == ticks_total"

    projection = project(events)
    assert projection.trades, "the bankruptcy scenario produced no trade"
    timeline = behavioral._build_timeline(projection)
    assert timeline.played[freeze.agent_id] == freeze.tick
    assert timeline.played[projection.agent_ids[-1]] == projection.ticks_total

    row = descriptors_by_agent(projection)[freeze.agent_id]
    # Its holding spell is cut at the freeze tick instead of running to the
    # settlement, which is the whole point of normalising on ticks played.
    assert 0 < row.holding_horizon_milli <= freeze.tick * MILLI_ONE
    assert row.holding_horizon_milli < projection.ticks_total * MILLI_ONE
    # And the signals it was handed after the freeze do not count as ignored
    # information: it was not allowed to act on them.
    late = [signal for signal in projection.signals if signal.agent_id == freeze.agent_id and signal.tick > freeze.tick]
    assert late, "no signal arrived after the freeze, so the window guard is untested here"
    assert row.reaction_latency_milli == 0, "a seat that traded every tick it played answered every signal at once"


# ---------------------------------------------------------------------------
# T5.1: inter seed stability, and a bench that can fail
# ---------------------------------------------------------------------------
@pytest.mark.statistical
def test_descriptors_stable_across_seeds() -> None:
    """T5.1: each descriptor correlates above 0.6 across five seeds.

    The bench replays one scenario (``election``, 24 ticks, 3 markets) on the
    five fixed seeds of :data:`STABILITY_SEEDS` with the same six harnesses in
    the same seats. For each descriptor, the population vector of one seed is
    correlated with the population vector of every other seed, and the mean over
    the ten pairs must exceed 0.6: a descriptor that ranked the harnesses
    differently on every seed would be a measurement of the world and not of the
    players, and a MAP-Elites archive built on it would move cells for free.

    Tolerance: the observed means are 0.84 and above, the weakest axis being
    ``holding_horizon_milli``. The threshold is the PRD's, not a fitted one.
    """
    per_seed = bench_vectors(erratic=False)
    assert len(per_seed) == len(STABILITY_SEEDS)

    for name in DESCRIPTOR_NAMES:
        for seed, vectors in per_seed.items():
            assert len(set(vectors[name])) > 1, f"{name} is constant across the population on seed {seed}"
        cor = mean_inter_seed_correlation(per_seed, name)
        assert cor is not None, f"{name} had no variance to correlate"
        assert cor > STABILITY_THRESHOLD, f"{name} inter seed correlation {cor:.3f} <= {STABILITY_THRESHOLD}"


@pytest.mark.statistical
def test_the_stability_bench_can_fail() -> None:
    """The control: erratic agents break the T5.1 claim, so the bench has teeth.

    Six :class:`Erratic` seats draw every decision from their own seed derived
    substream, so nothing about them is a style. Their descriptors are seed
    noise, the inter seed correlation collapses, and at least one axis falls
    below the threshold. Without this test,
    ``test_descriptors_stable_across_seeds`` could be green because the metric
    is constant rather than because it is stable.
    """
    per_seed = bench_vectors(erratic=True)
    scores = {name: mean_inter_seed_correlation(per_seed, name) for name in DESCRIPTOR_NAMES}
    assert any(cor is None or cor <= STABILITY_THRESHOLD for cor in scores.values()), (
        f"the erratic population was ruled stable, so the bench cannot fail: {scores}"
    )
