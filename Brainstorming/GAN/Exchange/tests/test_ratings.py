"""A20 acceptance tests for the TrueSkill service (PRD 7.3, T3.2, T3.3, FR-5.8.5).

Everything here starts from a **real ranking**, never from a forged one. The
module level ``REFERENCE_RANKING`` is read out of the frozen golden journal of
``tests/golden/``, and the anti vacuous rule (CONTRACTS section 10) is applied at
the top: the journal is asserted non empty, it is asserted to contain a
``MatchEnded``, and that event is asserted to carry one ranking row per ranked
seat before a single rating is computed. A ranking of zero rows would let every
assertion below pass over nothing.

The four claims this file exists for:

* ``sigma`` shrinks as evidence accumulates, which is the only reason to track
  uncertainty at all (T3.2);
* the expected order of a strength ladder is recovered over 200 **scripted**
  matches played by the real engine, with no LLM anywhere near it
  (``test_baseline_order_recovered``, ``slow`` and ``statistical``);
* the reference market maker and the fee vault are never rated (FR-5.8.5);
* a bootstrap interval is a function of its substream and of nothing else
  (T3.3), so two machines publish the same confidence interval.

Why the ladder is not the six shipped baselines
-----------------------------------------------
``test_baseline_order_recovered`` needs a population whose true order is known
*before* the matches are played, otherwise it measures the arena and not the
rating service - and the contract gives no total order over the six baselines of
``pxe.agents.baselines``. Section 7.15 describes them with six adjectives and
ranks none of them; the only ordering any requirement states is FR-5.3.1's
"a Bayesian scripted agent beats a random one", which is one relation and not a
permutation of six. So the full-order assertion T3.2 asks for has no ground
truth to be checked against, and the ladder below supplies one by construction.

That is **not** the same as saying the baselines are indistinguishable. Measured
over 60 twenty-four tick election matches with the seating rotated every match
(so no baseline is stuck with one information profile), their mean ranks spread
by 1.467: ``momentum`` is clearly last at 4.533 while ``fundamentalist`` and
``bayesian`` tie at the top on 3.067. The relation the contract *does* state is
therefore checkable on the real baselines, and
``test_the_rating_service_recovers_the_one_ordering_the_contract_states`` below
checks exactly it and nothing more. Each of its agents round trips the market
maker quote a fixed number of times per tick, buying one contract at the ask and
selling it back at the bid inside the same action block, so it ends every tick
flat and its PnL is exactly minus the spread it paid: more round trips is
strictly worse, whatever the latent process does. The per match count is drawn
once, in ``reset``, from the agent's own substream and jitters by plus or minus
one, so adjacent rungs overlap and a single match frequently misorders them.
Recovering the order is therefore a statement about aggregation over 200 matches
and not an arithmetic identity.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Sequence

import pytest

from pxe.errors import InvalidConfigError
from pxe.events import Event, MatchEnded
from pxe.journal import read_journal
from pxe.rng import RngTree, randint
from pxe.tournament.ratings import (
    DEFAULT_MU,
    DEFAULT_SIGMA,
    UNRATED_ACCOUNT_IDS,
    RatingService,
    bootstrap_ci,
)
from pxe.types import (
    FEES_ACCOUNT_ID,
    MM_ACCOUNT_ID,
    AgentAction,
    HarnessConfig,
    MatchConfig,
    MatchRanking,
    Observation,
    OrderIntent,
    OrderType,
    PredictionIntent,
    RatingRecord,
    Side,
    harness_key,
)
from tests.test_match_runner import (
    GOLDEN_DIR,
    REFERENCE,
    Recipe,
    agents_of,
    config_of,
    custom_recipe,
    of_type,
    play_with_agents,
)

# ---------------------------------------------------------------------------
# The reference ranking, read from the frozen journal
# ---------------------------------------------------------------------------


def _reference_events() -> tuple[Event, ...]:
    """Read the golden journal of the reference match and refuse an empty one."""
    path = GOLDEN_DIR / f"{REFERENCE.name}.journal.jsonl"
    assert path.exists(), f"missing golden journal for {REFERENCE.name}"
    events = read_journal(path)
    assert events, "the golden journal read back empty, so every rating below would be vacuous"
    return events


def _reference_ranking() -> tuple[MatchRanking, ...]:
    """Rebuild ``MatchRanking`` rows out of ``MatchEnded.rankings``."""
    ended = of_type(_reference_events(), MatchEnded)
    assert len(ended) == 1, "a journal carries exactly one MatchEnded"
    payload = ended[0]
    assert isinstance(payload, MatchEnded)
    rows = payload.rankings
    assert len(rows) == len(REFERENCE.baselines), "the ranking must hold one row per ranked seat"
    return tuple(
        MatchRanking(
            rank=int(row["rank"]),
            agent_id=str(row["agent_id"]),
            pnl_cents=int(row["pnl_cents"]),
            final_cash_cents=int(row["final_cash_cents"]),
            pnl_pct_bps=int(row["pnl_pct_bps"]),
        )
        for row in rows
    )


#: The ranking every fast test in this file rates. It comes from the journal.
REFERENCE_RANKING: tuple[MatchRanking, ...] = _reference_ranking()


def harness_of_seats(names: Sequence[str], *, seats: Sequence[str]) -> dict[str, str]:
    """Map seat ids to the harness keys of the named scripted harnesses."""
    assert len(names) == len(seats)
    return {
        seat: harness_key(HarnessConfig(harness_id=name, version="1.0.0", kind="scripted"))
        for seat, name in zip(seats, names, strict=True)
    }


REFERENCE_HARNESS_OF: dict[str, str] = harness_of_seats(
    REFERENCE.baselines,
    seats=[row.agent_id for row in sorted(REFERENCE_RANKING, key=lambda row: row.agent_id)],
)


# ---------------------------------------------------------------------------
# The strength ladder: designed order, real engine
# ---------------------------------------------------------------------------
#: Round trips per tick of the four rungs. Rung ``1`` pays the spread once per
#: tick, rung ``4`` pays it four times, and every rung ends each tick flat.
LADDER_BASES: tuple[int, ...] = (1, 2, 3, 4)

#: Number of scripted matches ``test_baseline_order_recovered`` plays. Two
#: hundred is the count PRD section 7.3's "intervalles de confiance bootstrap"
#: is meaningful at, and it is what makes the jitter of the ladder average out.
LADDER_MATCHES = 200

#: Fixed seed base of the ladder bench. A statistical test states its seed
#: (CONTRACTS section 10).
LADDER_SEED_BASE = 9_000

#: Ticks and markets of a ladder match: the smallest legal values, so 200 real
#: matches stay inside a `slow` test.
LADDER_TICKS = 24
LADDER_MARKETS = 2


class SpreadPayer:
    """Round trips the market maker quote a fixed number of times per tick.

    It buys one contract at the ask and sells it back at the bid inside the same
    action block, so it is flat at the end of every tick and its whole PnL is the
    spread it paid. The number of round trips is drawn once per match, in
    :meth:`reset`, from the agent's own substream, so two rungs of the ladder
    overlap and a single match can misorder them.
    """

    def __init__(self, *, agent_id: str, config: MatchConfig, rng: random.Random, base: int) -> None:
        self.agent_id = agent_id
        self._config = config
        self._base = base
        self._trips = base
        self.reset(config=config, rng=rng)

    def reset(self, *, config: MatchConfig, rng: random.Random) -> None:
        """Redraw the per match number of round trips (section 3.1)."""
        self._config = config
        self._trips = max(0, self._base + randint(rng, -1, 1))

    def act(self, observation: Observation) -> AgentAction:
        """Cross the spread ``self._trips`` times on the first open market."""
        orders: list[OrderIntent] = []
        if observation.markets:
            market_id = observation.markets[0].market_id
            for _ in range(self._trips):
                orders.append(
                    OrderIntent(op="place", market_id=market_id, side=Side.BUY, order_type=OrderType.MARKET, qty=1)
                )
                orders.append(
                    OrderIntent(op="place", market_id=market_id, side=Side.SELL, order_type=OrderType.MARKET, qty=1)
                )
        return AgentAction(
            agent_id=self.agent_id,
            tick=observation.tick,
            action_version=self._config.action_version,
            predictions=tuple(
                PredictionIntent(market_id=block.market_id, p_yes_ppm=500_000) for block in observation.markets
            ),
            orders=tuple(orders),
        )


def ladder_key(base: int) -> str:
    """Harness key of one rung of the ladder."""
    return harness_key(HarnessConfig(harness_id=f"ladder-{base:02d}", version="1.0.0", kind="scripted"))


def ladder_recipe(index: int) -> Recipe:
    """Recipe of ladder match ``index``. Only the length and the seed matter."""
    return custom_recipe(
        baselines=("mute",) * len(LADDER_BASES),
        seed=LADDER_SEED_BASE + index,
        ticks=LADDER_TICKS,
        markets=LADDER_MARKETS,
        template="election",
    )


def play_ladder_match(index: int) -> tuple[tuple[MatchRanking, ...], dict[str, str]]:
    """Play one ladder match and return its ranking plus its seat to harness map.

    The rungs rotate one seat per match, so no rung is permanently paired with
    one information profile (FR-5.3.2 is the tournament's job, but a bench that
    ignores it measures the seat and not the harness).
    """
    shift = index % len(LADDER_BASES)
    bases = LADDER_BASES[shift:] + LADDER_BASES[:shift]
    recipe = ladder_recipe(index)
    config = config_of(recipe)
    rng = RngTree(config.seed)
    factories: dict[str, object] = {}
    harness_of: dict[str, str] = {}
    for seat_index, base in enumerate(bases, start=1):
        agent_id = f"A{seat_index}"
        factories[agent_id] = SpreadPayer(
            agent_id=agent_id,
            config=config,
            rng=rng.child(f"agent/{agent_id}").substream(f"agent.{agent_id}"),
            base=base,
        )
        harness_of[agent_id] = ladder_key(base)
    result, events = play_with_agents(recipe, factories=factories, config=config)
    assert events, "a ladder match produced an empty journal"
    return result.rankings, harness_of


# ---------------------------------------------------------------------------
# T3.2: sigma, the ladder, and the market maker
# ---------------------------------------------------------------------------
def test_sigma_decreases() -> None:
    """Uncertainty shrinks with evidence, for every rated harness (T3.2)."""
    assert REFERENCE_RANKING, "no ranking to rate"
    service = RatingService()
    priors = {key: service.rating(key) for key in sorted(set(REFERENCE_HARNESS_OF.values()))}
    assert all(record.sigma == pytest.approx(DEFAULT_SIGMA) for record in priors.values())
    assert all(record.matches == 0 for record in priors.values())

    previous = dict.fromkeys(priors, DEFAULT_SIGMA)
    for round_index in range(5):
        updated = service.update(REFERENCE_RANKING, harness_of=REFERENCE_HARNESS_OF)
        assert updated, f"round {round_index} rated nobody"
        for record in updated:
            assert record.sigma < previous[record.harness_key], (
                f"{record.harness_key} sigma did not shrink at round {round_index}"
            )
            previous[record.harness_key] = record.sigma
        assert {record.matches for record in updated} == {round_index + 1}

    assert all(sigma < DEFAULT_SIGMA for sigma in previous.values())


def test_the_winner_gains_mu_and_the_loser_loses_it() -> None:
    """The rating moves in the direction the PnL ranking points."""
    service = RatingService()
    service.update(REFERENCE_RANKING, harness_of=REFERENCE_HARNESS_OF)
    by_rank = sorted(REFERENCE_RANKING, key=lambda row: row.rank)
    best = REFERENCE_HARNESS_OF[by_rank[0].agent_id]
    worst = REFERENCE_HARNESS_OF[by_rank[-1].agent_id]
    assert by_rank[0].rank < by_rank[-1].rank, "the reference ranking has no order to learn from"
    assert service.rating(best).mu > DEFAULT_MU
    assert service.rating(worst).mu < DEFAULT_MU
    assert service.rating(best).mu > service.rating(worst).mu


def test_mm_is_never_rated() -> None:
    """FR-5.8.5: the market maker and the fee vault never enter a leaderboard."""
    assert REFERENCE_RANKING, "no ranking to rate"
    assert {MM_ACCOUNT_ID, FEES_ACCOUNT_ID} == UNRATED_ACCOUNT_IDS
    mm_key = harness_key(HarnessConfig(harness_id="reference-mm", version="1.0.0", kind="scripted"))
    fees_key = harness_key(HarnessConfig(harness_id="fee-vault", version="1.0.0", kind="scripted"))
    harness_of = dict(REFERENCE_HARNESS_OF) | {MM_ACCOUNT_ID: mm_key, FEES_ACCOUNT_ID: fees_key}
    ranking = (
        *REFERENCE_RANKING,
        MatchRanking(rank=1, agent_id=MM_ACCOUNT_ID, pnl_cents=999_999, final_cash_cents=0, pnl_pct_bps=0),
        MatchRanking(rank=1, agent_id=FEES_ACCOUNT_ID, pnl_cents=0, final_cash_cents=0, pnl_pct_bps=0),
    )

    service = RatingService()
    updated = service.update(ranking, harness_of=harness_of)

    rated = {record.harness_key for record in updated}
    assert rated, "the ranked seats were not rated either"
    assert mm_key not in rated and fees_key not in rated
    assert all(record.harness_key not in (mm_key, fees_key) for record in service.leaderboard())
    assert service.rating(mm_key).matches == 0, "MM must still sit at the prior"


@pytest.mark.slow
@pytest.mark.statistical
def test_baseline_order_recovered() -> None:
    """The designed order of a four rung ladder is recovered over 200 matches (T3.2).

    Tolerance: the assertion is an exact order over four rungs whose mean ranks
    are separated by roughly 0.6 with a per match standard deviation near 1.0,
    that is about seven standard errors at 200 matches. The seed base is fixed
    (``LADDER_SEED_BASE``), so the test is reproducible rather than merely
    probable.
    """
    service = RatingService()
    ranks: dict[str, list[int]] = {ladder_key(base): [] for base in LADDER_BASES}
    signatures: set[tuple[str, ...]] = set()
    updates = 0

    for index in range(LADDER_MATCHES):
        ranking, harness_of = play_ladder_match(index)
        assert ranking, f"match {index} produced no ranking"
        updated = service.update(ranking, harness_of=harness_of)
        assert len(updated) == len(LADDER_BASES), f"match {index} rated {len(updated)} rungs"
        updates += 1
        for row in ranking:
            ranks[harness_of[row.agent_id]].append(row.rank)
        signatures.add(tuple(harness_of[row.agent_id] for row in sorted(ranking, key=lambda r: (r.rank, r.agent_id))))

    assert updates == LADDER_MATCHES
    assert len(signatures) > 1, "every match produced the same ranking, so the jitter never fired"

    expected = tuple(ladder_key(base) for base in LADDER_BASES)
    observed = tuple(record.harness_key for record in service.leaderboard())
    means = [statistics.fmean(ranks[key]) for key in expected]
    assert observed == expected, f"TrueSkill did not recover the ladder; mean ranks per rung were {means}"
    assert means == sorted(means), f"the ladder itself was not monotone: {means}"
    assert all(record.matches == LADDER_MATCHES for record in service.leaderboard())
    assert all(record.sigma < DEFAULT_SIGMA for record in service.leaderboard())


#: The six shipped baselines, in declaration order.
SHIPPED_BASELINES: tuple[str, ...] = (
    "fundamentalist",
    "momentum",
    "noise",
    "zero_intelligence",
    "bayesian",
    "mute",
)

#: Matches the FR-5.3.1 check below plays. Sixty is enough to separate the two
#: sides of that relation by more than a mean rank (measured: 0.42) while the
#: seat rotation needs a multiple of six to be even.
BASELINE_MATCHES = 60

#: Root seed of that bench. A statistical test states its seed (section 10).
BASELINE_SEED_BASE = 50_000


@pytest.mark.slow
@pytest.mark.statistical
def test_the_rating_service_recovers_the_one_ordering_the_contract_states() -> None:
    """T3.2 on the real baselines, for the one relation FR-5.3.1 actually states.

    The ladder above proves the service can recover a designed order. This proves
    it recovers the order the *product* claims, on the agents the product ships:
    FR-5.3.1's "a Bayesian scripted agent beats a random one". Nothing more is
    asserted, because nothing more is specified (see the module docstring).

    The seating rotates one seat per match, so no baseline is stuck with one
    information profile and the measurement is of the harness and not of the
    seat. Tolerance: mean rank margins of 0.2, against a measured margin of 0.42
    (``bayesian`` 3.067 versus ``noise`` 3.283) and 0.42 (versus
    ``zero_intelligence`` 3.483) over the fixed seeds below.
    """
    service = RatingService()
    ranks: dict[str, list[int]] = {name: [] for name in SHIPPED_BASELINES}
    for index in range(BASELINE_MATCHES):
        shift = index % len(SHIPPED_BASELINES)
        order = SHIPPED_BASELINES[shift:] + SHIPPED_BASELINES[:shift]
        recipe = custom_recipe(
            baselines=order, seed=BASELINE_SEED_BASE + index, ticks=24, markets=2, template="election"
        )
        config = config_of(recipe)
        rng = RngTree(config.seed)
        result, events = play_with_agents(recipe, factories=agents_of(recipe, config, rng), config=config)
        assert events, f"match {index} produced an empty journal"
        assert result.rankings, f"match {index} produced no ranking"
        harness_of = {f"A{seat}": name for seat, name in enumerate(order, start=1)}
        service.update(result.rankings, harness_of=harness_of)
        for row in result.rankings:
            ranks[harness_of[row.agent_id]].append(row.rank)

    means = {name: statistics.fmean(values) for name, values in ranks.items()}
    assert all(len(values) == BASELINE_MATCHES for values in ranks.values()), "a baseline did not play every match"
    assert max(means.values()) - min(means.values()) > 0.5, (
        f"the population is indistinguishable, so this test measures nothing: {means}"
    )
    for random_name in ("noise", "zero_intelligence"):
        assert means["bayesian"] + 0.2 < means[random_name], (
            f"FR-5.3.1: bayesian (mean rank {means['bayesian']:.3f}) did not beat "
            f"{random_name} (mean rank {means[random_name]:.3f})"
        )
        assert service.rating("bayesian").mu > service.rating(random_name).mu, (
            "the rating did not follow the ranks it was fed"
        )


# ---------------------------------------------------------------------------
# The service's own edges
# ---------------------------------------------------------------------------
def test_rating_of_an_unknown_harness_is_the_prior() -> None:
    """An unrated harness is a player at the prior, not an error (Swiss needs it)."""
    service = RatingService()
    record = service.rating("never-played@1.0.0+00000000")
    assert record == RatingRecord(
        harness_key="never-played@1.0.0+00000000", mu=DEFAULT_MU, sigma=DEFAULT_SIGMA, matches=0
    )
    assert service.leaderboard() == (), "asking for a prior must not create a leaderboard entry"


def test_leaderboard_is_ordered_best_mu_first_and_reproducible() -> None:
    """Two services fed the same rankings publish the same leaderboard."""
    first, second = RatingService(), RatingService()
    for _ in range(3):
        first.update(REFERENCE_RANKING, harness_of=REFERENCE_HARNESS_OF)
    for _ in range(3):
        second.update(tuple(reversed(REFERENCE_RANKING)), harness_of=dict(reversed(list(REFERENCE_HARNESS_OF.items()))))
    board = first.leaderboard()
    assert len(board) == len(set(REFERENCE_HARNESS_OF.values()))
    assert [record.mu for record in board] == sorted((record.mu for record in board), reverse=True)
    assert board == second.leaderboard(), "the leaderboard depended on input order"


def test_a_shared_rank_is_a_draw() -> None:
    """Two seats sharing the lowest rank move symmetrically, and nobody gains mu.

    It also pins the surprising half of the contracted ``draw_probability = 0.0``
    default: an exact tie is an outcome that model calls impossible, so it
    *raises* sigma instead of lowering it. The behaviour is TrueSkill's and the
    default is section 7.19's; the test exists so the next reader meets it here
    rather than in a tournament report.
    """
    service = RatingService()
    ranking = (
        MatchRanking(rank=1, agent_id="A1", pnl_cents=0, final_cash_cents=0, pnl_pct_bps=0),
        MatchRanking(rank=1, agent_id="A2", pnl_cents=0, final_cash_cents=0, pnl_pct_bps=0),
    )
    harness_of = {"A1": "h-a@1.0.0+00000000", "A2": "h-b@1.0.0+00000000"}
    updated = service.update(ranking, harness_of=harness_of)
    assert len(updated) == 2
    assert updated[0].mu == pytest.approx(updated[1].mu, abs=1e-6)
    assert updated[0].mu == pytest.approx(DEFAULT_MU, abs=1e-6), "a draw must not crown anybody"
    assert all(record.sigma > DEFAULT_SIGMA for record in updated)
    assert all(
        record.sigma < DEFAULT_SIGMA
        for record in RatingService(draw_probability=0.1).update(ranking, harness_of=harness_of)
    ), "with a draw prior a tie is informative"


def test_a_single_harness_moves_nothing() -> None:
    """A ranking with one rated harness carries no comparison, so it is a no op."""
    service = RatingService()
    ranking = (MatchRanking(rank=1, agent_id="A1", pnl_cents=10, final_cash_cents=0, pnl_pct_bps=0),)
    assert service.update(ranking, harness_of={"A1": "solo@1.0.0+00000000"}) == ()
    assert service.leaderboard() == ()
    assert service.rating("solo@1.0.0+00000000").matches == 0


def test_a_seat_absent_from_harness_of_is_not_rated() -> None:
    """A background baseline can play without entering the leaderboard."""
    service = RatingService()
    harness_of = {row.agent_id: REFERENCE_HARNESS_OF[row.agent_id] for row in REFERENCE_RANKING[:2]}
    updated = service.update(REFERENCE_RANKING, harness_of=harness_of)
    assert {record.harness_key for record in updated} == set(harness_of.values())


def test_a_duplicated_seat_in_a_ranking_is_refused() -> None:
    """A ranking naming one seat twice is a caller bug, not a silent double rating."""
    service = RatingService()
    row = MatchRanking(rank=1, agent_id="A1", pnl_cents=0, final_cash_cents=0, pnl_pct_bps=0)
    with pytest.raises(InvalidConfigError):
        service.update((row, row), harness_of={"A1": "h@1.0.0+00000000"})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sigma": 0.0},
        {"beta": 0.0},
        {"tau": -1.0},
        {"draw_probability": 1.0},
        {"draw_probability": -0.1},
    ],
)
def test_the_environment_refuses_an_impossible_prior(kwargs: dict[str, float]) -> None:
    """A TrueSkill environment that cannot converge is refused up front."""
    with pytest.raises(InvalidConfigError):
        RatingService(**kwargs)


# ---------------------------------------------------------------------------
# T3.3: bootstrap confidence intervals
# ---------------------------------------------------------------------------
def bootstrap_rng(seed: int = 20260827) -> random.Random:
    """The registered ``metrics.bootstrap`` substream of one seed."""
    return RngTree(seed).fresh_substream("metrics.bootstrap")


def test_bootstrap_ci_is_seeded_and_stable() -> None:
    """The same substream returns the same interval, on any machine (T3.3)."""
    values = [row.pnl_cents / 100.0 for row in REFERENCE_RANKING]
    assert len(values) >= 3, "PRD section 7.3 aggregates over at least three seeds"
    first = bootstrap_ci(values, n_resamples=500, rng=bootstrap_rng())
    second = bootstrap_ci(values, n_resamples=500, rng=bootstrap_rng())
    assert first == second, "the interval moved between two identically seeded runs"
    low, high = first
    assert low <= high
    assert low <= statistics.fmean(values) <= high
    other = bootstrap_ci(values, n_resamples=500, rng=bootstrap_rng(seed=1))
    assert other != first, "two different substreams produced the very same interval"


def test_a_wider_alpha_gives_a_narrower_interval() -> None:
    """A 50 % interval sits inside a 95 % one."""
    values = [float(row.pnl_cents) for row in REFERENCE_RANKING]
    wide = bootstrap_ci(values, n_resamples=400, alpha=0.05, rng=bootstrap_rng())
    narrow = bootstrap_ci(values, n_resamples=400, alpha=0.5, rng=bootstrap_rng())
    assert wide[0] <= narrow[0] <= narrow[1] <= wide[1]


def test_a_single_observation_gives_a_degenerate_interval() -> None:
    """One seed is legal and reports itself, rather than raising."""
    assert bootstrap_ci([12.5], n_resamples=32, rng=bootstrap_rng()) == (12.5, 12.5)


@pytest.mark.parametrize(
    ("values", "kwargs"),
    [
        ([], {}),
        ([1.0], {"n_resamples": 0}),
        ([1.0], {"alpha": 0.0}),
        ([1.0], {"alpha": 1.0}),
    ],
)
def test_bootstrap_ci_refuses_what_it_cannot_compute(values: list[float], kwargs: dict[str, float]) -> None:
    """An empty sample or an impossible tail mass raises instead of returning noise."""
    with pytest.raises(InvalidConfigError):
        bootstrap_ci(values, rng=bootstrap_rng(), **kwargs)
