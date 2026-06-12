"""Parse a pytest-json-report file into per-node outcomes.

Used to ground per-test states on the REAL pytest run rather than the dev
agent's self-report. Robust to a missing/corrupt report (returns {}).
"""

from __future__ import annotations

import json
from pathlib import Path


def parse(report_path: str | Path) -> dict[str, str]:
    """Return {nodeid: outcome} from a pytest-json-report JSON file.

    outcome is pytest's: "passed" / "failed" / "error" / "skipped" / "xfailed"…
    """
    try:
        data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    results: dict[str, str] = {}
    for test in data.get("tests", []):
        node = test.get("nodeid")
        outcome = test.get("outcome")
        if node and outcome:
            results[node] = outcome
    return results
