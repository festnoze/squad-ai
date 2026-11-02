"""Aggregate every docs/bench/**/*.json into docs/bench/README.md (newest date first)."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from bench.paths import DOCS_BENCH_DIR

CONFIG_NAMES = {"a": "A v1", "b": "B harness nu", "c": "C v2"}


def _row(result: dict) -> str:
    oracle = result.get("oracle") or {}
    m5 = oracle.get("m5_suite") or {}
    m6 = oracle.get("m6_oracle") or {}
    m7 = oracle.get("m7_smoke") or {}
    completed = {True: "oui", False: "non", None: "n/a"}[result.get("m1_completed")]
    duration = result.get("m2_duration_s")
    cost = result.get("m3_cost_usd")
    return " | ".join([
        result["project"], CONFIG_NAMES.get(result["config"], result["config"]), result.get("model", ""),
        completed,
        f"{duration / 60:.1f} min" if isinstance(duration, (int, float)) else "",
        f"{cost:.2f} $" if isinstance(cost, (int, float)) else "",
        str(result.get("m4_agent_calls") or ""),
        f"{m5.get('passed', 0)}/{m5.get('passed', 0) + m5.get('failed', 0)}" + (" vert" if m5.get("green") else ""),
        f"{m6.get('passed', 0)}/{m6.get('total', 0)}",
        "oui" if m7.get("ok") else "non",
        result.get("git_sha", ""),
    ])


def build(root: Path = DOCS_BENCH_DIR) -> str:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(root.glob("*/*/*.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        result["_file"] = path.relative_to(root).as_posix()
        by_date[result["date"]].append(result)
    lines = ["# Banc de mesure Autospec", "",
             "Généré par `python -m bench.report` depuis les JSON de ce dossier. Métriques : "
             "docs/REFONTE_V2.md section 5.2 (M1 complétion sans intervention, M2 durée, M3 coût, "
             "M4 appels agents, M5 suite du produit en environnement propre, M6 oracle caché, M7 smoke).", ""]
    for day in sorted(by_date, reverse=True):
        lines += [f"## {day}", "",
                  "| Projet | Config | Modèle | M1 | M2 | M3 | M4 | M5 | M6 | M7 | Commit |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for result in sorted(by_date[day], key=lambda r: (r["project"], r["config"], r["_file"])):
            lines.append(f"| {_row(result)} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    DOCS_BENCH_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_BENCH_DIR / "README.md").write_text(build(), encoding="utf-8")
    print(DOCS_BENCH_DIR / "README.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
