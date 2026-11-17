"""Structural rules of the v2 core (docs/REFONTE_V2.md sections 3 and 4)."""

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "autospec" / "core"
V1_MODULES = ("autospec.orchestrator", "autospec.agents", "autospec.config", "autospec.api",
              "autospec.models", "autospec.storage", "autospec.validation")
CORE_LINE_BUDGET = 2_500 + 300  # plan target for core/ (excluding models) plus margin


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
                for p in _core_files() if p.name != "models.py")
    assert total <= CORE_LINE_BUDGET, f"core/ is {total} lines, budget {CORE_LINE_BUDGET}"


def test_no_em_dash_in_core():
    assert not [p.name for p in _core_files() if "—" in p.read_text(encoding="utf-8")]
