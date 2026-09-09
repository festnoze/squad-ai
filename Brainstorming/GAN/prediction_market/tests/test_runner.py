"""E5: the bar loop, the projection, the metrics, the leaderboard, the run index and the two commands.

The acceptance vehicle is ``tests/fixtures/contract/journal.backtest.jsonl``, the two-agent journal the
contract ships, and it is used in the two ways it can honestly be used:

* **As bytes into the projection.** ``test_projection_of_the_contract_fixture`` reads the shipped file
  and asserts every number section 12 says a projection carries: the market's own Brier, each agent's
  Brier, ``skill(market_follower) == 0``, the realised PnL, the blocks, the horizon buckets and the
  reliability bins. Nothing is recomputed by the test that the contract does not state in prose.
* **As the target of a real run.** ``test_run_reproduces_the_contract_fixture`` runs the two scripted
  stubs the contract names (``follower(1000, 0)``, which trades nothing, and ``legacy(name=0)``, the
  contrarian, which does) over ``data/demo_v1`` on the fixture's window and seed, and asserts the run
  reproduces the fixture's identifiers and its scored payloads exactly: the two genome hashes, the
  market ids hash, the config hash, the per-bar prices, the forecasts, the settlement numbers and the
  equity series. ``test_the_run_reproduces_the_fixture_payload_for_payload`` then compares the **whole
  payload**, event by event, over every event type both journals can carry, so a single differing
  price, tradable set, intent, probability or category fails it.

Six things in the shipped fixture cannot be reproduced by a run of 2026-09-09, and each is a fact of
the contract rather than of this test (each is reported as a contract issue):

1. its ``dataset_hash`` is ``f60463ae...`` while the committed ``data/demo_v1`` hashes to
   ``9f91a13f...``, so its ``run_id`` names a dataset that no longer exists byte for byte;
2. it is a **pre-latency** journal (section 9.2 says so in as many words): its order is decided and
   filled in the same bar, while amendment C1 (16.2) fills it at the next bar, which for this market is
   the settling bar, so the correct journal now carries ``order_rejected(not_tradable)`` and no fill;
3. its fill reads ``price_source: "vwap"``, which ruling R113 abolished and R138 forbids a
   ``LiquidityModel`` from returning;
4. it carries ``hive_written`` and ``memory_written``, which A2 and A3 emit in wave 3; a wave-2 run
   passes ``memory=None`` and ``hive=None`` and emits neither (sections 10.3 and 12.11 say that is
   exactly what the gate run produces);
5. its ``observation_built.obs_sha256`` and ``bytes`` predate E1's observation shape;
6. its ``run_started.config`` payload predates amendment C1b's ``RunConfig`` fields, so its
   ``config_hash`` and therefore its ``run_id`` name a config shape that no longer exists;
   ``RUN_CONFIG_HASH`` is what the same run hashes to today (rulings R157 and R188).

Its ``market_listed``, ``forecast_recorded`` and ``order_placed`` payloads were completed at gate G2
with the fields ruling R164 promoted to required (the eight instrument fields of 17.1 on a binary, the
two nulls of a binary forecast, and ``decided_at_ms``, which in this pre-latency journal is the bar the
order filled on). Nothing else in the bytes moved.

The second half of the file is amendment C1b's: one continuous instrument driven through the whole bar
loop (the listing, the fill, the cash event, the forced flat, the horizon resolution, the hive entries
and the projection's ``(instrument, week, horizon)`` cells). It is built on the declared records of
``pmx.types`` (``ContinuousInstrument``, ``MarketMeta.kind``, ``CashEvent``, ``HorizonForecast``), so
the continuous half runs over the real types and not over a stand-in for them.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest

from pmx import ENGINE_VERSION
from pmx.cli_run import main as cli_main
from pmx.engine.liquidity import make_liquidity
from pmx.engine.runner import Agent, ResolutionEvent, replay, run_backtest
from pmx.errors import DatasetHashMismatchError, InvalidConfigError, JournalError
from pmx.journal import (
    ActionReceived,
    ActionRejected,
    AgentRuined,
    BarClosed,
    BarOpened,
    EquityMarked,
    FeeCharged,
    Filled,
    ForecastRecorded,
    JournalEvent,
    MarketPriced,
    OrderPlaced,
    OrderRejected,
    ResearchSpent,
    RunStarted,
    Settled,
    SettlementApplied,
    canonical_json,
    canonical_sha256,
    journal_hash_of_file,
    read_journal,
    validate_event_dict,
)
from pmx.metrics.behavioral import contrarian_bp, signed_mean, turnover_ppm
from pmx.metrics.leaderboard import build as build_leaderboard
from pmx.metrics.leaderboard import seed_of_run_id
from pmx.metrics.performance import (
    abstention_ppm,
    drawdown_series_min_bp,
    equity_change_bp,
    fill_ratio_ppm,
    sd_bp,
    sharpe_milli,
)
from pmx.metrics.projection import RunHandle, project
from pmx.rng import RngTree
from pmx.scoring import (
    RANDOM_WALK_BRIER_MICRO,
    directional_brier_micro,
    pinball_micro,
    random_walk_resolution,
)
from pmx.store import CandidateRow, RunStore
from pmx.types import (
    PPM_ONE,
    Actions,
    Bar,
    CashEvent,
    ContinuousInstrument,
    Dataset,
    DatasetWindow,
    HiveView,
    HorizonForecast,
    Lesson,
    MarketAction,
    MarketMeta,
    MarketQuality,
    Observation,
    ResearchRequest,
    RunConfig,
    Session,
    SessionCalendar,
    market_set_hash,
    ppm_from_bp,
    round_half_up,
)

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "data" / "demo_v1"
FIXTURE = REPO / "tests" / "fixtures" / "contract" / "journal.backtest.jsonl"

#: The fixture's own window over ``demo-brexit-2016``: two daily bars, the second one settling.
BREXIT = "demo-brexit-2016"
T0_MS = 1_466_640_000_000
T1_MS = 1_466_812_800_000
SEED = 7

#: What the shipped fixture pins, and what a run of the same window must reproduce (section 12.1).
#: ``FIXTURE_CONFIG_HASH`` is the fixture's **own** recorded hash, over the pre-amendment ``RunConfig``
#: whose payload the fixture carries; ``RUN_CONFIG_HASH`` is what the same run hashes to today, because
#: ``RunConfig`` gained amendment C1b's ``horizons_bars`` and ``kinds`` and resolves the first to
#: ``default_horizons_bars`` before hashing (rulings R157 and R188). That is the sixth item of this
#: module's docstring list: the identity of a run moved with the dataclass, and both values are pinned
#: exactly rather than one of them being dropped.
FIXTURE_CONFIG_HASH = "f119e64ee0c29537a33765970f71212c01ada3f34b22609993efc9143272cd03"
RUN_CONFIG_HASH = "705b9c611c460b31f638275d4ca3ae1f5758951d54d7ae473b104d118e710a68"
FIXTURE_MARKET_IDS_HASH = "066120f77f7495af7498e0214cec29ee681c5cdd419372b6a13224cb5e293b25"
FIXTURE_GENOME_HASHES = {
    "contrarian": "504d43f154e28de7780cb4c70ba2a45dd85e6e7fe622c7d9f1bb6899c1a1c0d4",
    "market_follower": "afb292b9d744b0efb0bee0a0b15aa1378bc42ea7164092327d066d5cf8d5dbde",
}
MARKET_BRIER_TW_MICRO = 533_800
CONTRARIAN_BRIER_TW_MICRO = 73_800
LIFE_MEAN_PRICE_BP = 6_400


# --------------------------------------------------------------------------------------------------
# The scripted stubs the contract names (section 10.5). A1 ships the real families in wave 3; these are
# E5's own test vehicles and they implement exactly the two rows of the default roster this journal
# uses: ``follower(shrink_permille=1000, edge_min_bp=0)``, which ties the market's Brier and trades
# nothing, and ``legacy(name=0)``, the contrarian, which states ``PPM_ONE - ppm_from_bp(last)`` and
# takes the position the default rule of 10.5 sizes.
# --------------------------------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class StubGenome:
    """A genome in the shape ``run_started.roster`` journals (section 10.1)."""

    family: str
    genes: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "family": self.family,
            "genes": {name: value for name, value in sorted(self.genes)},
            "inner": None,
            "members": [],
            "prompt": None,
        }


def _default_target(prob_ppm: int, last_price_bp: int) -> int:
    """The default position rule of section 10.5: full size 20 points of edge from the price."""
    edge_ppm = prob_ppm - ppm_from_bp(last_price_bp)
    return max(-100, min(100, edge_ppm * 100 // 200_000))


@dataclass(slots=True)
class StubAgent:
    """One scripted agent: a belief rule, the default position rule, and no memory of its own."""

    agent_id: str
    family: str
    genome: StubGenome
    trades: bool = True
    needs_gateway: bool = False
    kind: str = "scripted"
    model: str | None = None
    knowledge_cutoff_ms: int | None = None
    observation: Observation | None = None
    learned: list[ResolutionEvent] = field(default_factory=list)
    resets: int = 0

    def belief_ppm(self, last_price_bp: int) -> int:
        if self.family == "legacy":
            return PPM_ONE - ppm_from_bp(last_price_bp)
        return ppm_from_bp(last_price_bp)

    def reset(self, *, rng: object, memory: object, config: RunConfig) -> None:
        assert isinstance(rng, random.Random)
        self.resets += 1

    def observe(self, obs: Observation) -> None:
        self.observation = obs

    def decide(self) -> Actions:
        obs = self.observation
        assert obs is not None
        actions: list[MarketAction] = []
        for view in obs.markets:
            prob_ppm = self.belief_ppm(view.last_price_bp)
            target = _default_target(prob_ppm, view.last_price_bp) if self.trades else 0
            if target == 0:
                actions.append(MarketAction(market_id=view.market_id, prob_ppm=prob_ppm, kind="hold"))
            else:
                actions.append(
                    MarketAction(
                        market_id=view.market_id,
                        prob_ppm=prob_ppm,
                        kind="target",
                        target_position=target,
                    )
                )
        return Actions(actions_version="actions.v2", markets=tuple(actions))

    def learn(self, event: ResolutionEvent) -> None:
        self.learned.append(event)

    def snapshot(self) -> dict[str, object]:
        return {"resets": self.resets}


def market_follower() -> StubAgent:
    """``follower(shrink_permille=1000, edge_min_bp=0)``: the market's own Brier, and no order ever."""
    return StubAgent(
        agent_id="market_follower",
        family="follower",
        genome=StubGenome(family="follower", genes=(("edge_min_bp", 0), ("shrink_permille", 1_000))),
        trades=False,
    )


def contrarian() -> StubAgent:
    """``legacy(name=0)``: the mirror of the market price, sized by the default rule of 10.5."""
    return StubAgent(
        agent_id="contrarian",
        family="legacy",
        genome=StubGenome(family="legacy", genes=(("name", 0),)),
        trades=True,
    )


@dataclass(slots=True)
class RecordingHive:
    """A hive that records the four writes of section 10.4 and returns an empty view.

    A3 ships ``RunHive`` in wave 3 and it is the one emitter of ``hive_written`` (section 9.3), so a
    wave-2 test cannot assert on the journal for the hive phase. What it can assert, and what phase 7
    of section 8.2 is about, is **which writes the runner drives and in what order**.
    """

    forecasts: list[tuple[str, str, int, int, int, int | None]] = field(default_factory=list)
    resolutions: list[tuple[str, int]] = field(default_factory=list)
    lessons: list[tuple[str, str, tuple[str, ...]]] = field(default_factory=list)
    reputations: list[tuple[str, str, int]] = field(default_factory=list)

    def view(
        self,
        *,
        now_ms: int,
        agent_id: str,
        market_ids: Sequence[str],
        limits: object,
        live_coop: bool,
    ) -> HiveView:
        return HiveView(
            lessons=(), reputations=(), resolutions=(), forecasts=(), prev_bar_forecasts=()
        )

    def write_forecast(
        self,
        *,
        agent_id: str,
        market_id: str,
        bar_ms: int,
        prob_ppm: int,
        resolved_at_ms: int,
        interval_min: int,
        horizon_bars: int = 0,
        quantiles_ticks: tuple[int, ...] | None = None,
        price_ref_ticks: int = 0,
        resolves_at_ms: int | None = None,
    ) -> object:
        self.forecasts.append(
            (agent_id, market_id, bar_ms, prob_ppm, horizon_bars, resolves_at_ms)
        )
        return None

    def write_resolution(
        self,
        *,
        market_id: str,
        outcome: int,
        life_mean_price_bp: int,
        resolved_at_ms: int,
        interval_min: int,
    ) -> object:
        self.resolutions.append((market_id, outcome))
        return None

    def write_lesson(
        self,
        *,
        agent_id: str,
        text: str,
        market_ids: tuple[str, ...],
        bar_ms: int,
        interval_min: int,
    ) -> object:
        self.lessons.append((agent_id, text, market_ids))
        return None

    def write_reputation(
        self,
        *,
        agent_id: str,
        category: str,
        bar_ms: int,
        interval_min: int,
        n: int,
        skill_micro: int,
        pnl_cents: int,
    ) -> object:
        self.reputations.append((agent_id, category, skill_micro))
        return None

    def snapshot(self) -> dict[str, object]:
        return {"n_forecasts": len(self.forecasts)}


@dataclass(slots=True)
class TalkativeAgent(StubAgent):
    """An agent that writes two lessons and a note on the first bar and nothing after it."""

    spoken: bool = False

    def decide(self) -> Actions:
        obs = self.observation
        assert obs is not None
        if self.spoken:
            return Actions(actions_version="actions.v2", markets=())
        self.spoken = True
        return Actions(
            actions_version="actions.v2",
            markets=(),
            notes="the market drifted all week",
            lessons=(
                Lesson(text="a late upset is not a late price", market_ids=(BREXIT,)),
                Lesson(text="volume before the close is thin", market_ids=()),
            ),
        )


@dataclass(slots=True)
class LimitAgent(StubAgent):
    """One resting limit order per open market per bar, priced where it can never cross.

    It exists for ruling R131's identity: section 8.4 gives ``target`` and ``abstain`` two no-op rules
    and a ``limit`` none, so every intent this agent sends produces exactly one execute-phase event.
    ``ttl_bars=1`` makes the order expire at the next bar's open phase, so the reservation never grows.
    """

    def decide(self) -> Actions:
        obs = self.observation
        assert obs is not None
        return Actions(
            actions_version="actions.v2",
            markets=tuple(
                MarketAction(
                    market_id=view.market_id,
                    prob_ppm=ppm_from_bp(view.last_price_bp),
                    kind="limit",
                    side="buy",
                    price_bp=1,
                    size=1,
                    ttl_bars=1,
                )
                for view in obs.markets
            ),
        )


def limit_agent() -> LimitAgent:
    """The limit-only roster of the R131 test."""
    return LimitAgent(
        agent_id="limiter",
        family="follower",
        genome=StubGenome(family="follower", genes=(("edge_min_bp", 0),)),
        trades=True,
    )


@dataclass(slots=True)
class NoisyAgent:
    """An agent whose reply breaks one rule of section 8.4 per item, to pin the refusal reasons."""

    agent_id: str = "noisy"
    family: str = "follower"
    genome: StubGenome = field(
        default_factory=lambda: StubGenome(family="follower", genes=(("edge_min_bp", 0),))
    )
    needs_gateway: bool = False
    kind: str = "scripted"
    model: str | None = None
    knowledge_cutoff_ms: int | None = None
    observation: Observation | None = None

    def reset(self, *, rng: object, memory: object, config: RunConfig) -> None:
        return None

    def observe(self, obs: Observation) -> None:
        self.observation = obs

    def decide(self) -> Actions:
        """Eight items on one market, ordered so that each one reaches its own reason.

        Section 8.4 refuses a second action on a market it already accepted, and the first occurrence
        wins, so the **invalid** items come first (an invalid item is never accepted and never claims
        the market), the one valid item next, and the duplicate last. An earlier ordering put the valid
        item first and every later item read ``duplicate``, which is what section 8.4 says and which
        hid the other seven reasons.
        """
        obs = self.observation
        assert obs is not None
        first = obs.markets[0].market_id
        return Actions(
            actions_version="actions.v2",
            markets=(
                MarketAction(market_id="demo-not-a-market", prob_ppm=500_000, kind="hold"),
                MarketAction(market_id=first, prob_ppm=PPM_ONE + 1, kind="hold"),
                MarketAction(market_id=first, prob_ppm=500_000, kind="sideways"),
                MarketAction(market_id=first, prob_ppm=500_000, kind="target"),
                MarketAction(
                    market_id=first,
                    prob_ppm=500_000,
                    kind="limit",
                    side="buy",
                    price_bp=0,
                    size=1,
                    ttl_bars=1,
                ),
                MarketAction(
                    market_id=first,
                    prob_ppm=500_000,
                    kind="limit",
                    side="buy",
                    price_bp=5_000,
                    size=1,
                    ttl_bars=0,
                ),
                MarketAction(market_id=first, prob_ppm=400_000, kind="hold"),
                MarketAction(market_id=first, prob_ppm=500_000, kind="hold"),
            ),
            research=ResearchRequest(kind="oracle", market_id=None),
            notes="n" * 501,
            lessons=tuple(Lesson(text="x" * 301) for _ in range(1)),
        )

    def learn(self, event: ResolutionEvent) -> None:
        return None

    def snapshot(self) -> dict[str, object]:
        return {}


# --------------------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def pack() -> Dataset:
    """The whole committed demo pack (12 markets)."""
    from pmx.data.loader import load_dataset

    return load_dataset(DEMO)


@pytest.fixture(scope="module")
def demo(pack: Dataset) -> Dataset:
    """The demo pack narrowed to ``demo-brexit-2016``, which is the market set the fixture ran on.

    A run's market set is the dataset's, filtered by fold (``pmx.engine.calendar``), so a run over one
    market is a ``Dataset`` over one market. ``Dataset`` is built for exactly that: it holds the
    manifest, the metas and the loaders, and opens no file of its own (section 7.2, D1).
    """
    return _narrow(pack, BREXIT)


def _narrow(pack: Dataset, *market_ids: str) -> Dataset:
    wanted = frozenset(market_ids)
    return Dataset(
        manifest=pack.manifest,
        metas=tuple(meta for meta in pack.metas if meta.id in wanted),
        path=pack.path,
        market_loader=pack.market_loader,
        news_loader=pack.news_loader,
        background_loader=pack.background_loader,
    )


def _config(
    *,
    market_ids: Sequence[str],
    seed: int = SEED,
    t0_ms: int | None = T0_MS,
    t1_ms: int | None = T1_MS,
    bankroll_cents: int = 100_000,
    ruin_floor_cents: int = 1_000,
) -> RunConfig:
    return RunConfig(
        seed=seed,
        t0_ms=t0_ms,
        t1_ms=t1_ms,
        bankroll_cents=bankroll_cents,
        ruin_floor_cents=ruin_floor_cents,
        market_ids_hash=market_set_hash(market_ids),
    )


def _run(
    demo: Dataset,
    tmp_path: Path,
    *,
    roster: Sequence[Agent] | None = None,
    config: RunConfig | None = None,
    dump_observations: bool = False,
) -> RunHandle:
    agents = list(roster) if roster is not None else [contrarian(), market_follower()]
    run_config = config if config is not None else _config(market_ids=[BREXIT])
    return run_backtest(
        demo,
        agents,
        run_config,
        tree=RngTree(run_config.seed),
        journal_dir=tmp_path,
        liquidity=make_liquidity(run_config),
        dump_observations=dump_observations,
    )


def _fixture_events() -> tuple[JournalEvent, ...]:
    return read_journal(FIXTURE, validate=True)


#: A journal this size or smaller is validated event by event on every read.
#: ``pmx.journal.validate_event_dict`` costs about 27 ms an event (a 29-branch ``oneOf`` with
#: ``unevaluatedProperties: false``), so the two-bar demo journal validates in a second while the demo
#: pack's 15 000 events take seven minutes and the real dataset's journal would take hours. Reported as
#: a contract issue against ``pmx.journal``.
VALIDATE_MAX_EVENTS = 200


def _read(path: Path) -> tuple[JournalEvent, ...]:
    """A journal's events, validated in full when it is small enough to afford it.

    A journal too big for that is asserted against the schema once, at complete type coverage, by
    :func:`test_the_journal_of_a_run_validates_against_the_v2_schema`; every other test over a
    whole-pack run reads the same bytes without paying for the validator again.
    """
    events = read_journal(path, validate=False)
    if len(events) <= VALIDATE_MAX_EVENTS:
        return read_journal(path, validate=True)
    return events


def _of[E: JournalEvent](events: Sequence[JournalEvent], kind: type[E]) -> list[E]:
    """Every event of one class, typed as that class, so a test reads a payload field directly."""
    return [event for event in events if isinstance(event, kind)]


# --------------------------------------------------------------------------------------------------
# The shipped fixture, as bytes into the projection
# --------------------------------------------------------------------------------------------------
def test_the_contract_fixture_still_says_what_this_package_was_built_against() -> None:
    """The three identifiers this file pins are the fixture's own, read from the shipped bytes."""
    events = _fixture_events()
    started = events[0]
    assert isinstance(started, RunStarted)
    assert started.config_hash == FIXTURE_CONFIG_HASH
    assert started.config["market_ids_hash"] == FIXTURE_MARKET_IDS_HASH
    assert {
        str(row["agent_id"]): str(row["genome_hash"]) for row in started.roster
    } == FIXTURE_GENOME_HASHES
    settled = _of(events, Settled)
    assert len(settled) == 1
    assert isinstance(settled[0], Settled)
    assert settled[0].market_brier_tw_micro == MARKET_BRIER_TW_MICRO
    assert settled[0].life_mean_price_bp == LIFE_MEAN_PRICE_BP


def test_projection_of_the_contract_fixture() -> None:
    """Every number of section 12 over the contract's own journal bytes."""
    projection = project(_fixture_events())
    assert projection.run_id == "r-f60463ae-7-f119e64e"
    assert projection.interval_min == 1_440
    assert projection.liquidity == "historical"
    assert projection.liquidity_params_hash == ""
    assert [row.agent_id for row in projection.agents] == ["contrarian", "market_follower"]
    assert [row.market_id for row in projection.markets] == [BREXIT]

    market = projection.markets[0]
    assert market.outcome == 1
    assert market.n_bars == 2
    assert market.market_brier_tw_micro == MARKET_BRIER_TW_MICRO
    assert market.life_mean_price_bp == LIFE_MEAN_PRICE_BP
    assert market.fold == "train"
    assert market.hardness_tags == ("upset",)
    assert market.block_key == "w2016-25"

    follower = projection.agent("market_follower")
    assert follower.n_markets == 1
    assert follower.brier_tw_micro == MARKET_BRIER_TW_MICRO
    assert follower.skill.point == 0, "the market_follower identity: it ties the market exactly"
    assert follower.n_markets_traded == 0
    assert follower.fill_ratio_ppm == 0
    assert follower.pnl_cents == 0
    assert follower.descriptors.turnover_ppm == 0
    assert follower.descriptors.contrarian_bp == 0
    assert follower.abstention_ppm == PPM_ONE

    row = projection.rows_of("contrarian")[0]
    assert row.n_forecast_bars == 2
    assert row.agent_brier_tw_micro == CONTRARIAN_BRIER_TW_MICRO
    assert row.market_brier_tw_micro == MARKET_BRIER_TW_MICRO
    assert row.skill_micro == MARKET_BRIER_TW_MICRO - CONTRARIAN_BRIER_TW_MICRO
    assert row.realised_pnl_cents == 7_000
    assert row.n_fills == 1
    assert row.traded is True
    assert row.fees_cents == 0
    assert row.unit_key == BREXIT
    assert row.kind == "binary"
    assert row.abstained_bars == 0, "it held the position it opened on bar one"

    agent = projection.agent("contrarian")
    assert agent.pnl_cents == 7_000
    assert agent.return_bp == 700
    assert agent.turnover_cents == 3_000
    assert agent.fill_ratio_ppm == PPM_ONE
    assert agent.n_markets_traded == 1
    assert agent.max_drawdown_bp == 0
    assert agent.descriptors.holding_horizon_bars == 1
    assert agent.descriptors.category_coverage_ppm == PPM_ONE
    assert [bucket.bucket for bucket in agent.horizons] == ["30d", "7d", "2d", "0d"]
    assert [bucket.n_bars for bucket in agent.horizons] == [0, 0, 0, 2]
    assert agent.horizons[3].brier_tw_micro == CONTRARIAN_BRIER_TW_MICRO
    assert agent.horizons[3].skill_micro == MARKET_BRIER_TW_MICRO - CONTRARIAN_BRIER_TW_MICRO
    bins = {row.bin: row for row in agent.calibration}
    assert bins[7].n == 2 and bins[7].n_yes == 2
    assert all(row.category == "politics" and row.horizon_bucket == "0d" for row in agent.calibration)


def test_projection_refuses_a_journal_it_cannot_score() -> None:
    """A projection starts at ``run_started`` and says so rather than returning an empty result."""
    with pytest.raises(JournalError):
        project([])


# --------------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------------
def test_run_reproduces_the_contract_fixture(demo: Dataset, tmp_path: Path) -> None:
    """The two stubs over the fixture's window reproduce every identifier and every scored payload.

    What differs from the shipped bytes is the five items this module's docstring lists, and the two
    that touch this test are the decision latency (the order is rejected at the settling bar instead of
    filling at the deciding one) and the absent memory and hive events.
    """
    handle = _run(demo, tmp_path)
    assert handle.config_hash == RUN_CONFIG_HASH
    assert handle.run_id == f"r-{demo.manifest.dataset_hash[:8]}-{SEED}-{RUN_CONFIG_HASH[:8]}"
    assert handle.n_bars == 2
    events = _read(handle.journal_path)
    assert len(events) == handle.n_events

    started = events[0]
    assert isinstance(started, RunStarted)
    assert started.t0_ms == T0_MS
    assert started.t1_ms == T1_MS
    assert started.market_ids == (BREXIT,)
    assert started.interval_min == 1_440
    assert started.engine_version == ENGINE_VERSION
    assert {
        str(row["agent_id"]): str(row["genome_hash"]) for row in started.roster
    } == FIXTURE_GENOME_HASHES

    priced = [event for event in _of(events, MarketPriced)]
    assert [(event.bar_ms, event.close_bp, event.last_close_bp) for event in priced] == [
        (T0_MS, 3_000, 2_400),
        (T0_MS + 86_400_000, 9_800, 3_000),
    ]

    forecasts = {
        (event.agent_id, event.bar_ms): (event.prob_ppm, event.carried)
        for event in _of(events, ForecastRecorded)
    }
    assert forecasts[("contrarian", T0_MS)] == (760_000, False)
    assert forecasts[("contrarian", T0_MS + 86_400_000)] == (700_000, False)
    assert forecasts[("market_follower", T0_MS)] == (240_000, False)
    assert forecasts[("market_follower", T0_MS + 86_400_000)] == (300_000, False)

    settled = _of(events, Settled)
    assert len(settled) == 1
    assert settled[0].outcome == 1
    assert settled[0].payout_bp == 10_000
    assert settled[0].n_bars == 2
    assert settled[0].market_brier_tw_micro == MARKET_BRIER_TW_MICRO
    assert settled[0].life_mean_price_bp == LIFE_MEAN_PRICE_BP

    applied = {event.agent_id: event for event in _of(events, SettlementApplied)}
    assert applied["contrarian"].agent_brier_tw_micro == CONTRARIAN_BRIER_TW_MICRO
    assert applied["market_follower"].agent_brier_tw_micro == MARKET_BRIER_TW_MICRO
    assert applied["contrarian"].n_forecast_bars == 2
    assert applied["market_follower"].n_forecast_bars == 2

    # The latency rule: the contrarian's target is decided on bar one and has nowhere to fill, because
    # bar two is the settling bar and is never tradable (sections 5.3 and 16.2).
    rejected = _of(events, OrderRejected)
    assert len(rejected) == 1
    assert isinstance(rejected[0], OrderRejected)
    assert rejected[0].reason == "not_tradable"
    assert rejected[0].bar_ms == T0_MS + 86_400_000
    assert _of(events, Filled) == []
    assert _of(events, OrderPlaced) == []
    assert _of(events, FeeCharged) == []

    equity = {
        (event.agent_id, event.bar_ms): event.equity_cents for event in _of(events, EquityMarked)
    }
    assert equity[("contrarian", T0_MS)] == 100_000
    assert equity[("market_follower", T1_MS - 86_400_000)] == 100_000
    assert [event.n_events for event in _of(events, BarClosed)] == [12, 15]
    assert _of(events, AgentRuined) == []


#: The event types a wave-2 run over the fixture's window reproduces **payload for payload**. The five
#: the module docstring lists are excluded and each for a stated reason: ``observation_built`` carries
#: hand-written ``bytes`` and ``obs_sha256`` from before E1's shape; ``order_placed``, ``filled`` and
#: ``fee_charged`` belong to a pre-latency journal, where the order filled on the bar it was decided at
#: (16.2 fills it at the next, which here is the settling bar, so the run writes
#: ``order_rejected(not_tradable)`` and no fill); ``hive_written`` and ``memory_written`` are A2's and
#: A3's, which a wave-2 run passing ``memory=None`` and ``hive=None`` emits none of; ``equity_marked``
#: and the money half of ``settlement_applied`` move with that absent fill; and ``run_started`` and
#: ``run_ended`` carry the fixture's stale ``dataset_hash`` and its own event count.
REPRODUCED_TYPES = ("bar_opened", "market_listed", "market_priced", "action_received",
                    "forecast_recorded")


def _payloads(events: Sequence[JournalEvent], event_type: str) -> list[dict[str, object]]:
    """Every event of one type as its journal mapping, minus the two fields a run assigns itself."""
    rows: list[dict[str, object]] = []
    for event in events:
        row = event.to_dict()
        if row["type"] != event_type:
            continue
        row.pop("seq")
        row.pop("run_id")
        rows.append(row)
    return rows


def test_the_run_reproduces_the_fixture_payload_for_payload(demo: Dataset, tmp_path: Path) -> None:
    """The acceptance test: every event the contract's own journal and a wave-2 run both carry.

    This is the strong half of the reproduction. ``test_run_reproduces_the_contract_fixture`` asserts
    the identifiers and the scored numbers field by field; this one asserts the whole payload, event by
    event, for the five types a latency-correct run of 2026-09-08 can write, and it would fail on a
    single differing price, tradable set, intent, probability or category.
    """
    handle = _run(demo, tmp_path)
    produced = read_journal(handle.journal_path, validate=True)
    shipped = _fixture_events()
    for event_type in REPRODUCED_TYPES:
        expected = _payloads(shipped, event_type)
        assert expected, f"the fixture carries no {event_type}: the comparison would be vacuous"
        assert _payloads(produced, event_type) == expected, event_type

    # And the settle phase's own numbers, which are the runner's (section 9.3) and which no fill moves.
    settled = _payloads(produced, "settled")
    assert settled == _payloads(shipped, "settled")
    scored = {
        str(row["agent_id"]): (row["agent_brier_tw_micro"], row["n_forecast_bars"])
        for row in _payloads(produced, "settlement_applied")
    }
    assert scored == {
        str(row["agent_id"]): (row["agent_brier_tw_micro"], row["n_forecast_bars"])
        for row in _payloads(shipped, "settlement_applied")
    }


def test_the_journal_of_a_run_validates_against_the_v2_schema(
    pack: Dataset, demo: Dataset, tmp_path: Path
) -> None:
    """Section 9.2: every event a wave-2 run writes validates, and all eighteen types are covered.

    The two-bar journal is validated in full. The whole-pack journals are validated **one event per
    type**, over three rosters chosen so that the union is every type a wave-2 backtest can write: the
    default roster fills and settles, the limit-only agent rests and expires, and the low-bankroll run
    ruins. That is complete type coverage for the cost reason :func:`_read` states.
    """
    small = _run(demo, tmp_path / "small")
    assert read_journal(small.journal_path, validate=True), "the small journal validates in full"

    ids = _all_ids(pack)
    runs = (
        _run(pack, tmp_path / "fills", config=_config(market_ids=ids, t0_ms=None, t1_ms=None)),
        _run(
            pack,
            tmp_path / "rests",
            roster=[limit_agent()],
            config=_config(market_ids=ids, t0_ms=None, t1_ms=None),
        ),
        _run(
            pack,
            tmp_path / "ruins",
            config=_config(
                market_ids=ids, t0_ms=None, t1_ms=None, bankroll_cents=4_000, ruin_floor_cents=3_500
            ),
        ),
    )
    by_type: dict[str, dict[str, Any]] = {}
    for handle in runs:
        for row in _raw_events(handle.journal_path):
            by_type.setdefault(str(row["type"]), row)
    assert sorted(by_type) == [
        "action_received",
        "agent_ruined",
        "bar_closed",
        "bar_opened",
        "equity_marked",
        "fee_charged",
        "filled",
        "forecast_recorded",
        "market_listed",
        "market_priced",
        "observation_built",
        "order_expired",
        "order_placed",
        "order_rejected",
        "run_ended",
        "run_started",
        "settled",
        "settlement_applied",
    ]
    for row in by_type.values():
        validate_event_dict(row)


def test_the_phase_order_and_the_bar_counts_hold(demo: Dataset, tmp_path: Path) -> None:
    """Section 9.1's ordering over a real run: dense seq, non-decreasing bars, forward phases."""
    handle = _run(demo, tmp_path)
    events = _read(handle.journal_path)
    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    assert events[-1].TYPE == "run_ended"
    assert events[-1].bar_ms == T1_MS
    bars = [event.bar_ms for event in _of(events, BarOpened)]
    assert bars == sorted(bars)
    counts = [event.n_events for event in _of(events, BarClosed)]
    assert sum(counts) + 2 == len(events), "every event belongs to a bar, plus run_started and run_ended"


def test_no_fill_lands_on_a_close_or_settling_bar(pack: Dataset, tmp_path: Path) -> None:
    """Ruling R9 over the whole demo pack: no fill at ``bar_of(close_at)`` or ``bar_of(resolved_at)``."""
    handle = _run(pack, tmp_path, config=_config(market_ids=_all_ids(pack), t0_ms=None, t1_ms=None))
    events = _read(handle.journal_path)
    forbidden = set()
    for meta in pack.metas:
        span = 86_400_000
        forbidden.add((meta.id, meta.close_at_ms // span * span))
        forbidden.add((meta.id, meta.resolved_at_ms // span * span))
    for event in _of(events, Filled):
        assert isinstance(event, Filled)
        assert (event.market_id, event.bar_ms) not in forbidden
    assert _of(events, Filled), "a run that fills nothing would pass this vacuously"


def test_every_queued_item_produces_exactly_one_execute_phase_event(
    pack: Dataset, tmp_path: Path
) -> None:
    """Ruling R131: the drain is driven over the queue's own market set, and nothing is lost in it.

    The roster is a limit-only agent on purpose. Section 8.4 makes a ``target`` whose
    ``target_position`` already equals the position, and an ``abstain`` on a flat book, produce **no
    order and no event**, so counting every non-``hold`` intent of a ``target`` agent counts intents the
    contract says are no-ops. A resting limit order has no such rule: every one of them is either an
    ``order_placed`` or an ``order_rejected``, which is what makes the identity of R131 checkable.
    """
    config = _config(market_ids=_all_ids(pack), t0_ms=None, t1_ms=None)
    handle = _run(pack, tmp_path, roster=[limit_agent()], config=config)
    events = _read(handle.journal_path)
    queued = 0
    for event in _of(events, ActionReceived):
        queued += sum(1 for intent in event.intents if intent["kind"] != "hold")
    placed = _of(events, OrderPlaced)
    rejected = _of(events, OrderRejected)
    dropped = _dropped_with_no_execution_bar(events)
    assert queued > 0
    assert dropped > 0, "the demo pack settles markets inside the run: some items lose their bar"
    assert len(placed) + len(rejected) + dropped == queued

    # The half of R131 the bar slice cannot express: a market that settled at the bar the intent was
    # decided at is in none of the slice's four tuples at the execution bar, and is still owed its
    # rejection. Every such rejection lands on a bar where the market is not open.
    open_at = {
        event.bar_ms: frozenset(event.open_market_ids)
        for event in _of(events, BarOpened)
        if isinstance(event, BarOpened)
    }
    settled_out = [
        event
        for event in rejected
        if isinstance(event, OrderRejected)
        and event.market_id not in open_at.get(event.bar_ms, frozenset())
    ]
    assert settled_out, "no drained item survived its market: R131 would be untested"
    assert {event.reason for event in settled_out} == {"not_tradable"}


def _dropped_with_no_execution_bar(events: Sequence[JournalEvent]) -> int:
    """Items whose execution bar is not a bar of the run at all (section 16.2's last row).

    Two cases, and the journal tells them apart with ``bar_opened`` alone. The run's last bar is one:
    there is no later bar to drain it, and section 16.2 states the drop as the rule. The other is a
    **gap** in the run calendar: the demo pack's markets settle years apart, so a grid point where no
    market is open is not a bar of the run (section 17.2, ruling R149), and an item decided the bar
    before it has nowhere to go either.

    Section 17.2 says such an item is owed an ``order_rejected(not_tradable)`` at the run's last bar and
    today it is silently dropped, because ``Execution`` is given neither the run's resolved window nor
    E1's ``Calendar`` and ``RunConfig.t1_ms`` is legally ``None``. That is reported as a contract issue
    against ``pmx.engine.execution``; this helper counts exactly the items it covers, so the identity
    below stays an equality and would break the day one more item went missing.
    """
    span = 86_400_000
    run_bars = {event.bar_ms for event in _of(events, BarOpened)}
    dropped = 0
    for event in _of(events, ActionReceived):
        if event.bar_ms + span in run_bars:
            continue
        dropped += sum(1 for intent in event.intents if intent["kind"] != "hold")
    return dropped


def test_no_order_is_placed_from_a_decision_on_the_last_actionable_bar(
    pack: Dataset, tmp_path: Path
) -> None:
    """E5's own statement of section 16.2, read off ``decided_at_ms`` (rulings R111 and R192).

    The rule is "no ``order_placed`` carries a ``decided_at_ms`` equal to its instrument's last
    actionable bar or later", and its checkable form over the journal is the pair of facts that make it
    true: every placed order was decided at the bar **before** the one it landed on, and it landed on a
    bar its own market was **tradable** at. An order decided on a last actionable bar would land on a
    bar the market is not tradable at, which is the second assertion.

    ``decided_at_ms`` is read from the raw JSON because ``pmx.journal.OrderPlaced`` does not carry it
    yet (ruling R129, gate G2) and ``from_dict`` drops the key on the way back in; the field is in the
    bytes, which is where the contract puts it.
    """
    span = 86_400_000
    handle = _run(pack, tmp_path, config=_config(market_ids=_all_ids(pack), t0_ms=None, t1_ms=None))
    events = _read(handle.journal_path)
    last_bar = handle.projection.t1_ms - span
    tradable_at = {
        event.bar_ms: frozenset(event.tradable_market_ids) for event in _of(events, BarOpened)
    }
    placed = _rows_of(_raw_events(handle.journal_path), "order_placed")
    assert placed, "a run that places nothing would pass this vacuously"
    for row in placed:
        assert int(row["bar_ms"]) <= last_bar
        assert int(row["decided_at_ms"]) == int(row["bar_ms"]) - span, "R192 on a dense grid"
        assert str(row["market_id"]) in tradable_at[int(row["bar_ms"])]
    for event in _of(events, OrderPlaced):
        assert event.bar_ms <= last_bar


def _all_ids(demo: Dataset) -> list[str]:
    return [meta.id for meta in demo.metas]


def test_forecast_bars_are_equal_across_the_roster(pack: Dataset, tmp_path: Path) -> None:
    """Section 8.2's rule: a market's scored bar set is the same for every agent of the roster."""
    handle = _run(pack, tmp_path, config=_config(market_ids=_all_ids(pack), t0_ms=None, t1_ms=None))
    events = _read(handle.journal_path)
    per_market: dict[str, set[int]] = {}
    for event in _of(events, SettlementApplied):
        assert isinstance(event, SettlementApplied)
        per_market.setdefault(event.market_id, set()).add(event.n_forecast_bars)
    assert per_market
    for market_id, counts in sorted(per_market.items()):
        assert len(counts) == 1, f"{market_id} scored two different bar sets"


def test_the_accounting_invariant_holds_over_the_journal_alone(pack: Dataset, tmp_path: Path) -> None:
    """Section 8.9 for every agent at run end, computed from the journal and from nothing else."""
    config = _config(market_ids=_all_ids(pack), t0_ms=None, t1_ms=None)
    handle = _run(pack, tmp_path, config=config)
    events = _read(handle.journal_path)
    cash: dict[str, int] = {}
    for event in events:
        if isinstance(event, Filled):
            cash[event.agent_id] = cash.get(event.agent_id, 0) + event.cash_delta_cents
        elif isinstance(event, FeeCharged):
            cash[event.agent_id] = cash.get(event.agent_id, 0) - event.fee_cents
        elif isinstance(event, SettlementApplied):
            cash[event.agent_id] = cash.get(event.agent_id, 0) + event.cash_delta_cents
    final = {
        event.agent_id: event
        for event in _of(events, EquityMarked)
        if event.bar_ms == max(row.bar_ms for row in _of(events, EquityMarked))
    }
    assert final
    for agent_id, marked in sorted(final.items()):
        assert isinstance(marked, EquityMarked)
        assert marked.cash_cents == config.bankroll_cents + cash.get(agent_id, 0)
        assert marked.reserved_cents == 0, "every market of the run has settled"
        assert marked.equity_cents == marked.cash_cents + marked.positions_value_cents
        assert marked.positions_value_cents == 0


def test_the_same_inputs_give_the_same_journal_over_fifty_seeds(demo: Dataset, tmp_path: Path) -> None:
    """AC-3's determinism claim: the journal hash is a function of the inputs, seed by seed.

    Fifty seeds, each run twice into two directories. A seed changes ``config_hash`` and therefore the
    run id, so the fifty hashes differ from each other; what the claim is about is that a hash is
    reproducible, and a run whose events depended on a clock or on ``set`` order would fail here.
    """
    hashes: set[str] = set()
    for seed in range(50):
        config = _config(market_ids=[BREXIT], seed=seed)
        first = _run(demo, tmp_path / f"a{seed}", config=config)
        second = _run(demo, tmp_path / f"b{seed}", config=config)
        assert first.journal_hash == second.journal_hash
        assert first.run_id == second.run_id
        hashes.add(first.journal_hash)
    assert len(hashes) == 50


def test_replay_rebuilds_results_json_byte_for_byte(demo: Dataset, tmp_path: Path) -> None:
    """Section 9.5: the projection is rebuilt from the journal alone and compared with the stored file."""
    handle = _run(demo, tmp_path)
    rebuilt = replay(handle.run_dir)
    stored = (handle.run_dir / "results.json").read_text(encoding="utf-8")
    assert stored == canonical_json(rebuilt.to_dict()) + "\n"
    assert rebuilt.to_dict() == handle.projection.to_dict()
    digest = (handle.run_dir / "journal.sha256").read_text(encoding="utf-8")
    assert digest == f"{handle.journal_hash}  journal.jsonl\n"


def test_replay_refuses_a_journal_from_another_engine(demo: Dataset, tmp_path: Path) -> None:
    """Section 13.2: a replay refuses a journal whose ``engine_version`` differs, naming both."""
    handle = _run(demo, tmp_path)
    path = handle.journal_path
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    lines[0] = lines[0].replace(f'"engine_version":"{ENGINE_VERSION}"', '"engine_version":"1.9.0"')
    with open(path, "w", encoding="utf-8", newline="\n") as handle_file:
        handle_file.writelines(lines)
    # A journal written by another engine carries its own digest; rewriting it here is what makes the
    # test about the engine check and not about the hash check, which fires first and is its own test.
    digest = journal_hash_of_file(path)
    with open(
        handle.run_dir / "journal.sha256",
        "w",
        encoding="utf-8",
        newline="\n",
    ) as digest_file:
        digest_file.write(f"{digest}  journal.jsonl\n")
    with pytest.raises(JournalError) as error:
        replay(handle.run_dir)
    assert "1.9.0" in str(error.value)


def test_the_manifest_carries_what_section_9_5_asks_for(demo: Dataset, tmp_path: Path) -> None:
    """Section 9.5's artefact list, over a real run directory."""
    handle = _run(demo, tmp_path, dump_observations=True)
    run_dir = handle.run_dir
    import json

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == handle.run_id
    assert manifest["kind"] == "backtest"
    assert manifest["dataset_hash"] == demo.manifest.dataset_hash
    assert manifest["journal_hash"] == handle.journal_hash
    assert manifest["memory_snapshots"] == {}
    assert manifest["hive_snapshot"] is None
    assert sorted(manifest["agent_snapshots"]) == ["contrarian", "market_follower"]
    assert manifest["config_hash"] == RUN_CONFIG_HASH
    dumped = sorted(path.name for path in (run_dir / "observations").iterdir())
    assert dumped == [
        f"{T0_MS}-contrarian.json",
        f"{T0_MS}-market_follower.json",
        f"{T0_MS + 86_400_000}-contrarian.json",
        f"{T0_MS + 86_400_000}-market_follower.json",
    ]


def test_the_runner_refuses_a_config_that_does_not_match_its_market_set(
    demo: Dataset, tmp_path: Path
) -> None:
    """Section 8.1: ``market_ids_hash`` is recomputed, and an empty or wrong value is refused."""
    with pytest.raises(InvalidConfigError):
        _run(demo, tmp_path, config=RunConfig(seed=SEED, t0_ms=T0_MS, t1_ms=T1_MS))
    wrong = _config(market_ids=["demo-trump-2016"])
    with pytest.raises(DatasetHashMismatchError):
        _run(demo, tmp_path, config=wrong)


def test_the_runner_refuses_a_liquidity_model_the_config_did_not_name(
    demo: Dataset, tmp_path: Path
) -> None:
    """Ruling R112: a journal may not claim a liquidity it did not run under."""

    class ForeignModel:
        model_id = "adversarial_mm"
        params_hash = ""

        def quote_bar(self, *args: object, **kwargs: object) -> tuple[object, ...]:
            return ()

        def on_bar_end(self, observed_flow: object) -> None:
            return None

    config = _config(market_ids=[BREXIT])
    with pytest.raises(InvalidConfigError):
        run_backtest(
            demo,
            [contrarian()],
            config,
            tree=RngTree(config.seed),
            journal_dir=tmp_path,
            liquidity=ForeignModel(),  # type: ignore[arg-type]
        )


def test_every_refusal_reason_of_section_8_4_is_journaled(demo: Dataset, tmp_path: Path) -> None:
    """One reply that breaks eight rules produces eight refusals, each with its own reason."""
    handle = _run(demo, tmp_path, roster=[NoisyAgent()])
    events = _read(handle.journal_path)
    reasons = {
        event.reason
        for event in _of(events, ActionRejected)
        if isinstance(event, ActionRejected) and event.bar_ms == T0_MS
    }
    assert reasons == {
        "unknown_market",
        "duplicate",
        "bad_prob",
        "bad_kind",
        "missing_field",
        "bad_price",
        "bad_ttl",
        "notes_too_long",
        "lesson_too_long",
        "bad_research",
    }
    received = [event for event in _of(events, ActionReceived) if event.bar_ms == T0_MS]
    assert isinstance(received[0], ActionReceived)
    assert received[0].notes == ""
    assert received[0].n_lessons == 0
    assert len(received[0].intents) == 1, "the first occurrence of a market wins (section 8.4)"


def test_research_is_priced_granted_at_the_next_bar_and_journaled(demo: Dataset, tmp_path: Path) -> None:
    """Sections 8.1 and 8.4: a request costs its kind's units and its payload arrives one bar later."""

    @dataclass(slots=True)
    class Researcher(StubAgent):
        seen_grants: list[int] = field(default_factory=list)

        def decide(self) -> Actions:
            obs = self.observation
            assert obs is not None
            self.seen_grants.append(len(obs.research.granted))
            return Actions(
                actions_version="actions.v2",
                markets=(),
                research=ResearchRequest(kind="news", market_id=obs.markets[0].market_id),
            )

    agent = Researcher(
        agent_id="researcher",
        family="follower",
        genome=StubGenome(family="follower", genes=(("edge_min_bp", 0),)),
        trades=False,
    )
    handle = _run(demo, tmp_path, roster=[agent])
    events = _read(handle.journal_path)
    spent = [event for event in _of(events, ResearchSpent) if isinstance(event, ResearchSpent)]
    assert len(spent) == 2
    assert [event.units for event in spent] == [1, 1]
    assert [event.remaining for event in spent] == [9, 8]
    assert all(event.granted for event in spent)
    assert agent.seen_grants == [0, 1], "the payload of a request arrives at the next bar"


def test_a_ruined_agent_stops_deciding_and_keeps_being_scored(pack: Dataset, tmp_path: Path) -> None:
    """Sections 8.2 and 8.7: no observation, no decision, and every later bar still forecast-carried."""
    config = _config(
        market_ids=_all_ids(pack), t0_ms=None, t1_ms=None, bankroll_cents=4_000, ruin_floor_cents=3_500
    )
    handle = _run(pack, tmp_path, config=config)
    events = _read(handle.journal_path)
    ruined = _of(events, AgentRuined)
    assert ruined, "the bankroll and the floor of this run are chosen so that a ruin happens"
    victim = ruined[0].agent_id
    ruin_bar = ruined[0].bar_ms
    later = [
        event
        for event in _of(events, ActionReceived)
        if isinstance(event, ActionReceived) and event.agent_id == victim and event.bar_ms > ruin_bar
    ]
    assert later == [], "a ruined agent receives no further decide call"
    carried = [
        event
        for event in _of(events, ForecastRecorded)
        if isinstance(event, ForecastRecorded) and event.agent_id == victim and event.bar_ms > ruin_bar
    ]
    assert carried, "its forecasts keep being recorded"
    assert all(isinstance(event, ForecastRecorded) and event.carried for event in carried)


def test_the_hive_phase_writes_every_entry_of_section_8_2_in_its_order(
    demo: Dataset, tmp_path: Path
) -> None:
    """Phase 7 of section 8.2: forecasts, then resolutions, then reputations, then lessons and notes.

    The lesson and note entries were missing before this test: the runner wrote the agent's lessons to
    memory in ``decide`` and never handed them to the hive, so a lesson an agent stated was invisible
    to every other agent and the poisoning test of section 10.4 would have had nothing to rank.
    """
    hive = RecordingHive()
    agent = TalkativeAgent(
        agent_id="talker",
        family="follower",
        genome=StubGenome(family="follower", genes=(("edge_min_bp", 0),)),
        trades=False,
    )
    config = _config(market_ids=[BREXIT])
    run_backtest(
        demo,
        [agent],
        config,
        tree=RngTree(config.seed),
        journal_dir=tmp_path,
        liquidity=make_liquidity(config),
        hive=hive,
    )
    assert [row[2] for row in hive.forecasts] == [T0_MS, T0_MS + 86_400_000]
    assert [row[4] for row in hive.forecasts] == [0, 0], "a binary forecast has no horizon"
    assert hive.resolutions == [(BREXIT, 1)]
    assert [row[0] for row in hive.reputations] == ["talker"]
    assert hive.lessons == [
        ("talker", "a late upset is not a late price", (BREXIT,)),
        ("talker", "volume before the close is thin", ()),
        ("talker", "the market drifted all week", ()),
    ], "two lessons and one note, in submission order, the note last"


def test_the_hive_of_a_continuous_run_writes_one_entry_per_horizon(
    perp: Dataset, tmp_path: Path
) -> None:
    """Ruling R160: one ``forecast`` entry per ``(forecast, horizon)``, and none for a horizon that
    never resolves."""
    hive = RecordingHive()
    config = _perp_config()
    run_backtest(
        perp,
        [perp_agent()],
        config,
        tree=RngTree(config.seed),
        journal_dir=tmp_path,
        liquidity=make_liquidity(config),
        hive=hive,
    )
    # Five one-bar horizons resolve; the sixth has no bar left, and no seven-bar horizon resolves.
    assert [row[4] for row in hive.forecasts] == [1] * 5
    assert [row[5] for row in hive.forecasts] == [
        PERP_T0 + index * DAY_MS for index in range(1, 6)
    ]
    assert hive.resolutions == [], "a continuous instrument has no resolution entry (17.5)"


def test_learn_is_called_for_every_settled_market_the_agent_forecast(
    demo: Dataset, tmp_path: Path
) -> None:
    """Phase 6 of section 8.2, with the resolution event section 10.2 declares."""
    agent = contrarian()
    _run(demo, tmp_path, roster=[agent])
    assert len(agent.learned) == 1
    event = agent.learned[0]
    assert event.market_id == BREXIT
    assert event.outcome == 1
    assert event.category == "politics"
    assert event.forecasts == ((T0_MS, 760_000), (T0_MS + 86_400_000, 700_000))
    assert event.market_prices == ((T0_MS, 2_400), (T0_MS + 86_400_000, 3_000))
    assert event.agent_brier_tw_micro == CONTRARIAN_BRIER_TW_MICRO
    assert event.market_brier_tw_micro == MARKET_BRIER_TW_MICRO
    assert canonical_sha256(event.to_dict())


# --------------------------------------------------------------------------------------------------
# The leaderboard, the metric helpers and the run index
# --------------------------------------------------------------------------------------------------
def test_the_leaderboard_pins_the_market_follower_row_in_every_slice(
    pack: Dataset, tmp_path: Path
) -> None:
    """Section 12.10: the ``market_follower`` row is present in every slice with ``skill.point == 0``."""
    handle = _run(pack, tmp_path, config=_config(market_ids=_all_ids(pack), t0_ms=None, t1_ms=None))
    rows = build_leaderboard(handle.projection, resamples=64)
    follower_rows = [row for row in rows if row.agent_id == "market_follower"]
    assert follower_rows
    assert {row.skill.point for row in follower_rows} == {0}
    assert {row.kind for row in rows} == {"binary"}
    assert {row.horizon_bars for row in rows} == {0}
    assert all(row.provider == "demo" for row in rows)
    assert any(row.category == "all" and row.hardness_tag == "all" for row in follower_rows)
    assert any(row.hardness_tag == "upset" for row in rows)
    assert all(row.n_clean is None for row in rows)
    keys = [
        (row.agent_id, row.kind, row.provider, row.horizon_bars, row.fold, row.category, row.hardness_tag)
        for row in rows
    ]
    assert keys == sorted(keys)
    assert len(keys) == len(set(keys))


def test_a_roster_of_one_follower_projects_to_a_complete_row_of_zeros(
    demo: Dataset, tmp_path: Path
) -> None:
    """Section 12's preamble: every ratio is ``0`` when its denominator is, never a ZeroDivisionError."""
    handle = _run(demo, tmp_path, roster=[market_follower()])
    result = handle.projection.agent("market_follower")
    assert result.fill_ratio_ppm == 0
    assert result.descriptors.turnover_ppm == 0
    assert result.descriptors.category_coverage_ppm == 0
    assert result.skill.point == 0
    assert result.pnl.point == 0
    assert result.sharpe_milli == 0
    assert result.max_drawdown_bp == 0
    rows = build_leaderboard(handle.projection, resamples=32)
    # One market, one category and one hardness tag make four slices: (all, all), (all, upset),
    # (politics, all) and (politics, upset). Section 12's preamble asks for a *complete* row, not for
    # one row, and the pinned slice is the one that pools everything.
    assert len(rows) == 4
    pooled = [row for row in rows if row.category == "all" and row.hardness_tag == "all"]
    assert len(pooled) == 1
    for row in rows:
        assert row.n_markets == 1
        assert row.fill_ratio_ppm == 0
        assert row.turnover_ppm == 0
        assert row.category_coverage_ppm == 0
        assert row.skill.point == 0
        assert row.verdict is None
        assert row.pinball_skill is None


def test_the_leaderboard_reports_n_clean_from_the_caller_only(demo: Dataset, tmp_path: Path) -> None:
    """Section 11.5: the contaminated set arrives as an argument, never from an import."""
    handle = _run(demo, tmp_path)
    rows = build_leaderboard(
        handle.projection,
        contaminated={"contrarian": frozenset({BREXIT})},
        resamples=32,
    )
    by_agent = {row.agent_id: row for row in rows}
    assert by_agent["contrarian"].n_clean == 0
    assert by_agent["market_follower"].n_clean is None


def test_seed_of_run_id_reads_the_seed_back(demo: Dataset, tmp_path: Path) -> None:
    """A leaderboard is rebuildable from a projection alone because the run id carries the seed."""
    handle = _run(demo, tmp_path)
    assert seed_of_run_id(handle.run_id) == SEED
    with pytest.raises(JournalError):
        seed_of_run_id("not-a-run-id")


def test_the_metric_helpers_are_integer_functions_with_zero_denominators() -> None:
    """Section 12.3's definitions, one by one, including every zero-denominator case."""
    assert fill_ratio_ppm(filled_size=1, requested_size=3) == 333_333
    assert fill_ratio_ppm(filled_size=0, requested_size=0) == 0
    assert abstention_ppm(abstained_bars=1, decision_bars=4) == 250_000
    assert abstention_ppm(abstained_bars=0, decision_bars=0) == 0
    assert drawdown_series_min_bp([0, -120, -35]) == -120
    assert drawdown_series_min_bp([]) == 0
    assert equity_change_bp([100_000, 100_120, 99_900], bankroll_cents=100_000) == (12, -22)
    assert equity_change_bp([100_000], bankroll_cents=100_000) == ()
    assert sd_bp([12, 12, 12]) == 0
    assert sd_bp([1]) == 0
    assert sharpe_milli([12, 12, 12]) == 0
    # mean = 134 // 4 = 33 (the truncated integer mean of 12.3, never a float one), sd = isqrt(4490 //
    # 3) = 38, so the ratio is round_half_up(1000 * 33, 38) = 868. A float mean of 33.5 would read 891.
    assert sharpe_milli([12, 85, -3, 40]) == 868
    assert signed_mean(-3, 2) == -2, "half away from zero, so a loss and its mirror gain agree"
    assert signed_mean(3, 2) == 2
    assert signed_mean(5, 0) == 0
    assert contrarian_bp([-300, 300]) == 0
    assert contrarian_bp([]) == 0
    assert turnover_ppm(turnover_cents=3_000, bankroll_cents=100_000, n_markets_open=1) == 30_000
    assert turnover_ppm(turnover_cents=3_000, bankroll_cents=100_000, n_markets_open=0) == 0


def test_the_run_index_answers_what_the_api_and_the_claims_ask_it(
    demo: Dataset, tmp_path: Path
) -> None:
    """Sections 12.6, 12.8 and 12.12: the rows, the monotone index and ``candidates_store``."""
    handle = _run(demo, tmp_path)
    with RunStore(tmp_path / "index.sqlite") as store:
        row = store.index_run(
            handle,
            dataset_name=demo.manifest.name,
            seed=SEED,
            fold="all",
            market_ids_hash=FIXTURE_MARKET_IDS_HASH,
        )
        assert row.created_at_index == 1
        assert row.run_id == handle.run_id
        again = store.index_run(
            handle,
            dataset_name=demo.manifest.name,
            seed=SEED,
            fold="all",
            market_ids_hash=FIXTURE_MARKET_IDS_HASH,
        )
        assert again.created_at_index == 1, "indexing a run twice does not inflate the ledger"
        assert store.next_created_at_index() == 2
        assert store.run(handle.run_id) == row
        assert store.runs(dataset_hash=demo.manifest.dataset_hash) == (row,)
        assert store.runs(kind="evolution") == ()
        written = store.index_projection(handle, fold="all")
        assert written == 2
        assert store.candidates_store(demo.manifest.dataset_hash) == 2
        assert store.genome_hashes(demo.manifest.dataset_hash) == tuple(
            sorted(FIXTURE_GENOME_HASHES.values())
        )
        store.index_candidate(
            CandidateRow(
                dataset_hash=demo.manifest.dataset_hash,
                genome_hash="f" * 64,
                agent_id="p001-ffffffff",
                run_id=handle.run_id,
                fold="validation",
                skill_lb_micro=-10,
                pnl_lb_cents=-5,
            )
        )
        assert store.candidates_store(demo.manifest.dataset_hash) == 3
        assert len(store.candidates(demo.manifest.dataset_hash)) == 3
        assert store.candidates_store("0" * 64) == 0


# --------------------------------------------------------------------------------------------------
# The commands
# --------------------------------------------------------------------------------------------------
def test_pmx_replay_reads_a_run_directory_and_prints_its_leaderboard(
    demo: Dataset, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``pmx replay <run_id>`` rebuilds and compares; ``--leaderboard`` prints canonical rows."""
    handle = _run(demo, tmp_path)
    code = cli_main(["replay", handle.run_id, "--runs-dir", str(tmp_path)])
    assert code == 0
    assert "rebuilt from the journal" in capsys.readouterr().out
    code = cli_main(
        ["replay", handle.run_id, "--runs-dir", str(tmp_path), "--leaderboard"]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert '"agent_id":"contrarian"' in printed
    assert cli_main(["replay", "r-00000000-1-00000000", "--runs-dir", str(tmp_path)]) == 2


def test_pmx_backtest_reports_the_missing_registry_rather_than_an_import_error(
    demo: Dataset, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The roster is A1's (wave 3); until it lands the command says so and exits 1, never crashes."""
    code = cli_main(
        ["backtest", "--dataset", str(DEMO), "--runs-dir", str(tmp_path), "--seed", "7", "--no-index"]
    )
    assert code == 1
    assert "registry" in capsys.readouterr().err


def test_the_projection_of_a_partial_window_scores_only_what_settled(
    demo: Dataset, tmp_path: Path
) -> None:
    """A market still open at ``t1_ms`` is counted as seen and not as scored (this module's docstring)."""
    config = _config(market_ids=[BREXIT], t1_ms=T0_MS + 86_400_000)
    handle = _run(demo, tmp_path, config=config)
    result = handle.projection.agent("contrarian")
    assert result.n_markets == 0
    assert result.n_markets_open == 1
    assert result.brier_tw_micro == 0
    assert result.skill.point == 0
    assert handle.projection.markets == ()
    assert replay(handle.run_dir).to_dict() == handle.projection.to_dict()


# --------------------------------------------------------------------------------------------------
# Amendment C1b: one continuous instrument through the whole loop (sections 17.2, 17.3 and 17.5)
#
# The instrument, its meta, its cash event and its horizon forecasts are the declared records of
# ``pmx.types`` (``ContinuousInstrument``, ``MarketMeta.kind``, ``CashEvent``, ``HorizonForecast`` and
# ``Actions.horizon_forecasts``, all landed by gate G2), so this is a real end-to-end run over the real
# types: the calendar, the observation, the execution, the cash event, the forced flat, the horizon
# resolution and the projection all run over it.
#
# The window sits **inside** the demo pack's validation window, because ``Dataset.market`` clips a
# continuous instrument at ``split.validation_end_ms`` (ruling R182): a perp whose bars are all in the
# sealed months would reach the run with no tape at all, which is the clip working and not a fixture.
# --------------------------------------------------------------------------------------------------
PERP = "demo-btcusdt-perp"
DAY_MS = 86_400_000
#: Seven days ending at the demo pack's ``validation_end_ms``, so the delisting survives the clip.
PERP_T0 = 1_479_945_600_000
PERP_T1 = PERP_T0 + 6 * DAY_MS
PERP_CLOSES = (5_000, 5_100, 5_050, 5_200, 5_150, 5_300)
PERP_HORIZONS = (1, 7)


def _perp_bars() -> tuple[Bar, ...]:
    """Six dense daily bars with a quote-free tape, so the base price is each bar's own open."""
    bars: list[Bar] = []
    previous = PERP_CLOSES[0]
    for index, close_bp in enumerate(PERP_CLOSES):
        open_bp = previous
        bars.append(
            Bar(
                t_ms=PERP_T0 + index * DAY_MS,
                open_bp=open_bp,
                high_bp=max(open_bp, close_bp) + 10,
                low_bp=min(open_bp, close_bp) - 10,
                close_bp=close_bp,
                vwap_bp=(open_bp + close_bp) // 2,
                volume_milli=10_000_000,
                n_trades=500,
                yes_bid_bp=None,
                yes_ask_bp=None,
                open_interest=0,
            )
        )
        previous = close_bp
    return tuple(bars)


def _perp_instrument() -> ContinuousInstrument:
    """The perpetual of section 17.1: shortable, an underlying, no borrow and no carry schedule."""
    return ContinuousInstrument(
        schema_version="instrument.v1",
        id=PERP,
        provider="demo",
        vendor="binance",
        symbol="BTCUSDT",
        kind="perp",
        currency="usd",
        tick_size_micro=100,
        point_value_micro=1_000_000,
        session_calendar_id="continuous",
        fee_schedule_id="demo-zero",
        borrow_schedule_id=None,
        carry_schedule_id=None,
        listed_at_ms=PERP_T0,
        delisted_at_ms=PERP_T1,
        short_allowed=True,
        interval_min=1_440,
        bars=_perp_bars(),
        trades=(),
        url="https://example.invalid/btcusdt",
        description="a perpetual future, for the continuous half of the engine",
        category="crypto",
        tags=(),
        twins=(),
        underlying_id="demo-btcusdt-spot",
        roll_source=None,
        first_price_ticks=PERP_CLOSES[0],
        quality=MarketQuality(
            n_trades=0,
            unique_bettors=0,
            life_days=6,
            volume_milli_total=60_000_000,
            traded_bars=6,
            tape_kind="bars_only",
        ),
        cash_events=(
            CashEvent.build(
                market_id=PERP,
                kind="funding",
                t_ms=PERP_T0 + 2 * DAY_MS,
                detail={"rate_ppm": 1_000, "mark_ticks": PERP_CLOSES[2]},
                source_url="https://example.invalid/funding",
            ),
        ),
        source="reconstructed",
        notes="",
    )


def _perp_meta() -> MarketMeta:
    """The continuous ``MarketMeta`` values of ruling R186, spelled out."""
    return MarketMeta(
        id=PERP,
        provider="demo",
        category="crypto",
        tags=(),
        event_key=None,
        created_at_ms=PERP_T0,
        close_at_ms=PERP_T1,
        resolved_at_ms=PERP_T1,
        resolution=-1,
        interval_min=1_440,
        n_bars=len(PERP_CLOSES),
        hardness_tags=(),
        fee_schedule_id="demo-zero",
        fold="all",
        kind="perp",
    )


@pytest.fixture(scope="module")
def perp(pack: Dataset) -> Dataset:
    """A one-instrument dataset over the perpetual, on the demo pack's manifest and grid."""
    instrument = _perp_instrument()
    return Dataset(
        manifest=pack.manifest,
        metas=(_perp_meta(),),
        path=pack.path,
        market_loader=lambda market_id: instrument,
        news_loader=lambda: (),
        background_loader=lambda market_id: (),
    )


@dataclass(slots=True)
class PerpAgent(StubAgent):
    """A perpetual trader: one long of a milli-unit, restated every bar, and one stated probability.

    It states ``prob_ppm`` and **no** ``horizon_forecasts``, which is ruling R184's case: the runner
    synthesises the shortest horizon from ``prob_ppm`` and carries the random walk on the rest, so a
    family that states only a probability states a direction instead of being rejected on every bar.
    """

    target_milli: int = 1_000
    prob_ppm: int = 700_000

    def decide(self) -> Actions:
        obs = self.observation
        assert obs is not None
        return Actions(
            actions_version="actions.v2",
            markets=tuple(
                MarketAction(
                    market_id=view.market_id,
                    prob_ppm=self.prob_ppm,
                    kind="target",
                    target_position=self.target_milli,
                )
                for view in obs.markets
            ),
        )


def perp_agent() -> PerpAgent:
    return PerpAgent(
        agent_id="perp_trader",
        family="trend",
        genome=StubGenome(family="trend", genes=(("lookback_bars", 3),)),
        trades=True,
    )


@dataclass(slots=True)
class QuantileAgent(StubAgent):
    """An agent that states five pairs, of which one is legal and four break one rule each.

    The disagreeing pair comes **first** on purpose: section 8.4's first-occurrence rule means a pair
    accepted for ``(market, shortest horizon)`` makes every later pair on it a ``duplicate``, so a
    disagreement placed after the legal pair could never reach ``bad_prob``.
    """

    def decide(self) -> Actions:
        obs = self.observation
        assert obs is not None
        market_id = obs.markets[0].market_id
        return Actions(
            actions_version="actions.v2",
            markets=(
                MarketAction(market_id=market_id, prob_ppm=640_000, kind="hold"),
            ),
            horizon_forecasts=(
                HorizonForecast(market_id, 1, 999_000, None),
                HorizonForecast(market_id, 1, 640_000, (4_900, 4_950, 5_000, 5_050, 5_100)),
                HorizonForecast(market_id, 1, 640_000, None),
                HorizonForecast(market_id, 3, 500_000, None),
                HorizonForecast(market_id, 7, 500_000, (5_000, 4_000, 5_100, 5_200, 5_300)),
            ),
        )


@dataclass(slots=True)
class SilentPerpAgent(StubAgent):
    """An agent that states nothing at all: every horizon of every bar carries the random walk."""

    def decide(self) -> Actions:
        return Actions(actions_version="actions.v2", markets=())


def silent_perp_agent() -> SilentPerpAgent:
    return SilentPerpAgent(
        agent_id="random_walk",
        family="random_walk",
        genome=StubGenome(family="random_walk", genes=()),
        trades=False,
    )


def quantile_agent() -> QuantileAgent:
    return QuantileAgent(
        agent_id="quantiler",
        family="trend",
        genome=StubGenome(family="trend", genes=(("lookback_bars", 5),)),
        trades=False,
    )


def _perp_config() -> RunConfig:
    return RunConfig(
        seed=SEED,
        t0_ms=PERP_T0,
        t1_ms=PERP_T1,
        market_ids_hash=market_set_hash([PERP]),
    )


def _raw_events(path: Path) -> list[dict[str, Any]]:
    """The journal as the canonical JSON objects it is.

    ``read_journal`` refuses amendment C1b's three events until gate G2 registers their classes and
    admits them to ``journal.v2.json``'s ``oneOf`` (ruling R164), so the bytes are read directly. Every
    other test in this file reads the journal through ``read_journal``, which is what a binary run
    writes and what the replay guarantee of section 9.5 is about.
    """
    import json

    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _rows_of(events: Sequence[Mapping[str, Any]], event_type: str) -> list[Mapping[str, Any]]:
    return [row for row in events if row["type"] == event_type]


def test_a_continuous_instrument_runs_the_whole_bar_loop(perp: Dataset, tmp_path: Path) -> None:
    """Sections 17.2, 17.3 and 17.5 end to end: the listing, the fill, the cash event, the flat."""
    config = _perp_config()
    handle = run_backtest(
        perp,
        [perp_agent()],
        config,
        tree=RngTree(config.seed),
        journal_dir=tmp_path,
        liquidity=make_liquidity(config),
    )
    assert handle.n_bars == len(PERP_CLOSES)
    events = _raw_events(handle.journal_path)

    listed = _rows_of(events, "market_listed")
    assert len(listed) == 1
    assert listed[0]["kind"] == "perp"
    assert listed[0]["vendor"] == "binance"
    assert listed[0]["symbol"] == "BTCUSDT"
    assert listed[0]["tick_size_micro"] == 100
    assert listed[0]["point_value_micro"] == 1_000_000
    assert listed[0]["session_calendar_id"] == "continuous"
    assert listed[0]["close_at_ms"] == PERP_T1, "section 9.2: a journal carries delisted_at_ms"
    assert listed[0]["borrow_schedule_id"] is None

    # The latency rule of 16.2 on a continuous instrument: decided at bar 0, filled at bar 1's open.
    fills = _rows_of(events, "filled")
    agent_fills = [row for row in fills if row["price_source"] != "event"]
    assert len(agent_fills) == 1
    assert agent_fills[0]["bar_ms"] == PERP_T0 + DAY_MS
    assert agent_fills[0]["filled_size"] == 1_000
    assert agent_fills[0]["position_after"] == 1_000

    # One data cash event, applied at its own bar, and the forced flat at last_bar(i) (17.3).
    applied = _rows_of(events, "cash_event_applied")
    by_kind = {str(row["kind"]): row for row in applied}
    assert sorted(by_kind) == ["forced_flat", "funding"]
    funding = by_kind["funding"]
    assert funding["bar_ms"] == PERP_T0 + 2 * DAY_MS
    assert funding["position_before"] == 1_000
    assert funding["position_after"] == 1_000
    assert isinstance(funding["cash_delta_cents"], int)
    assert int(funding["cash_delta_cents"]) < 0, "a long pays when the funding rate is positive"
    flat = by_kind["forced_flat"]
    assert flat["bar_ms"] == PERP_T0 + 5 * DAY_MS
    assert flat["position_before"] == 1_000
    assert flat["position_after"] == 0
    assert flat["cash_delta_cents"] == 0, "the money of a forced flat moves in its event fill"
    event_fills = [row for row in fills if row["price_source"] == "event"]
    assert len(event_fills) == 1
    assert event_fills[0]["phase"] == "settle"
    assert event_fills[0]["fill_price_bp"] == PERP_CLOSES[5]

    # instrument_closed once, at last_bar(i), after the forced flat (17.3).
    closed = _rows_of(events, "instrument_closed")
    assert len(closed) == 1
    assert closed[0]["bar_ms"] == PERP_T0 + 5 * DAY_MS
    assert closed[0]["reason"] == "delisted"
    assert closed[0]["last_price_ticks"] == PERP_CLOSES[5]
    assert closed[0]["n_bars"] == len(PERP_CLOSES)
    # Six statements at the seven-bar horizon and one at the one-bar horizon of the last bar have no
    # bar left to resolve at (ruling R160).
    assert closed[0]["n_forecasts_unresolved"] == 7
    assert closed[0]["market_id"] == PERP

    # A continuous instrument never settles (17.2).
    assert _rows_of(events, "settled") == []
    assert _rows_of(events, "settlement_applied") == []


def test_the_shortest_horizon_is_synthesised_from_prob_ppm(perp: Dataset, tmp_path: Path) -> None:
    """Ruling R184: a family that states only ``prob_ppm`` states a direction, and is not rejected."""
    config = _perp_config()
    handle = run_backtest(
        perp,
        [perp_agent()],
        config,
        tree=RngTree(config.seed),
        journal_dir=tmp_path,
        liquidity=make_liquidity(config),
    )
    events = _raw_events(handle.journal_path)
    assert _rows_of(events, "action_rejected") == [], "R184 exists so that this list stays empty"
    recorded = _rows_of(events, "forecast_recorded")
    assert len(recorded) == len(PERP_CLOSES)
    first = recorded[0]
    assert first["price_ref_ticks"] == PERP_CLOSES[0], "the market's first bar shows first_price_bp"
    horizons = first["horizons"]
    assert isinstance(horizons, list)
    assert [row["horizon_bars"] for row in horizons] == list(PERP_HORIZONS)
    assert horizons[0]["up_probability_ppm"] == 700_000
    assert horizons[0]["quantiles_ticks"] is None, "a synthesised pair states no quantile"
    assert horizons[1]["up_probability_ppm"] == 500_000, "the rest carries the random walk"
    assert horizons[1]["quantiles_ticks"] == [PERP_CLOSES[0]] * 5


def test_a_horizon_resolves_at_the_bar_its_realisation_became_public(
    perp: Dataset, tmp_path: Path
) -> None:
    """Ruling R160 and section 17.5: the reference, the realisation, and the two losses."""
    config = _perp_config()
    handle = run_backtest(
        perp,
        [perp_agent()],
        config,
        tree=RngTree(config.seed),
        journal_dir=tmp_path,
        liquidity=make_liquidity(config),
    )
    events = _raw_events(handle.journal_path)
    resolved = _rows_of(events, "forecast_resolved")
    # The one-bar horizon of bars 0 to 4 resolves at bars 1 to 5; the seven-bar horizon never does.
    assert {int(row["horizon_bars"]) for row in resolved} == {1}
    assert [int(row["bar_ms"]) for row in resolved] == [
        PERP_T0 + index * DAY_MS for index in range(1, 6)
    ]
    assert all(row["phase"] == "settle" for row in resolved)

    first = resolved[0]
    assert first["forecast_bar_ms"] == PERP_T0
    assert first["price_ref_ticks"] == PERP_CLOSES[0]
    assert first["price_realised_ticks"] == PERP_CLOSES[0], "bar 0's own close is the realisation"
    assert first["realised_sign"] == 0, "a flat return"
    assert first["up_probability_ppm"] == 700_000
    assert first["directional_brier_micro"] == directional_brier_micro(700_000, 0)
    assert first["pinball_micro"] is None, "the synthesised pair stated no quantile"
    assert first["baseline_pinball_micro"] == 0, "the realisation is the reference"
    assert first["carried"] is False

    second = resolved[1]
    assert second["forecast_bar_ms"] == PERP_T0 + DAY_MS
    assert second["price_ref_ticks"] == PERP_CLOSES[0]
    assert second["price_realised_ticks"] == PERP_CLOSES[1]
    assert second["realised_sign"] == 1
    assert second["directional_brier_micro"] == directional_brier_micro(700_000, 1)

    # The random walk's own skill is zero by construction, on the same arithmetic (ruling R158).
    for row in resolved:
        baseline = random_walk_resolution(
            forecast_bar_ms=int(row["forecast_bar_ms"]),
            horizon_bars=1,
            price_ref_ticks=int(row["price_ref_ticks"]),
            price_realised_ticks=int(row["price_realised_ticks"]),
        )
        assert RANDOM_WALK_BRIER_MICRO - baseline.directional_brier_micro == 0


def test_the_carried_random_walk_scores_zero_skill_on_every_bar(
    perp: Dataset, tmp_path: Path
) -> None:
    """Ruling R158 and AC-23: the baseline's skill is zero by construction, at every horizon and bar.

    The random walk is defined **against the current reference price**, so a silent agent's carried
    statement is rebuilt each bar. A carried statement that remembered the first bar's quantiles would
    score them against a later realisation and the identity below would fail on every bar but the
    first, which is exactly the bug this test pins.
    """
    config = _perp_config()
    handle = run_backtest(
        perp,
        [silent_perp_agent()],
        config,
        tree=RngTree(config.seed),
        journal_dir=tmp_path,
        liquidity=make_liquidity(config),
    )
    events = _raw_events(handle.journal_path)
    resolved = _rows_of(events, "forecast_resolved")
    assert len(resolved) == 5
    for row in resolved:
        assert row["carried"] is True
        assert row["up_probability_ppm"] == 500_000
        assert row["quantiles_ticks"] == [row["price_ref_ticks"]] * 5
        assert row["directional_brier_micro"] == RANDOM_WALK_BRIER_MICRO
        assert row["pinball_micro"] == row["baseline_pinball_micro"]
    # And therefore both skills are zero over every cell of the projection.
    rows = handle.projection.rows_of("random_walk")
    assert rows
    assert {row.skill_micro for row in rows} == {0}
    assert {row.baseline_pinball_micro - row.pinball_micro for row in rows} == {0}
    result = handle.projection.agent("random_walk")
    assert result.pinball_skill is not None
    assert result.pinball_skill.point == 0


def test_a_stated_horizon_pair_is_validated_against_section_17_5(
    perp: Dataset, tmp_path: Path
) -> None:
    """Ruling R157: a duplicate, a horizon outside the config and a bad quantile tuple are refused."""
    config = _perp_config()
    handle = run_backtest(
        perp,
        [quantile_agent()],
        config,
        tree=RngTree(config.seed),
        journal_dir=tmp_path,
        liquidity=make_liquidity(config),
    )
    events = _raw_events(handle.journal_path)
    rejected = _rows_of(events, "action_rejected")
    reasons = {str(row["reason"]) for row in rejected if row["bar_ms"] == PERP_T0}
    assert reasons == {"bad_horizon", "bad_quantiles", "duplicate", "bad_prob"}
    recorded = _rows_of(events, "forecast_recorded")
    horizons = recorded[0]["horizons"]
    assert isinstance(horizons, list)
    assert horizons[0]["up_probability_ppm"] == 640_000, "the first legal pair of the shortest horizon"
    assert horizons[0]["quantiles_ticks"] == [4_900, 4_950, 5_000, 5_050, 5_100]
    resolved = _rows_of(events, "forecast_resolved")
    assert resolved[0]["pinball_micro"] == pinball_micro(
        (4_900, 4_950, 5_000, 5_050, 5_100), PERP_CLOSES[0], PERP_CLOSES[0]
    )


def test_the_projection_of_a_continuous_run_carries_the_cells_of_section_17_6(
    perp: Dataset, tmp_path: Path
) -> None:
    """Rulings R163 and R186: one row per ``(agent, instrument, week, horizon)``, and the market row."""
    config = _perp_config()
    handle = run_backtest(
        perp,
        [perp_agent()],
        config,
        tree=RngTree(config.seed),
        journal_dir=tmp_path,
        liquidity=make_liquidity(config),
    )
    projection = handle.projection
    rows = projection.rows_of("perp_trader")
    assert rows, "a continuous run carries scored rows"
    assert {row.kind for row in rows} == {"perp"}
    assert {row.horizon_bars for row in rows} == {1}
    assert all(row.unit_key.startswith(f"{PERP}/w") for row in rows)
    assert all(row.block_key == row.unit_key.split("/")[1] for row in rows)
    assert all(row.market_brier_tw_micro == RANDOM_WALK_BRIER_MICRO for row in rows)
    assert all(row.hardness_tags == () for row in rows)
    assert sum(row.n_resolved for row in rows) == 5
    assert sum(row.n_cash_events for row in rows) >= 1

    assert len(projection.markets) == 1
    market = projection.markets[0]
    assert market.kind == "perp"
    assert market.vendor == "binance"
    assert market.outcome == -1, "a continuous instrument has nothing to be right about"
    assert market.n_bars == len(PERP_CLOSES)
    assert market.last_price_ticks == PERP_CLOSES[5]
    assert market.market_brier_tw_micro == RANDOM_WALK_BRIER_MICRO
    assert market.life_mean_price_bp == round_half_up(sum(PERP_CLOSES), len(PERP_CLOSES))

    result = projection.agent("perp_trader")
    assert result.n_cash_events == 2, "the funding event and the forced flat"
    assert [kind for kind, _ in result.exposure_by_kind] == ["perp"]
    assert result.exposure_by_kind[0][1] > 0
    assert result.pinball_skill is not None, "a continuous row reports the quantile half"
    rows_of_board = build_leaderboard(projection, resamples=32)
    assert {row.kind for row in rows_of_board} == {"perp"}
    assert {row.horizon_bars for row in rows_of_board} == {1}
    assert all(row.pinball_skill is not None for row in rows_of_board)
    assert all(row.log_micronats == 0 for row in rows_of_board)


# --------------------------------------------------------------------------------------------------
# The run's calendar reaches the observation (rulings R183 and R187)
#
# ``build_observation`` takes the run's ``Calendar`` and three fields of a market view are lookups only
# it can answer: ``tradable`` on a continuous instrument, ``hours_to_next_bar`` and the application bar
# of a cash event. A runner that built the observation without it would publish ``hours_to_next_bar =
# 0`` across every session gap and hide a dividend the engine had already paid, and no binary test could
# see it, because a binary's own answer for that field is ``0`` and a binary carries no cash event.
# So the run below is a **session** instrument: a weekday venue whose Friday bar is followed by Monday,
# which is the one shape where the venue's schedule and the run's own timeline differ by more than a
# bar. A ``0`` in that column means the calendar did not reach the builder.
# --------------------------------------------------------------------------------------------------
HOUR_MS = 3_600_000
SESSION_CALENDAR_ID = "xtst"
#: The Monday before ``PERP_T0``, which is a Thursday: the calendar starts before the run and ends after
#: it, as a sealed calendar covers the dataset window and not one run's window (17.2).
SESSION_MONDAY = PERP_T0 - 3 * DAY_MS
SESSION_SESSIONS: tuple[Session, ...] = tuple(
    Session(
        open_ms=SESSION_MONDAY + day * DAY_MS + 13 * HOUR_MS + 30 * 60_000,
        close_ms=SESSION_MONDAY + day * DAY_MS + 20 * HOUR_MS,
    )
    for day in range(21)
    if day % 7 not in (5, 6)
)
SESSION_CALENDAR = SessionCalendar(
    calendar_id=SESSION_CALENDAR_ID,
    description="A weekday venue, 13:30Z to 20:00Z, for the session half of amendment C1b.",
    source_url="https://example.invalid/xtst",
    as_of_date="2026-09-09",
    window=DatasetWindow(start_ms=SESSION_MONDAY, end_ms=SESSION_MONDAY + 21 * DAY_MS),
    sessions=SESSION_SESSIONS,
)
#: Thursday, Friday, Monday, Tuesday: the four session bars of the perp's window, weekend removed.
SESSION_BARS = (PERP_T0, PERP_T0 + DAY_MS, PERP_T0 + 4 * DAY_MS, PERP_T0 + 5 * DAY_MS)
#: The venue's hours to the next bar at each of them, the weekend included and the last bar's answered
#: from the sealed calendar and never from the run (ruling R181).
SESSION_HOURS = (24, 72, 24, 24)


def _session_instrument() -> ContinuousInstrument:
    """The perpetual of :func:`_perp_instrument` on a weekday venue, with only its session bars.

    Every bar is inside a session, which is what the loader requires of a sealed dataset, and the
    funding event is stamped on the Friday so that its application bar is a bar of the run.
    """
    base = _perp_instrument()
    bars = tuple(bar for bar in base.bars if bar.t_ms in SESSION_BARS)
    assert len(bars) == len(SESSION_BARS), "the fixture's bars are the venue's session bars"
    return replace(
        base,
        session_calendar_id=SESSION_CALENDAR_ID,
        bars=bars,
        cash_events=(
            CashEvent.build(
                market_id=PERP,
                kind="funding",
                t_ms=PERP_T0 + DAY_MS,
                detail={"rate_ppm": 1_000, "mark_ticks": PERP_CLOSES[1]},
                source_url="https://example.invalid/funding",
            ),
        ),
    )


@pytest.fixture(scope="module")
def perp_sessions(pack: Dataset) -> Dataset:
    """The perpetual on a weekday venue, with the sealed calendar the dataset hands the run."""
    instrument = _session_instrument()
    return Dataset(
        manifest=pack.manifest,
        metas=(replace(_perp_meta(), n_bars=len(SESSION_BARS)),),
        path=pack.path,
        market_loader=lambda market_id: instrument,
        news_loader=lambda: (),
        background_loader=lambda market_id: (),
        calendar_loader=lambda calendar_id: SESSION_CALENDAR,
    )


@dataclass(slots=True)
class RecordingPerpAgent(PerpAgent):
    """:class:`PerpAgent` that keeps every market view it was shown, bar by bar."""

    seen: list[tuple[int, int, bool, tuple[tuple[str, int], ...]]] = field(default_factory=list)

    def observe(self, obs: Observation) -> None:
        # Named explicitly rather than through a zero-argument ``super()``: ``dataclass(slots=True)``
        # rebuilds the class, so the implicit ``__class__`` cell of a slotted dataclass is the old one.
        StubAgent.observe(self, obs)
        for view in obs.markets:
            self.seen.append(
                (
                    obs.now_ms,
                    view.hours_to_next_bar,
                    view.tradable,
                    tuple((event.kind, event.applied_at_ms) for event in view.cash_events),
                )
            )


def test_a_continuous_run_publishes_the_venues_session_gap_in_every_observation(
    perp_sessions: Dataset, tmp_path: Path
) -> None:
    """The runner hands ``build_observation`` the run's calendar, so the gap is published (R187).

    Four bars, one weekend, and the hours to the next bar read off the sealed calendar at every one of
    them: ``24``, ``72`` across the weekend, ``24``, and ``24`` on the instrument's last bar, where the
    run has no next bar and the venue reopens the next morning (ruling R181). A runner that did not pass
    its calendar publishes ``0`` at all four, which is why the exact tuple is asserted and why the
    weekend is one of its entries.
    """
    config = _perp_config()
    agent = RecordingPerpAgent(
        agent_id="perp_trader",
        family="trend",
        genome=StubGenome(family="trend", genes=(("lookback_bars", 3),)),
        trades=True,
    )
    handle = run_backtest(
        perp_sessions,
        [agent],
        config,
        tree=RngTree(config.seed),
        journal_dir=tmp_path,
        liquidity=make_liquidity(config),
    )
    assert handle.n_bars == len(SESSION_BARS), "a weekend is not a bar of a session run (17.2)"
    assert [row[0] for row in agent.seen] == list(SESSION_BARS)
    assert [row[1] for row in agent.seen] == list(SESSION_HOURS)
    assert 0 not in [row[1] for row in agent.seen], (
        "hours_to_next_bar is 0 only when build_observation was given no calendar"
    )
    assert [row[2] for row in agent.seen] == [True, True, True, True], (
        "tradable is open(i, t) on a continuous instrument and every session bar is open (R181)"
    )
    # Ruling R183 through the runner, on the one implementation of R175: the Friday funding is the
    # venue's published past from the Monday on, and never before its own application bar completed.
    assert [row[3] for row in agent.seen] == [
        (),
        (),
        (("funding", PERP_T0 + DAY_MS),),
        (("funding", PERP_T0 + DAY_MS),),
    ]
    events = _raw_events(handle.journal_path)
    listed = _rows_of(events, "market_listed")
    assert len(listed) == 1
    assert listed[0]["session_calendar_id"] == SESSION_CALENDAR_ID
    applied = _rows_of(events, "cash_event_applied")
    assert [(str(row["kind"]), int(row["bar_ms"])) for row in applied] == [
        ("funding", PERP_T0 + DAY_MS),
        ("forced_flat", SESSION_BARS[-1]),
    ], "the funding applies at its own bar and the flat at last_bar(i), which is the Tuesday"
