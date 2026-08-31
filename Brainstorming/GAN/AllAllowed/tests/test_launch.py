"""Tests for launching a match through the control API (W13).

Two things matter here. First, a match launched through :func:`ala.runner.launch.launch_match` must be
byte-identical to the same seed run any other way: launching from HTTP must not become a second, subtly
different code path. Second, ``POST /runs`` must validate its input and must be absent when the server
is built read-only.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ala.api.app import create_app
from ala.journal import read_events
from ala.runner.launch import LaunchParams, launch_match

_PARAMS = LaunchParams(
    scenario="concours",
    seed=123,
    agents="grinder,allier,raider,forger",
    ticks=16,
    cull_every=8,
)


def test_launch_is_deterministic(tmp_path: Path) -> None:
    """Two launches of the same params write byte-identical journals (the AC-1 property, over HTTP)."""
    a = launch_match(tmp_path / "a", _PARAMS)
    b = launch_match(tmp_path / "b", _PARAMS)
    assert a.journal_hash == b.journal_hash
    left = (tmp_path / "a" / a.match_id / "journal.jsonl").read_bytes()
    right = (tmp_path / "b" / b.match_id / "journal.jsonl").read_bytes()
    assert left == right


def test_launch_second_run_gets_a_suffixed_dir(tmp_path: Path) -> None:
    """A second launch of the same seed never clobbers the first; it lands in a suffixed directory."""
    first = launch_match(tmp_path, _PARAMS)
    second = launch_match(tmp_path, _PARAMS)
    assert first.match_id != second.match_id
    assert (tmp_path / first.match_id / "journal.jsonl").is_file()
    assert (tmp_path / second.match_id / "journal.jsonl").is_file()


def test_post_runs_creates_a_replayable_match(tmp_path: Path) -> None:
    """POST /runs writes a journal the read-only routes immediately serve."""
    client = TestClient(create_app(tmp_path))
    res = client.post(
        "/runs",
        json={"seed": 7, "agents": ["grinder", "grinder", "allier", "mute"], "ticks": 12, "cull_every": 6},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    match_id = body["match_id"]
    assert body["ticks"] == 12
    assert body["final_ranking"]
    # the read-only surface now sees it
    assert match_id in client.get("/matches").json()
    summary = client.get(f"/matches/{match_id}")
    assert summary.status_code == 200
    # and its journal is a real, non-empty event stream
    events = list(read_events(tmp_path / match_id / "journal.jsonl"))
    assert any(e.kind == "match_started" for e in events)
    assert any(e.kind == "match_ended" for e in events)


def test_post_runs_matches_the_direct_launch_hash(tmp_path: Path) -> None:
    """The HTTP path and the direct function agree bit for bit on the same seed."""
    direct = launch_match(tmp_path / "direct", LaunchParams(seed=55, ticks=12))
    client = TestClient(create_app(tmp_path / "http"))
    res = client.post(
        "/runs",
        json={
            "seed": 55,
            "agents": ["grinder", "allier", "raider", "forger"],
            "ticks": 12,
            "cull_every": 8,
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["journal_hash"] == direct.journal_hash


@pytest.mark.parametrize(
    "payload",
    [
        {"agents": ["grinder", "wizard"]},  # unknown archetype
        {"agents": []},  # empty
        {"permission": "godmode"},  # unknown dial
        {"scenario": "chantier"},  # not built yet
        {"ticks": 0},  # out of bounds
    ],
)
def test_post_runs_rejects_bad_input(tmp_path: Path, payload: dict[str, object]) -> None:
    """Every malformed request is refused with a 4xx, never a 500 and never a run."""
    client = TestClient(create_app(tmp_path))
    res = client.post("/runs", json=payload)
    assert 400 <= res.status_code < 500, res.text
    # nothing was written
    assert client.get("/matches").json() == []


def test_read_only_app_has_no_launch(tmp_path: Path) -> None:
    """Built read-only, the server refuses POST /runs (the route is simply not mounted)."""
    client = TestClient(create_app(tmp_path, allow_launch=False))
    res = client.post("/runs", json={"seed": 1})
    assert res.status_code in (404, 405)
