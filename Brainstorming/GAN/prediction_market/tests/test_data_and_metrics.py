"""Loader validation, the bundled dataset, the leaderboard, and the walk-forward split."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pmx.v1.agents import AGENT_IDS
from pmx.v1.data.loader import load_market, load_markets
from pmx.v1.tournament import run_tournament, walk_forward


def test_bundled_dataset_loads_and_is_labelled(seeded_data: Path) -> None:
    markets = load_markets(seeded_data)
    assert len(markets) == 12
    # every bundled market is honestly flagged as reconstructed, never as imported real data
    assert all(m.source == "reconstructed" for m in markets)
    # both outcomes are represented, so selection has signal in both directions
    assert {m.resolution for m in markets} == {0, 1}
    # loaded in chronological order for the walk-forward split
    dates = [m.resolved_date for m in markets]
    assert dates == sorted(dates)


def test_loader_rejects_bad_price(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "id": "x",
                "question": "q",
                "resolution": 1,
                "resolved_date": "2020",
                "prices": [{"t": "a", "price": 0}, {"t": "b", "price": 50}],  # price 0 is illegal
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_market(bad)


def test_loader_rejects_single_point(tmp_path: Path) -> None:
    bad = tmp_path / "bad2.json"
    bad.write_text(
        json.dumps(
            {
                "id": "x",
                "question": "q",
                "resolution": 0,
                "resolved_date": "2020",
                "prices": [{"t": "a", "price": 50}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_market(bad)


def test_leaderboard_ranks_market_follower_at_zero_skill(seeded_data: Path) -> None:
    board = run_tournament(load_markets(seeded_data), AGENT_IDS).board
    by_id = {r.agent_id: r for r in board}
    # the follower's skill against the market is exactly zero by construction
    assert by_id["market_follower"].skill_vs_market_micro == 0
    # a naive contrarian is clearly worse than believing the price
    assert by_id["contrarian"].mean_brier_micro > by_id["market_follower"].mean_brier_micro
    # the board is sorted best (lowest Brier) first
    briers = [r.mean_brier_micro for r in board]
    assert briers == sorted(briers)


def test_walk_forward_splits_in_time(seeded_data: Path) -> None:
    wf = walk_forward(load_markets(seeded_data), AGENT_IDS)
    assert len(wf.train_ids) + len(wf.test_ids) == 12
    assert len(wf.train_ids) >= len(wf.test_ids)  # odd extra goes to train
    assert wf.train_ids[0] != wf.test_ids[0]
    assert isinstance(wf.generalised, bool)
