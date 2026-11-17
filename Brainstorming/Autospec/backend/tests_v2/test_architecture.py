"""Structural rules of the v2 core (docs/REFONTE_V2.md sections 3 and 4)."""

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "autospec" / "core"
V1_MODULES = ("autospec.orchestrator", "autospec.agents", "autospec.config", "autospec.api",
              "autospec.models", "autospec.storage", "autospec.validation")
# The plan aimed at 2,500 lines (API and models excluded); fullstack, cancellable process
# trees and resume scheduling brought it to about 2,850. Raising it again needs a reason.
CORE_LINE_BUDGET = 2_900
OUTSIDE_BUDGET = ("api.py", "models.py")  # docs/REFONTE_V2.md 4.7 excludes them


def _core_files():
    return sorted(p for p in CORE.glob("*.py"))


def test_core_never_imports_v1():
    offenders = []
    for path in _core_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            offenders += [f"{path.name}: {n}" for n in names if n.startswith(V1_MODULES)]
    assert offenders == []


def test_core_stays_small():
    total = sum(len(p.read_text(encoding="utf-8").splitlines())
                for p in _core_files() if p.name not in OUTSIDE_BUDGET)
    assert total <= CORE_LINE_BUDGET, f"core/ is {total} lines, budget {CORE_LINE_BUDGET}"


def test_no_em_dash_in_core():
    em_dash = chr(0x2014)  # spelled by code point so this file holds none either
    assert not [p.name for p in _core_files() if em_dash in p.read_text(encoding="utf-8")]
