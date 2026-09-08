"""The JSON schemas of CONTRACTS_V2 and the fixtures that exercise them.

These tests pin four things before any package exists: that every schema is itself a valid draft 2020-12
document, that a document built by the contract's own rules validates, that the schemas refuse what the
contract forbids (a float where an integer belongs, a price of 0, a news kind that contradicts its source,
an extra property on an action, an unknown or over-full journal event), and that the worked examples of
section 1 are the numbers the document claims.

Amendment C1 (CONTRACTS_V2 section 16) adds four schemas and six fixtures: ``cluster.v1.json`` (event
clusters, constraints and the sealed manual override file), ``opportunity.v1.json`` (a detector's output
and its opportunity events), ``features.v1.json`` (the integer feature layout, whose fixture **is** the
normative thirty-seven-field vector of 16.5) and ``model_card.v1.json`` (the card that is a
``torch_policy`` genome). Their tests pin the same four things and one more: that the identifiers, the
hashes and the scores in the fixtures are the derivations section 16 states, not decoration, so a package
that computes one differently fails here rather than in a review.

The fixtures under ``tests/fixtures/contract/`` come from the migrated v1 Brexit market and hold the
identities of section 7.10. The two journals are **complete** journals of small runs, not excerpts: the
backtest one covers the last two bars of that tape (2016-06-23 and 2016-06-24, the settling bar), so
``seq`` is dense from 1, every bar of the run is in the file, and the accounting invariant of section 8.9
can be asserted per agent rather than admired. Its roster is deliberately two agents: ``market_follower``,
which must never place an order (section 10.5), and ``contrarian``, which trades, so neither half of the
invariant holds vacuously. Everything here is offline and reads only files in the repository.

Amendment C1b (CONTRACTS_V2 section 17) adds four schemas and six fixtures: ``instrument.v1.json`` (a
continuous instrument with its integer scales, calendar, schedules, bars in ticks and data cash events),
``cash_event.v1.json`` (the dated cash-flow family), ``session_calendar.v1.json`` (the dated sessions a bar
must intersect) and ``forecast.v1.json`` (the per-horizon forecast record). Their tests pin the same things
and execute the worked examples of 17.1, 17.4 and 17.5: the binary scales reproduce section 1.4 to the
cent, the Corwin and Schultz estimator gives the stated ticks, the random walk scores zero skill on every
outcome. Four of its rulings (R167 to R170) describe what the data package implemented in its own files
at the same time, and one test reads both sides so the two cannot drift.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parent.parent
SCHEMAS = REPO / "src" / "pmx" / "schemas"          # section 7.13: inside the package, not at the root
FIXTURES = REPO / "tests" / "fixtures" / "contract"
CONTRACT = REPO / "docs" / "CONTRACTS_V2.md"

SCHEMA_FILES = ("market.v2.json", "news.v1.json", "dataset.v1.json", "actions.v2.json", "journal.v2.json")
#: Amendment C1, CONTRACTS_V2 section 16: the four schemas the v3 waves are built against.
V3_SCHEMA_FILES = ("cluster.v1.json", "opportunity.v1.json", "features.v1.json", "model_card.v1.json")
#: Amendment C1b, CONTRACTS_V2 section 17: the four schemas the instrument generalisation is built against.
C1B_SCHEMA_FILES = ("instrument.v1.json", "cash_event.v1.json", "session_calendar.v1.json", "forecast.v1.json")
ALL_SCHEMA_FILES = SCHEMA_FILES + V3_SCHEMA_FILES + C1B_SCHEMA_FILES
PPM_ONE = 1_000_000
BP_ONE = 10_000
MS_PER_DAY = 86_400_000
#: CONTRACTS_V2 section 9.1: `generation` sits between `close` and `post`, and a journal never mixes it
#: with the bar phases.
PHASE_ORDER = (
    "pre", "open", "observe", "decide", "execute", "settle", "learn", "hive", "close", "generation", "post",
)


def _schema(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    return loaded


def _validator(name: str) -> Draft202012Validator:
    schema = _schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _events(name: str) -> list[dict[str, Any]]:
    with (FIXTURES / name).open(encoding="utf-8", newline="\n") as handle:
        text = handle.read()
    assert "\r" not in text
    return [json.loads(line) for line in text.splitlines() if line]


def _subschema(name: str, ref: str) -> Draft202012Validator:
    """A validator for one ``$defs`` entry of a schema, for the documents that are not its root."""
    schema = _schema(name)
    rooted = {"$schema": schema["$schema"], "$ref": f"#/$defs/{ref}", "$defs": schema["$defs"]}
    Draft202012Validator.check_schema(rooted)
    return Draft202012Validator(rooted)


def _canonical(payload: Any) -> str:
    """Section 4.1's encoder, spelled here so the fixtures are checked against the contract, not the code."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _errors(validator: Draft202012Validator, doc: Any) -> list[str]:
    return [e.message for e in validator.iter_errors(doc)]


def _of_type(events: list[dict[str, Any]], etype: str) -> list[dict[str, Any]]:
    return [e for e in events if e["type"] == etype]


def _preamble() -> str:
    """The contributor rules above section 0, which carry preamble rule 3's list of legal float sites."""
    text = CONTRACT.read_text(encoding="utf-8")
    return text[: text.index("## 0. Table of contents")]


# --------------------------------------------------------------------------------------------------
# The schemas themselves
# --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ALL_SCHEMA_FILES)
def test_schema_is_valid_draft_2020_12(name: str) -> None:
    schema = _schema(name)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


def test_the_schemas_live_inside_the_package() -> None:
    """Section 7.13: A5 hands `actions.v2.json` to the CLI at run time, so a root path would not exist."""
    assert not (REPO / "schemas").exists()
    for name in ALL_SCHEMA_FILES:
        assert (SCHEMAS / name).is_file(), name


def test_fixture_files_are_canonical_single_line_lf() -> None:
    for path in sorted(FIXTURES.glob("*.json")):
        raw = path.read_bytes()
        assert b"\r" not in raw and raw.endswith(b"\n"), path.name
        obj = json.loads(raw)
        canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        assert raw.decode("utf-8") == canonical + "\n", path.name


# --------------------------------------------------------------------------------------------------
# Positive: the fixtures validate
# --------------------------------------------------------------------------------------------------
def test_migrated_demo_market_validates_with_the_section_7_10_identities() -> None:
    market = _fixture("market.demo-brexit-2016.json")
    assert _errors(_validator("market.v2.json"), market) == []
    v1 = json.loads((REPO / "data" / "markets" / "brexit-2016.json").read_text(encoding="utf-8"))
    assert market["first_price_bp"] == v1["prices"][0]["price"] * 100
    assert market["final_price_bp"] == v1["prices"][-1]["price"] * 100
    assert "last_price_bp" not in market  # section 7.2: that name belongs to the as-of MarketView only
    bars = market["bars"]
    assert all(b["t_ms"] % MS_PER_DAY == 0 for b in bars)
    assert all(b2["t_ms"] - b1["t_ms"] == MS_PER_DAY for b1, b2 in zip(bars, bars[1:], strict=False))
    assert bars[0]["t_ms"] <= market["created_at_ms"] < bars[0]["t_ms"] + MS_PER_DAY
    assert bars[-1]["t_ms"] <= market["resolved_at_ms"] < bars[-1]["t_ms"] + MS_PER_DAY
    assert market["source"] == "reconstructed" and market["provider"] == "demo"
    assert market["fee_schedule_id"] == "demo-zero" and market["trades"] == []
    assert all(b["volume_milli"] == 0 for b in bars)  # PRD 3.3; section 8.6 step 1 exempts it instead
    assert "upset" in market["hardness_tags"]  # Brexit: priced Remain until the night, resolved Leave


def test_wiki_subjects_carries_a_real_article_title_and_tags_cannot() -> None:
    """Section 7.2: subject titles have spaces and capitals, `tags` are slugs. They are two fields."""
    validator = _validator("market.v2.json")
    market = _fixture("market.demo-brexit-2016.json")
    assert any(" " in title for title in market["wiki_subjects"])
    as_tag = copy.deepcopy(market)
    as_tag["tags"] = ["wiki:2016 United Kingdom European Union membership referendum"]
    assert _errors(validator, as_tag) != []
    long_subject = copy.deepcopy(market)
    long_subject["wiki_subjects"] = ["x" * 257]
    assert _errors(validator, long_subject) != []


def test_news_item_validates_and_carries_the_safety_lag() -> None:
    item = _fixture("news.wce-20160623-0007.json")
    assert _errors(_validator("news.v1.json"), item) == []
    assert item["visible_from_ms"] - item["published_at_ms"] == 21_600_000
    assert item["published_at_ms"] % MS_PER_DAY == 0  # end of the page day, section 5.5
    # section 2 and 7.1: the id names the page day D, the file name day_start_ms(published_at_ms) = D + 1
    assert item["news_id"] == "wce-20160623-0007"
    day_of_file = item["published_at_ms"] // MS_PER_DAY * MS_PER_DAY
    assert day_of_file == item["published_at_ms"]
    assert item["revid"] is None and item["asof_day"] is None  # only wikipedia_asof carries them


def test_dataset_manifest_validates_and_its_hash_is_the_contract_formula() -> None:
    manifest = _fixture("dataset.manifest.json")
    assert _errors(_validator("dataset.v1.json"), manifest) == []
    lines = "\n".join(f"{f['path']} {f['sha256']}" for f in manifest["files"]) + "\n"
    assert manifest["dataset_hash"] == hashlib.sha256(lines.encode("utf-8")).hexdigest()
    edges = manifest["split"]["month_edges_ms"]
    offsets = [(e - edges[0]) // MS_PER_DAY for e in edges]
    assert offsets == [0, 30, 60, 91, 121, 152, 182, 212, 243, 273, 304, 334, 365]
    assert manifest["split"]["train_end_ms"] == edges[8]
    assert manifest["split"]["validation_end_ms"] == edges[10]
    assert manifest["sealed"] is False  # the demo pack is never sealed
    # section 7.4: the ten filter keys, every one always present
    assert set(manifest["filters"]["removed"]) == {
        "window", "opened_early", "binary", "min_trades", "min_life", "density", "self_resolved",
        "kalshi_shards", "resolution", "no_leak",
    }
    # section 7.1: the demo pack's window is derived from its own markets, not from the freeze
    assert manifest["window"]["start_ms"] % MS_PER_DAY == 0
    assert manifest["window"]["end_ms"] < manifest["freeze_ms"]


def test_actions_sample_validates() -> None:
    actions = _fixture("actions.sample.json")
    assert _errors(_validator("actions.v2.json"), actions) == []
    kinds = {m["kind"] for m in actions["markets"]}
    assert kinds == {"target", "limit", "abstain"}
    ids = [m["market_id"] for m in actions["markets"]]
    assert len(ids) == len(set(ids))  # section 8.4: one action per market per bar


@pytest.mark.parametrize("name", ("journal.backtest.jsonl", "journal.evolution.jsonl"))
def test_journal_fixture_events_validate(name: str) -> None:
    validator = _validator("journal.v2.json")
    events = _events(name)
    assert events, name
    for event in events:
        assert _errors(validator, event) == [], event["type"]


# --------------------------------------------------------------------------------------------------
# The journal fixtures hold the rules of sections 8 and 9
# --------------------------------------------------------------------------------------------------
def test_backtest_journal_respects_the_ordering_guarantees() -> None:
    events = _events("journal.backtest.jsonl")
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert events[0]["type"] == "run_started" and events[-1]["type"] == "run_ended"
    assert len({e["run_id"] for e in events}) == 1
    assert events[0]["bar_ms"] == 0 and events[-1]["bar_ms"] == events[0]["t1_ms"]
    bars = [e["bar_ms"] for e in events]
    assert bars == sorted(bars)
    assert "generation" not in {e["phase"] for e in events}
    for a, b in zip(events, events[1:], strict=False):
        if a["bar_ms"] == b["bar_ms"]:
            assert PHASE_ORDER.index(a["phase"]) <= PHASE_ORDER.index(b["phase"]), (a["type"], b["type"])
    counted = _of_type(events, "bar_closed")
    assert [e["n_events"] for e in counted] == [
        sum(1 for x in events if x["bar_ms"] == e["bar_ms"]) for e in counted
    ]
    assert _of_type(events, "run_ended")[0]["event_count"] == len(events)
    assert _of_type(events, "run_ended")[0]["n_bars"] == len(counted)


def test_the_accounting_invariant_of_section_8_9_holds_for_every_agent() -> None:
    events = _events("journal.backtest.jsonl")
    bankroll = events[0]["config"]["bankroll_cents"]
    agents = [entry["agent_id"] for entry in events[0]["roster"]]
    assert len(agents) >= 2, "one agent makes half of this invariant vacuous"
    traded = 0
    for agent in agents:
        fills = sum(e["cash_delta_cents"] for e in _of_type(events, "filled") if e["agent_id"] == agent)
        fees = sum(e["fee_cents"] for e in _of_type(events, "fee_charged") if e["agent_id"] == agent)
        settle = sum(
            e["cash_delta_cents"] for e in _of_type(events, "settlement_applied") if e["agent_id"] == agent
        )
        marks = [e for e in _of_type(events, "equity_marked") if e["agent_id"] == agent]
        assert marks, agent
        assert marks[-1]["cash_cents"] == bankroll + fills - fees + settle, agent
        assert marks[-1]["reserved_cents"] == 0  # every market of the run has settled
        assert marks[-1]["positions_value_cents"] == 0
        traded += 1 if fills else 0
    assert traded == 1, "exactly one of the two agents trades, so neither branch is untested"


def test_the_market_follower_baseline_ties_the_market_and_never_trades() -> None:
    """Sections 10.5 and 12.1: `follower(1000, 0)` states the market's price and places no order."""
    events = _events("journal.backtest.jsonl")
    settled = _of_type(events, "settled")[0]
    applied = {e["agent_id"]: e for e in _of_type(events, "settlement_applied")}
    assert applied["market_follower"]["agent_brier_tw_micro"] == settled["market_brier_tw_micro"]
    assert applied["contrarian"]["agent_brier_tw_micro"] != settled["market_brier_tw_micro"]
    assert all(e["agent_id"] != "market_follower" for e in _of_type(events, "order_placed"))
    assert all(e["agent_id"] != "market_follower" for e in _of_type(events, "filled"))
    # every agent is scored on the same bars (section 8.2), so the baseline is comparable
    assert len({e["n_forecast_bars"] for e in applied.values()}) == 1
    # the stated probability is the last completed close, bar by bar (section 12.1)
    priced = {e["bar_ms"]: e for e in _of_type(events, "market_priced")}
    for forecast in _of_type(events, "forecast_recorded"):
        if forecast["agent_id"] == "market_follower":
            assert forecast["prob_ppm"] == priced[forecast["bar_ms"]]["last_close_bp"] * 100


def test_no_fill_happens_on_the_close_bar_or_the_settling_bar() -> None:
    """Section 5.3: only a bar entirely inside the trading window is tradable."""
    events = _events("journal.backtest.jsonl")
    settling = _of_type(events, "settled")[0]["bar_ms"]
    fills = _of_type(events, "filled")
    assert fills, "a journal with no fill would satisfy the rule without exercising it"
    assert all(e["bar_ms"] != settling for e in fills)
    opened = {e["bar_ms"]: e for e in _of_type(events, "bar_opened")}
    assert opened[settling]["tradable_market_ids"] == []
    assert opened[settling]["settling_market_ids"] != []
    resolved = _of_type(events, "settled")[0]["resolved_at_ms"]
    interval_ms = events[0]["interval_min"] * 60_000
    assert settling == resolved // interval_ms * interval_ms


def test_a_target_equal_to_the_current_position_places_no_order() -> None:
    """Section 8.4: the second bar restates `target_position = 100` and no order is emitted."""
    events = _events("journal.backtest.jsonl")
    settling = _of_type(events, "settled")[0]["bar_ms"]
    intents = [
        item
        for e in _of_type(events, "action_received")
        if e["bar_ms"] == settling and e["agent_id"] == "contrarian"
        for item in e["intents"]
    ]
    assert [i["kind"] for i in intents] == ["target"]
    fills = [e for e in _of_type(events, "filled") if e["agent_id"] == "contrarian"]
    assert intents[0]["target_position"] == fills[-1]["position_after"]
    placed = _of_type(events, "order_placed")
    assert placed, "the fixture must place orders somewhere, or this rule is vacuous"
    assert all(e["bar_ms"] != settling for e in placed)


def test_hive_forecasts_are_released_only_after_the_settling_bar() -> None:
    """Sections 9.2 and 10.4: `visible_from_ms = bar_of(resolved_at_ms) + interval_ms`."""
    events = _events("journal.backtest.jsonl")
    interval_ms = events[0]["interval_min"] * 60_000
    resolved = _of_type(events, "settled")[0]["resolved_at_ms"]
    release = resolved // interval_ms * interval_ms + interval_ms
    written = _of_type(events, "hive_written")
    forecasts = [e for e in written if e["kind"] in ("forecast", "resolution")]
    assert forecasts
    for entry in forecasts:
        assert entry["visible_from_ms"] == release
        assert entry["visible_from_ms"] > entry["bar_ms"]
    last_bar = max(e["bar_ms"] for e in _of_type(events, "bar_closed"))
    assert release > last_bar  # nobody reads another agent's forecast inside this run
    assert [e["entry_id"] for e in written] == sorted({e["entry_id"] for e in written})


def test_the_inputs_the_projection_needs_are_in_the_journal() -> None:
    """Section 9.5: `results.json` is rebuilt from the journal alone, so the inputs must be there."""
    events = _events("journal.backtest.jsonl")
    listed = _of_type(events, "market_listed")
    assert len(listed) == 1 and listed[0]["phase"] == "open"
    assert {"category", "event_key", "close_at_ms", "hardness_tags", "fold"} <= set(listed[0])
    priced = _of_type(events, "market_priced")
    open_bars = {
        (e["bar_ms"], mid)
        for e in _of_type(events, "bar_opened")
        for mid in e["open_market_ids"]
    }
    assert {(e["bar_ms"], e["market_id"]) for e in priced} == open_bars
    started = events[0]
    assert started["folds"]["train_end_ms"] < started["folds"]["validation_end_ms"]
    assert "market_ids_hash" in started["config"] and "fold" in started["config"]
    assert started["config_hash"].startswith(started["run_id"].rsplit("-", 1)[1])


def test_evolution_journal_envelope_and_fold_separation() -> None:
    events = _events("journal.evolution.jsonl")
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert events[0]["type"] == "evolution_started" and events[-1]["type"] == "evolution_ended"
    assert all(e["bar_ms"] == 0 for e in events)          # section 9.1
    assert [e["phase"] for e in events] == ["pre"] + ["generation"] * (len(events) - 2) + ["post"]
    for a, b in zip(events, events[1:], strict=False):
        assert PHASE_ORDER.index(a["phase"]) <= PHASE_ORDER.index(b["phase"]), (a["type"], b["type"])
    started = _of_type(events, "generation_started")[0]
    # section 8.1: `fold` and `market_ids_hash` are in the config, so the two runs cannot collide
    assert started["train_run_id"] != started["validation_run_id"]
    assert all(e["run_id"].startswith("e-") for e in events)


def test_every_genome_in_a_journal_carries_its_member_list() -> None:
    """Section 10.1: `members` is always present, so `genome_hash` is defined once and for all."""
    genomes: list[dict[str, Any]] = []
    for name in ("journal.backtest.jsonl", "journal.evolution.jsonl"):
        for event in _events(name):
            for entry in event.get("roster", []) + event.get("initial_population", []):
                genomes.append(entry["genome"])
            champion = event.get("champion")
            if champion is not None:
                genomes.append(champion["genome"])
    assert genomes
    for genome in genomes:
        assert set(genome) == {"family", "genes", "inner", "members", "prompt"}
        assert genome["members"] == []


def test_genome_hashes_in_the_fixtures_are_the_contract_formula() -> None:
    for name in ("journal.backtest.jsonl", "journal.evolution.jsonl"):
        for event in _events(name):
            for entry in event.get("roster", []) + event.get("initial_population", []):
                payload = json.dumps(
                    entry["genome"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
                )
                assert entry["genome_hash"] == hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------------------------------
# Negative: what the contract forbids is refused
# --------------------------------------------------------------------------------------------------
def test_market_schema_refuses_floats_and_zero_prices() -> None:
    validator = _validator("market.v2.json")
    market = _fixture("market.demo-brexit-2016.json")
    # A zero-fraction float (3200.0) is an integer to JSON Schema; that half of the float ban belongs to
    # canonical_json and to D1's strict pydantic ints (section 4.1). The schema refuses a fractional one.
    with_float = copy.deepcopy(market)
    with_float["bars"][0]["close_bp"] = 3200.5
    assert _errors(validator, with_float) != []
    zero_price = copy.deepcopy(market)
    zero_price["bars"][0]["low_bp"] = 0
    assert _errors(validator, zero_price) != []
    bad_source = copy.deepcopy(market)
    bad_source["source"] = "synthetic"
    assert _errors(validator, bad_source) != []
    extra = copy.deepcopy(market)
    extra["resolution_prob"] = 1
    assert _errors(validator, extra) != []
    bad_id = copy.deepcopy(market)
    bad_id["id"] = "kalshi:KXBTC"  # a colon is not a legal file name character on Windows
    assert _errors(validator, bad_id) != []
    bad_fee = copy.deepcopy(market)
    bad_fee["fee_schedule_id"] = "demo zero"
    assert _errors(validator, bad_fee) != []
    missing = copy.deepcopy(market)
    del missing["wiki_subjects"]
    assert _errors(validator, missing) != []


def test_the_shipped_demo_fee_schedule_id_matches_the_section_2_regex() -> None:
    """Section 2 and 8.8: `demo-zero` is spelled out in the regex, so loading the demo pack works."""
    pattern = _schema("market.v2.json")["properties"]["fee_schedule_id"]["pattern"]
    for schedule_id in ("demo-zero", "kalshi-general-2026-09", "manifold-zero-2026-09"):
        assert re.match(pattern, schedule_id), schedule_id
    assert re.match(pattern, "Kalshi-General-2026-09") is None
    text = CONTRACT.read_text(encoding="utf-8")
    # section 2 writes the same regex in a markdown table, so its pipe is escaped there
    assert pattern.replace("|", chr(92) + "|") in text


def test_news_schema_refuses_a_kind_that_contradicts_its_source() -> None:
    validator = _validator("news.v1.json")
    item = _fixture("news.wce-20160623-0007.json")
    wrong_kind = copy.deepcopy(item)
    wrong_kind["kind"] = "comment"
    assert _errors(validator, wrong_kind) != []
    float_time = copy.deepcopy(item)
    float_time["published_at_ms"] = 1466726400000.5
    assert _errors(validator, float_time) != []
    over_scale = copy.deepcopy(item)
    over_scale["match_scores_permille"] = [400_600]  # section 7.6: the score lands in [0, 1000]
    assert _errors(validator, over_scale) != []


def test_news_schema_requires_a_revision_for_a_point_in_time_article() -> None:
    """Section 7.1: an as-of background snapshot names its revid and the day it asked for."""
    validator = _validator("news.v1.json")
    item = _fixture("news.wce-20160623-0007.json")
    asof = copy.deepcopy(item)
    asof.update(
        source="wikipedia_asof", kind="background", news_id="wasof-20160601-0001",
        section=None, revid=None, asof_day=None,
    )
    assert _errors(validator, asof) != []
    asof["revid"] = 726_318_555
    asof["asof_day"] = "2016-06-01"
    assert _errors(validator, asof) == []
    asof["asof_day"] = "2016-6-1"
    assert _errors(validator, asof) != []
    stamped_headline = copy.deepcopy(item)
    stamped_headline["revid"] = 1  # only wikipedia_asof carries one
    assert _errors(validator, stamped_headline) != []


def test_actions_schema_is_strict_and_flat() -> None:
    validator = _validator("actions.v2.json")
    actions = _fixture("actions.sample.json")
    extra = copy.deepcopy(actions)
    extra["markets"][0]["confidence"] = 3
    assert _errors(validator, extra) != []
    missing = copy.deepcopy(actions)
    del missing["markets"][0]["side"]
    assert _errors(validator, missing) != []
    long_notes = copy.deepcopy(actions)
    long_notes["notes"] = "x" * 501
    assert _errors(validator, long_notes) != []
    six_lessons = copy.deepcopy(actions)
    six_lessons["lessons"] = [{"text": "t", "market_ids": []}] * 6
    assert _errors(validator, six_lessons) != []
    bad_prob = copy.deepcopy(actions)
    bad_prob["markets"][0]["prob_ppm"] = 0.5
    assert _errors(validator, bad_prob) != []


def test_journal_schema_refuses_unknown_types_floats_and_extra_fields() -> None:
    validator = _validator("journal.v2.json")
    events = _events("journal.backtest.jsonl")
    filled = _of_type(events, "filled")[0]
    with_float = copy.deepcopy(filled)
    with_float["cash_delta_cents"] = -320.5
    assert _errors(validator, with_float) != []
    extra = copy.deepcopy(filled)
    extra["latency_ms"] = 12  # wall clock never enters a journal
    assert _errors(validator, extra) != []
    unknown = copy.deepcopy(filled)
    unknown["type"] = "trade_executed"  # an Exchange name, not a pmx one
    assert _errors(validator, unknown) != []
    wrong_phase = copy.deepcopy(filled)
    wrong_phase["phase"] = "decide"  # settle is legal since C1b for an event fill (17.3, R152); decide never is
    assert _errors(validator, wrong_phase) != []
    no_seq = copy.deepcopy(filled)
    del no_seq["seq"]
    assert _errors(validator, no_seq) != []


def test_journal_schema_requires_the_new_provenance_fields() -> None:
    """Sections 8.1 and 9.2: memory and contamination provenance are journaled, not implied."""
    validator = _validator("journal.v2.json")
    started = _events("journal.backtest.jsonl")[0]
    assert _errors(validator, started) == []
    for field in ("folds", "memory_from_run_id", "memory_hash", "memory_from_run_t1_ms",
                  "contamination_hash"):
        stripped = copy.deepcopy(started)
        del stripped[field]
        assert _errors(validator, stripped) != [], field
    genome_without_members = copy.deepcopy(started)
    del genome_without_members["roster"][0]["genome"]["members"]
    assert _errors(validator, genome_without_members) != []


def test_a_generation_that_scored_nothing_on_validation_is_still_legal() -> None:
    """Section 9.4: `candidates_evaluated_cum` is non negative, not strictly positive."""
    validator = _validator("journal.v2.json")
    closed = _of_type(_events("journal.evolution.jsonl"), "generation_closed")[0]
    assert closed["candidates_evaluated_cum"] == 0
    assert _errors(validator, closed) == []
    ended = _of_type(_events("journal.evolution.jsonl"), "evolution_ended")[0]
    assert _errors(validator, ended) == []


# --------------------------------------------------------------------------------------------------
# The contract text and the schema agree
# --------------------------------------------------------------------------------------------------
#: Amendment C1b's three events: declared under ``$defs`` now, admitted to ``oneOf`` by gate G2 together with
#: their ``pmx.journal`` dataclasses, which D7's tests pin to the schema (ruling R164, the discipline of R129).
C1B_PENDING_EVENTS = frozenset({"cash_event_applied", "instrument_closed", "forecast_resolved"})


def test_every_catalogue_event_has_a_schema_and_vice_versa() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    start = text.index("### 9.2 The backtest catalogue")
    end = text.index("### 9.5 Artefacts on disk")
    catalogue = set(re.findall(r"^\| `([a-z_]+)` \|", text[start:end], flags=re.MULTILINE))
    schema = _schema("journal.v2.json")
    in_schema = {ref["$ref"].rsplit("/", 1)[1] for ref in schema["oneOf"]}
    assert catalogue == in_schema | C1B_PENDING_EVENTS
    # Ruling R164: the three are declared, not yet admitted; the day one is admitted without its class, or
    # dropped from $defs, this fails and the gate has to say why.
    assert set(schema["$defs"]) >= C1B_PENDING_EVENTS
    assert C1B_PENDING_EVENTS.isdisjoint(in_schema)
    for event in C1B_PENDING_EVENTS:
        assert schema["$defs"][event]["properties"]["type"] == {"const": event}
    deferred = _flat(text.split("### 17.9 What amendment C1b does not own")[1])
    assert "EVENT_TYPES" in deferred and "PHASES" in deferred and "gate G2" in deferred


def test_every_event_type_in_a_fixture_is_in_the_catalogue() -> None:
    schema = _schema("journal.v2.json")
    in_schema = {ref["$ref"].rsplit("/", 1)[1] for ref in schema["oneOf"]}
    used = {
        e["type"]
        for name in ("journal.backtest.jsonl", "journal.evolution.jsonl")
        for e in _events(name)
    }
    assert used <= in_schema
    assert {"market_listed", "market_priced"} <= used


#: The one optional field of the 7.2 table (ruling R169): a file written before the flag existed still loads.
OPTIONAL_MARKET_FIELDS = frozenset({"wiki_subject_provenance"})


def test_every_schema_field_of_the_market_table_is_in_the_schema() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    start = text.index("### 7.2 Market")
    end = text.index("### 7.3 NewsItem")
    table = text[start:end]
    fields = set(re.findall(r"^\| `([a-z_]+)` \|", table, flags=re.MULTILINE))
    schema = _schema("market.v2.json")
    assert fields == set(schema["properties"])
    assert set(schema["required"]) == set(schema["properties"]) - OPTIONAL_MARKET_FIELDS
    for field in OPTIONAL_MARKET_FIELDS:
        row = next(line for line in table.splitlines() if line.startswith(f"| `{field}` |"))
        assert "**optional**" in row, field


def test_the_phase_order_of_section_9_1_is_the_one_this_file_checks() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    spelled = "pre | open | observe | decide | execute | settle | learn | hive | close | generation | post"
    assert spelled in text
    assert tuple(part.strip() for part in spelled.split("|")) == PHASE_ORDER
    schema_phases = set(_schema("journal.v2.json")["$defs"]["phase"]["enum"])
    assert schema_phases == set(PHASE_ORDER)


def test_the_contract_carries_no_float_literal_in_a_formula() -> None:
    """Preamble rule 3 and section 1.2: `PPM_ONE`, never `1e6`, and no `/` in an integer formula."""
    text = CONTRACT.read_text(encoding="utf-8")
    assert "1e6" not in text
    assert "round_half_up(1e6" not in text
    assert chr(0x2014) not in text


# --------------------------------------------------------------------------------------------------
# The worked examples of section 1, executed
# --------------------------------------------------------------------------------------------------
def _cost_cents(size: int, price_bp: int) -> int:
    return -((-size * price_bp) // 100)


def _proceeds_cents(size: int, price_bp: int) -> int:
    return (size * price_bp) // 100


def _brier_micro(prob_ppm: int, outcome: int) -> int:
    d = prob_ppm - outcome * PPM_ONE
    return (d * d) // PPM_ONE


def _bp_ratio(numerator: int, denominator: int) -> int:
    scaled = numerator * BP_ONE
    q, r = divmod(abs(scaled), denominator)
    q += 1 if 2 * r >= denominator else 0
    return q if scaled >= 0 else -q


def _round_half_up(numerator: int, denominator: int) -> int:
    return (2 * numerator + denominator) // (2 * denominator)


def _neg_ln_micronats(prob_ppm: int) -> int:
    with localcontext() as ctx:
        ctx.prec = 40
        value = -(Decimal(prob_ppm) / Decimal(PPM_ONE)).ln() * Decimal(PPM_ONE)
        return int(value.to_integral_value(rounding=ROUND_HALF_UP))


def _fee_cents(mult_permille: int, size: int, price_bp: int) -> int:
    numerator = mult_permille * size * price_bp * (BP_ONE - price_bp)
    return -((-numerator) // 1_000_000_000)


def test_section_1_worked_examples() -> None:
    assert _brier_micro(700_000, 1) == 90_000
    assert _brier_micro(630_000, 1) == 136_900
    assert _cost_cents(40, 6_327) == 2_531
    assert _proceeds_cents(40, 6_327) == 2_530
    assert _cost_cents(40, 10_000 - 6_327) == 1_470
    assert _bp_ratio(-1_850, 100_000) == -185 and _bp_ratio(1_850, 100_000) == 185
    assert _neg_ln_micronats(500_000) == 693_147
    assert _neg_ln_micronats(10_000) == 4_605_170
    assert _neg_ln_micronats(990_000) == 10_050
    assert _fee_cents(70, 100, 5_000) == 175
    assert _fee_cents(70, 10, 9_000) == 7
    assert _fee_cents(0, 100, 5_000) == 0


def test_the_journal_scores_are_the_section_12_1_formulas() -> None:
    """The fixture's Brier numbers are recomputed here from its own `market_priced` events."""
    events = _events("journal.backtest.jsonl")
    outcome = _of_type(events, "settled")[0]["outcome"]
    priced = {e["bar_ms"]: e for e in _of_type(events, "market_priced")}
    forecasts: dict[str, dict[int, int]] = {}
    for e in _of_type(events, "forecast_recorded"):
        forecasts.setdefault(e["agent_id"], {})[e["bar_ms"]] = e["prob_ppm"]
    bars = sorted(priced)
    market_brier = _round_half_up(
        sum(_brier_micro(priced[t]["last_close_bp"] * 100, outcome) for t in bars), len(bars)
    )
    assert _of_type(events, "settled")[0]["market_brier_tw_micro"] == market_brier
    for applied in _of_type(events, "settlement_applied"):
        own = forecasts[applied["agent_id"]]
        expected = _round_half_up(sum(_brier_micro(own[t], outcome) for t in bars), len(bars))
        assert applied["agent_brier_tw_micro"] == expected, applied["agent_id"]
    settled = _of_type(events, "settled")[0]
    assert settled["life_mean_price_bp"] == _round_half_up(
        sum(priced[t]["close_bp"] for t in bars), len(bars)
    )
    assert settled["n_bars"] == len(bars)


# --------------------------------------------------------------------------------------------------
# Amendment C1 (CONTRACTS_V2 section 16): the four v3 schemas and their fixtures
# --------------------------------------------------------------------------------------------------
#: (schema, fixture, the ``$defs`` entry to validate against, or None for the schema's root).
C1_DOCUMENTS = (
    ("cluster.v1.json", "clusters.sample.json", None),
    ("cluster.v1.json", "cluster_overrides.sample.json", "override_file"),
    ("opportunity.v1.json", "opportunity.divergence.json", None),
    ("features.v1.json", "features.spec.json", None),
    ("features.v1.json", "features.vector.json", "feature_vector"),
    ("model_card.v1.json", "model_card.sample.json", None),
)
CONSTRAINT_KINDS = ("complement", "implies", "monotone_ladder", "sum_to_one")
DETECTOR_IDS = ("comparative", "divergence", "logic", "news_lead")
LIQUIDITY_MODELS = ("adversarial_mm", "calibrated_impact", "historical")
#: Every file amendment C1 added to the module map of section 13, with no owner of its own here: the test
#: reads the owner out of the map and checks it against ``docs/PLAN_V3_WAVES.md``.
C1_MAP_PATHS = (
    "schemas/cluster.v1.json", "schemas/opportunity.v1.json", "schemas/features.v1.json",
    "schemas/model_card.v1.json", "cli_analyze.py", "cli_learn.py", "cli_adversary.py",
    "cli_portfolio.py", "data/universe.py", "data/clusters.py", "data/impact.py", "data/embeddings.py",
    "engine/liquidity.py", "agents/families/torch_policy.py", "api/routes_analysis.py",
    "analysis/__init__.py", "analysis/news_lead.py", "analysis/divergence.py", "analysis/logic.py",
    "analysis/comparative.py", "analysis/report.py", "features/__init__.py", "features/spec.py",
    "features/build.py", "features/view.py", "features/quantise.py", "learn/__init__.py",
    "learn/supervised.py", "learn/env.py", "learn/llm_finetune.py", "adversary/__init__.py",
    "adversary/mm.py", "adversary/coevolution.py", "adversary/stress.py", "adversary/train/__init__.py",
    "portfolio/__init__.py", "portfolio/meta.py", "live/opportunities.py",
)


def _contract_section(start: str, end: str) -> str:
    """The text between two headings; `end` is looked for *after* `start`, never from the top of the file."""
    text = CONTRACT.read_text(encoding="utf-8")
    first = text.index(start)
    return text[first : text.index(end, first + len(start))]


def _flat(text: str) -> str:
    """The same text with every run of whitespace collapsed, so a sentence of the contract may wrap."""
    return " ".join(text.split())


@pytest.mark.parametrize(("schema", "fixture", "ref"), C1_DOCUMENTS)
def test_the_c1_fixtures_validate(schema: str, fixture: str, ref: str | None) -> None:
    validator = _validator(schema) if ref is None else _subschema(schema, ref)
    assert _errors(validator, _fixture(fixture)) == []


def test_cluster_ids_scores_and_asof_are_the_derivations_of_section_16_3() -> None:
    doc = _fixture("clusters.sample.json")
    for cluster in doc["clusters"]:
        assert cluster["cluster_id"] == "ec-" + _sha(sorted(cluster["market_ids"]))[:16]
        assert len(cluster["market_ids"]) >= 2
        assert cluster["market_ids"] == sorted(cluster["market_ids"])
        # 16.3: the score is the MINIMUM over the reasons, because the matcher is conservative.
        assert cluster["score_permille"] == min(r["score_permille"] for r in cluster["reasons"])
        assert cluster["score_permille"] >= doc["min_score_permille"]
        # Ruling R116: a cluster is as-of only when every reason it stored is.
        assert cluster["asof"] == (
            all(r["asof"] for r in cluster["reasons"]) and cluster["source"] == "matcher"
        )
    for constraint in doc["constraints"]:
        payload = [constraint["kind"], constraint["market_ids"], constraint["direction"]]
        expected = f"cn-{constraint['kind']}-" + _sha(payload)[:12]
        assert constraint["constraint_id"] == expected
        assert constraint["kind"] in CONSTRAINT_KINDS
        if constraint["kind"] in ("implies", "complement"):
            assert len(constraint["market_ids"]) == 2
        assert (constraint["direction"] == "none") == (constraint["kind"] != "monotone_ladder")


def test_the_manual_override_file_is_sealed_into_the_clusters_document() -> None:
    """Ruling R117: the review is hashed into the document, so it cannot be edited after the seal."""
    raw = (FIXTURES / "cluster_overrides.sample.json").read_bytes()
    doc = _fixture("clusters.sample.json")
    assert doc["overrides_sha256"] == hashlib.sha256(raw).hexdigest()
    overrides = _fixture("cluster_overrides.sample.json")
    assert overrides["dataset_name"] == doc["dataset_name"]
    forbidden = {tuple(entry["market_ids"]) for entry in overrides["forbid"]}
    for cluster in doc["clusters"]:
        assert tuple(cluster["market_ids"]) not in forbidden


def test_opportunity_ids_and_the_params_hash_are_derivations_of_section_16_4() -> None:
    doc = _fixture("opportunity.divergence.json")
    assert doc["params_sha256"] == _sha(doc["params"])
    assert doc["n_events"] == len(doc["events"])
    assert doc["detector_id"] in DETECTOR_IDS
    for event in doc["events"]:
        payload = [
            event["detector_id"], sorted(event["market_ids"]),
            event["window"]["start_ms"], event["window"]["end_ms"],
            event["cluster_id"], event["constraint_id"],
        ]
        assert event["opportunity_id"] == f"op-{event['detector_id']}-" + _sha(payload)[:16]
        assert event["window"]["start_ms"] <= event["window"]["end_ms"]
        # 16.4: a play-money leg is never tradable for money, whatever the size.
        assert event["tradable_for_money"] is (event["currency"] == "usd")


def test_a_divergence_event_names_a_cluster_that_exists_and_its_members() -> None:
    """16.4: a divergence event lives on a cluster; a free-floating pair would be an unreviewable claim."""
    clusters = {c["cluster_id"]: c for c in _fixture("clusters.sample.json")["clusters"]}
    for event in _fixture("opportunity.divergence.json")["events"]:
        cluster = clusters[event["cluster_id"]]
        assert set(event["market_ids"]) <= set(cluster["market_ids"])
        assert len(cluster["providers"]) >= 2  # cross-venue divergence needs two venues
        assert event["currency"] == "mixed" and set(cluster["currencies"]) == {"mana", "usd"}


def test_the_features_fixture_is_the_normative_layout_of_section_16_5() -> None:
    doc = _fixture("features.spec.json")
    features = doc["features"]
    assert doc["features_hash"] == _sha(features)
    assert doc["n_features"] == len(features) == 37
    assert [f["index"] for f in features] == list(range(len(features)))
    assert len({f["name"] for f in features}) == len(features)
    assert {f["source"] for f in features} == {
        "market_view", "bars", "calendar", "category", "news", "cluster", "portfolio", "constraint",
    }
    for spec in features:
        assert spec["lo"] <= spec["hi"] and spec["scale"] >= 1
        # Ruling R116: cluster and constraint arithmetic is as-of only, and nothing else is marked so.
        assert spec["asof_only"] is (spec["source"] in ("cluster", "constraint"))
    # 16.5: the quantisation boundary is fixed, not a dial.
    assert doc["quantise"] == {
        "prob_scale": PPM_ONE, "rounding": "half_up", "position_unit": 1,
        "clamp_lo_ppm": 0, "clamp_hi_ppm": PPM_ONE,
    }
    vector = _fixture("features.vector.json")
    assert vector["features_hash"] == doc["features_hash"]
    assert len(vector["values"]) == doc["n_features"]


def test_the_model_card_is_pinned_to_its_weights_and_to_the_feature_layout() -> None:
    card = _fixture("model_card.sample.json")
    assert card["model_id"] == "mc-" + card["weights_sha256"][:16]
    assert card["features_hash"] == _fixture("features.spec.json")["features_hash"]
    assert card["train"]["fold"] == "train" and card["validation"]["fold"] == "validation"
    assert card["train"]["t0_ms"] < card["train"]["t1_ms"]
    assert card["n_parameters"] <= 5_000_000          # PRD v3 5.4's ceiling, for every non-QLoRA family
    assert not isinstance(card["validation"]["skill_lb_micro"], float)


@pytest.mark.parametrize(
    ("mutate", "why"),
    [
        (lambda d: d["clusters"][0].update(market_ids=[d["clusters"][0]["market_ids"][0]]), "one member"),
        (lambda d: d["clusters"][0]["reasons"].append(
            {"kind": "manual", "asof": True, "detail": "hand", "score_permille": 1000}), "manual is as-of"),
        (lambda d: d["constraints"][0].update(direction="none"), "a ladder with no direction"),
        (lambda d: d["clusters"][0].update(score_permille=880.5), "a float score"),
        (lambda d: d["constraints"][1].update(market_ids=["kalshi-a", "kalshi-b", "kalshi-c"]),
         "a three-legged complement"),
        # Ruling R132: an as-of cluster never read a resolution date, so it cannot report a span.
        (lambda d: d["clusters"][0].update(resolution_span_ms=86_400_000),
         "an as-of cluster reporting a resolution span"),
        (lambda d: d.update(dataset_hash="0" * 64), "a cluster document holding the hash it is inside"),
    ],
)
def test_the_cluster_schema_refuses_what_section_16_3_forbids(mutate: Any, why: str) -> None:
    doc = copy.deepcopy(_fixture("clusters.sample.json"))
    mutate(doc)
    assert _errors(_validator("cluster.v1.json"), doc) != [], why


@pytest.mark.parametrize(
    ("mutate", "why"),
    [
        (lambda d: d["events"][0].update(tradable_for_money=True), "play money labelled tradable"),
        (lambda d: d["events"][0].update(size_ppm=62_000.5), "a float size"),
        (lambda d: d["events"][0].update(cluster_id=None), "a divergence with no cluster"),
        (lambda d: d.update(detector_id="vibes"), "an unregistered detector"),
        (lambda d: d["events"][0].update(evidence=[]), "an event with no evidence"),
    ],
)
def test_the_opportunity_schema_refuses_what_section_16_4_forbids(mutate: Any, why: str) -> None:
    doc = copy.deepcopy(_fixture("opportunity.divergence.json"))
    mutate(doc)
    assert _errors(_validator("opportunity.v1.json"), doc) != [], why


@pytest.mark.parametrize(
    ("mutate", "why"),
    [
        (lambda d: [f.update(asof_only=False) for f in d["features"] if f["source"] == "cluster"],
         "a cluster feature that is not as-of only"),
        (lambda d: d["features"][0].update(scale=0), "a scale of zero"),
        (lambda d: d["quantise"].update(prob_scale=1_000), "a quantisation scale that is not ppm"),
        (lambda d: d["features"][0].update(name="Last_Price_BP"), "a name outside the identifier shape"),
    ],
)
def test_the_features_schema_refuses_what_section_16_5_forbids(mutate: Any, why: str) -> None:
    doc = copy.deepcopy(_fixture("features.spec.json"))
    mutate(doc)
    assert _errors(_validator("features.v1.json"), doc) != [], why


@pytest.mark.parametrize(
    ("mutate", "why"),
    [
        (lambda d: d["train"].update(fold="sealed"), "a card trained on the sealed fold"),
        (lambda d: d.update(n_parameters=6_000_000), "an MLP above the 5 M ceiling"),
        (lambda d: d.update(model_id="mc-not-hex"), "an id that is not the weights digest"),
        (lambda d: d.update(inference_kind="gpu"), "an inference path that cannot replay"),
        (lambda d: d["validation"].update(brier_tw_micro=184_220.5), "a float score"),
    ],
)
def test_the_model_card_schema_refuses_what_section_16_5_forbids(mutate: Any, why: str) -> None:
    doc = copy.deepcopy(_fixture("model_card.sample.json"))
    mutate(doc)
    assert _errors(_validator("model_card.v1.json"), doc) != [], why


# --------------------------------------------------------------------------------------------------
# Amendment C1: the contract text itself
# --------------------------------------------------------------------------------------------------
def test_section_16_declares_every_interface_the_v3_waves_are_built_against() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    for heading in (
        "## 16. v3 interfaces (amendment C1)",
        "### 16.1 The `LiquidityModel` protocol and the envelope rule",
        "### 16.2 The decision latency rule",
        "### 16.3 `EventCluster` and `Constraint`",
        "### 16.4 `OpportunityEvent` and the analysis outputs",
        "### 16.5 `features.v1`, the `torch_policy` genome and the quantisation rule",
        "### 16.6 The v3 module map and the three new architecture rules",
        "### 16.7 v3 identifier formats",
        "### 16.8 What amendment C1 does not own",
        "### 15.8 Amendment C1",
    ):
        assert heading in text, heading
    section = _contract_section("### 15.8 Amendment C1", "\n---\n")
    rulings = set(re.findall(r"^\| (R1[0-4][0-9]) \|", section, re.MULTILINE))
    # R107..R125 are C1's first pass; R126..R143 are its arbitration pass over the findings against it.
    assert rulings == {f"R{n}" for n in range(107, 144)}


def test_the_liquidity_protocol_and_its_envelope_are_literal() -> None:
    section = _contract_section("### 16.1 The `LiquidityModel` protocol", "### 16.2 The decision latency")
    for name in (
        # Ruling R126: the model is handed the whole bar's batch, with the kind, the limit price and the
        # fee schedule on it, because the limit rule of 8.6 and the fee role of rule 5 need all three.
        "def quote_bar(self, market_view: LiquidityMarketView, bar: Bar,",
        "orders: Sequence[LiquidityOrder], *, schedule: FeeSchedule,",
        "def on_bar_end(self, observed_flow: ObservedFlow) -> None: ...",
        "def check_envelope(model: LiquidityModel, *, market_view: LiquidityMarketView, bar: Bar,",
        "orders: Sequence[LiquidityOrder], config: RunConfig,",
        "def allocate_cap(orders: Sequence[LiquidityOrder], *, cap_milli: int) -> tuple[int, ...]: ...",
        # Ruling R173: the two functions that establish rule 5 receive the view whose kind and scales the
        # fee call needs, as a keyword-only default (preamble rule 2).
        "def truncate_for_cash(fill: Fill, *, max_filled_milli: int, schedule: FeeSchedule,",
        "market_view: LiquidityMarketView | None = None) -> Fill: ...",
        "def slippage_ticks(base: int, *, config: RunConfig, taken_pct: int, view: LiquidityMarketView) -> int: ...",
        "def clamp_price(x: int, *, view: LiquidityMarketView) -> int: ...",
        "class LiquidityOrder:",
        "limit_price_bp: int | None",
        "resting_since_ms: int | None",
        # Ruling R130: the two numbers the `filled` event requires are on the Fill, and so is the role.
        "price_bp: int",
        "base_price_bp: int",
        "slippage_bp: int",
        "filled_milli: int",
        "unfilled_milli: int",
        "unfilled_reason: str",
        "price_source: str",
        "role: str",
        "fee_cents: int",
    ):
        assert name in section, name
    # Ruling R138: vwap is gone from the protocol; it survives only in the journal schema's enum.
    assert '"open"|"quote"|"limit"|"impact"|"mm"' in section
    assert '"vwap"|' not in section
    # The five envelope rules, numbered, with R41's exemption restated inside rule 2.
    flat = _flat(section)
    assert re.search(r"^1\. \*\*Never quote inside the observed spread", section, re.MULTILINE)
    assert re.search(r"^4\. \*\*Never let arrival order matter", section, re.MULTILINE)
    assert re.search(r"^5\. \*\*Never invent a fee", section, re.MULTILINE)
    assert "ruling R41" in flat and 'source == "reconstructed"' in flat
    # Ruling R127: the invariant is the multiset, and pro-rata rationing is what makes it hold.
    assert "multiset of returned `Fill`s is invariant" in flat
    assert "rations pro rata" in flat
    assert "role=fill.role" in flat
    for model in LIQUIDITY_MODELS:
        assert f"`{model}`" in section, model
    assert 'liquidity: str = "historical"' in section
    assert "liquidity_params_hash" in section


def test_the_decision_latency_rule_is_stated_in_every_section_it_changes() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    assert "DECISION_LATENCY_BARS = 1" in text
    calendar = _contract_section("### 5.3 The run calendar", "### 5.4 As-of")
    assert "`actionable(m, t)`" in calendar and "tradable(m, t + interval_ms)" in calendar
    asof = _flat(_contract_section("### 5.4 As-of", "### 5.5 The safety lag"))
    assert "open of bar" in asof and "vwap" in asof  # the superseded spelling is named, not deleted
    phases = _flat(_contract_section("### 8.2 The bar phase order", "### 8.3 `Observation`"))
    assert "drain the queue" in phases and "stays after `observe`" in phases
    fills = _flat(_contract_section("### 8.6 Fills", "### 8.7 Settlement"))
    assert "decided_at_ms" in fills and "no_liquidity" in fills
    latency = _flat(_contract_section("### 16.2 The decision latency rule", "### 16.3 `EventCluster`"))
    assert "`order_rejected(not_tradable)`" in latency
    assert "last tradable bar has nowhere to fill" in latency


def test_the_cluster_visibility_rule_has_both_halves() -> None:
    section = _flat(_contract_section("### 16.3 `EventCluster`", "### 16.4 `OpportunityEvent`"))
    assert "never a label to an agent" in section.lower()
    assert "never adds a market to an observation because it is a cluster peer" in section
    assert "exactly as any market's prices are" in section
    assert "asof" in section and "R116" in section


def test_every_module_map_row_of_amendment_c1_has_exactly_one_owner_from_the_v3_plan() -> None:
    module_map = _contract_section("## 13. Module map and file ownership", "### 13.1 The error taxonomy")
    plan = (REPO / "docs" / "PLAN_V3_WAVES.md").read_text(encoding="utf-8")
    packages = set(re.findall(r"^### ([A-Z][0-9a-z]{1,3})\b", plan, re.MULTILINE))
    assert {"R1a", "R2e", "R3d", "R4a", "R5a", "C1"} <= packages
    known = packages | {"E2", "C2", "C3", "C4", "C5"}
    for path in C1_MAP_PATHS:
        rows = [line for line in module_map.splitlines() if path in line]
        assert len(rows) == 1, (path, rows)
        match = re.search(r"\s+([A-Z][0-9a-z]{1,3})(?:\s+\(|\s*$)", rows[0])
        assert match is not None, rows[0]
        assert match.group(1) in known, (path, match.group(1))


def test_the_journal_edits_of_r111_are_applied_in_the_files_c1_owns() -> None:
    """Ruling R129: 9.2 and `journal.v2.json` are C1's, so the widening is applied, not deferred."""
    filled = _schema("journal.v2.json")["$defs"]["filled"]["properties"]
    assert {"open", "impact", "mm"} <= set(filled["price_source"]["enum"])
    assert "no_liquidity" in filled["unfilled_reason"]["enum"]
    # R138: vwap stays in the schema so a pre-amendment journal validates, and nowhere else.
    assert "vwap" in filled["price_source"]["enum"]
    for event in ("order_placed", "order_rejected"):
        properties = _schema("journal.v2.json")["$defs"][event]["properties"]
        assert "decided_at_ms" in properties, event
    catalogue = _contract_section("### 9.2 The backtest catalogue", "### 9.3 One emitter")
    assert '`price_source: "open"|"quote"|"limit"|"impact"|"mm"`' in catalogue
    assert '"no_cross"|"no_liquidity"' in catalogue
    assert catalogue.count("`decided_at_ms: int`") == 2
    # The one half that is still someone else's file is named in 16.8 with its gate.
    issues = _flat(CONTRACT.read_text(encoding="utf-8").split("### 16.8 What amendment C1 does not own")[1])
    assert "R129" in issues and "pmx.journal" in issues and "gate G2" in issues


def test_the_detector_and_constraint_vocabularies_agree_everywhere() -> None:
    opportunity = _schema("opportunity.v1.json")
    assert tuple(sorted(opportunity["$defs"]["detectorId"]["enum"])) == DETECTOR_IDS
    cluster = _schema("cluster.v1.json")
    kinds = cluster["$defs"]["constraint"]["properties"]["kind"]["enum"]
    assert tuple(sorted(kinds)) == CONSTRAINT_KINDS
    section = _contract_section("### 16.3 `EventCluster`", "### 16.5 `features.v1`")
    for kind in CONSTRAINT_KINDS:
        assert f'"{kind}"' in section, kind
    for detector in DETECTOR_IDS:
        assert f'"{detector}"' in section, detector


# --------------------------------------------------------------------------------------------------
# Amendment C1's arbitration pass (rulings R126 to R143)
# --------------------------------------------------------------------------------------------------
def test_no_cluster_document_carries_the_dataset_hash_it_is_inside() -> None:
    """Ruling R128: the walk of 4.3 covers `clusters/`, so a file in it cannot also hold the digest."""
    schema = _schema("cluster.v1.json")
    assert "dataset_hash" not in schema["properties"]
    assert "dataset_hash" not in schema["required"]
    assert "dataset_hash" not in _fixture("clusters.sample.json")
    assert "dataset_hash" not in schema["$defs"]["override_file"]["properties"]
    hashes = _contract_section("### 4.3 Hashes", "### 4.4 What is forbidden")
    assert "clusters/ sorted by relpath" in hashes
    assert "no `dataset_hash` field of their own" in _flat(hashes)


def test_an_asof_cluster_reports_no_resolution_span() -> None:
    """Ruling R132: a grouping filtered by a resolution tolerance is hindsight, reason stored or not."""
    for cluster in _fixture("clusters.sample.json")["clusters"]:
        assert (cluster["resolution_span_ms"] == -1) is cluster["asof"], cluster["cluster_id"]
    section = _flat(_contract_section("### 16.3 `EventCluster`", "### 16.4 `OpportunityEvent`"))
    assert "consulted `resolved_at_ms` in any way" in section
    assert "resolution_tolerance_ms" in section and "R132" in section
    leaks = _flat(_contract_section("### 7.9 Data leak rules", "### 7.10 v1 migration"))
    for name in ("cluster_id", "constraint_id", "MatchReason", "resolution_span_ms", "OpportunityEvent"):
        assert name in leaks, name


def test_a_constraint_that_names_a_cluster_lives_inside_it() -> None:
    """Ruling R143: the matcher extends the cluster rather than filing against a partial one."""
    doc = _fixture("clusters.sample.json")
    members = {c["cluster_id"]: set(c["market_ids"]) for c in doc["clusters"]}
    filed = 0
    for constraint in doc["constraints"]:
        if constraint["cluster_id"] is None:
            continue
        filed += 1
        assert constraint["cluster_id"] in members, constraint["constraint_id"]
        assert set(constraint["market_ids"]) <= members[constraint["cluster_id"]]
    assert filed >= 1, "the fixture must exercise the invariant, not only satisfy it vacuously"
    assert "lives inside it" in _contract_section("### 16.3 `EventCluster`", "### 16.4 `OpportunityEvent`")


def test_the_stale_normative_text_of_the_first_pass_is_applied_in_place() -> None:
    """Ruling R136: a section of this document is never a contract issue, so all four are amended here."""
    config = _contract_section("### 8.1 `RunConfig`", "### 8.2 The bar phase order")
    assert 'liquidity: str = "historical"' in config and "liquidity_params_hash" in config
    stats = _contract_section("### 12.4 Statistics", "### 12.5 Behavioural descriptors")
    assert "def block_key(market: MarketMeta, *, cluster_id: str | None = None) -> str" in stats
    preamble = _flat(_preamble())
    assert "A float is legal in exactly five places" in preamble
    assert "torch_policy" in preamble
    determinism = _contract_section("### 6.4 Determinism claims", "## 7. The data layer")
    assert "`torch_policy` backtest" in determinism and "integer_table" in determinism



def test_amendment_c1_owns_its_own_files_in_the_module_map() -> None:
    """Ruling R142: the amendment's inputs had two owners; section 13 now names C1 beside C0."""
    module_map = _contract_section("## 13. Module map and file ownership", "### 13.1 The error taxonomy")
    lines = module_map.splitlines()

    def _row(path: str) -> str:
        """A map row plus its continuation lines, which is where a long owner note wraps to."""
        first = next(i for i, line in enumerate(lines) if line.startswith("  " + path + " "))
        last = first + 1
        while last < len(lines) and lines[last].startswith(" " * 40):
            last += 1
        return _flat(" ".join(lines[first:last]))

    for path in ("docs/CONTRACTS_V2.md", "docs/PLAN_V2_WAVES.md"):
        assert "C1..C5" in _row(path), path
    assert "never edited by a package" not in _row("docs/PLAN_V2_WAVES.md")
    for path in ("    test_architecture.py", "    test_contract_schemas.py", "    fixtures/contract/**"):
        row = next(line for line in lines if line.startswith(path + " "))
        assert "C1..C5" in row, path
    owned = _flat(CONTRACT.read_text(encoding="utf-8").split("### 16.8 What amendment C1 does not own")[1])
    assert "section 13 now says exactly" in owned
    assert "A section of this document is never a contract issue" in owned


def test_the_end_to_end_test_of_rung_zero_has_an_owner() -> None:
    """Ruling R137: G7..G11 close rungs 1 to 6, so rung 0's file belonged to nobody."""
    module_map = _contract_section("## 13. Module map and file ownership", "### 13.1 The error taxonomy")
    row = next(line for line in module_map.splitlines() if "test_e2e_0_base.py" in line)
    assert "G6" in row
    waves = _contract_section("## 14. Wave plan cross-reference", "### 14.1 Decisions a reviewer")
    assert "| G6 |" in waves and "test_e2e_0_base.py" in waves
    assert "fails when a delivered rung's file is absent" in _flat(waves)
    assert "gate G6" in _flat(_contract_section("### 16.6 The v3 module map", "### 16.7 v3 identifier"))


def test_the_runner_is_handed_its_liquidity_model_and_never_builds_one() -> None:
    """Ruling R139: the old default said the runner both never builds a model and builds one."""
    section = _contract_section("### 12.11 The structures", "### 12.12 The HTTP surface")
    assert "tree: RngTree, journal_dir: Path, liquidity: LiquidityModel," in section
    assert "liquidity: LiquidityModel | None = None" not in section
    flat = _flat(section)
    assert "required and keyword-only, exactly like" in flat
    assert "make_liquidity(config)" in flat


def test_the_dataset_manifest_carries_the_optional_cluster_and_impact_blocks() -> None:
    """Rulings R117 and R135: both blocks are declared here, and the impact one is train-fold only."""
    schema = _schema("dataset.v1.json")
    clusters = schema["properties"]["clusters"]
    assert "clusters" not in schema["required"] and "impact" not in schema["required"]
    assert "overrides_sha256" in clusters["required"]
    assert "dataset_hash" not in clusters["properties"]
    impact = schema["properties"]["impact"]
    assert impact["properties"]["fit_fold"] == {"const": "train"}
    for field in ("fit_t1_ms", "params_sha256", "impact_bp_per_pct_by_decile", "n_markets_fit"):
        assert field in impact["required"], field
    assert "clusters" in schema["properties"]["files"]["items"]["properties"]["path"]["pattern"]
    manifest = _contract_section("### 7.8 Manifest, seal and verify", "### 7.9 Data leak rules")
    assert "fit_fold" in manifest and "n_clusters_asof" in manifest
    liquidity = _flat(_contract_section("### 16.1 The `LiquidityModel` protocol", "### 16.2 The decision"))
    assert "fit on the training fold" in liquidity and "R135" in liquidity


def test_the_drain_is_driven_by_the_queue_and_not_by_the_bar_slice() -> None:
    """Ruling R131: a market that settled is in no BarSlice tuple, and it is still owed a rejection."""
    fills = _contract_section("### 8.6 Fills", "### 8.7 Settlement")
    assert "def pending_market_ids(self, *, t_ms: int) -> tuple[str, ...]: ..." in fills
    latency = _flat(_contract_section("### 16.2 The decision latency rule", "### 16.3 `EventCluster`"))
    assert "pending_market_ids(t_ms=t)" in latency
    assert "exactly one execute-phase event" in latency


def test_the_cap_is_rationed_pro_rata_and_the_truncation_stays_in_one_module() -> None:
    """Rulings R127, R130 and R141: fair rationing, and no fill arithmetic outside liquidity.py."""
    fills = _flat(_contract_section("### 8.6 Fills", "### 8.7 Settlement"))
    assert "rationed pro rata, not first come" in fills
    assert "(size_i * cap_milli) // requested" in fills
    assert "truncate_for_cash" in fills and "not `Execution`'s own arithmetic" in fills
    liquidity = _flat(_contract_section("### 16.1 The `LiquidityModel`", "### 16.2 The decision latency"))
    assert "R141" in _flat(_contract_section("### 15.8 Amendment C1", "## 16. v3 interfaces"))
    assert "identity of the agent" in liquidity


def test_the_adversary_reads_no_hive_and_the_float_view_reaches_the_inference_boundary() -> None:
    """Rulings R134 and R140: two impossible instructions, each replaced by the reachable one."""
    liquidity = _flat(_contract_section("### 16.1 The `LiquidityModel`", "### 16.2 The decision latency"))
    assert "hive's reputations are per" in liquidity and "R134" in liquidity
    features = _flat(_contract_section("### 16.5 `features.v1`", "### 16.6 The v3 module map"))
    assert "inference boundary of `pmx.agents.families.torch_policy`, and from nowhere else" in features
    rules = _flat(_contract_section("### 16.6 The v3 module map", "### 16.7 v3 identifier formats"))
    assert "float_view` is not a training library" in rules


def test_cluster_features_are_computed_over_the_peers_listed_at_now_ms() -> None:
    """Ruling R133: a peer created after `now_ms` is a market that does not yet exist."""
    features = _flat(_contract_section("### 16.5 `features.v1`", "### 16.6 The v3 module map"))
    assert "listed(peer, now_ms)" in features
    assert "cluster_peer_count` (index 28) counts those members only" in features
    assert "clamped to its `lo` when fewer than two qualify" in features
    spec = {f["name"]: f for f in _fixture("features.spec.json")["features"]}
    assert spec["cluster_peer_count"]["index"] == 28 and spec["cluster_gap_bp"]["index"] == 27
    assert spec["cluster_peer_count"]["asof_only"] is True


# --------------------------------------------------------------------------------------------------
# Amendment C1b (CONTRACTS_V2 section 17): instruments across kinds
# --------------------------------------------------------------------------------------------------
#: The six kinds of 17.1, in the order of ``INSTRUMENT_KINDS``.
INSTRUMENT_KINDS = ("binary", "spot_crypto", "perp", "fx", "equity", "future")
CASH_EVENT_KINDS = ("funding", "dividend", "split", "roll", "borrow_fee", "carry", "forced_flat")
#: The grid of each fixture instrument, so an engine event's ``t_ms`` can be checked against ruling R176.
FIXTURE_INTERVAL_MS = {"binance-BTCUSDT.PERP": 3_600_000, "xnas-AAPL": MS_PER_DAY, "otcfx-EURUSD": MS_PER_DAY,
                       "xcme-ES": MS_PER_DAY}
QUANTILE_LEVELS_PPM = (100_000, 250_000, 500_000, 750_000, 900_000)
MILLI = 1_000
NOTIONAL_DENOMINATOR = 10**13
RANDOM_WALK_BRIER_MICRO = 250_000
C1B_DOCUMENTS = (
    ("instrument.v1.json", "instrument.binance-btcusdt-perp.json"),
    ("instrument.v1.json", "instrument.xnas-aapl.json"),
    ("session_calendar.v1.json", "session_calendar.xnys.json"),
    ("forecast.v1.json", "forecast.sample.json"),
)
#: Every file amendment C1b added to the module map of section 13, with the owners the plan allows.
C1B_MAP_PATHS = (
    "schemas/instrument.v1.json", "schemas/cash_event.v1.json", "schemas/session_calendar.v1.json",
    "schemas/forecast.v1.json", "data/importers/binance.py", "data/importers/kraken.py",
    "data/importers/coinbase.py", "data/importers/bybit.py", "data/importers/yahoo.py",
    "data/importers/frankfurter.py", "data/importers/ecb.py", "data/news/edgar.py", "data/news/fred.py",
    "data/news/release_calendar.py", "data/news/cboe.py", "data/sessions.py", "data/calendars/*.json",
    "data/universe_finance.py", "agents/families/random_walk.py", "agents/families/carry.py",
    "agents/families/basis.py", "agents/families/pairs.py", "agents/families/vol_regime.py",
    "agents/families/calendar.py", "analysis/cross_domain.py", "test_import_crypto.py",
    "test_import_yahoo_fx.py", "test_finance_news.py", "test_sessions_universe.py",
    "e2e/test_e2e_1b_multi_asset.py", "e2e/test_e2e_2b_cross_domain.py",
    "lexicons/kalshi_series_subjects.v1.json", "lexicons/kalshi_series_categories.v1.json",
)
#: D1 owns ``data/sessions.py`` since ruling R174 (it must exist at gate G2, before wave 3b).
C1B_KNOWN_OWNERS = {"C1b", "F1", "F2", "F3", "F4", "D1", "D2", "A1", "R2f", "G3b", "G8"}


def _notional_micro(size_milli: int, price_ticks: int, tick: int, point: int) -> int:
    return size_milli * price_ticks * tick * point


def _cash_out_cents(size_milli: int, price_ticks: int, tick: int, point: int) -> int:
    return -((-_notional_micro(size_milli, price_ticks, tick, point)) // NOTIONAL_DENOMINATOR)


def _cash_in_cents(size_milli: int, price_ticks: int, tick: int, point: int) -> int:
    return _notional_micro(size_milli, price_ticks, tick, point) // NOTIONAL_DENOMINATOR


def _directional_brier_micro(up_ppm: int, realised_sign: int) -> int:
    if realised_sign > 0:
        return _brier_micro(up_ppm, 1)
    if realised_sign < 0:
        return _brier_micro(up_ppm, 0)
    return (_brier_micro(up_ppm, 1) + _brier_micro(up_ppm, 0)) // 2


def _pinball_micro(quantiles: list[int], realised: int, ref: int) -> int:
    total = 0
    for level, q in zip(QUANTILE_LEVELS_PPM, quantiles, strict=True):
        total += level * max(0, realised - q) + (PPM_ONE - level) * max(0, q - realised)
    return _round_half_up(total, len(QUANTILE_LEVELS_PPM) * ref)


def _half_spread_ticks(h1: int, l1: int, h2: int, l2: int, open_ticks: int, *, floor: int = 0) -> int:
    """Section 17.4's Corwin and Schultz estimator, spelled here from the contract, not from the code."""
    with localcontext() as ctx:
        ctx.prec = 40
        dh1, dl1, dh2, dl2 = (Decimal(x) for x in (h1, l1, h2, l2))
        beta = (dh1 / dl1).ln() ** 2 + (dh2 / dl2).ln() ** 2
        gamma = (max(dh1, dh2) / min(dl1, dl2)).ln() ** 2
        k = Decimal(3) - Decimal(2) * Decimal(2).sqrt()
        alpha = ((Decimal(2) * beta).sqrt() - beta.sqrt()) / k - (gamma / k).sqrt()
        estimate = 0
        if alpha > 0:
            spread = Decimal(2) * (alpha.exp() - 1) / (1 + alpha.exp())
            estimate = int((spread * Decimal(open_ticks) / 2).to_integral_value(rounding=ROUND_HALF_UP))
    return max(estimate, floor)


def _cash_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = _fixture("cash_events.sample.json")["events"]
    return events


@pytest.mark.parametrize(("schema", "fixture"), C1B_DOCUMENTS)
def test_the_c1b_fixtures_validate(schema: str, fixture: str) -> None:
    assert _errors(_validator(schema), _fixture(fixture)) == []


def test_every_cash_event_kind_has_a_fixture_that_validates() -> None:
    validator = _validator("cash_event.v1.json")
    events = _cash_events()
    assert tuple(sorted(e["kind"] for e in events)) == tuple(sorted(CASH_EVENT_KINDS))
    for event in events:
        assert _errors(validator, event) == [], event["kind"]


def test_the_two_cash_event_definitions_agree_field_by_field() -> None:
    """17.3: an instrument file embeds its data events; the embedded shape may not drift from the schema."""
    root = _schema("cash_event.v1.json")
    instrument = _schema("instrument.v1.json")
    embedded = instrument["$defs"]["data_cash_event"]
    assert set(root["properties"]) == set(embedded["properties"])
    assert set(root["required"]) == set(embedded["required"]) == set(root["properties"])

    def _resolved(doc: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
        """The node with a local ``$ref`` followed and its prose dropped, so two spellings compare as one."""
        if "$ref" in node:
            node = doc["$defs"][node["$ref"].rsplit("/", 1)[1]]
        return {k: v for k, v in node.items() if k != "description"}

    for name in ("schema_version", "cash_event_id", "market_id", "t_ms", "detail"):
        assert _resolved(root, root["properties"][name]) == _resolved(instrument, embedded["properties"][name]), name
    assert embedded["properties"]["kind"]["enum"] == list(CASH_EVENT_KINDS[:4])
    assert embedded["properties"]["origin"] == {"const": "data"}


def test_the_binary_scales_and_the_worked_examples_of_section_17_1() -> None:
    """Rulings R145 and R146: (100, 1_000_000) reproduces section 1.4 and the PRD's 10_000 does not."""
    assert _cash_out_cents(40_000, 6_327, 100, 1_000_000) == 2_531 == _cost_cents(40, 6_327)
    assert _cash_in_cents(40_000, 6_327, 100, 1_000_000) == 2_530 == _proceeds_cents(40, 6_327)
    assert _cash_out_cents(40_000, 6_327, 10_000, 1_000_000) == 253_080  # the PRD's row, a hundred times off
    for price_bp in range(1, 10_000):
        for size in (1, 7, 40):
            assert _cash_out_cents(size * MILLI, price_bp, 100, 1_000_000) == _cost_cents(size, price_bp)
            assert _cash_in_cents(size * MILLI, price_bp, 100, 1_000_000) == _proceeds_cents(size, price_bp)
    assert _cash_in_cents(40 * MILLI, 10_000, 100, 1_000_000) == 40 * 100  # the payout of 8.7
    # BTCUSDT, ES, EURUSD
    assert _cash_out_cents(1, 6_341_257, 10_000, 1_000_000) == 6_342
    assert _cash_in_cents(1, 6_341_257, 10_000, 1_000_000) == 6_341
    assert _cash_out_cents(2_000, 21_729, 250_000, 50_000_000) == 54_322_500
    assert _cash_in_cents(2_000, 21_729, 250_000, 50_000_000) == 54_322_500
    assert _cash_out_cents(100_000_000, 108_325, 10, 1_000_000) == 10_832_500
    # the overflow bounds of ruling R147
    assert _notional_micro(1_000, 40_000, 250_000, 50_000_000) == 5 * 10**20
    per_milli = 21_729 * 250_000 * 50_000_000
    assert _notional_micro(36_817_156_795, 1, per_milli, 1) <= 10**15 * NOTIONAL_DENOMINATOR
    assert _notional_micro(36_817_156_796, 1, per_milli, 1) > 10**15 * NOTIONAL_DENOMINATOR
    assert _cash_in_cents(10**12, 100_000, 10, 1_000_000) == 10**11  # EURUSD: the size cap fires first
    text = CONTRACT.read_text(encoding="utf-8")
    for literal in ("36_817_156_795", "BINARY_TICK_SIZE_MICRO = 100", "BINARY_POINT_VALUE_MICRO = 1_000_000",
                    "NOTIONAL_DENOMINATOR = MILLI * MICRO * MICRO // CENTS_PER_UNIT"):
        assert literal in text, literal


def test_the_corwin_schultz_half_spread_is_the_worked_value_of_section_17_4() -> None:
    assert _half_spread_ticks(6_360_000, 6_300_000, 6_350_000, 6_310_000, 6_330_000) == 14_619
    assert _half_spread_ticks(100, 100, 100, 100, 100) == 0            # two flat bars: the demo pack case
    assert _half_spread_ticks(110, 100, 121, 110, 110) == 0            # two trending bars: alpha < 0
    assert _half_spread_ticks(110, 100, 121, 110, 110, floor=5) == 5   # the schedule's floor applies
    section = _flat(_contract_section("### 17.4 Fee, borrow and carry schedules", "### 17.5 The forecast record"))
    assert "14_619" in section and "Corwin and Schultz" in section and "min_half_spread_ticks" in section


def test_the_directional_brier_and_the_pinball_loss_are_the_formulas_of_section_17_5() -> None:
    """Rulings R158 and R159: the random walk scores zero skill on every outcome, tie included."""
    for sign in (-1, 0, 1):
        assert _directional_brier_micro(500_000, sign) == RANDOM_WALK_BRIER_MICRO
    assert _directional_brier_micro(700_000, 1) == 90_000
    assert _directional_brier_micro(700_000, -1) == 490_000
    assert _directional_brier_micro(700_000, 0) == 290_000
    horizon = _fixture("forecast.sample.json")["horizons"][0]
    ref, realised = 6_341_257, 6_352_010
    agent = _pinball_micro(horizon["quantiles_ticks"], realised, ref)
    baseline = _pinball_micro([ref] * 5, realised, ref)
    assert (agent, baseline, baseline - agent) == (666, 848, 182)
    assert _pinball_micro([ref] * 5, realised, ref) - baseline == 0  # the random walk's pinball skill
    section = _flat(_contract_section("### 17.5 The forecast record", "### 17.6 Claims, leaderboards"))
    for literal in ("pinball_micro = 666", "848", "290_000", "RANDOM_WALK_BRIER_MICRO = 250_000",
                    "QUANTILE_LEVELS_PPM = (100_000, 250_000, 500_000, 750_000, 900_000)", "zero by construction"):
        assert literal in section, literal


@pytest.mark.parametrize(
    ("mutate", "why"),
    [
        (lambda d: d.update(kind="binary"), "a binary stored as an instrument file"),
        (lambda d: d.update(tick_size_micro=0), "a zero tick"),
        (lambda d: d.update(kind="spot_crypto", underlying_id=None, short_allowed=True), "a shortable spot"),
        (lambda d: d.update(kind="equity", underlying_id=None, borrow_schedule_id=None, short_allowed=True),
         "an equity short with no borrow schedule"),
        (lambda d: d["bars"][0].update(close_ticks=6_341_257.5), "a float price"),
        (lambda d: d.update(provider="nyse"), "a provider outside the seventeen"),
        (lambda d: d.update(roll_source="vendor"), "a roll source on a perp"),
        (lambda d: d["cash_events"][0].update(origin="engine"), "an engine event inside a data file"),
        (lambda d: d["cash_events"][0].update(kind="forced_flat"), "a forced flat inside a data file"),
        (lambda d: d["quality"].pop("tape_kind"), "a quality block without tape_kind"),
        (lambda d: d.update(bars=[]), "an instrument with no bar"),
        (lambda d: d.update(source="reconstructed"), "a reconstructed instrument"),
    ],
)
def test_the_instrument_schema_refuses_what_section_17_1_forbids(mutate: Any, why: str) -> None:
    doc = copy.deepcopy(_fixture("instrument.binance-btcusdt-perp.json"))
    mutate(doc)
    assert _errors(_validator("instrument.v1.json"), doc) != [], why


def test_cash_event_ids_origins_and_details_are_the_derivations_of_section_17_3() -> None:
    required = {
        "funding": {"rate_ppm", "mark_ticks"}, "dividend": {"dividend_micro"},
        "split": {"numerator", "denominator"},
        "roll": {"from_symbol", "to_symbol", "from_price_ticks", "to_price_ticks", "gap_ticks"},
        "borrow_fee": {"rate_ppm_per_day", "days", "mark_ticks"}, "forced_flat": {"reason", "price_ticks"},
        "carry": {"rate_ppm_per_day", "days", "mark_ticks"},
    }
    for event in _cash_events():
        payload = [event["market_id"], event["kind"], event["t_ms"], event["detail"]]
        assert event["cash_event_id"] == "ce-" + _sha(payload)[:16], event["kind"]
        assert event["origin"] == ("data" if event["kind"] in CASH_EVENT_KINDS[:4] else "engine")
        assert (event["source_url"] == "") is (event["origin"] == "engine")
        assert required[event["kind"]] <= set(event["detail"]), event["kind"]
        if event["kind"] == "roll":
            detail = event["detail"]
            assert detail["gap_ticks"] == detail["to_price_ticks"] - detail["from_price_ticks"]
        if event["origin"] == "engine":
            # Ruling R176: an engine event is stamped with the last instant of the bar it applies at, so
            # bar_of(t_ms) is that bar and never the next grid point.
            interval_ms = FIXTURE_INTERVAL_MS[event["market_id"]]
            assert event["t_ms"] % interval_ms == interval_ms - 1, event["kind"]
    # Ruling R175: a dividend, split or roll is stamped with the first instant of the new regime, a bar open.
    for event in _cash_events():
        if event["kind"] in ("dividend", "split", "roll"):
            assert event["t_ms"] % FIXTURE_INTERVAL_MS[event["market_id"]] == 0, event["kind"]
    aapl = _fixture("instrument.xnas-aapl.json")
    ex_date_bar = aapl["bars"][-1]
    assert all(e["t_ms"] == ex_date_bar["t_ms"] for e in aapl["cash_events"])
    assert ex_date_bar["open_ticks"] < aapl["bars"][-2]["close_ticks"] // 3  # the ex-date bar is in the new scale
    carry = next(e for e in _cash_events() if e["kind"] == "carry")
    assert carry["market_id"].startswith("otcfx-") and carry["detail"]["rate_ppm_per_day"] < 0
    # the instrument files carry data events only, in (t_ms, kind, id) order
    for name in ("instrument.binance-btcusdt-perp.json", "instrument.xnas-aapl.json"):
        events = _fixture(name)["cash_events"]
        assert events, name
        keys = [(e["t_ms"], CASH_EVENT_KINDS.index(e["kind"]), e["cash_event_id"]) for e in events]
        assert keys == sorted(keys)
        assert all(e["origin"] == "data" for e in events)


@pytest.mark.parametrize(
    ("kind", "mutate", "why"),
    [
        ("funding", lambda e: e.update(origin="engine", source_url=""), "a funding event claimed by the engine"),
        ("split", lambda e: e["detail"].update(denominator=0), "a split by zero"),
        ("roll", lambda e: e["detail"].pop("gap_ticks"), "a roll without its gap"),
        ("dividend", lambda e: e["detail"].update(dividend_micro=0), "a zero dividend"),
        ("forced_flat", lambda e: e.update(source_url="https://example.invalid"), "an engine event with a source"),
        ("forced_flat", lambda e: e["detail"].update(reason="expired"), "an unknown flat reason"),
        ("funding", lambda e: e.update(kind="swap"), "a kind outside the seven"),
        ("borrow_fee", lambda e: e["detail"].update(days=0), "a borrow fee over zero days"),
        ("funding", lambda e: e["detail"].update(rate_ppm=0.5), "a float rate"),
        ("carry", lambda e: e.update(origin="data", source_url="https://example.invalid"),
         "a carry claimed by data (ruling R177: the importer may not read the carry schedules)"),
        ("carry", lambda e: e["detail"].pop("days"), "a carry without its day count"),
    ],
)
def test_the_cash_event_schema_refuses_what_section_17_3_forbids(kind: str, mutate: Any, why: str) -> None:
    event = copy.deepcopy(next(e for e in _cash_events() if e["kind"] == kind))
    mutate(event)
    assert _errors(_validator("cash_event.v1.json"), event) != [], why


def test_the_session_calendar_is_dated_and_the_equity_bars_sit_inside_it() -> None:
    """Ruling R149: sessions are explicit and dated (DST moves the UTC open), and a bar exists only inside one."""
    calendar = _fixture("session_calendar.xnys.json")
    sessions = calendar["sessions"]
    assert len(sessions) >= 2
    for session in sessions:
        assert session["open_ms"] < session["close_ms"]
        assert calendar["window"]["start_ms"] <= session["open_ms"]
        assert session["close_ms"] <= calendar["window"]["end_ms"]
    for a, b in zip(sessions, sessions[1:], strict=False):
        assert a["close_ms"] <= b["open_ms"]
    opens_minute_of_day = {(s["open_ms"] % MS_PER_DAY) // 60_000 for s in sessions}
    assert len(opens_minute_of_day) == 2, "the fixture spans a daylight saving change on purpose"
    aapl = _fixture("instrument.xnas-aapl.json")
    assert aapl["session_calendar_id"] == calendar["calendar_id"]
    interval_ms = aapl["interval_min"] * 60_000

    def in_session(t_ms: int) -> bool:
        return any(t_ms < s["close_ms"] and t_ms + interval_ms > s["open_ms"] for s in sessions)

    assert all(in_session(bar["t_ms"]) for bar in aapl["bars"])
    saturday = aapl["bars"][0]["t_ms"] + 5 * MS_PER_DAY  # 2026-03-07
    assert not in_session(saturday)
    for mutate, why in (
        (lambda d: d.update(sessions=[]), "a calendar with no session"),
        (lambda d: d.update(as_of_date="2026-9-8"), "a malformed date"),
        (lambda d: d.pop("window"), "a calendar without its window"),
        (lambda d: d.update(calendar_id="XNYS"), "an id outside the slug shape"),
        (lambda d: d.update(calendar_id="continuous"), "the reserved id: synthesised, never a file (ruling R185)"),
    ):
        doc = copy.deepcopy(calendar)
        mutate(doc)
        assert _errors(_validator("session_calendar.v1.json"), doc) != [], why


def test_the_forecast_record_is_the_shape_of_section_17_5() -> None:
    forecast = _fixture("forecast.sample.json")
    horizons = forecast["horizons"]
    assert [h["horizon_bars"] for h in horizons] == sorted(h["horizon_bars"] for h in horizons)
    assert forecast["prob_ppm"] == horizons[0]["up_probability_ppm"]  # the shortest horizon
    for h in horizons:
        if h["quantiles_ticks"] is not None:
            assert h["quantiles_ticks"] == sorted(h["quantiles_ticks"])
    assert any(h["quantiles_ticks"] is None for h in horizons), "a direction-only horizon is legal"
    for mutate, why in (
        (lambda d: d.update(kind="binary"), "a binary with horizons"),
        (lambda d: d["horizons"][0].update(quantiles_ticks=[1, 2, 3, 4]), "four quantiles"),
        (lambda d: d.update(horizons=[]), "a continuous forecast with no horizon"),
        (lambda d: d["horizons"][0].update(up_probability_ppm=1_000_001), "a probability over one"),
        (lambda d: d.update(price_ref_ticks=0), "a zero reference price"),
    ):
        doc = copy.deepcopy(forecast)
        mutate(doc)
        assert _errors(_validator("forecast.v1.json"), doc) != [], why
    binary = copy.deepcopy(forecast)
    binary.update(kind="binary", market_id="kalshi-KXTEST-26", price_ref_ticks=6_327, prob_ppm=632_700, horizons=[])
    assert _errors(_validator("forecast.v1.json"), binary) == []


def _envelope(seq: int, etype: str, phase: str, bar_ms: int) -> dict[str, Any]:
    run_id = _events("journal.backtest.jsonl")[0]["run_id"]
    return {"seq": seq, "type": etype, "run_id": run_id, "bar_ms": bar_ms, "phase": phase}


def test_the_journal_schema_accepts_the_c1b_events_and_widenings() -> None:
    validator = _validator("journal.v2.json")
    bar = 1_772_438_400_000
    perp = "binance-BTCUSDT.PERP"
    pending = {name: _subschema("journal.v2.json", name) for name in C1B_PENDING_EVENTS}
    applied = {
        **_envelope(10, "cash_event_applied", "settle", bar), "agent_id": "carry_a", "market_id": perp,
        "cash_event_id": "ce-" + "0" * 16, "kind": "funding", "origin": "data", "position_before": 2_500,
        "position_after": 2_500, "avg_cost_ticks_before": 6_331_000, "avg_cost_ticks_after": 6_331_000,
        "cash_delta_cents": -16, "order_ids": [], "detail": {"rate_ppm": 100, "mark_ticks": 6_352_010},
    }
    assert _errors(pending["cash_event_applied"], applied) == []
    assert _errors(validator, applied) != []  # not in oneOf until gate G2 lands the dataclass (R164)
    split = {**applied, "kind": "split", "cash_delta_cents": 0, "position_after": 10_000,
             "avg_cost_ticks_after": 1_582_750, "detail": {"numerator": 4, "denominator": 1}}
    assert _errors(pending["cash_event_applied"], split) == []
    roll = {**applied, "kind": "roll", "cash_delta_cents": 0, "order_ids": ["o-00000007", "o-00000008"],
            "detail": {"from_symbol": "ESH26", "to_symbol": "ESM26", "from_price_ticks": 21_729,
                       "to_price_ticks": 21_788, "gap_ticks": 59}}
    cash_events = pending["cash_event_applied"]
    assert _errors(cash_events, roll) == []
    assert _errors(cash_events, {**split, "cash_delta_cents": 5}) != []       # a split moves no cash here
    assert _errors(cash_events, {**applied, "order_ids": ["o-00000001"]}) != []  # funding places no fill
    assert _errors(cash_events, {**applied, "kind": "swap"}) != []
    assert _errors(cash_events, {**applied, "phase": "execute"}) != []
    carry = {**applied, "kind": "carry", "origin": "engine", "market_id": "otcfx-EURUSD", "cash_delta_cents": -6,
             "detail": {"rate_ppm_per_day": -55, "days": 1, "mark_ticks": 108_325}}
    assert _errors(cash_events, carry) == []  # ruling R177: the fx carry is an engine kind of its own
    closed = {**_envelope(11, "instrument_closed", "settle", bar), "market_id": perp, "kind": "perp",
              "reason": "window_end", "last_price_ticks": 6_338_800, "n_bars": 3, "n_forecasts_unresolved": 2}
    assert _errors(pending["instrument_closed"], closed) == []
    assert _errors(pending["instrument_closed"], {**closed, "kind": "binary"}) != []
    resolved = {**_envelope(12, "forecast_resolved", "settle", bar), "agent_id": "carry_a", "market_id": perp,
                "forecast_bar_ms": bar - 3_600_000, "horizon_bars": 1, "up_probability_ppm": 480_000,
                "quantiles_ticks": [6_300_000, 6_325_000, 6_341_257, 6_356_000, 6_380_000],
                "price_ref_ticks": 6_341_257, "price_realised_ticks": 6_352_010, "realised_sign": 1,
                "directional_brier_micro": 270_400, "pinball_micro": 666, "baseline_pinball_micro": 848,
                "carried": False}
    assert _errors(pending["forecast_resolved"], resolved) == []
    assert _errors(pending["forecast_resolved"], {**resolved, "realised_sign": 2}) != []
    assert _errors(pending["forecast_resolved"], {**resolved, "quantiles_ticks": [1, 2, 3]}) != []
    # the widenings on the existing events, applied now
    filled = copy.deepcopy(_of_type(_events("journal.backtest.jsonl"), "filled")[0])
    event_fill = {**filled, "price_source": "event", "market_id": perp,
                  "base_price_bp": 6_338_800, "fill_price_bp": 6_338_800, "avg_cost_bp_after": 0}
    assert _errors(validator, event_fill) == []
    assert _errors(validator, {**filled, "price_source": "event", "market_id": "kalshi:X"}) != []
    placed = copy.deepcopy(_of_type(_events("journal.backtest.jsonl"), "order_placed")[0])
    assert _errors(validator, {**placed, "origin": "forced_flat"}) == []
    assert _errors(validator, {**placed, "origin": "liquidation"}) != []
    # the settle phase of an event fill is what pmx.journal's PHASES pin: declared, widened at gate G2 (R164)
    for event in ("order_placed", "filled", "fee_charged"):
        assert _schema("journal.v2.json")["$defs"][event]["properties"]["phase"]["const"] == "execute"
    assert _errors(validator, {**event_fill, "phase": "settle"}) != []
    marked = copy.deepcopy(_of_type(_events("journal.backtest.jsonl"), "equity_marked")[0])
    assert _errors(validator, {**marked, "positions_value_cents": -1_250}) == []
    # Rulings R179 and R180: a debit balance and a negative equity are journal states, not schema failures.
    negative = {**marked, "cash_cents": -100, "positions_value_cents": -1_150, "equity_cents": -1_250,
                "drawdown_bp": -10_125}
    assert _errors(validator, negative) == []
    ruined = {**_envelope(13, "agent_ruined", "close", bar), "agent_id": "carry_a", "equity_cents": -1_250,
              "cancelled_order_ids": []}
    assert _errors(validator, ruined) == []
    expired = {**_envelope(14, "order_expired", "settle", bar), "order_id": "o-00000007", "agent_id": "carry_a",
               "market_id": perp, "remaining_size": 2_500, "released_cents": 1_585, "reason": "debit"}
    assert _errors(validator, expired) == []
    assert _errors(validator, {**expired, "reason": "margin_call"}) != []
    listed = copy.deepcopy(_of_type(_events("journal.backtest.jsonl"), "market_listed")[0])
    listed.update(kind="perp", vendor="binance", symbol="BTCUSDT", tick_size_micro=10_000,
                  point_value_micro=1_000_000, session_calendar_id="continuous",
                  borrow_schedule_id=None, carry_schedule_id=None, market_id=perp, provider="binance")
    assert _errors(validator, listed) == []
    assert _errors(validator, {**listed, "kind": "bond"}) != []
    opened = {**_envelope(2, "sealed_test_opened", "pre", 0), "dataset_hash": "a" * 64, "genome_hash": "b" * 64,
              "provider": "binance", "n_markets": 60, "market_ids": [perp]}
    for claim_id in ("c-0123abcd-perp-binance-h24-0123456789abcdef", "c-0123abcd-manifold-0123456789abcdef"):
        assert _errors(validator, {**opened, "claim_id": claim_id}) == [], claim_id
    assert _errors(validator, {**opened, "claim_id": "c-0123abcd-bond-binance-h24-0123456789abcdef"}) != []
    recorded = copy.deepcopy(_of_type(_events("journal.backtest.jsonl"), "forecast_recorded")[0])
    recorded.update(market_id=perp, price_ref_ticks=6_341_257,
                    horizons=[{"horizon_bars": 1, "up_probability_ppm": 480_000, "quantiles_ticks": None}])
    assert _errors(validator, recorded) == []


def test_the_actions_schema_accepts_horizon_forecasts_and_stays_strict() -> None:
    validator = _validator("actions.v2.json")
    actions = copy.deepcopy(_fixture("actions.sample.json"))
    actions["horizon_forecasts"] = [
        {"market_id": "binance-BTCUSDT.PERP", "horizon_bars": 1, "up_probability_ppm": 480_000,
         "quantiles_ticks": [6_300_000, 6_325_000, 6_341_257, 6_356_000, 6_380_000]},
        {"market_id": "binance-BTCUSDT.PERP", "horizon_bars": 24, "up_probability_ppm": 470_000,
         "quantiles_ticks": None},
    ]
    assert _errors(validator, actions) == []
    four = copy.deepcopy(actions)
    four["horizon_forecasts"][0]["quantiles_ticks"] = [1, 2, 3, 4]
    assert _errors(validator, four) != []
    missing = copy.deepcopy(actions)
    del missing["horizon_forecasts"][1]["quantiles_ticks"]
    assert _errors(validator, missing) != []
    extra = copy.deepcopy(actions)
    extra["horizon_forecasts"][0]["confidence"] = 1
    assert _errors(validator, extra) != []
    milli = copy.deepcopy(actions)
    milli["markets"][0]["target_position"] = 2_500_000  # milli-units on a continuous instrument (R148)
    assert _errors(validator, milli) == []


def test_section_17_declares_every_interface_the_engine_wave_is_built_against() -> None:
    text = CONTRACT.read_text(encoding="utf-8")
    for heading in (
        "## 17. Instruments across kinds (amendment C1b)",
        "### 17.1 The six kinds, the `Instrument` base and the integer price model",
        "### 17.2 Session calendars, the run calendar and tradability",
        "### 17.3 `CashEvent`: funding, dividends, splits, rolls, borrow fees and the forced flat",
        "### 17.4 Fee, borrow and carry schedules as data, and the half-spread floor",
        "### 17.5 The forecast record across kinds: horizons, the random walk, the directional Brier and the"
        " pinball loss",
        "### 17.6 Claims, leaderboards and folds per kind and provider",
        "### 17.7 The wave 3b module map, the new families and the two new architecture rules",
        "### 17.8 v4 identifier formats",
        "### 17.9 What amendment C1b does not own",
        "### 15.9 Amendment C1b",
    ):
        assert heading in text, heading
    assert "17. Instruments across kinds" in text[: text.index("## 1. Units")]
    section = _contract_section("### 15.9 Amendment C1b", "\n---\n")
    rulings = set(re.findall(r"^\| (R1[4-9][0-9]) \|", section, re.MULTILINE))
    # R144..R172 are C1b's first pass; R173..R199 are its arbitration pass over the findings against it.
    assert rulings == {f"R{n}" for n in range(144, 200)}
    # the C1 rulings are untouched: 15.8 still ends where it did
    c1 = _contract_section("### 15.8 Amendment C1", "\n---\n")
    assert set(re.findall(r"^\| (R1[0-4][0-9]) \|", c1, re.MULTILINE)) == {f"R{n}" for n in range(107, 144)}
    kinds = _contract_section("### 17.1 The six kinds", "### 17.2 Session calendars")
    assert 'INSTRUMENT_KINDS = ("binary", "spot_crypto", "perp", "fx", "equity", "future")' in kinds
    for kind in INSTRUMENT_KINDS:
        assert f"`{kind}`" in kinds, kind
    assert "def cash_out_cents" in kinds and "def cash_in_cents" in kinds and "def mark_value_cents" in kinds
    assert "INT63_MAX = 2**63 - 1" in kinds
    events = _contract_section("### 17.3 `CashEvent`", "### 17.4 Fee, borrow")
    assert "CASH_EVENT_KINDS = (" + ", ".join(f'"{k}"' for k in CASH_EVENT_KINDS) + ")" in events
    for kind in CASH_EVENT_KINDS:
        assert f"`{kind}`" in events, kind
    assert "def apply_cash_events(self, *, t_ms: int, market: Instrument) -> None: ..." in text
    assert "def force_flat(self, *, t_ms: int, market: Instrument) -> None: ..." in text
    assert "def event_fill(order: LiquidityOrder, *, price_ticks: int, schedule: FeeSchedule) -> Fill: ..." in text
    owned = _flat(text.split("### 17.9 What amendment C1b does not own")[1])  # the last section of the file
    assert "A section of this document is never a contract issue" in owned
    for name in ("src/pmx/types.py", "market.v2.json", "dataset.v1.json", "news.v1.json", "pmx.journal", "gate G2"):
        assert name in owned, name


def test_the_binary_only_wording_is_generalised_in_place() -> None:
    """Ruling R136 applied to C1b: no earlier section is left stating the binary rule as the whole rule."""
    units = _flat(_contract_section("### 1.1 The unit table", "### 1.2 Conversion formulas"))
    assert "There is no other payout **on a binary**" in units and "six instrument kinds" in units
    conversions = _flat(_contract_section("### 1.2 Conversion formulas", "### 1.3 The natural logarithm"))
    assert "cash_out_cents" in conversions and "against the agent" in conversions
    grid = _flat(_contract_section("### 5.2 The bar grid", "### 5.3 The run calendar"))
    assert "session calendar" in grid and "load error" in grid
    calendar = _flat(_contract_section("### 5.3 The run calendar", "### 5.4 As-of"))
    assert "union of the instruments' bar timestamps" in calendar and "last_bar(i)" in calendar
    market = _flat(_contract_section("### 7.2 Market", "### 7.3 NewsItem"))
    assert "`Market` is the binary `Instrument`" in market and "Market.instrument" in market
    assert "wiki_subject_provenance" in market and "tape_kind" in market
    filters = _flat(_contract_section("### 7.4 Window and quality filters", "### 7.5 Hardness tags"))
    for name in ("bars_only", "min_traded_bars", "dataset.subsample", 'derive_seed(0, f"dataset/{name}")',
                 "kinds: tuple[str, ...]", "stratified"):
        assert name in filters, name
    linker = _flat(_contract_section("### 7.6 The linker", "### 7.7 Split"))
    assert "renormalised" in linker and "1000 permille on keywords" in linker
    leaks = _flat(_contract_section("### 7.9 Data leak rules", "### 7.10 v1 migration"))
    for name in ("cash_event_id", "delisted_at_ms", "price_realised_ticks", "gap_ticks"):
        assert name in leaks, name
    config = _contract_section("### 8.1 `RunConfig`", "### 8.2 The bar phase order")
    assert "horizons_bars: tuple[int, ...] = ()" in config and "kinds: tuple[str, ...] = ()" in config
    phases = _flat(_contract_section("### 8.2 The bar phase order", "### 8.3 `Observation`"))
    assert "apply_cash_events" in phases and "force_flat" in phases and "forecast_resolved" in phases
    actions = _flat(_contract_section("### 8.4 `Actions`", "### 8.5 Positions and cash"))
    assert "horizon_forecasts" in actions and "bad_horizon" in actions and "bad_quantiles" in actions
    positions = _flat(_contract_section("### 8.5 Positions and cash", "### 8.6 Fills"))
    assert "liability model" in positions and "short_allowed" in positions
    fills = _flat(_contract_section("### 8.6 Fills", "### 8.7 Settlement"))
    assert "Event fills" in fills and "bad_size" in fills and "half-spread floor" in fills
    settlement = _flat(_contract_section("### 8.7 Settlement", "### 8.8 Fee schedules"))
    assert "mark_value_cents" in settlement and "never written for a continuous instrument" in settlement
    fees = _contract_section("### 8.8 Fee schedules", "### 8.9 The accounting invariant")
    assert 'FEE_MODELS = ("pq_permille", "notional_bp", "per_contract", "zero")' in fees
    assert "min_half_spread_ticks" in fees and "CARRY_SCHEDULES" in fees
    invariant = _contract_section("### 8.9 The accounting invariant", "## 9. Journal v2")
    assert "sum(cash_event_applied.cash_delta_cents" in invariant and "split_position_milli" in invariant
    assert "positions_value_cents(a)" in invariant
    catalogue = _contract_section("### 9.2 The backtest catalogue", "### 9.3 One emitter")
    for row in ("| `cash_event_applied` | settle |", "| `instrument_closed` | settle |",
                "| `forecast_resolved` | settle |"):
        assert row in catalogue, row
    assert '"corporate_action"|"roll"|"delisted"' in catalogue and '"roll"|"forced_flat"' in catalogue
    emitters = _contract_section("### 9.3 One emitter per event", "### 9.4 The evolution catalogue")
    assert "| `cash_event_applied` | `engine/execution.py` (E2)" in emitters
    assert "| `forecast_resolved` | `engine/runner.py` (E5)" in emitters
    memory = _contract_section("### 10.3 `Memory`", "### 10.4 `Hive`")
    assert "n_yes_x2" in memory and 'f"h{horizon_bars}"' in memory
    hive = _contract_section("### 10.4 `Hive`", "### 10.5 The scripted families")
    assert "horizon_bars: int = 0" in hive and "resolves_at_ms" in hive
    scores = _flat(_contract_section("### 12.1 Forecast scores", "### 12.2 Calibration"))
    assert "directional_brier_micro" in scores and "random-walk baseline" in scores
    calibration = _flat(_contract_section("### 12.2 Calibration", "### 12.3 Trading metrics"))
    assert "(kind, horizon)" in calibration
    trading = _flat(_contract_section("### 12.3 Trading metrics", "### 12.4 Statistics"))
    assert "exposure_by_kind" in trading and "n_cash_events" in trading
    bar = _flat(_contract_section("### 12.6 The selection objective", "### 12.7 Folds"))
    assert "per `(kind, provider)`" in bar and "(instrument, ISO week)" in bar
    folds = _contract_section("### 12.7 Folds", "### 12.8 Claims")
    assert 'kind: str = "binary") -> tuple[str, ...]' in folds and "every** fold whose months" in folds
    claims = _flat(_contract_section("### 12.8 Claims", "### 12.9 Prompt mutation"))
    assert "c-{dataset_hash[:8]}-{kind}-{provider}-h{horizon_bars}-{genome_hash[:16]}" in claims
    board = _flat(_contract_section("### 12.10 The leaderboard", "### 12.11 The structures"))
    assert "(agent_id, kind, provider, horizon_bars, fold" in board and "random_walk" in board
    structures = _contract_section("### 12.11 The structures", "### 12.12 The HTTP surface")
    for field in ('kind: str = "binary"; horizon_bars: int = 0; unit_key: str = ""',
                  "pinball_skill: Interval | None = None",
                  "exposure_by_kind: tuple[tuple[str, int], ...] = ()", "last_price_ticks: int = 0"):
        assert field in structures, field
    routes = _contract_section("### 12.12 The HTTP surface", "## 13. Module map")
    assert "&kind=&horizon_bars=" in routes
    liquidity = _flat(_contract_section("### 16.1 The `LiquidityModel`", "### 16.2 The decision latency"))
    assert "half_spread_ticks" in liquidity and "unconstrained by this rule" not in liquidity
    assert '"open"|"quote"|"limit"|"impact"|"mm"|"event"' in liquidity


def test_every_module_map_row_of_amendment_c1b_has_exactly_one_owner_from_the_plan() -> None:
    module_map = _contract_section("## 13. Module map and file ownership", "### 13.1 The error taxonomy")
    plan = (REPO / "docs" / "PLAN_V3_WAVES.md").read_text(encoding="utf-8")
    assert {"F1", "F2", "F3", "F4", "C1b"} <= set(re.findall(r"^### ([A-Z][0-9a-z]{1,3})\b", plan, re.MULTILINE))
    for path in C1B_MAP_PATHS:
        rows = [line for line in module_map.splitlines() if path in line]
        assert len(rows) == 1, (path, rows)
        match = re.search(r"\s+([A-Z][0-9a-z]{1,3})(?:\s+\(|\s*$)", rows[0])
        assert match is not None, rows[0]
        assert match.group(1) in C1B_KNOWN_OWNERS, (path, match.group(1))
    waves = _contract_section("## 14. Wave plan cross-reference", "### 14.1 Decisions a reviewer")
    for package in ("| C1b |", "| F1 |", "| F2 |", "| F3 |", "| F4 |", "| G3b |", "| R2f |"):
        assert package in waves, package
    for row_start, must_carry in (("| E2 |", "17.3"), ("| E3 |", "17.5"), ("| E5 |", "17.6"), ("| A1 |", "17.7"),
                                  ("| E1 |", "17.2")):
        row = next(line for line in waves.splitlines() if line.startswith(row_start))
        assert must_carry in row, (row_start, must_carry)


def test_the_arbitration_pass_of_c1b_is_applied_in_place() -> None:
    """Rulings R173 to R199: every finding against the first pass is resolved in the text, not deferred."""
    text = CONTRACT.read_text(encoding="utf-8")
    assert "InstrumentBar` is `Bar` with" not in text  # R173: one in-memory bar type
    kinds = _flat(_contract_section("### 17.1 The six kinds", "### 17.2 Session calendars"))
    assert "one bar type and one trade type for every kind" in kinds and "open_bp <- open_ticks" in kinds
    liquidity = _flat(_contract_section("### 16.1 The `LiquidityModel`", "### 16.2 The decision latency"))
    for phrase in ("size_milli = size` on a continuous instrument", "`clamp_price`",
                   "point_value_micro=market_view.point_value_micro", "on a continuous view"):
        assert phrase in liquidity, phrase
    assert "price (`1..9_999`, `clamp_price_bp`)" not in liquidity
    fills = _flat(_contract_section("### 8.6 Fills", "### 8.7 Settlement"))
    for phrase in ("slippage_ticks(base, config=config, taken_pct=taken_pct, view=market_view)",
                   "calendars: Mapping[str, SessionCalendar] | None = None", "bar.high_bp`, the largest price",
                   "the instrument's previous bar"):
        assert phrase in fills, phrase
    module_map = _contract_section("## 13. Module map and file ownership", "### 13.1 The error taxonomy")
    sessions = next(line for line in module_map.splitlines() if "data/sessions.py" in line)
    assert re.search(r"\s+D1\s+\(", sessions), sessions  # R174
    events = _flat(_contract_section("### 17.3 `CashEvent`", "### 17.4 Fee, borrow"))
    for phrase in ("def applies_at(event: CashEvent, instrument: Instrument, calendar: Calendar) -> int | None:",
                   "Entitlement follows the regime of the prices", "t_ms = last_bar(i) + interval_ms - 1",
                   "| `carry` | `fx` with a `carry_schedule_id`", "A debit balance", 'reason = "debit"',
                   "(kind order as in CASH_EVENT_KINDS, t_ms, cash_event_id)",
                   "before the first and after the last event fill", "MarketView.cash_events"):
        assert phrase in events, phrase
    assert "the only event whose `t_ms` is the bar's own close" not in events
    assert "A `CashEvent` record never appears in an observation" not in events
    invariant = _contract_section("### 8.9 The accounting invariant", "## 9. Journal v2")
    assert "unless the last event that moved it is a cash_event_applied DEBIT" in invariant
    assert "reserved_cents(a) <= max(0, cash_cents(a))" in invariant
    views = _contract_section("### 8.3 `Observation`", "### 8.4 `Actions`")
    for field in ("kind: str = \"binary\"", "hours_to_next_bar: int = 0", "underlying_id: str | None = None",
                  "twins: tuple[str, ...] = ()", "cash_events: tuple[CashEventView, ...] = ()",
                  "class CashEventView:",
                  "closing_ids: tuple[str, ...] = ()", "def last_bar(self, market_id: str) -> int: ...",
                  "def next_bar(self, market_id: str, t_ms: int) -> int | None: ...",
                  "def prev_bar(self, market_id: str, t_ms: int) -> int | None: ...", "n_yes_x2 = 0"):
        assert field in views, field
    assert "close_at_ms is 0 and tradable is open(i, t)" in views  # R181
    market = _flat(_contract_section("### 7.2 Market", "### 7.3 NewsItem"))
    for phrase in ("def sealed_market(self, market_id: str) -> Instrument: ...",
                   "CLIPPED at manifest.split.validation_end_ms", "resolved_at_ms = delisted_at_ms",
                   "resolution = -1", "TRADE_SIDES"):
        assert phrase in market, phrase
    actions = _flat(_contract_section("### 8.4 `Actions`", "### 8.5 Positions and cash"))
    assert "synthesises the pair from `MarketAction.prob_ppm`" in actions
    assert "bad_size` for a notional" not in actions
    calendar = _flat(_contract_section("### 17.2 Session calendars", "### 17.3 `CashEvent`"))
    for phrase in ("binds a `ContinuousInstrument` only", "reserved and synthesised by the loader, never a file",
                   "D1's file, applied by gate G2"):
        assert phrase in calendar, phrase
    schedules = _contract_section("### 17.4 Fee, borrow and carry schedules", "### 17.5 The forecast record")
    for phrase in ("`xnys-zero-2026-09`, `xnas-zero-2026-09`, `arcx-zero-2026-09`", "xnas-borrowgc-2026-09",
                   "def half_spread_ticks(bar_prev: Bar, bar: Bar, *, schedule: FeeSchedule) -> int:",
                   "bar_prev.high_bp"):
        assert phrase in schedules, phrase
    assert "usequity-" not in schedules and "detail.role" not in schedules
    forecasts = _flat(_contract_section("### 17.5 The forecast record", "### 17.6 Claims, leaderboards"))
    assert "the **plain mean**" in forecasts and "12.1's argument" not in forecasts
    assert "`RE_HORIZON_BUCKET`" in forecasts and "HORIZON_BUCKETS` gains" not in forecasts
    claims = _flat(_contract_section("### 17.6 Claims, leaderboards", "### 17.7 The wave 3b module map"))
    assert "`price_realised_ticks` is not shuffled" in claims and "realised_signs=" in claims
    stats = _contract_section("### 12.4 Statistics", "### 12.5 Behavioural descriptors")
    assert "realised_signs: Mapping[str, Sequence[int]] | None = None" in stats
    structures = _contract_section("### 12.11 The structures", "### 12.12 The HTTP surface")
    assert "sorted by (agent_id, market_id, horizon_bars, unit_key)" in structures
    errors = _contract_section("### 13.1 The error taxonomy", "### 13.2 Version constants")
    assert "(dataset_hash, kind, provider, horizon_bars, genome_hash)" in errors
    ids = _contract_section("### 17.8 v4 identifier formats", "### 17.9 What amendment C1b does not own")
    assert "carry\\|forced_flat" in ids and "RE_HORIZON_BUCKET" in ids and "one of seven" in ids
    owned = _flat(text.split("### 17.9 What amendment C1b does not own")[1])
    for phrase in ("R189", "docs/PRD_V4_MULTI_ASSET.md", "docs/PLAN_V3_WAVES.md", "Dataset.sealed_market",
                   "RE_HORIZON_BUCKET", "NEWS_KIND_BY_SOURCE", "applies_at"):
        assert phrase in owned, phrase
    assert "InstrumentBar" not in owned
    for ruling in ("R145", "R163"):
        row = next(line for line in text.splitlines() if line.startswith(f"| {ruling} |"))
        assert "is not amended" not in row and "byte-identical" not in row
    schema = _schema("journal.v2.json")["$defs"]
    assert schema["equity_marked"]["properties"]["equity_cents"]["$ref"] == "#/$defs/int"
    assert schema["equity_marked"]["properties"]["cash_cents"]["$ref"] == "#/$defs/int"
    assert schema["agent_ruined"]["properties"]["equity_cents"]["$ref"] == "#/$defs/int"
    assert "minimum" not in schema["equity_marked"]["properties"]["drawdown_bp"]
    assert "carry" in schema["cash_event_applied"]["properties"]["kind"]["enum"]
    assert "debit" in schema["order_expired"]["properties"]["reason"]["enum"]
    assert _schema("session_calendar.v1.json")["properties"]["calendar_id"]["not"] == {"const": "continuous"}
    horizon_forecasts = _schema("actions.v2.json")["properties"]["horizon_forecasts"]
    assert "synthesises it from that market's prob_ppm" in horizon_forecasts["description"]
    assert _fixture("instrument.xnas-aapl.json")["fee_schedule_id"] == "xnas-zero-2026-09"


def test_the_four_data_rulings_say_what_the_data_files_do() -> None:
    """Rulings R167 to R170 were implemented by the data package in its own files while this amendment was
    written; the contract and the files must say the same thing, so this test reads both."""
    lexicons = REPO / "src" / "pmx" / "lexicons"
    for name in ("kalshi_series_categories.v1.json", "kalshi_series_subjects.v1.json"):
        assert (lexicons / name).is_file(), name
        json.loads((lexicons / name).read_text(encoding="utf-8"))
    market = _schema("market.v2.json")
    assert market["properties"]["quality"]["properties"]["tape_kind"]["enum"] == ["prints", "bars_only"]
    assert "tape_kind" not in market["properties"]["quality"]["required"]  # a pre-flag file still loads
    assert set(market["properties"]["wiki_subject_provenance"]["items"]["enum"]) == {"stated", "derived"}
    counts = _schema("dataset.v1.json")["properties"]["counts"]["properties"]
    for name in ("precap_per_provider_month", "n_bars_only", "n_category_fallback"):
        assert name in counts, name
    builder = (REPO / "src" / "pmx" / "data" / "builder.py").read_text(encoding="utf-8")
    assert "def stratified_cap(" in builder and 'derive_seed(0, f"dataset/{name}")' in builder
    assert '"dataset.subsample"' in builder
    rulings = _flat(_contract_section("### 15.9 Amendment C1b", "\n---\n"))
    for literal in ("tape_kind", "min_traded_bars", "precap_per_provider_month", "n_category_fallback",
                    "wiki_subject_provenance", "kalshi_series_categories.v1.json", "kalshi_series_subjects.v1.json",
                    'derive_seed(0, f"dataset/{name}")', "R105"):
        assert literal in rulings, literal
