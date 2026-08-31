"""Tests for the ``ala`` CLI (W13).

These exercise the deterministic path only: a scripted match run, a verify that must report OK on an
identical seed, and a replay of the journal that run produced. The reporting layer (metrics, detectors)
may be authored separately; these tests assert the exit codes and the journal artefact, which do not
depend on it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ala.cli import main

_RUN_ARGS = [
    "match",
    "run",
    "--scenario",
    "concours",
    "--seed",
    "42",
    "--agents",
    "grinder,allier,raider,forger",
    "--ticks",
    "12",
    "--cull-every",
    "6",
]


def _find_journal(out_dir: Path) -> Path:
    matches = list(out_dir.glob("**/journal.jsonl"))
    assert matches, f"no journal.jsonl written under {out_dir}"
    return matches[0]


def test_match_run_writes_journal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main([*_RUN_ARGS, "--out", str(tmp_path)])
    assert code == 0
    journal = _find_journal(tmp_path)
    assert journal.exists()
    out = capsys.readouterr().out
    assert "journal hash:" in out
    assert "final ranking:" in out


def test_match_run_twice_does_not_clobber(tmp_path: Path) -> None:
    assert main([*_RUN_ARGS, "--out", str(tmp_path)]) == 0
    assert main([*_RUN_ARGS, "--out", str(tmp_path)]) == 0
    journals = list(tmp_path.glob("**/journal.jsonl"))
    assert len(journals) == 2, journals


def test_match_verify_ok(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "match",
            "verify",
            "--scenario",
            "concours",
            "--seed",
            "42",
            "--agents",
            "grinder,allier,raider,forger",
            "--ticks",
            "12",
            "--cull-every",
            "6",
            "--repeat",
            "2",
        ]
    )
    assert code == 0
    assert "OK" in capsys.readouterr().out


def test_match_replay(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([*_RUN_ARGS, "--out", str(tmp_path)]) == 0
    capsys.readouterr()  # drop the run output
    journal = _find_journal(tmp_path)
    code = main(["match", "replay", str(journal)])
    assert code == 0
    out = capsys.readouterr().out
    assert "final ranking:" in out


def test_no_subcommand_returns_usage() -> None:
    assert main([]) == 2
