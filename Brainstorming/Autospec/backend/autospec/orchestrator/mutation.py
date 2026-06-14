"""Lightweight built-in mutation testing (Q1).

Applies small, single-point semantic mutations to a Python source string (via the
AST) so the orchestrator can run the test suite against each mutant and measure
how many the tests "kill" — a test-robustness signal beyond plain green/red, with
no external dependency (mutmut/cosmic-ray not required).
"""

from __future__ import annotations

import ast

_BINOP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}
_CMP = {
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE, ast.GtE: ast.Lt,
    ast.Gt: ast.LtE, ast.LtE: ast.Gt,
}
_BOOL = {ast.And: ast.Or, ast.Or: ast.And}


def _collect(tree: ast.AST) -> list[ast.AST]:
    """Mutable nodes, in a stable document order."""
    out: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOP:
            out.append(node)
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP:
            out.append(node)
        elif isinstance(node, ast.BoolOp) and type(node.op) in _BOOL:
            out.append(node)
        elif isinstance(node, ast.Constant) and isinstance(node.value, bool):
            out.append(node)
    return out


def _mutate(node: ast.AST) -> str:
    """Mutate ``node`` in place; return a short description of the change."""
    if isinstance(node, ast.BinOp):
        new = _BINOP[type(node.op)]
        desc = f"{type(node.op).__name__}->{new.__name__}"
        node.op = new()
        return desc
    if isinstance(node, ast.Compare):
        new = _CMP[type(node.ops[0])]
        desc = f"{type(node.ops[0]).__name__}->{new.__name__}"
        node.ops = [new()]
        return desc
    if isinstance(node, ast.BoolOp):
        new = _BOOL[type(node.op)]
        desc = f"{type(node.op).__name__}->{new.__name__}"
        node.op = new()
        return desc
    desc = f"const {node.value}->{not node.value}"  # bool constant
    node.value = not node.value
    return desc


def generate_mutants(source: str, max_mutants: int = 50) -> list[tuple[str, str]]:
    """Return up to ``max_mutants`` (description, mutated_source) pairs, each a
    single-point mutation (one operator or bool constant flipped). Returns [] when
    the source does not parse or has no mutable construct.

    ``ast.unparse`` normalizes formatting/comments, so a mutant is the source
    re-emitted with exactly one semantic change — enough to probe the tests."""
    try:
        n_targets = len(_collect(ast.parse(source)))
    except SyntaxError:
        return []
    mutants: list[tuple[str, str]] = []
    for i in range(min(n_targets, max_mutants)):
        fresh = ast.parse(source)  # fresh tree per mutant (node identity per parse)
        desc = _mutate(_collect(fresh)[i])
        try:
            mutants.append((f"#{i + 1} {desc}", ast.unparse(fresh)))
        except Exception:  # noqa: BLE001 — unparse can choke on exotic trees
            continue
    return mutants
