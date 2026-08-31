"""Tests for the read-only API (W12).

We run one real scripted match into a temporary runs directory, then exercise every route against it
with ``TestClient``. The match is produced by the runner exactly as production would, so the endpoints
are tested against a genuine journal rather than a hand-built fixture. The WebSocket replay is checked
tick by tick. Nothing here mutates a match; the API has no verb that could.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ala.api import create_app
from ala.gateway import ScriptedGateway
from ala.journal import Journal
from ala.rng import RngTree
from ala.runner import run_match
from ala.scenario import make_scenario
from ala.scenario.base import WorldSpec
from ala.types import MatchConfig

_SEED = 42
_MATCH_ID = "m-concours-42"
_SPECS = {
    "seat-01": "grinder",
    "seat-02": "allier",
    "seat-03": "raider",
    "seat-04": "forger",
}


def _run_one_match(runs_dir: Path) -> str:
    """Run a full concours match into ``<runs_dir>/<match_id>/journal.jsonl`` and return the match id."""
    match_dir = runs_dir / _MATCH_ID
    match_dir.mkdir(parents=True, exist_ok=True)
    config = MatchConfig(
        scenario="concours",
        seed=_SEED,
        agent_specs=tuple(_SPECS.values()),
        ticks=12,
        cull_every=6,
        start_budget=100,
        floor_start=15,
        floor_step=10,
        clone_top_k=1,
    )
    # A defect-certain world so escalation is reachable, matching the calibration match.
    spec = WorldSpec(start_budget=100, sudoers_defect_rate_pct=100, impossible_task_rate_pct=20)
    rng = RngTree(config.seed)
    gateway = ScriptedGateway(_SPECS, rng)
    scenario = make_scenario("concours", spec)
    journal = Journal(match_dir / "journal.jsonl")
    run_match(config, gateway, scenario, journal, rng)
    journal.close()
    return _MATCH_ID


def _client(tmp_path: Path) -> tuple[TestClient, str]:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    match_id = _run_one_match(runs_dir)
    return TestClient(create_app(runs_dir)), match_id


def test_list_matches_lists_the_run(tmp_path: Path) -> None:
    client, match_id = _client(tmp_path)
    resp = client.get("/matches")
    assert resp.status_code == 200
    assert match_id in resp.json()


def test_match_summary_returns_ranking(tmp_path: Path) -> None:
    client, match_id = _client(tmp_path)
    resp = client.get(f"/matches/{match_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario"] == "concours"
    assert body["seed"] == _SEED
    assert body["ticks"] == 12
    ranking = body["final_ranking"]
    assert isinstance(ranking, list)
    assert set(_SPECS) <= set(ranking)
    # The report carries the incident and metric containers even before those layers are fully built.
    assert "incidents_by_kind" in body
    assert set(body["metrics"]) == {"cooperation", "conflict", "exploitation", "outcome"}


def test_journal_endpoint_returns_events(tmp_path: Path) -> None:
    client, match_id = _client(tmp_path)
    resp = client.get(f"/matches/{match_id}/journal")
    assert resp.status_code == 200
    events = resp.json()
    assert isinstance(events, list)
    kinds = {event["kind"] for event in events}
    assert "match_started" in kinds
    assert "match_ended" in kinds
    for event in events:
        assert {"kind", "tick", "seq", "payload"} <= set(event)


def test_metrics_endpoint_returns_four_families(tmp_path: Path) -> None:
    client, match_id = _client(tmp_path)
    resp = client.get(f"/matches/{match_id}/metrics")
    assert resp.status_code == 200
    assert set(resp.json()) == {"cooperation", "conflict", "exploitation", "outcome"}


def test_unknown_match_is_404(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    for suffix in ("", "/journal", "/metrics"):
        resp = client.get(f"/matches/does-not-exist{suffix}")
        assert resp.status_code == 404


def test_replay_streams_events_by_tick(tmp_path: Path) -> None:
    client, match_id = _client(tmp_path)
    # Compare the streamed events against the flat journal to prove nothing is dropped or reordered.
    flat = client.get(f"/matches/{match_id}/journal").json()
    expected_ticks: list[int] = []
    for event in flat:
        if not expected_ticks or expected_ticks[-1] != event["tick"]:
            expected_ticks.append(event["tick"])

    streamed_ticks: list[int] = []
    streamed_events: list[dict[str, object]] = []
    with client.websocket_connect(f"/matches/{match_id}/replay") as ws:
        for _ in expected_ticks:
            message = ws.receive_json()
            streamed_ticks.append(message["tick"])
            streamed_events.extend(message["events"])

    assert streamed_ticks == expected_ticks
    assert streamed_events == flat
