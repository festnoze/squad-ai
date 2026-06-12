import json

from autospec.orchestrator import pytest_report


def test_parse_extracts_node_outcomes(tmp_path):
    report = tmp_path / "r.json"
    report.write_text(
        json.dumps(
            {
                "exitcode": 1,
                "tests": [
                    {"nodeid": "tests/unit/test_a.py::test_x", "outcome": "passed"},
                    {"nodeid": "tests/unit/test_b.py::test_y", "outcome": "failed"},
                ],
            }
        ),
        encoding="utf-8",
    )
    assert pytest_report.parse(report) == {
        "tests/unit/test_a.py::test_x": "passed",
        "tests/unit/test_b.py::test_y": "failed",
    }


def test_parse_missing_file_returns_empty(tmp_path):
    assert pytest_report.parse(tmp_path / "nope.json") == {}


def test_parse_corrupt_file_returns_empty(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert pytest_report.parse(bad) == {}
