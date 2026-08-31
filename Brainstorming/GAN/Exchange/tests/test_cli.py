"""A23 acceptance tests for `pxe.cli` (CONTRACTS section 7.22).

Every verb of section 7.22's table is exercised, and the exit codes it names
(``0`` success, ``1`` user error, ``2`` determinism failure, ``3`` budget
exceeded, ``4`` invariant violation) are pinned.

The headline test is ``test_a_real_tournament_through_the_entry_point_writes_the_report``:
it runs a real three match tournament by **spawning the installed entry point**
(``python -m pxe.cli``), not by calling ``main`` in process, and then asserts
that the report file exists and holds every mandated section, with a control
proving the assertion fails when a section is removed. That is the only shape
of test that can catch a CLI which imports cleanly and does nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from pxe import cli
from pxe.cli import (
    EXIT_BUDGET,
    EXIT_DETERMINISM,
    EXIT_INVARIANT,
    EXIT_OK,
    EXIT_USER_ERROR,
    main,
)
from pxe.errors import BudgetExceededError, InvariantViolationError, JournalHashMismatchError
from pxe.events import journal_hash
from pxe.journal import read_journal
from pxe.store.db import Store, default_store_url
from pxe.store.files import artefact_paths
from pxe.tournament.report import HELDOUT_DIRNAME, MANDATED_SECTIONS, REPORT_HTML_NAME, REPORT_MARKDOWN_NAME

#: A four seat, two market, 24 tick scripted match: the smallest legal match
#: (``MatchConfig.__post_init__`` refuses fewer than 24 ticks or 4 seats) that
#: still trades, predicts and settles.
SMALL_MATCH = (
    "--template",
    "election",
    "--ticks",
    "24",
    "--markets",
    "2",
    "--agents",
    "fundamentalist,momentum,noise,bayesian",
)

TOURNAMENT_ID = "T-cli-0001"

TOURNAMENT_TOML = """
tournament_id = "T-cli-0001"
format = "round_robin"
template_ids = ["election"]
seeds = [21, 22, 23]
agents_per_match = 4
rounds = 1
background_baselines = ["fundamentalist", "momentum", "noise", "bayesian"]
max_cost_usd = 0.0

[match_defaults]
ticks_total = 24
n_agents = 4
n_markets = 2
liquidity_profile_name = "standard"

[gateway]
timeout_s = 30.0
"""


def _json_of(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    """Return the last JSON object the CLI printed on stdout.

    Args:
        capsys: pytest's capture fixture.

    Returns:
        The parsed object.
    """
    out = capsys.readouterr().out
    for line in reversed(out.splitlines()):
        if line.startswith("{"):
            parsed: dict[str, Any] = json.loads(line)
            return parsed
    raise AssertionError(f"the CLI printed no JSON object:\n{out}")


def _spawn(repo_root: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run the real entry point in a fresh process.

    Args:
        repo_root: Working directory of the child.
        argv: Arguments after ``python -m pxe.cli``.

    Returns:
        The finished process.
    """
    env = dict(os.environ)
    env.pop("PYTHONHASHSEED", None)
    return subprocess.run(  # noqa: S603 - argv is built by the test itself
        [sys.executable, "-m", "pxe.cli", *argv],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env=env,
        check=False,
    )


# ---------------------------------------------------------------------------
# pxe match run
# ---------------------------------------------------------------------------
def test_match_run_writes_a_journal_and_mirrors_the_store(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``pxe match run`` produces the four artefacts and a database row."""
    runs_dir = tmp_path / "runs"
    code = main(["--quiet", "match", "run", *SMALL_MATCH, "--seed", "101", "--runs-dir", str(runs_dir), "--json"])
    assert code == EXIT_OK
    payload = _json_of(capsys)
    match_id = payload["match_id"]
    assert match_id == "m-election-101-01"
    assert payload["event_count"] > 100, payload
    assert len(payload["rankings"]) == 4

    paths = artefact_paths(runs_dir, match_id)
    events = read_journal(paths["journal"])
    assert events, "the journal is empty"
    assert journal_hash(events) == payload["journal_hash"], "the printed hash is not the journal's"
    assert paths["metrics"].is_file()
    assert paths["meta"].is_file()
    assert json.loads(paths["metrics"].read_text(encoding="utf-8"))["performance"]

    with Store(url=default_store_url(runs_dir), runs_dir=runs_dir) as store:
        assert store.has_match(match_id)
        assert store.load_projection(match_id).trades, "the mirrored match traded nothing"
        assert store.load_metrics(match_id).calibration


def test_match_run_refuses_an_unknown_template(tmp_path: Path) -> None:
    """A user error is exit code 1, never the determinism code."""
    code = main(["--quiet", "match", "run", "--template", "nope", "--seed", "1", "--runs-dir", str(tmp_path)])
    assert code == EXIT_USER_ERROR


def test_match_run_accepts_a_custom_match_id_and_skips_the_store(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--match-id`` and ``--no-store`` are honoured."""
    runs_dir = tmp_path / "runs"
    code = main(
        [
            "--quiet",
            "match",
            "run",
            *SMALL_MATCH,
            "--seed",
            "102",
            "--match-id",
            "m-election-102-07",
            "--runs-dir",
            str(runs_dir),
            "--no-store",
            "--json",
        ]
    )
    assert code == EXIT_OK
    assert _json_of(capsys)["match_id"] == "m-election-102-07"
    assert (runs_dir / "m-election-102-07" / "journal.jsonl").is_file()
    assert not (runs_dir / "pxe.sqlite3").exists(), "--no-store still opened a database"


# ---------------------------------------------------------------------------
# pxe match verify (AC-P1)
# ---------------------------------------------------------------------------
@pytest.mark.determinism
@pytest.mark.slow
def test_match_verify_compares_two_fresh_processes(capsys: pytest.CaptureFixture[str]) -> None:
    """AC-P1: the same seed twice, in two processes, is one hash."""
    code = main(["--quiet", "match", "verify", *SMALL_MATCH, "--seed", "103", "--repeat", "2", "--json"])
    payload = _json_of(capsys)
    assert code == EXIT_OK
    assert payload["repeat"] == 2
    assert len(payload["hashes"]) == 2
    assert all(len(value) == 64 for value in payload["hashes"]), payload
    assert payload["identical"] is True


def test_match_verify_refuses_an_llm_harness() -> None:
    """Section 3.7: AC-P1 is a scripted claim, so this refuses with code 1."""
    code = main(
        ["--quiet", "match", "verify", *SMALL_MATCH, "--seed", "1", "--llm-model", "claude-sonnet-5", "--repeat", "2"]
    )
    assert code == EXIT_USER_ERROR


def test_match_verify_needs_at_least_two_runs() -> None:
    """One run compares with nothing, which is a user error and not a pass."""
    assert main(["--quiet", "match", "verify", *SMALL_MATCH, "--seed", "1", "--repeat", "1"]) == EXIT_USER_ERROR


@pytest.mark.determinism
def test_match_verify_reports_a_divergence_with_exit_code_two(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two different hashes are exit code 2, and the verb says so out loud."""
    seen: list[int] = []

    def fake_child(_args: Any, *, index: int, runs_dir: Path) -> str:
        seen.append(index)
        return f"{index:064x}"

    monkeypatch.setattr(cli, "_run_verify_child", fake_child)
    code = main(["--quiet", "match", "verify", *SMALL_MATCH, "--seed", "1", "--repeat", "2", "--json"])
    payload = _json_of(capsys)
    assert seen == [0, 1], "the two runs did not both happen"
    assert payload["identical"] is False
    assert code == EXIT_DETERMINISM


# ---------------------------------------------------------------------------
# pxe match replay
# ---------------------------------------------------------------------------
def test_match_replay_prints_the_projected_metrics(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``pxe match replay`` folds a journal and prints one row per seat."""
    runs_dir = tmp_path / "runs"
    assert (
        main(["--quiet", "match", "run", *SMALL_MATCH, "--seed", "104", "--runs-dir", str(runs_dir), "--no-store"])
        == EXIT_OK
    )
    capsys.readouterr()
    journal = artefact_paths(runs_dir, "m-election-104-01")["journal"]
    assert main(["--quiet", "match", "replay", str(journal), "--json"]) == EXIT_OK
    payload = _json_of(capsys)
    assert payload["match_id"] == "m-election-104-01"
    assert payload["ticks_total"] == 24
    assert payload["event_count"] > 100
    assert len(payload["agents"]) == 4
    assert all(row["n_terms"] > 0 for row in payload["agents"]), "no Brier term was counted"
    assert any(row["trade_count"] > 0 for row in payload["agents"]), "nobody traded"


def test_match_replay_refuses_a_missing_file(tmp_path: Path) -> None:
    """A path that is not there is a user error."""
    assert main(["--quiet", "match", "replay", str(tmp_path / "nope.jsonl")]) == EXIT_USER_ERROR


# ---------------------------------------------------------------------------
# pxe schema, pxe world, pxe mm, pxe store, pxe integrity
# ---------------------------------------------------------------------------
def test_schema_dump_prints_a_versioned_schema(capsys: pytest.CaptureFixture[str]) -> None:
    """Both the shorthand and the explicit version resolve."""
    assert main(["--quiet", "schema", "dump", "action"]) == EXIT_OK
    schema = json.loads(capsys.readouterr().out)
    assert schema["$id"].endswith("action.v1.json")
    assert schema["properties"]["orders"]

    assert main(["--quiet", "schema", "dump", "observation.v1"]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["$id"].endswith("observation.v1.json")
    assert main(["--quiet", "schema", "dump", "nope"]) == EXIT_USER_ERROR


def test_world_stats_runs_the_frequency_test(capsys: pytest.CaptureFixture[str]) -> None:
    """FR-5.2.2, on a small number of draws so the test stays cheap."""
    assert main(["--quiet", "world", "stats", "election", "--draws", "40", "--markets", "2", "--json"]) == EXIT_OK
    payload = _json_of(capsys)
    assert payload["draws"] == 40
    assert set(payload["yes_frequency_ppm"]) == {"M1", "M2"}
    assert all(0 <= value <= 1_000_000 for value in payload["yes_frequency_ppm"].values())
    assert main(["--quiet", "world", "stats", "nope"]) == EXIT_USER_ERROR


def test_mm_study_writes_the_t26_document(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """T2.6: the study is journal only and lands where ``--out`` says.

    ``--out`` defaults to ``docs/MM_LIQUIDITY_COST.md`` and this test never
    points it there: that document is A07's and is pinned by
    ``test_market_maker.py::test_mm_liquidity_cost_doc_matches_the_study``.
    See CONTRACT ISSUES.
    """
    out = tmp_path / "study.md"
    code = main(
        [
            "--quiet",
            "mm",
            "study",
            "--profile",
            "standard",
            "--matches",
            "2",
            "--ticks",
            "24",
            "--markets",
            "2",
            "--out",
            str(out),
            "--json",
        ]
    )
    assert code == EXIT_OK
    payload = _json_of(capsys)
    assert payload["matches_per_profile"] == 2
    assert [row["profile_name"] for row in payload["rows"]] == ["standard"]
    assert payload["rows"][0]["two_sided_ppm"] > 0, "the market maker never quoted two sided"
    document = out.read_text(encoding="utf-8")
    assert document.startswith("# Cost of liquidity")
    assert "standard" in document
    assert "matches per preset: 2" in document
    assert main(["--quiet", "mm", "study", "--matches", "0", "--out", str(out)]) == EXIT_USER_ERROR


def test_store_init_then_rebuild_reimports_the_journals(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``pxe store init`` and ``pxe store rebuild`` (section 7.20)."""
    runs_dir = tmp_path / "runs"
    assert main(["--quiet", "store", "init", "--runs-dir", str(runs_dir), "--json"]) == EXIT_OK
    assert _json_of(capsys)["schema_version"]
    assert (
        main(["--quiet", "match", "run", *SMALL_MATCH, "--seed", "105", "--runs-dir", str(runs_dir), "--json"])
        == EXIT_OK
    )
    capsys.readouterr()
    assert main(["--quiet", "store", "rebuild", str(runs_dir), "--json"]) == EXIT_OK
    payload = _json_of(capsys)
    assert payload["matches"] == 1, payload
    with Store(url=default_store_url(runs_dir), runs_dir=runs_dir) as store:
        assert store.has_match("m-election-105-01")


def test_integrity_scan_writes_the_incidents_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``pxe integrity scan`` runs the detectors offline (section 4.5)."""
    runs_dir = tmp_path / "runs"
    assert main(["--quiet", "match", "run", *SMALL_MATCH, "--seed", "106", "--runs-dir", str(runs_dir)]) == EXIT_OK
    capsys.readouterr()
    assert main(["--quiet", "integrity", "scan", "m-election-106-01", "--runs-dir", str(runs_dir), "--json"]) == EXIT_OK
    payload = _json_of(capsys)
    path = artefact_paths(runs_dir, "m-election-106-01")["incidents"]
    assert Path(payload["path"]) == path
    assert path.is_file(), "incidents.jsonl was not written"
    assert payload["incidents"] == len([line for line in path.read_text(encoding="utf-8").splitlines() if line])


# ---------------------------------------------------------------------------
# pxe api
# ---------------------------------------------------------------------------
def test_api_openapi_writes_the_document_and_the_fixtures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``pxe api openapi`` renders the document, and ``--samples`` the fixtures.

    ``--out`` and ``--fixtures-dir`` both point into ``tmp_path``: the committed
    ``docs/REPLAY_API.md`` and ``web/tests/fixtures/`` are A22's and A24's.
    """
    runs_dir = tmp_path / "runs"
    assert main(["--quiet", "match", "run", *SMALL_MATCH, "--seed", "107", "--runs-dir", str(runs_dir)]) == EXIT_OK
    capsys.readouterr()
    out = tmp_path / "REPLAY_API.md"
    fixtures = tmp_path / "fixtures"
    code = main(
        [
            "--quiet",
            "api",
            "openapi",
            "--runs-dir",
            str(runs_dir),
            "--out",
            str(out),
            "--samples",
            "--match-id",
            "m-election-107-01",
            "--fixtures-dir",
            str(fixtures),
            "--json",
        ]
    )
    assert code == EXIT_OK
    payload = _json_of(capsys)
    assert out.read_text(encoding="utf-8").startswith("# Replay API")
    assert payload["fixtures"], "no fixture was written"
    assert (fixtures / "match_detail.json").is_file()
    assert json.loads((fixtures / "match_detail.json").read_text(encoding="utf-8"))["match_id"] == "m-election-107-01"

    assert main(["--quiet", "api", "openapi", "--runs-dir", str(runs_dir), "--out", str(out), "--samples"]) == (
        EXIT_USER_ERROR
    )


def test_api_serve_builds_the_application(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``pxe api serve`` hands a real app to uvicorn on the asked address."""
    served: dict[str, Any] = {}

    def fake_run(app: Any, **kwargs: Any) -> None:
        served["app"] = app
        served.update(kwargs)

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    code = main(
        ["--quiet", "api", "serve", "--runs-dir", str(tmp_path / "runs"), "--host", "127.0.0.1", "--port", "8123"]
    )
    assert code == EXIT_OK
    assert served["host"] == "127.0.0.1"
    assert served["port"] == 8123
    assert served["app"].title == "pxe replay API"
    assert "/api/health" in served["app"].openapi()["paths"]


# ---------------------------------------------------------------------------
# pxe tournament and pxe report, through the real entry point
# ---------------------------------------------------------------------------
@pytest.mark.e2e
@pytest.mark.slow
def test_a_real_tournament_through_the_entry_point_writes_the_report(tmp_path: Path, repo_root: Path) -> None:
    """T3.6, AC-P3 and AC-P5, end to end through a spawned ``python -m pxe.cli``.

    The tournament is played by a **child process**, so nothing here can pass
    because of an import side effect or a fixture: if the console script is
    broken, this test is red.
    """
    config = tmp_path / "cli_tournament.toml"
    config.write_text(TOURNAMENT_TOML, encoding="utf-8", newline="\n")
    runs_dir = tmp_path / "runs"

    completed = _spawn(
        repo_root,
        "--quiet",
        "tournament",
        "run",
        str(config),
        "--runs-dir",
        str(runs_dir),
        "--max-workers",
        "1",
        "--json",
    )
    assert completed.returncode == EXIT_OK, completed.stderr[-2000:]
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["tournament_id"] == TOURNAMENT_ID
    assert payload["matches"] == 3, payload
    assert len(payload["ratings"]) == 4, payload

    out_dir = runs_dir / TOURNAMENT_ID
    markdown = out_dir / REPORT_MARKDOWN_NAME
    document = out_dir / REPORT_HTML_NAME
    heldout = out_dir / HELDOUT_DIRNAME
    for path in (markdown, document, heldout / REPORT_MARKDOWN_NAME, heldout / REPORT_HTML_NAME):
        assert path.is_file(), f"{path} was not written with no manual action"

    text = markdown.read_text(encoding="utf-8")
    every = (*MANDATED_SECTIONS, "Calibration and reliability curves", "Brier versus PnL", "KPIs", "Profile balance")
    missing = [heading for heading in every if f"## {heading}" not in text]
    assert missing == [], missing
    assert "| Rank | Harness | mu | sigma | Matches |" in text, "the leaderboard table has no rows"
    assert text.count("| 1 |") >= 1
    assert "| liquidity_cost_cents_per_match |" in text

    # The control the assertion above needs to mean anything: remove one
    # section and the very same check must fail.
    mutilated = text.replace("## Deltas", "## Removed", 1)
    assert [heading for heading in every if f"## {heading}" not in mutilated] == ["Deltas"]

    # `pxe report build` rebuilds the same four files from the store alone.
    rebuilt = _spawn(repo_root, "--quiet", "report", "build", TOURNAMENT_ID, "--runs-dir", str(runs_dir), "--json")
    assert rebuilt.returncode == EXIT_OK, rebuilt.stderr[-2000:]
    rebuilt_payload = json.loads(rebuilt.stdout.strip().splitlines()[-1])
    assert rebuilt_payload["matches"] == 3
    assert Path(rebuilt_payload["markdown"]) == markdown
    assert Path(rebuilt_payload["heldout_markdown"]) == heldout / REPORT_MARKDOWN_NAME
    rebuilt_text = markdown.read_text(encoding="utf-8")
    assert [heading for heading in every if f"## {heading}" not in rebuilt_text] == []

    # And it is idempotent: a second resume replays nothing.
    resumed = _spawn(repo_root, "--quiet", "tournament", "resume", str(config), "--runs-dir", str(runs_dir), "--json")
    assert resumed.returncode == EXIT_OK, resumed.stderr[-2000:]
    assert json.loads(resumed.stdout.strip().splitlines()[-1])["matches"] == 3


@pytest.mark.e2e
def test_report_build_refuses_an_unknown_tournament(tmp_path: Path) -> None:
    """Reporting on nothing is a user error, never an empty document."""
    assert main(["--quiet", "report", "build", "T-nope-0001", "--runs-dir", str(tmp_path)]) == EXIT_USER_ERROR


def test_tournament_run_refuses_a_missing_config(tmp_path: Path) -> None:
    """A missing preset is a user error."""
    assert main(["--quiet", "tournament", "run", str(tmp_path / "nope.toml")]) == EXIT_USER_ERROR


# ---------------------------------------------------------------------------
# Parser and exit codes
# ---------------------------------------------------------------------------
def test_help_and_version_exit_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """``--help`` and ``--version`` are not errors."""
    assert main(["--help"]) == EXIT_OK
    assert "match" in capsys.readouterr().out
    assert main(["--version"]) == EXIT_OK
    assert capsys.readouterr().out.strip().startswith("pxe ")


def test_an_unknown_verb_is_a_user_error_and_never_code_two(capsys: pytest.CaptureFixture[str]) -> None:
    """argparse's own exit code 2 is remapped: it must not read as AC-P1 failing."""
    assert main(["nope"]) == EXIT_USER_ERROR
    assert "invalid choice" in capsys.readouterr().err
    assert main([]) == EXIT_USER_ERROR
    assert main(["match"]) == EXIT_USER_ERROR
    assert main(["match", "run"]) == EXIT_USER_ERROR


def test_every_contracted_verb_is_registered() -> None:
    """Section 7.22's table, verb by verb, is reachable from the parser."""
    parser = cli._build_parser()
    groups = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
    assert set(groups.choices) == {
        "match",
        "tournament",
        "api",
        "store",
        "report",
        "schema",
        "world",
        "mm",
        "integrity",
    }
    expected = {
        "match": {"run", "verify", "replay"},
        "tournament": {"run", "resume"},
        "api": {"serve", "openapi"},
        "store": {"init", "rebuild"},
        "report": {"build"},
        "schema": {"dump"},
        "world": {"stats"},
        "mm": {"study"},
        "integrity": {"scan"},
    }
    for group, verbs in expected.items():
        sub = next(
            action for action in groups.choices[group]._actions if isinstance(action, argparse._SubParsersAction)
        )
        assert set(sub.choices) == verbs, group


def test_the_exit_code_table_is_the_contracted_one() -> None:
    """Section 7.22: 0, 1, 2, 3, 4, and one mapping from error to code."""
    assert (EXIT_OK, EXIT_USER_ERROR, EXIT_DETERMINISM, EXIT_BUDGET, EXIT_INVARIANT) == (0, 1, 2, 3, 4)
    assert cli._exit_code_of(JournalHashMismatchError("x")) == EXIT_DETERMINISM
    assert cli._exit_code_of(BudgetExceededError("x")) == EXIT_BUDGET
    assert cli._exit_code_of(InvariantViolationError("x")) == EXIT_INVARIANT


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (BudgetExceededError("cap reached"), EXIT_BUDGET),
        (InvariantViolationError("I2 breached"), EXIT_INVARIANT),
        (JournalHashMismatchError("seq gap"), EXIT_DETERMINISM),
    ],
)
def test_a_raising_handler_returns_the_mapped_exit_code(
    monkeypatch: pytest.MonkeyPatch, error: Exception, code: int
) -> None:
    """The mapping is applied by ``main`` and not only available as a helper."""

    def boom(_args: Any) -> int:
        raise error

    monkeypatch.setattr(cli, "_cmd_schema_dump", boom)
    assert main(["--quiet", "schema", "dump", "action"]) == code
