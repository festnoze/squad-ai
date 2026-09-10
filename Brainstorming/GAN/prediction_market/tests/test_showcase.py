"""DS2: the showcase pack (CONTRACTS_V2 7.1, 5.6, decision D-S5, rulings R263, R264, R291).

What these tests are really guarding:

* the pack **grows past the twelve** of v1 and the floor says so. A "showcase pack" that ended up with
  twelve markets again would be the v1 demo pack under a new name;
* a showcase market carries **a research market's depth**. The measurement is in
  ``tests/fixtures/ds2/demo_v1_depth.json``: the twelve v1 markets carry 4 to 361 bars, zero prints,
  zero traded bars and no news at all, so **not one of them clears the bar**, and the test asserts the
  refusal on all twelve rather than accepting eleven;
* the pack is honest about being partial. Every landmark that could not be sourced is in the manifest's
  ``notes`` with the archive it waits on and what is missing, which is what ruling R264 asks for and the
  only alternative to a pack whose missing rows look like rows nobody wanted;
* the **exemption is the window rule and nothing else** (ruling R263). ``purpose = "showcase"`` is not a
  flag that relaxes a filter, a freeze check or a fold, and ``refuse_if_showcase`` is the one spelling of
  the refusal the six callers of 5.6 share.

This package fetches nothing (the no-network rule of this lot), so what is tested is the plan, the
refusals and the arithmetic, and the list a later networked lot works through.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Final

import pytest

from pmx.data.showcase import (
    SHOWCASE_BARS_MIN,
    SHOWCASE_LANDMARKS,
    SHOWCASE_MARKETS_MIN,
    SHOWCASE_MARKETS_TARGET,
    SHOWCASE_NAME,
    SHOWCASE_SOURCES,
    SOURCE_DEMO_V1,
    ShowcaseLandmark,
    check_showcase_depth,
    landmarks_by_source,
    landmarks_with_bars,
    refuse_if_showcase,
    showcase_build_config,
    showcase_notes,
    showcase_plan,
    sourced_landmarks,
    unsourced_landmarks,
)
from pmx.errors import InvalidConfigError, PmxError, SchemaError, ShowcaseDatasetError
from pmx.types import PURPOSE_RESEARCH, PURPOSE_SHOWCASE, WINDOW_DAYS_MAX, BuildConfig

FIXTURES: Final = Path(__file__).resolve().parent / "fixtures" / "ds2"


def _depth_rows() -> tuple[Mapping[str, object], ...]:
    payload = json.loads((FIXTURES / "demo_v1_depth.json").read_text(encoding="utf-8"))
    rows = payload["markets"]
    assert isinstance(rows, list)
    return tuple(rows)


# --------------------------------------------------------------------------------------------------
# The plan: a few dozen, unique, sorted, and past the twelve of v1
# --------------------------------------------------------------------------------------------------
def test_the_pack_grows_past_the_twelve_of_the_v1_demo_pack() -> None:
    """Ruling R264: "a few dozen markets", read as a floor of twenty-four and a table of forty-one.

    The v1 pack holds twelve. A floor at or below twelve would let the showcase pack be the demo pack
    under a new name, which is the one outcome decision D-S5 exists to prevent.
    """
    plan = showcase_plan()
    assert SHOWCASE_MARKETS_MIN == 24
    assert SHOWCASE_MARKETS_MIN > 12
    assert SHOWCASE_MARKETS_TARGET == len(SHOWCASE_LANDMARKS) == plan.n
    assert plan.n >= SHOWCASE_MARKETS_MIN
    assert SHOWCASE_NAME == "showcase_v1"
    # Sorted by id and unique, because the plan is rendered into a manifest a human reads.
    ids = [row.landmark_id for row in plan.landmarks]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)
    # Every row is a real event with a checkable date and one of the four archives.
    for row in plan.landmarks:
        assert row.source in SHOWCASE_SOURCES
        assert len(row.resolved_on) == 10 and row.resolved_on[4] == "-"
        assert row.question.strip() == row.question and row.question
        assert row.source_hint
    # A duplicate id is refused rather than silently collapsing two landmarks into one.
    with pytest.raises(InvalidConfigError, match="share an id"):
        showcase_plan([SHOWCASE_LANDMARKS[0], SHOWCASE_LANDMARKS[0]])
    # And a landmark is not a market: it carries no resolution, no price and no tape, because the
    # resolution is read off the venue's own record by the lot that sources it.
    row = plan.landmarks[0]
    for banned in ("resolution", "final_price_bp", "first_price_bp", "bars", "trades"):
        assert not hasattr(row, banned), banned


def test_no_landmark_is_sourced_yet_and_the_plan_says_so() -> None:
    """The honest state of the pack, and the reason: this lot opened no socket.

    ``bars_available`` is the eleven v1 markets that clear the bar count, which is the difference between
    a row that needs a whole tape and a row that needs the news and the prints beside a tape it has.
    """
    plan = showcase_plan()
    assert sourced_landmarks(plan) == ()
    assert plan.n_sourced == 0
    assert plan.reaches_floor is False
    assert len(unsourced_landmarks(plan)) == plan.n
    with_bars = landmarks_with_bars(plan)
    assert len(with_bars) == 11
    assert all(row.source == SOURCE_DEMO_V1 for row in with_bars)
    assert {row.landmark_id for row in plan.landmarks if row.source == SOURCE_DEMO_V1} - {
        row.landmark_id for row in with_bars
    } == {"titan-submersible-2023"}
    # What each row still needs, in the order a sourcing lot would get it.
    by_id = {row.landmark_id: row for row in plan.landmarks}
    assert by_id["brexit-2016"].missing == ("news", "trades")
    assert by_id["titan-submersible-2023"].missing == ("bars", "news", "trades")
    assert by_id["russia-invasion-2022"].missing == ("bars", "news", "trades")
    # A sourced row needs nothing, which is what the flag will mean once a lot has done the work.
    assert replace(by_id["brexit-2016"], sourced=True).missing == ()


def test_the_notes_entry_documents_every_landmark_that_could_not_be_sourced() -> None:
    """Ruling R264: "a ``notes`` entry documenting what could not be sourced"."""
    plan = showcase_plan()
    notes = showcase_notes(plan)
    assert notes.startswith(f"showcase pack {SHOWCASE_NAME}: {plan.n} landmark events, 0 sourced")
    lines = notes.splitlines()
    assert len(lines) == 1 + plan.n_unsourced
    for row in unsourced_landmarks(plan):
        assert any(row.landmark_id in line and row.source in line for line in lines[1:]), row.landmark_id
    # The counts in the headline are the plan's, so the sentence cannot drift from the table.
    assert f"{plan.n_with_bars} with a bar tape" in lines[0]
    assert f"floor {SHOWCASE_MARKETS_MIN}, target {SHOWCASE_MARKETS_TARGET}" in lines[0]
    # A fully sourced plan renders one line and no complaints, which is what the pack should look like.
    done = showcase_plan([replace(row, sourced=True) for row in SHOWCASE_LANDMARKS])
    assert showcase_notes(done).splitlines() == [
        f"showcase pack {SHOWCASE_NAME}: {plan.n} landmark events, {plan.n} sourced, "
        f"{plan.n_with_bars} with a bar tape already in the repository, 0 not sourced "
        f"(floor {SHOWCASE_MARKETS_MIN}, target {SHOWCASE_MARKETS_TARGET})."
    ]
    assert done.reaches_floor is True
    # No em-dash and no non-ASCII sneaks into a manifest field through this string.
    assert notes.isascii()


def test_the_work_order_names_the_archive_each_landmark_waits_on() -> None:
    """The deliverable half this package cannot finish: the list a networked lot works through."""
    order = landmarks_by_source()
    assert set(order) <= set(SHOWCASE_SOURCES)
    assert sum(len(ids) for ids in order.values()) == showcase_plan().n
    for source, ids in order.items():
        assert list(ids) == sorted(ids), source
    assert "brexit-2016" in order[SOURCE_DEMO_V1]
    assert "russia-invasion-2022" in order["manifold_history"]
    assert "scottish-referendum-2014" in order["wayback"]
    assert "cpi-91-july-2022" in order["kalshi_history"]
    # A sourced row leaves the work order.
    assert "brexit-2016" not in landmarks_by_source(
        [replace(row, sourced=True) for row in SHOWCASE_LANDMARKS]
    ).get(SOURCE_DEMO_V1, ())
    # A landmark naming an archive nobody can read is refused at construction.
    with pytest.raises(InvalidConfigError, match="one of the four archives"):
        ShowcaseLandmark(
            landmark_id="x",
            title="X",
            question="Will X?",
            provider="demo",
            category="other",
            resolved_on="2020-01-01",
            source="my-hard-drive",
            source_hint="",
        )
    with pytest.raises(InvalidConfigError, match="title and a question"):
        ShowcaseLandmark(
            landmark_id="x",
            title="X",
            question="",
            provider="demo",
            category="other",
            resolved_on="2020-01-01",
            source=SOURCE_DEMO_V1,
            source_hint="",
        )


# --------------------------------------------------------------------------------------------------
# The depth bar, measured against the pack the ruling replaces
# --------------------------------------------------------------------------------------------------
def test_a_showcase_market_carries_a_research_market_s_depth() -> None:
    """Ruling R264: bars, prints and news, each a refusal and not a warning."""
    assert SHOWCASE_BARS_MIN == 20
    check_showcase_depth("ok", n_bars=20, n_trades=1, n_news=1)  # the control: it accepts
    check_showcase_depth("ok-bars-only", n_bars=20, n_trades=0, n_news=1, traded_bars=3)
    with pytest.raises(ShowcaseDatasetError, match="depth of bars"):
        check_showcase_depth("thin", n_bars=19, n_trades=100, n_news=100)
    with pytest.raises(ShowcaseDatasetError, match="print tape or a per-bar size"):
        check_showcase_depth("silent", n_bars=100, n_trades=0, n_news=100)
    with pytest.raises(ShowcaseDatasetError, match="as-of news"):
        check_showcase_depth("newsless", n_bars=100, n_trades=100, n_news=0)
    assert issubclass(ShowcaseDatasetError, PmxError)
    assert not issubclass(ShowcaseDatasetError, SchemaError)


def test_not_one_market_of_the_v1_pack_clears_the_showcase_depth_bar() -> None:
    """The measurement behind ruling R264, recorded in ``tests/fixtures/ds2/demo_v1_depth.json``.

    The twelve v1 markets carry 4 to 361 daily bars, ``n_trades = 0`` and ``traded_bars = 0`` on every
    one, and ``data/demo_v1`` has no news directory at all. So the pack the ruling replaces is exactly
    the shallow demo it was written against, and a depth bar that accepted eleven of the twelve would be
    a bar that accepts a chart with no execution and no as-of stamp behind it.
    """
    rows = _depth_rows()
    assert len(rows) == 12
    refused: list[str] = []
    for row in rows:
        assert row["n_trades"] == 0
        assert row["traded_bars"] == 0
        assert row["n_news"] == 0
        with pytest.raises(ShowcaseDatasetError) as caught:
            check_showcase_depth(
                str(row["id"]),
                n_bars=int(row["n_bars"]),  # type: ignore[arg-type]
                n_trades=int(row["n_trades"]),  # type: ignore[arg-type]
                n_news=int(row["n_news"]),  # type: ignore[arg-type]
                traded_bars=int(row["traded_bars"]),  # type: ignore[arg-type]
            )
        refused.append(str(caught.value))
    assert len(refused) == 12
    # Eleven fail on the print tape first and the twelfth fails on bars, which is the one row the
    # landmark table marks as needing a finer grid rather than only the news beside its tape.
    on_bars = [message for message in refused if "depth of bars" in message]
    assert len(on_bars) == 1
    assert "titan" in on_bars[0]
    assert len([message for message in refused if "print tape" in message]) == 11
    # And the news clause is what would still refuse them if the pack ever gained a print tape: the
    # eleven markets with enough bars fail on news alone once the prints are supplied, which is the half
    # of the depth bar a "refused, therefore covered" reading of this test would leave untested.
    on_news = 0
    for row in rows:
        if int(row["n_bars"]) < SHOWCASE_BARS_MIN:  # type: ignore[arg-type]
            continue
        with pytest.raises(ShowcaseDatasetError, match="as-of news") as caught:
            check_showcase_depth(
                str(row["id"]),
                n_bars=int(row["n_bars"]),  # type: ignore[arg-type]
                n_trades=100,
                n_news=int(row["n_news"]),  # type: ignore[arg-type]
            )
        assert str(row["id"]) in str(caught.value)
        on_news += 1
    assert on_news == 11


# --------------------------------------------------------------------------------------------------
# purpose: showcase, and the exemption that is the window rule and nothing else
# --------------------------------------------------------------------------------------------------
def test_the_showcase_build_config_declares_the_purpose_and_relaxes_nothing_else() -> None:
    """5.6 and ruling R263: the purpose buys the window exemption, and buys nothing else."""
    config = showcase_build_config("2026-09-08")
    assert config.purpose == PURPOSE_SHOWCASE
    assert config.window_days == WINDOW_DAYS_MAX
    # Every other filter is the research one, value for value: a showcase build is not a lax build.
    research = BuildConfig(freeze_date="2026-09-08", providers=("demo",))
    for field in (
        "min_trades", "min_unique_bettors", "min_life_days", "min_traded_bars",
        "min_traded_bars_per_day_permille", "exclude_self_resolved", "exclude_kalshi_shards",
        "safety_lag_ms", "interval_min", "opened_early_days",
    ):
        assert getattr(config, field) == getattr(research, field), field
    # An override may change a filter, and may not change the purpose out from under the function.
    assert showcase_build_config("2026-09-08", min_trades=10).min_trades == 10
    with pytest.raises(ShowcaseDatasetError, match="purpose showcase and nothing else"):
        showcase_build_config("2026-09-08", purpose=PURPOSE_RESEARCH)
    # And the window ceiling still binds: the exemption is from the window RULE, not from its bound.
    with pytest.raises(InvalidConfigError):
        showcase_build_config("2026-09-08", window_days=WINDOW_DAYS_MAX + 1)


def test_refuse_if_showcase_is_the_one_spelling_of_the_refusal() -> None:
    """Rulings R263 and R291: no fold, no fitness, no promotion, no insight, no claim, no carry-forward.

    One implementation, so no caller can weaken it to a warning, and the error names the caller so a
    reader of a failed run knows which of the six refused.
    """
    refuse_if_showcase(PURPOSE_RESEARCH, caller="make_folds")  # the control: research passes
    for caller in ("make_folds", "run_generation", "evolve", "claim", "rule_tester", "feature_matrix"):
        with pytest.raises(ShowcaseDatasetError) as caught:
            refuse_if_showcase(PURPOSE_SHOWCASE, caller=caller)
        assert caller in str(caught.value)
        assert "never feeds a fold" in str(caught.value)
    # A purpose that is neither is a config error and not a silent pass, which is what a typo in a
    # manifest would otherwise be.
    with pytest.raises(InvalidConfigError, match="research or showcase"):
        refuse_if_showcase("demo", caller="make_folds")
    with pytest.raises(InvalidConfigError):
        refuse_if_showcase("", caller="make_folds")
