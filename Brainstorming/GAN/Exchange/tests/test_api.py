"""The read only replay API: every route, the WebSocket protocol and T4.1's budget (A22).

The whole file runs against **one real recorded match**: the reference match of
CONTRACTS section 7.21 (six baselines, forty-eight ticks, five markets, the
``standard_config`` seed), played once per session by :func:`recorded_runs`,
projected, saved into a real :class:`~pxe.store.db.Store`, scanned by the real
integrity detectors and wrapped in a real tournament. Nothing here is a stub,
because the API's whole job is to serve artefacts and a stubbed artefact proves
nothing.

Section 10's anti-vacuous rule applies with teeth, so every test asserts first
that the data it is about to inspect is non empty: the journal has thousands of
events, the projection has hundreds of trades, the tournament has a leaderboard.
A test that would pass on an empty run is a bug.
"""

from __future__ import annotations

import json
import shutil
import statistics
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from pxe import ACTION_VERSION, ENGINE_VERSION, OBS_VERSION
from pxe.agents.base import make_baseline
from pxe.api.app import (
    API_VERSION,
    create_app,
    render_replay_api_markdown,
    write_sample_fixtures,
)
from pxe.api.routes import (
    MATCH_CACHE_SIZE,
    MAX_QUERY_CHARS,
    WS_SPEEDS,
    Decision,
    Health,
    MatchDetail,
    MatchMetricsPayload,
    MatchSeries,
    ReplayService,
    TickState,
    TournamentDetail,
    TournamentSummary,
)
from pxe.api.ws import CLOSE_BAD_PARAMETER, CLOSE_UNKNOWN_MATCH
from pxe.events import MarkToMarket, OrderCancelled, OrderPlaced, TradeExecuted
from pxe.gateway.scripted import ScriptedGateway
from pxe.info.profiles import build_profile, default_profile_kinds
from pxe.integrity.detectors import run_detectors, write_incidents
from pxe.journal import read_journal
from pxe.metrics.aggregate import compute_all, read_metrics, write_metrics
from pxe.metrics.projection import project
from pxe.rng import RngTree
from pxe.runner.match_runner import run_match
from pxe.store.db import Store
from pxe.store.files import artefact_paths, match_dir
from pxe.tournament.elites import EliteCell
from pxe.tournament.latin_square import assign_profiles
from pxe.types import (
    AgentSpec,
    GatewayConfig,
    HarnessConfig,
    InfoProfileKind,
    MatchConfig,
    MatchTask,
    RatingRecord,
    TournamentConfig,
    TournamentFormat,
    make_agent_id,
)
from pxe.world.generator import generate_world

#: The reference match of CONTRACTS section 7.21: the PRD section 5.7 defaults,
#: the ``standard_config`` seed, six baselines, forty-eight ticks, five markets.
SEED = 20260827
TICKS_TOTAL = 48
N_MARKETS = 5
BASELINES = ("fundamentalist", "momentum", "noise", "zero_intelligence", "bayesian", "mute")
MATCH_ID = f"m-election-{SEED}-01"
TOURNAMENT_ID = "T-apitest-0001"

#: T4.1's numbered requirement: under 100 ms per replay request on the
#: reference match, measured warm.
TICK_BUDGET_MS = 100.0

#: The cold path bound of section 7.21, so the cache cannot hide an unusable
#: first request.
COLD_BUDGET_S = 2.0

#: Where the samples A24 builds on live (section 7.25).
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "web" / "tests" / "fixtures"

#: The declared route table of section 7.21, with a request that must answer 200.
ROUTE_TABLE: tuple[tuple[str, str], ...] = (
    ("GET", "/api/health"),
    ("GET", "/api/matches"),
    ("GET", f"/api/matches/{MATCH_ID}"),
    ("GET", f"/api/matches/{MATCH_ID}/events"),
    ("GET", f"/api/matches/{MATCH_ID}/ticks/1"),
    ("GET", f"/api/matches/{MATCH_ID}/series"),
    ("GET", f"/api/matches/{MATCH_ID}/metrics"),
    ("GET", f"/api/matches/{MATCH_ID}/incidents"),
    ("GET", f"/api/matches/{MATCH_ID}/highlights"),
    ("GET", f"/api/matches/{MATCH_ID}/decisions"),
    ("GET", "/api/tournaments"),
    ("GET", f"/api/tournaments/{TOURNAMENT_ID}"),
    ("GET", f"/replay/{MATCH_ID}"),
)

#: The fixture names ``pxe api openapi --samples`` writes, that is the files
#: A24 builds its whole application on.
FIXTURE_NAMES: tuple[str, ...] = (
    "decisions_page",
    "events_page",
    "health",
    "highlights",
    "incidents",
    "match_detail",
    "match_metrics",
    "match_series",
    "matches_page",
    "tick_state",
    "tick_state_final",
    "tick_state_zero",
    "tournament_detail",
    "tournaments_page",
    "ws_frames",
)


# ---------------------------------------------------------------------------
# One real recorded match, played once per session
# ---------------------------------------------------------------------------
def _play_reference(runs_dir: Path) -> None:
    """Play the reference match and write every artefact the API reads."""
    config = MatchConfig(seed=SEED, ticks_total=TICKS_TOTAL, n_agents=len(BASELINES), n_markets=N_MARKETS)
    world = generate_world(template_id="election", seed=SEED, ticks_total=TICKS_TOTAL, n_markets=N_MARKETS)
    kinds = default_profile_kinds(len(BASELINES))
    market_ids = world.market_ids()
    specs: list[AgentSpec] = []
    for index, name in enumerate(BASELINES, start=1):
        kind = kinds[index - 1]
        focus = market_ids[index % len(market_ids)] if kind is InfoProfileKind.SPECIALIST else None
        specs.append(
            AgentSpec(
                agent_id=make_agent_id(index),
                harness=HarnessConfig(harness_id=name, version="1.0.0", kind="scripted"),
                info_profile=build_profile(kind, market_ids=market_ids, focus_market_id=focus),
            )
        )
    rng = RngTree(config.seed)
    agents = {
        make_agent_id(index): make_baseline(
            name,
            agent_id=make_agent_id(index),
            config=config,
            rng=rng.child(f"agent/{make_agent_id(index)}").substream(f"agent.{make_agent_id(index)}"),
        )
        for index, name in enumerate(BASELINES, start=1)
    }
    result = run_match(
        config=config,
        world=world,
        agents=specs,
        gateway=ScriptedGateway(agents=agents),
        out_dir=match_dir(runs_dir, MATCH_ID),
        rng=rng,
        match_id=MATCH_ID,
    )
    paths = artefact_paths(runs_dir, MATCH_ID)
    events = read_journal(paths["journal"])
    projection = project(events)
    metrics = compute_all(projection)
    write_metrics(paths["metrics"], metrics)
    incidents = run_detectors(projection)
    write_incidents(paths["incidents"], incidents)
    with Store(runs_dir=runs_dir) as store:
        store.init_schema()
        store.save_match(result, projection, metrics)
        _save_tournament(store, incidents=incidents)


def _save_tournament(store: Store, *, incidents: Sequence[Any]) -> None:
    """Wrap the recorded match in a real tournament, so the T4.3 view has data."""
    harnesses = tuple(HarnessConfig(harness_id=name, version="1.0.0", kind="scripted") for name in BASELINES)
    seeds = (SEED, 2, 3)
    config = TournamentConfig(
        tournament_id=TOURNAMENT_ID,
        format=TournamentFormat.ROUND_ROBIN,
        harnesses=harnesses,
        template_ids=("election",),
        seeds=seeds,
        agents_per_match=len(BASELINES),
        rounds=1,
        gateway=GatewayConfig(),
        match_defaults=MatchConfig(seed=SEED, ticks_total=TICKS_TOTAL, n_agents=len(BASELINES), n_markets=N_MARKETS),
        max_cost_usd=1.0,
    )
    store.save_tournament(config)
    for harness in harnesses:
        store.save_harness_version(harness)
    seats = tuple(make_agent_id(index) for index in range(1, len(BASELINES) + 1))
    kinds = tuple(InfoProfileKind)
    for index, seed in enumerate(seeds):
        store.save_task(
            MatchTask(
                # Store.save_task reads the tournament id off the "<id>#<rest>"
                # task id prefix (pxe.store.db._tournament_id_of).
                task_id=f"{TOURNAMENT_ID}#{index:03d}",
                match_id=MATCH_ID if index == 0 else f"m-election-{seed}-01",
                template_id="election",
                seed=seed,
                agent_ids=seats,
                harness_keys=tuple(harness.key for harness in harnesses),
                profile_assignment=assign_profiles(agent_ids=seats, profile_kinds=kinds, seed_index=index),
            ),
            status="done" if index == 0 else "planned",
        )
    store.save_ratings(
        TOURNAMENT_ID,
        tuple(
            RatingRecord(harness_key=harness.key, mu=25.0 + index, sigma=8.333 - index * 0.3, matches=20 + index)
            for index, harness in enumerate(harnesses)
        ),
    )
    store.save_elites(
        TOURNAMENT_ID,
        (
            EliteCell(coords=(0, 1, 2), harness_key=harnesses[0].key, mu=27.0, descriptors=(500_000, 1_200, 3_400)),
            EliteCell(coords=(2, 0, 1), harness_key=harnesses[1].key, mu=26.0, descriptors=(300_000, 900, 2_100)),
        ),
    )
    if incidents:
        store.save_incidents(MATCH_ID, list(incidents))


@pytest.fixture(scope="session")
def recorded_runs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Play the reference match once and return its runs root."""
    runs_dir = tmp_path_factory.mktemp("api_runs")
    _play_reference(runs_dir)
    return runs_dir


@pytest.fixture(scope="session")
def api_app(recorded_runs: Path) -> FastAPI:
    """Build the application over the recorded runs root."""
    return create_app(runs_dir=recorded_runs)


@pytest.fixture(scope="session")
def client(api_app: FastAPI) -> Iterator[TestClient]:
    """A test client sharing one application, therefore one projection cache."""
    with TestClient(api_app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def journal(recorded_runs: Path) -> tuple[Any, ...]:
    """The recorded journal, read straight off disk for independent cross checks."""
    events = read_journal(artefact_paths(recorded_runs, MATCH_ID)["journal"])
    assert len(events) > 1000, "the reference journal is suspiciously short"
    return events


def _account_order(account_id: str) -> tuple[int, int]:
    """The canonical account order of CONTRACTS section 2.3: A1..An, then MM, then FEES."""
    if account_id.startswith("A") and account_id[1:].isdigit():
        return (0, int(account_id[1:]))
    return (1, 0) if account_id == "MM" else (2, 0)


def _await_frame(socket: Any, kind: str, *, limit: int = 200) -> dict[str, Any]:
    """Read frames until one of ``kind`` arrives, so a paced tick cannot mask a reply."""
    for _ in range(limit):
        frame = socket.receive_json()
        if frame["type"] == kind:
            return dict(frame)
    raise AssertionError(f"no {kind} frame in {limit} frames")


def _ok(client: TestClient, path: str) -> Any:
    """GET a path, assert ``200`` and return the decoded body."""
    response = client.get(path)
    assert response.status_code == 200, f"{path} answered {response.status_code}: {response.text[:400]}"
    return response.json()


# ---------------------------------------------------------------------------
# The route table and the read only guarantee
# ---------------------------------------------------------------------------
def test_every_route_of_section_7_21_exists(client: TestClient) -> None:
    """T4.1: every declared route answers with real data on the reference match."""
    assert len(ROUTE_TABLE) == 13, "the section 7.21 REST table has thirteen rows"
    for method, path in ROUTE_TABLE:
        response = client.request(method, path)
        assert response.status_code == 200, f"{method} {path} -> {response.status_code}: {response.text[:300]}"
        assert response.content, f"{method} {path} returned an empty body"
    # The WebSocket row of the same table.
    with client.websocket_connect(f"/ws/matches/{MATCH_ID}?speed=64&from_tick=1") as socket:
        assert socket.receive_json()["type"] == "hello"


def test_api_exposes_no_mutating_verb(client: TestClient, api_app: FastAPI) -> None:
    """CONTRACTS decision 33: no POST, PUT, PATCH or DELETE anywhere, on any path."""
    schema = api_app.openapi()
    assert schema["paths"], "the application declares no path at all"
    declared = {
        method.upper() for operations in schema["paths"].values() for method in operations if method != "parameters"
    }
    assert declared == {"GET"}, f"the schema declares a non GET verb: {sorted(declared)}"
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        for path in ("/api/health", f"/api/matches/{MATCH_ID}", f"/replay/{MATCH_ID}", "/anything/at/all"):
            response = client.request(method, path)
            assert response.status_code == 405, f"{method} {path} -> {response.status_code}"
            body = response.json()
            assert body["error"]["code"] == "READ_ONLY_API"
            assert body["error"]["detail"]["method"] == method


def test_error_bodies_have_one_shape(client: TestClient) -> None:
    """Section 7.21 rule 3: one error shape, the status carrying the class."""
    cases = (
        (404, "/api/matches/m-nope-1-01"),
        (404, f"/api/matches/{MATCH_ID}/ticks/9999"),
        (404, "/api/tournaments/T-nope-0000"),
        (400, f"/api/matches/{MATCH_ID}/decisions?q={'x' * (MAX_QUERY_CHARS + 1)}"),
        (400, f"/api/matches/{MATCH_ID}/decisions?limit=notanumber"),
    )
    for status, path in cases:
        response = client.get(path)
        assert response.status_code == status, f"{path} -> {response.status_code}"
        body = response.json()
        assert set(body) == {"error"}, body
        assert set(body["error"]) == {"code", "message", "detail"}, body
        assert body["error"]["code"], body
        assert body["error"]["message"], body
        assert isinstance(body["error"]["detail"], dict), body


# ---------------------------------------------------------------------------
# Match payloads
# ---------------------------------------------------------------------------
def test_health_reports_the_pinned_versions(client: TestClient) -> None:
    """The four versions a client pins itself against."""
    payload = Health.model_validate(_ok(client, "/api/health"))
    assert payload.status == "ok"
    assert payload.engine_version == ENGINE_VERSION
    assert payload.obs_version == OBS_VERSION
    assert payload.action_version == ACTION_VERSION
    assert payload.api_version == API_VERSION


def test_matches_page_lists_the_reference_match(client: TestClient) -> None:
    """``GET /api/matches`` finds the recorded match with its journalled facts."""
    page = _ok(client, "/api/matches")
    assert page["total"] >= 1, "no match was listed at all"
    ids = [row["match_id"] for row in page["items"]]
    assert MATCH_ID in ids, ids
    row = next(item for item in page["items"] if item["match_id"] == MATCH_ID)
    assert row["seed"] == SEED
    assert row["ticks_total"] == TICKS_TOTAL
    assert row["n_markets"] == N_MARKETS
    assert row["n_agents"] == len(BASELINES)
    assert row["finished"] is True
    assert len(row["journal_hash"]) == 64
    assert row["winner_agent_id"] and row["winner_harness_key"]
    assert row["tournament_id"] == TOURNAMENT_ID


def test_match_detail_comes_from_the_journal(client: TestClient, journal: tuple[Any, ...]) -> None:
    """Every field of ``MatchDetail`` is a journalled fact or a store row."""
    detail = MatchDetail.model_validate(_ok(client, f"/api/matches/{MATCH_ID}"))
    assert detail.event_count == len(journal)
    assert len(detail.markets) == N_MARKETS
    assert len(detail.agents) == len(BASELINES)
    assert len(detail.rankings) == len(BASELINES)
    assert [row.rank for row in detail.rankings] == sorted(row.rank for row in detail.rankings)
    assert detail.liquidity_profile_name == "standard"
    assert detail.talking_mode is False
    assert detail.config["seed"] == SEED
    assert detail.mm_config["quote_qty"] > 0
    # FR-5.2.1: correlated markets name each other, and at least one pair exists
    # in the election template.
    correlated = [market for market in detail.markets if market.correlated_with]
    assert correlated, "no correlated market in the reference world"
    for market in correlated:
        assert market.market_id not in market.correlated_with
    # Section 7.25: colours are assigned by seat, A1 gets 0, MM never gets one.
    for agent in detail.agents:
        assert agent.harness_key.count("@") == 1 and "+" in agent.harness_key
        assert agent.kind in ("llm", "scripted")
        assert agent.display_name
        if agent.ranked:
            assert 0 <= agent.colour_index <= 7
        else:
            assert agent.colour_index == -1
    assert detail.agents[0].agent_id == "A1"
    assert detail.agents[0].colour_index == 0


def test_tick_state_shape(client: TestClient) -> None:
    """T4.2: one payload carries markets, book, news, signals, trades and accounts."""
    busiest = max(
        (TickState.model_validate(_ok(client, f"/api/matches/{MATCH_ID}/ticks/{tick}")) for tick in range(1, 20)),
        key=lambda state: len(state.trades),
    )
    assert busiest.trades, "no tick between 1 and 19 carried a trade"
    assert busiest.markets and len(busiest.markets) == N_MARKETS
    assert busiest.accounts, "no PositionSnapshot reached the payload"
    assert busiest.predictions, "no PredictionRecorded reached the payload"
    assert busiest.open_market_ids
    assert any(market.bids or market.asks for market in busiest.markets), "the book was empty everywhere"
    assert any(market.mm_bid is not None for market in busiest.markets), "the market maker never quoted"
    for market in busiest.markets:
        assert 1 <= market.ref_price <= 99
        assert market.ref_source in ("mid", "last", "prior")
        assert len(market.bids) <= 3 and len(market.asks) <= 3
        assert all(1 <= level.price <= 99 and level.qty >= 1 for level in market.bids + market.asks)
    accounts = [row.account_id for row in busiest.accounts]
    assert accounts == sorted(accounts, key=_account_order), accounts
    assert "MM" in accounts and "FEES" in accounts
    # Any tick of the reference match publishes news at least somewhere.
    news_ticks = [
        tick
        for tick in range(1, 12)
        if TickState.model_validate(_ok(client, f"/api/matches/{MATCH_ID}/ticks/{tick}")).news
    ]
    assert news_ticks, "no news reached any tick payload"


def test_random_access_by_tick(client: TestClient) -> None:
    """T4.1: every tick of ``0..ticks_total + 1`` is reachable in any order."""
    order = [37, 1, 48, 0, 49, 12, 24, 2]
    for tick in order:
        state = TickState.model_validate(_ok(client, f"/api/matches/{MATCH_ID}/ticks/{tick}"))
        assert state.tick == tick
        assert state.match_id == MATCH_ID
    # Tick 0 is MatchStarted: every market open at its prior, no book, no snapshot.
    zero = TickState.model_validate(_ok(client, f"/api/matches/{MATCH_ID}/ticks/0"))
    assert len(zero.open_market_ids) == N_MARKETS
    assert all(market.ref_source == "prior" for market in zero.markets)
    assert all(not market.bids and not market.asks for market in zero.markets)
    # Finalisation resolves every market of the PRD default scenario.
    final = TickState.model_validate(_ok(client, f"/api/matches/{MATCH_ID}/ticks/{TICKS_TOTAL + 1}"))
    assert len(final.resolutions) == N_MARKETS, final.resolutions
    assert all(row.outcome in ("yes", "no") for row in final.resolutions)
    assert all(market.status == "resolved" for market in final.markets)
    assert client.get(f"/api/matches/{MATCH_ID}/ticks/{TICKS_TOTAL + 2}").status_code == 404
    assert client.get(f"/api/matches/{MATCH_ID}/ticks/-1").status_code == 404


def test_book_levels_agree_with_mark_to_market(client: TestClient, journal: tuple[Any, ...]) -> None:
    """The one derived field of ``MarketTick`` is checked against the journal.

    ``MarketTick.bids`` and ``.asks`` are the only numbers in a ``TickState``
    with no single journalled field behind them. This test folds the resting
    orders independently, asserts the fold reproduces every journalled
    ``best_bid``, ``best_ask``, ``bid_depth_qty`` and ``ask_depth_qty``, and
    then asserts the API serves the top three levels of that same fold.
    """
    resting: dict[str, list[Any]] = {}
    expected: dict[tuple[int, str], tuple[dict[int, int], dict[int, int]]] = {}
    marks = 0
    for event in journal:
        if isinstance(event, OrderPlaced):
            resting[event.order_id] = [event.market_id, event.side, event.price, event.qty]
        elif isinstance(event, TradeExecuted):
            for order_id in (event.maker_order_id, event.taker_order_id):
                row = resting.get(order_id)
                if row is None:
                    continue
                row[3] -= event.qty
                if row[3] <= 0:
                    resting.pop(order_id, None)
        elif isinstance(event, OrderCancelled):
            resting.pop(event.order_id, None)
        elif isinstance(event, MarkToMarket):
            bids: dict[int, int] = {}
            asks: dict[int, int] = {}
            for market_id, side, price, qty in resting.values():
                if market_id != event.market_id:
                    continue
                book = bids if side == "buy" else asks
                book[price] = book.get(price, 0) + qty
            assert (max(bids) if bids else None) == event.best_bid, (event.tick, event.market_id)
            assert (min(asks) if asks else None) == event.best_ask, (event.tick, event.market_id)
            assert sum(bids.values()) == event.bid_depth_qty, (event.tick, event.market_id)
            assert sum(asks.values()) == event.ask_depth_qty, (event.tick, event.market_id)
            expected[(event.tick, event.market_id)] = (bids, asks)
            marks += 1
    assert marks >= TICKS_TOTAL * N_MARKETS, f"only {marks} marks in the journal"
    non_empty = 0
    for tick in (5, 12, 24, 37, TICKS_TOTAL):
        state = TickState.model_validate(_ok(client, f"/api/matches/{MATCH_ID}/ticks/{tick}"))
        for market in state.markets:
            bids, asks = expected[(tick, market.market_id)]
            top_bids = sorted(bids, reverse=True)[:3]
            top_asks = sorted(asks)[:3]
            assert [level.price for level in market.bids] == top_bids, (tick, market.market_id)
            assert [level.qty for level in market.bids] == [bids[price] for price in top_bids]
            assert [level.price for level in market.asks] == top_asks, (tick, market.market_id)
            assert [level.qty for level in market.asks] == [asks[price] for price in top_asks]
            non_empty += 1 if market.bids or market.asks else 0
    assert non_empty > 0, "every sampled book was empty, the check proved nothing"


def test_series_length_equals_ticks_total(client: TestClient) -> None:
    """CONTRACTS section 9: every per tick series has length ``ticks_total``."""
    series = MatchSeries.model_validate(_ok(client, f"/api/matches/{MATCH_ID}/series"))
    assert series.ticks_total == TICKS_TOTAL
    assert len(series.equity_cents) == len(BASELINES)
    assert len(series.cash_cents) == len(BASELINES)
    assert len(series.ref_price) == N_MARKETS
    assert len(series.rank) == len(BASELINES)
    for row in series.equity_cents + series.cash_cents + series.rank:
        assert len(row.values) == TICKS_TOTAL, (row.agent_id, len(row.values))
    for row in series.ref_price:
        assert len(row.values) == TICKS_TOTAL
        assert all(1 <= value <= 99 for value in row.values)
    # The live leaderboard is 1 based and covers every seat at every tick.
    for index in range(TICKS_TOTAL):
        ranks = sorted(row.values[index] for row in series.rank)
        assert ranks[0] == 1, (index, ranks)
        assert all(1 <= value <= len(BASELINES) for value in ranks)
    # Anti-vacuous: equity actually moves, so the race has something to draw.
    assert any(len(set(row.values)) > 1 for row in series.equity_cents)


def test_series_filters_by_agent_and_market(client: TestClient) -> None:
    """The repeatable ``agent_id`` and ``market_id`` query parameters select rows."""
    filtered = MatchSeries.model_validate(
        _ok(client, f"/api/matches/{MATCH_ID}/series?agent_id=A1&agent_id=A2&market_id=M3")
    )
    assert [row.agent_id for row in filtered.equity_cents] == ["A1", "A2"]
    assert [row.agent_id for row in filtered.rank] == ["A1", "A2"]
    assert [row.market_id for row in filtered.ref_price] == ["M3"]
    assert len(filtered.equity_cents[0].values) == TICKS_TOTAL


def test_metrics_payload_carries_reliability_curves(client: TestClient, recorded_runs: Path) -> None:
    """The metrics route serves ``metrics.json`` plus one reliability curve per agent.

    Section 7.17's ruling R75: every number of the payload except the curve is
    read from the file, and the curve is ``reliability_curve`` over the
    projection the route already holds. The file comparison below is what keeps
    "one file read, no join" honest, because a route that recomputed the whole
    block from the journal would pass every other assertion here.
    """
    payload = MatchMetricsPayload.model_validate(_ok(client, f"/api/matches/{MATCH_ID}/metrics"))
    on_disk = read_metrics(artefact_paths(recorded_runs, MATCH_ID)["metrics"])
    assert on_disk.performance, "metrics.json holds no performance block"
    assert [row.model_dump() for row in payload.performance] == [
        {
            "agent_id": row.agent_id,
            "pnl_cents": row.pnl_cents,
            "pnl_bps": row.pnl_bps,
            "sharpe_milli": row.sharpe_milli,
            "max_drawdown_cents": row.max_drawdown_cents,
            "max_drawdown_bps": row.max_drawdown_bps,
            "volume_qty": row.volume_qty,
            "trade_count": row.trade_count,
            "maker_trade_count": row.maker_trade_count,
            "fees_paid_cents": row.fees_paid_cents,
        }
        for row in on_disk.performance
    ]
    assert [(row.agent_id, row.brier_ppm, row.n_terms, row.n_carried) for row in payload.calibration] == [
        (row.agent_id, row.brier_ppm, row.n_terms, row.n_carried) for row in on_disk.calibration
    ]
    assert [tuple(row.model_dump().values()) for row in payload.descriptors] == [
        (row.agent_id, *row.as_tuple()) for row in on_disk.descriptors
    ]
    assert len(payload.performance) == len(BASELINES)
    assert len(payload.calibration) == len(BASELINES)
    assert len(payload.descriptors) == len(BASELINES)
    assert any(row.trade_count > 0 for row in payload.performance), "no agent traded"
    assert any(row.volume_qty > 0 for row in payload.performance)
    assert all(row.n_terms > 0 for row in payload.calibration), "an agent produced no Brier term"
    assert any(row.reliability for row in payload.calibration), "no reliability curve was built"
    for row in payload.calibration:
        for bucket in row.reliability:
            assert 0 <= bucket.bin_upper_ppm <= 1_000_000
            assert 0 <= bucket.observed_yes_ppm <= 1_000_000
    assert all(0 <= row.maker_ratio_ppm <= 1_000_000 for row in payload.descriptors)
    # The API serves what the projection served, never a recomputation of its own.
    detail = MatchDetail.model_validate(_ok(client, f"/api/matches/{MATCH_ID}"))
    assert payload.mm_pnl_cents == detail.mm_pnl_cents
    assert payload.fees_collected_cents == detail.fees_collected_cents


def test_highlights_and_incidents_are_served(client: TestClient) -> None:
    """PRD section 9: annotated marking events, and the integrity alerts beside them."""
    highlights = _ok(client, f"/api/matches/{MATCH_ID}/highlights")["highlights"]
    assert highlights, "the reference match produced no highlight"
    kinds = {row["kind"] for row in highlights}
    assert kinds <= {"big_trade", "early_resolution", "integrity_alert", "bankruptcy"}
    assert all(row["label"] for row in highlights), "a highlight has no label, AC-P7 needs one"
    assert all(0 <= row["tick"] <= TICKS_TOTAL + 1 for row in highlights)
    one_kind = sorted(kinds)[0]
    filtered = _ok(client, f"/api/matches/{MATCH_ID}/highlights?kind={one_kind}")["highlights"]
    assert filtered and {row["kind"] for row in filtered} == {one_kind}
    incidents = _ok(client, f"/api/matches/{MATCH_ID}/incidents")["incidents"]
    assert incidents, "the detectors found nothing on the reference match"
    for row in incidents:
        assert row["match_id"] == MATCH_ID
        assert row["incident_id"] and row["kind"] and row["severity"]
        assert row["detector_version"]
        assert isinstance(row["detail"], dict)


def test_events_page_is_the_verbatim_journal(client: TestClient, journal: tuple[Any, ...]) -> None:
    """``JournalEvent`` is one journal line, verbatim, envelope included."""
    page = _ok(client, f"/api/matches/{MATCH_ID}/events?limit=20000")
    assert page["total"] == len(journal)
    assert len(page["items"]) == len(journal)
    for served, event in zip(page["items"], journal, strict=True):
        assert served == dict(event.to_dict())
    first = page["items"][0]
    assert first["type"] == "match_started" and first["seq"] == 1 and first["tick"] == 0
    # Tick and type filters.
    trades = _ok(client, f"/api/matches/{MATCH_ID}/events?types=trade_executed&limit=20000")
    assert trades["total"] > 100, trades["total"]
    assert {row["type"] for row in trades["items"]} == {"trade_executed"}
    window = _ok(client, f"/api/matches/{MATCH_ID}/events?from_tick=5&to_tick=5&limit=20000")
    assert window["total"] > 0
    assert {row["tick"] for row in window["items"]} == {5}
    paged = _ok(client, f"/api/matches/{MATCH_ID}/events?limit=10&offset=3")
    assert len(paged["items"]) == 10
    assert paged["items"][0]["seq"] == 4


# ---------------------------------------------------------------------------
# The decision journal (T4.4)
# ---------------------------------------------------------------------------
def test_decisions_cover_every_agent_and_tick(client: TestClient) -> None:
    """One row per ``(tick, agent)`` that produced an action, in ``(tick, agent_id)`` order."""
    page = _ok(client, f"/api/matches/{MATCH_ID}/decisions?limit=5000")
    rows = [Decision.model_validate(row) for row in page["items"]]
    assert rows, "no decision row at all"
    assert page["total"] == TICKS_TOTAL * len(BASELINES), page["total"]
    keys = [(row.tick, row.agent_id) for row in rows]
    assert keys == sorted(keys, key=lambda key: (key[0], int(key[1][1:])))
    assert all(row.headline for row in rows), "a decision row has no headline to search"
    assert all(row.source in ("llm", "scripted", "fallback") for row in rows)
    assert any(row.orders for row in rows), "no decision carried an order"
    assert any(row.predictions for row in rows), "no decision carried a prediction"
    outcomes = {order.outcome for row in rows for order in row.orders}
    assert outcomes, "no order outcome was reported"
    assert outcomes <= {"filled", "partial", "resting", "rejected", "cancelled"}
    for row in rows:
        for prediction in row.predictions:
            assert 0 <= prediction.p_yes_ppm <= 1_000_000
            assert isinstance(prediction.carried, bool)
    filtered = _ok(client, f"/api/matches/{MATCH_ID}/decisions?agent_id=A1&from_tick=3&to_tick=7&limit=5000")
    assert filtered["total"] == 5, filtered["total"]
    assert {row["agent_id"] for row in filtered["items"]} == {"A1"}
    assert {row["tick"] for row in filtered["items"]} == {3, 4, 5, 6, 7}


def test_decisions_text_search(client: TestClient) -> None:
    """Section 7.21: ``q`` is a case insensitive NFKC substring, never ranked or tokenised."""
    everything = _ok(client, f"/api/matches/{MATCH_ID}/decisions?limit=5000")["items"]
    assert everything, "no decision row to search"
    hit = _ok(client, f"/api/matches/{MATCH_ID}/decisions?q=M3&limit=5000")
    assert hit["total"] > 0, "the substring M3 matched nothing"
    assert all("m3" in row["headline"].casefold() for row in hit["items"])
    # Case insensitive: the lower case spelling finds exactly the same rows.
    lower = _ok(client, f"/api/matches/{MATCH_ID}/decisions?q=m3&limit=5000")
    assert [(row["tick"], row["agent_id"]) for row in lower["items"]] == [
        (row["tick"], row["agent_id"]) for row in hit["items"]
    ]
    # Ordering is preserved, not re-ranked.
    keys = [(row["tick"], row["agent_id"]) for row in hit["items"]]
    assert keys == sorted(keys, key=lambda key: (key[0], int(key[1][1:])))
    # A regex is treated as a literal, because q is not a regex.
    assert _ok(client, f"/api/matches/{MATCH_ID}/decisions?q=.%2B&limit=5000")["total"] == 0
    assert _ok(client, f"/api/matches/{MATCH_ID}/decisions?q=scripted&limit=5000")["total"] == len(everything)
    assert client.get(f"/api/matches/{MATCH_ID}/decisions?q={'x' * (MAX_QUERY_CHARS + 1)}").status_code == 400


def test_decisions_carry_trade_ids(client: TestClient) -> None:
    """T4.4: navigation tick to trade. Every id resolves to a trade of that tick."""
    rows = [
        Decision.model_validate(row) for row in _ok(client, f"/api/matches/{MATCH_ID}/decisions?limit=5000")["items"]
    ]
    with_trades = [row for row in rows if row.trade_ids]
    assert with_trades, "no decision row links to a trade"
    for row in with_trades[:20]:
        state = TickState.model_validate(_ok(client, f"/api/matches/{MATCH_ID}/ticks/{row.tick}"))
        available = {trade.trade_id for trade in state.trades}
        assert set(row.trade_ids) <= available, (row.tick, row.agent_id)
        for trade in state.trades:
            if trade.trade_id in row.trade_ids:
                assert row.agent_id in (trade.maker_agent_id, trade.taker_agent_id)


# ---------------------------------------------------------------------------
# The tournament view (T4.3)
# ---------------------------------------------------------------------------
def test_tournament_view_payload(client: TestClient) -> None:
    """T4.3 and T5.2: leaderboard, elites, progression, incidents, costs, balance, KPIs."""
    page = _ok(client, "/api/tournaments")
    assert page["total"] >= 1, "no tournament was listed"
    assert TOURNAMENT_ID in [row["tournament_id"] for row in page["items"]]
    TournamentSummary.model_validate(page["items"][0])
    detail = TournamentDetail.model_validate(_ok(client, f"/api/tournaments/{TOURNAMENT_ID}"))
    assert detail.tournament_id == TOURNAMENT_ID
    assert detail.format == "round_robin"
    assert detail.n_harnesses == len(BASELINES)
    assert detail.seeds and SEED in detail.seeds
    assert detail.n_matches >= 1
    # Leaderboard, best mu first, with a drawable interval.
    assert len(detail.leaderboard) == len(BASELINES)
    assert [row.rank for row in detail.leaderboard] == list(range(1, len(BASELINES) + 1))
    mus = [row.mu for row in detail.leaderboard]
    assert mus == sorted(mus, reverse=True), mus
    for row in detail.leaderboard:
        assert row.ci_low < row.mu < row.ci_high
        assert row.sigma > 0 and row.matches > 0
    # Per version progression curves (PRD section 9).
    assert detail.progression, "no progression curve"
    assert all(row.points for row in detail.progression)
    assert all(point.version for row in detail.progression for point in row.points)
    # The MAP-Elites grid reaches the UI (T5.2).
    assert detail.elites.cells, "the archive is empty"
    assert len(detail.elites.axes) == len(detail.elites.cells[0].coords)
    assert len(detail.elites.bins) == len(detail.elites.axes)
    assert all(cell.harness_key for cell in detail.elites.cells)
    # Integrity alerts, costs, cost of liquidity, Latin square residual, KPIs.
    assert detail.incidents, "no integrity alert reached the tournament view"
    # Every alert names its replay: a tournament view spans many matches, and an
    # empty match_id is a link the UI cannot build (section 7.21's Incident).
    assert all(row.match_id == MATCH_ID for row in detail.incidents)
    assert detail.costs_usd and len(detail.costs_usd) == len(BASELINES)
    assert detail.liquidity_cost_cents, "the cost of liquidity is missing"
    assert detail.liquidity_cost_cents[0].profile == "standard"
    assert detail.profile_balance.seats == len(BASELINES)
    assert detail.profile_balance.seeds > 0
    names = [row.name for row in detail.kpis]
    assert names == [
        "cost_per_match_usd_milli",
        "cost_per_tournament_usd_milli",
        "matches_per_night",
        "clean_completion_ppm",
        "sigma_shrink_ppm",
        "heldout_gain_mu_milli",
        "liquidity_cost_cents_per_match",
    ], names
    assert all(isinstance(row.value_ppm, int) for row in detail.kpis)
    assert {row.unit for row in detail.kpis} <= {"milli_usd", "count", "ppm", "milli", "cents"}


# ---------------------------------------------------------------------------
# The share link (T4.5)
# ---------------------------------------------------------------------------
def test_share_page_is_self_contained(client: TestClient) -> None:
    """AC-P7 and T4.5: a plain read only URL, no query string, no external reference."""
    response = client.get(f"/replay/{MATCH_ID}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert body.strip(), "the share page is empty"
    assert MATCH_ID in body, "the share page does not name the match it opens"
    lowered = body.lower()
    for marker in ("http://", "https://", "//cdn", "<iframe"):
        assert marker not in lowered, f"the share page references {marker}"
    assert "<form" not in lowered, "a read only page carries no form"
    assert client.get("/replay/m-nope-1-01").status_code == 404


# ---------------------------------------------------------------------------
# The WebSocket protocol
# ---------------------------------------------------------------------------
def test_ws_hello_snapshot_then_ticks_then_ended(client: TestClient) -> None:
    """The frame sequence of section 7.21, from ``hello`` to ``ended``."""
    with client.websocket_connect(f"/ws/matches/{MATCH_ID}?speed=64&from_tick=1") as socket:
        hello = socket.receive_json()
        assert hello["type"] == "hello"
        assert hello["match_id"] == MATCH_ID
        assert hello["ticks_total"] == TICKS_TOTAL
        assert hello["speed"] == 64
        assert hello["from_tick"] == 1
        assert hello["api_version"] == API_VERSION
        assert hello["engine_version"] == ENGINE_VERSION
        snapshot = socket.receive_json()
        assert snapshot["type"] == "snapshot" and snapshot["tick"] == 1
        assert snapshot["state"]["markets"], "the snapshot carries no market"
        ticks: list[int] = []
        highlights = 0
        pending_highlight = False
        ended: dict[str, Any] | None = None
        while ended is None:
            frame = socket.receive_json()
            if frame["type"] == "highlight":
                highlights += 1
                pending_highlight = True
                assert frame["highlight"]["label"]
            elif frame["type"] == "tick":
                if pending_highlight:
                    # A highlight is sent immediately before the tick it belongs to.
                    pending_highlight = False
                ticks.append(frame["tick"])
                assert frame["state"]["tick"] == frame["tick"]
            elif frame["type"] == "ended":
                ended = frame
            else:  # pragma: no cover - defensive
                raise AssertionError(f"unexpected frame {frame['type']}")
        assert ticks == list(range(2, TICKS_TOTAL + 2)), ticks[:5]
        assert highlights > 0, "no highlight was interleaved"
        assert ended["final_tick"] == TICKS_TOTAL
        assert len(ended["rankings"]) == len(BASELINES)
        assert ended["rankings"][0]["rank"] == 1
        assert ended["rankings"][0]["harness_key"]
        assert isinstance(ended["mm_pnl_cents"], int)
        assert isinstance(ended["fees_collected_cents"], int)
        # The socket stays open after `ended`.
        socket.send_json({"type": "ping", "t": 99})
        assert socket.receive_json() == {"type": "pong", "t": 99}


def test_ws_tick_frame_equals_rest_tick(client: TestClient) -> None:
    """Section 7.21: the two paths serve byte identical ``TickState`` for a tick."""
    tick = 7
    rest = client.get(f"/api/matches/{MATCH_ID}/ticks/{tick}")
    assert rest.status_code == 200
    assert rest.content, "the REST tick body is empty"
    with client.websocket_connect(f"/ws/matches/{MATCH_ID}?speed=64&from_tick={tick}") as socket:
        assert socket.receive_json()["type"] == "hello"
        raw = socket.receive_text()
    prefix = f'{{"type":"snapshot","tick":{tick},"state":'
    assert raw.startswith(prefix), raw[:80]
    state_bytes = raw[len(prefix) : -1].encode("utf-8")
    assert state_bytes == rest.content, "the socket and the route disagree byte for byte"


def test_ws_seek_and_speed(client: TestClient) -> None:
    """``seek`` answers with one ``snapshot``; ``speed`` takes effect on the next tick."""
    with client.websocket_connect(f"/ws/matches/{MATCH_ID}?speed=1&from_tick=1") as socket:
        assert socket.receive_json()["type"] == "hello"
        assert socket.receive_json()["type"] == "snapshot"
        socket.send_json({"type": "pause"})
        socket.send_json({"type": "seek", "tick": 30})
        frame = socket.receive_json()
        assert frame["type"] == "snapshot" and frame["tick"] == 30
        assert frame["state"]["tick"] == 30
        # A seek is clamped into 0..ticks_total + 1 at both ends.
        socket.send_json({"type": "seek", "tick": 10_000})
        assert _await_frame(socket, "snapshot")["tick"] == TICKS_TOTAL + 1
        socket.send_json({"type": "seek", "tick": -5})
        assert _await_frame(socket, "snapshot")["tick"] == 0
        # Resume fast from a known position and check the cursor followed.
        socket.send_json({"type": "seek", "tick": TICKS_TOTAL - 3})
        assert _await_frame(socket, "snapshot")["tick"] == TICKS_TOTAL - 3
        socket.send_json({"type": "speed", "speed": 64})
        socket.send_json({"type": "play"})
        seen: list[int] = []
        while len(seen) < 4:
            frame = socket.receive_json()
            if frame["type"] == "tick":
                seen.append(frame["tick"])
        assert seen == [TICKS_TOTAL - 2, TICKS_TOTAL - 1, TICKS_TOTAL, TICKS_TOTAL + 1], seen
        # An illegal speed is refused with an error frame and the socket lives.
        socket.send_json({"type": "speed", "speed": 3})
        error = _await_frame(socket, "error")
        assert error["code"] == "INVALID_SPEED"
        socket.send_json({"type": "ping", "t": 5})
        assert _await_frame(socket, "pong")["t"] == 5


@pytest.mark.parametrize("speed", WS_SPEEDS)
def test_ws_every_legal_speed_streams(client: TestClient, speed: int) -> None:
    """All seven of ``1, 2, 4, 8, 16, 32, 64`` are accepted and stream in order."""
    start = TICKS_TOTAL - 1
    with client.websocket_connect(f"/ws/matches/{MATCH_ID}?speed={speed}&from_tick={start}") as socket:
        hello = socket.receive_json()
        assert hello["type"] == "hello" and hello["speed"] == speed
        assert socket.receive_json()["type"] == "snapshot"
        ticks: list[int] = []
        while len(ticks) < 2:
            frame = socket.receive_json()
            if frame["type"] == "tick":
                ticks.append(frame["tick"])
                assert frame["state"]["tick"] == frame["tick"]
        assert ticks == [start + 1, start + 2], ticks


@pytest.mark.parametrize("speed", [0, 3, 5, 63, 128, -1])
def test_ws_illegal_speed_closes_4400(client: TestClient, speed: int) -> None:
    """Any speed outside the seven legal values closes the socket with ``4400``."""
    # Starlette raises WebSocketDisconnect, whose type is an implementation
    # detail; the contract is the close code, which is asserted below.
    with (
        pytest.raises(Exception) as caught,
        client.websocket_connect(f"/ws/matches/{MATCH_ID}?speed={speed}") as socket,
    ):
        frame = socket.receive_json()
        assert frame["type"] == "error" and frame["code"] == "INVALID_SPEED"
        socket.receive_json()
    assert getattr(caught.value, "code", None) == CLOSE_BAD_PARAMETER


@pytest.mark.parametrize("from_tick", [-1, TICKS_TOTAL + 2, 1000])
def test_ws_illegal_from_tick_closes_4400(client: TestClient, from_tick: int) -> None:
    """``from_tick`` outside ``0..ticks_total + 1`` closes the socket with ``4400``."""
    with (
        pytest.raises(Exception) as caught,
        client.websocket_connect(f"/ws/matches/{MATCH_ID}?from_tick={from_tick}") as socket,
    ):
        frame = socket.receive_json()
        assert frame["type"] == "error" and frame["code"] == "INVALID_TICK"
        socket.receive_json()
    assert getattr(caught.value, "code", None) == CLOSE_BAD_PARAMETER


@pytest.mark.parametrize("from_tick", [0, TICKS_TOTAL + 1])
def test_ws_from_tick_accepts_the_two_virtual_ticks(client: TestClient, from_tick: int) -> None:
    """Section 7.21: ``0`` (the opening configuration) and ``T + 1`` (finalisation)."""
    with client.websocket_connect(f"/ws/matches/{MATCH_ID}?speed=64&from_tick={from_tick}") as socket:
        assert socket.receive_json()["type"] == "hello"
        snapshot = socket.receive_json()
        assert snapshot["type"] == "snapshot" and snapshot["tick"] == from_tick
        assert snapshot["state"]["markets"], "the virtual tick carries no market"
        if from_tick == TICKS_TOTAL + 1:
            # Nothing left to stream: the stream ends immediately and stays open.
            assert socket.receive_json()["type"] == "ended"
            socket.send_json({"type": "ping", "t": 1})
            assert socket.receive_json() == {"type": "pong", "t": 1}


def test_ws_unknown_match_closes_4404(client: TestClient) -> None:
    """An unknown match id closes the socket with ``4404``."""
    with (
        pytest.raises(Exception) as caught,
        client.websocket_connect("/ws/matches/m-nope-1-01") as socket,
    ):
        socket.receive_json()
    assert getattr(caught.value, "code", None) == CLOSE_UNKNOWN_MATCH


def test_ws_bad_client_frame_keeps_the_socket_open(client: TestClient) -> None:
    """A bad client frame produces an ``error`` frame and the socket stays open."""
    with client.websocket_connect(f"/ws/matches/{MATCH_ID}?speed=64&from_tick={TICKS_TOTAL + 1}") as socket:
        assert socket.receive_json()["type"] == "hello"
        assert socket.receive_json()["type"] == "snapshot"
        assert socket.receive_json()["type"] == "ended"
        for payload in ("not json at all", "[1,2,3]", '{"type":"nope"}', '{"type":"seek"}'):
            socket.send_text(payload)
            frame = socket.receive_json()
            if payload == '{"type":"seek"}':
                # A seek with no tick keeps the cursor and still answers a snapshot.
                assert frame["type"] == "snapshot"
                continue
            assert frame["type"] == "error", (payload, frame)
            assert frame["code"] == "INVALID_FRAME"
            assert frame["message"]
        socket.send_json({"type": "ping", "t": 42})
        assert socket.receive_json() == {"type": "pong", "t": 42}


def test_ws_client_disconnects_mid_stream(client: TestClient) -> None:
    """A client that vanishes mid stream is normal, not an error, and the server survives."""
    for _attempt in range(3):
        with client.websocket_connect(f"/ws/matches/{MATCH_ID}?speed=64&from_tick=1") as socket:
            assert socket.receive_json()["type"] == "hello"
            assert socket.receive_json()["type"] == "snapshot"
            frame = socket.receive_json()
            assert frame["type"] in ("tick", "highlight")
            # Leaving the context manager closes the socket while frames are due.
    assert client.get("/api/health").status_code == 200
    with client.websocket_connect(f"/ws/matches/{MATCH_ID}?speed=64&from_tick=1") as socket:
        assert socket.receive_json()["type"] == "hello"


def test_ws_pause_stops_the_stream_without_closing_it(client: TestClient) -> None:
    """A ``pause`` followed by silence is fine: only ``pong`` answers, nothing closes."""
    with client.websocket_connect(f"/ws/matches/{MATCH_ID}?speed=1&from_tick=1") as socket:
        assert socket.receive_json()["type"] == "hello"
        assert socket.receive_json()["type"] == "snapshot"
        socket.send_json({"type": "pause"})
        socket.send_json({"type": "ping", "t": 1})
        # Drain whatever was already due, then the pong must arrive.
        for _ in range(10):
            frame = socket.receive_json()
            if frame["type"] == "pong":
                assert frame["t"] == 1
                break
        else:  # pragma: no cover - defensive
            raise AssertionError("no pong after a pause")
        socket.send_json({"type": "ping", "t": 2})
        assert socket.receive_json() == {"type": "pong", "t": 2}


# ---------------------------------------------------------------------------
# T4.1's numbered requirement
# ---------------------------------------------------------------------------
@pytest.mark.slow
def test_reference_match_tick_under_100ms(client: TestClient) -> None:
    """T4.1: under 100 ms per replay request on the reference match, warm.

    Fifty ``GET .../ticks/{tick}`` calls over the 6 by 48 reference match, in a
    scattered tick order so the measurement is a random access and not a warm
    single entry. The median is the contracted number; p95 is reported too,
    because a median under budget with a pathological tail is not a usable API.
    """
    path = f"/api/matches/{MATCH_ID}/ticks/1"
    assert client.get(path).status_code == 200, "the cache could not even be warmed"
    samples: list[float] = []
    for index in range(50):
        tick = (index * 17) % (TICKS_TOTAL + 2)
        started = time.perf_counter()
        response = client.get(f"/api/matches/{MATCH_ID}/ticks/{tick}")
        samples.append((time.perf_counter() - started) * 1000.0)
        assert response.status_code == 200
        assert len(response.content) > 200, "a tick payload came back suspiciously small"
    ordered = sorted(samples)
    p50 = statistics.median(ordered)
    p95 = ordered[int(0.95 * (len(ordered) - 1))]
    print(f"\ntick latency over {len(samples)} warm requests: p50={p50:.2f} ms p95={p95:.2f} ms")
    assert p50 < TICK_BUDGET_MS, f"median {p50:.2f} ms is over the {TICK_BUDGET_MS} ms budget"
    assert p95 < TICK_BUDGET_MS * 2, f"p95 {p95:.2f} ms has a pathological tail"


@pytest.mark.slow
def test_cold_projection_under_two_seconds(recorded_runs: Path) -> None:
    """Section 7.21: the cold path is bounded, so the cache cannot hide a bad first request."""
    app = create_app(runs_dir=recorded_runs)
    with TestClient(app) as cold:
        started = time.perf_counter()
        response = cold.get(f"/api/matches/{MATCH_ID}/ticks/24")
        elapsed = time.perf_counter() - started
        assert response.status_code == 200
        payload = TickState.model_validate(response.json())
        assert payload.markets and payload.accounts, "the cold request served an empty tick"
    print(f"\ncold first tick request: {elapsed * 1000:.1f} ms")
    assert elapsed < COLD_BUDGET_S, f"the cold path took {elapsed:.2f}s, over the {COLD_BUDGET_S}s bound"


@pytest.mark.slow
def test_cache_is_bounded_and_evicts_the_least_recently_used(recorded_runs: Path, tmp_path: Path) -> None:
    """Section 7.21: the LRU holds eight match views and evicts the oldest.

    Three distinct match ids are needed to see an eviction at all, and one
    recorded match is all the session has, so the recorded artefacts are copied
    under two extra ids. The copies are real journals on disk, which is what the
    service reads; only the cache key differs, and the cache key is the subject.
    """
    assert MATCH_CACHE_SIZE == 8, "section 7.21 fixes the default LRU at eight entries"
    runs = tmp_path / "lru_runs"
    source = match_dir(recorded_runs, MATCH_ID)
    assert (source / "journal.jsonl").exists(), "the recorded match was never written"
    ids = (MATCH_ID, "m-election-20260827-02", "m-election-20260827-03")
    for match_id in ids:
        shutil.copytree(source, match_dir(runs, match_id))
    with Store(runs_dir=runs) as store:
        store.init_schema()
        service = ReplayService(runs_dir=runs, store=store, cache_size=2)
        for match_id in ids:
            assert service.view(match_id).ticks_total == TICKS_TOTAL, match_id
        # The bound is the behaviour under test, so the private map is the subject.
        assert len(service._cache) == 2, "the LRU grew past its bound"
        assert tuple(service._cache) == ids[1:], "the least recently used view was not the one evicted"
        # Touching the older survivor makes the newer one the eviction candidate.
        service.view(ids[1])
        service.view(MATCH_ID)
        assert tuple(service._cache) == (ids[1], MATCH_ID)


# ---------------------------------------------------------------------------
# Generated artefacts: docs/REPLAY_API.md and web/tests/fixtures/*.json
# ---------------------------------------------------------------------------
def test_openapi_document_is_generated_from_the_app(api_app: FastAPI) -> None:
    """``pxe api openapi`` renders ``docs/REPLAY_API.md`` from the real schema."""
    document = render_replay_api_markdown(api_app)
    assert document.startswith("# Replay API")
    # Built by escape so this assertion does not itself trip the repo-wide style
    # rule in tests/test_style_rules.py, which scans sources for the literal.
    em_dash = chr(0x2014)
    assert em_dash not in document, "contract rule 4: no em-dash in produced content"
    for _method, path in ROUTE_TABLE:
        template = path.replace(MATCH_ID, "{match_id}").replace(TOURNAMENT_ID, "{tournament_id}")
        template = template.split("?")[0]
        if template.endswith("/ticks/1"):
            template = template.replace("/ticks/1", "/ticks/{tick}")
        assert f"`{template}`" in document, template
    for name in ("TickState", "MatchDetail", "Decision", "TournamentDetail", "MatchSeries", "Highlight"):
        assert f"### `{name}`" in document, name
    assert "| WS | `/ws/matches/{match_id}`" in document
    assert "Derived fields" in document
    committed = Path(__file__).resolve().parents[1] / "docs" / "REPLAY_API.md"
    assert committed.exists(), "docs/REPLAY_API.md has not been generated"
    assert committed.read_text(encoding="utf-8").startswith("# Replay API")


def test_fixtures_are_generated_from_the_real_api(api_app: FastAPI, tmp_path: Path) -> None:
    """Section 7.25: A24 builds on samples produced by the real API, never by hand."""
    written = write_sample_fixtures(
        api_app, match_id=MATCH_ID, out_dir=tmp_path / "fixtures", tournament_id=TOURNAMENT_ID
    )
    assert written, "no fixture was written"
    assert tuple(sorted(path.stem for path in written)) == FIXTURE_NAMES
    models: dict[str, type[BaseModel]] = {
        "match_detail": MatchDetail,
        "tick_state": TickState,
        "tick_state_zero": TickState,
        "tick_state_final": TickState,
        "match_series": MatchSeries,
        "match_metrics": MatchMetricsPayload,
        "tournament_detail": TournamentDetail,
        "health": Health,
    }
    for path in written:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload, f"{path.name} is empty"
        model = models.get(path.stem)
        if model is not None:
            model.model_validate(payload)
    ws_frames = json.loads((tmp_path / "fixtures" / "ws_frames.json").read_text(encoding="utf-8"))
    assert set(ws_frames) == {"hello", "snapshot", "tick", "highlight", "ended", "error", "pong"}
    assert ws_frames["tick"]["state"]["markets"], "the sample tick frame carries no market"


def test_committed_fixtures_match_the_current_payloads() -> None:
    """The committed samples parse against today's models and name the reference match."""
    assert FIXTURES_DIR.exists(), f"{FIXTURES_DIR} has not been generated"
    present = tuple(sorted(path.stem for path in FIXTURES_DIR.glob("*.json")))
    assert present == FIXTURE_NAMES, present
    detail = MatchDetail.model_validate(json.loads((FIXTURES_DIR / "match_detail.json").read_text(encoding="utf-8")))
    assert detail.match_id == MATCH_ID
    assert detail.ticks_total == TICKS_TOTAL
    assert detail.rankings, "the committed match_detail has no ranking"
    state = TickState.model_validate(json.loads((FIXTURES_DIR / "tick_state.json").read_text(encoding="utf-8")))
    assert state.match_id == MATCH_ID
    assert state.markets and state.accounts
    series = MatchSeries.model_validate(json.loads((FIXTURES_DIR / "match_series.json").read_text(encoding="utf-8")))
    assert len(series.equity_cents[0].values) == series.ticks_total
    tournament = TournamentDetail.model_validate(
        json.loads((FIXTURES_DIR / "tournament_detail.json").read_text(encoding="utf-8"))
    )
    assert tournament.leaderboard and tournament.kpis
