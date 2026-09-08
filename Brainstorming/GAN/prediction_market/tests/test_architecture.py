"""The ordering rules the gates enforce, as tests over the source tree (PLAN_V2_WAVES, "Ordering rules").

These tests read files, never import them, so they hold on the empty skeleton and keep holding while other
packages are mid-flight. Every rule is a statement about *where* a dependency may live; a package that needs
to break one does not get an exemption here, it gets a contract issue. The rules, in the order of the plan:

1. nothing in ``pmx.engine`` or ``pmx.agents`` imports ``pmx.gateway`` or ``pmx.llm``: the engine never calls
   an LLM, and the direction of that arrow is what keeps a backtest replayable without a provider;
2. ``pmx.metrics.calibration`` never imports ``pmx.engine.execution``: calibration is decoupled from PnL by
   construction, not by discipline;
3. nothing outside ``pmx.optimizer.claims`` reads the sealed test fold: the one accessor is
   ``open_sealed_test`` in ``pmx.optimizer.folds`` and its one caller is ``claims.py`` (CONTRACTS_V2 12.6);
   since amendment C1b's ruling R182 the same scan covers ``Dataset.sealed_market``, the one accessor of a
   continuous instrument's sealed months (``Dataset.market`` returns it clipped at ``validation_end_ms``);
4. nothing outside ``pmx.metrics.stats`` imports numpy: integers everywhere else;
5. nothing in ``pmx`` outside ``gateway``, ``llm``, ``live`` and ``data/importers`` opens a socket: the news
   fetchers go through the shared client in ``data/importers/_http.py``;
6. no engine module reads a wall clock, a UUID or module-level randomness: every draw comes from ``pmx.rng``.

Amendment C1 (CONTRACTS_V2 section 16.6, ruling R124) adds the three rules of ``docs/PLAN_V3_WAVES.md``:

7. nothing outside ``pmx.learn`` and ``pmx.adversary.train`` imports torch, sklearn or
   sentence_transformers: a module that imports a training library is a module a backtest cannot replay
   without one. ``pmx.features.view.float_view`` is not one of those libraries and is not covered: it is
   also legal at the inference boundary of ``agents/families/torch_policy.py`` (CONTRACTS_V2 16.5, ruling
   R140), which imports nothing from this list;
8. nothing in ``pmx.analysis`` writes a journal or reads the sealed test fold: a detector is a projection
   of the dataset, not an agent, and its output is never replayable evidence;
9. ``pmx.engine.liquidity`` is the only place a fill price is computed: every ``LiquidityModel``
   implementation, wherever it lives, returns its quote through that module's ``finalise_fill``, which is
   where the envelope of 16.1 is applied, and the cash truncation of 8.6 step 5 goes back through the same
   module's ``truncate_for_cash`` rather than being redone in ``execution.py`` (ruling R130).

All three bind on a tree where none of those directories exists yet, and they pass vacuously until the
first commit that adds one; that is the point of writing them in the amendment rather than in the wave.

Amendment C1b (CONTRACTS_V2 section 17.7, ruling R172) adds two more:

10. nothing under ``pmx.data`` imports ``pmx.engine``, ``pmx.agents``, ``pmx.metrics`` or
    ``pmx.optimizer``: a seal that depended on the engine version would move with it;
11. ``in_session`` is bound only in ``pmx.data.sessions`` (D1's file since ruling R174, so it exists at gate
    G2): "a bar outside its calendar does not exist" has one implementation, which the loader,
    ``pmx.engine.calendar`` and ``pmx.engine.execution`` call and never redefine.

Two house rules ride along because the same scan pays for them: no em-dash character anywhere in produced
content, and every v2 package ``__init__.py`` is a docstring and nothing else (CONTRACTS_V2 section 13).
``pmx.v1`` is the frozen legacy namespace and is outside every rule except the em-dash sweep.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "pmx"

EM_DASH = chr(0x2014)  # built from its code point so this file passes its own sweep

#: Client libraries whose import means "this module can open a socket". Server frameworks (fastapi, uvicorn)
#: are deliberately not listed: the rule is about the engine reaching out, not about the API listening.
SOCKET_MODULES = (
    "socket",
    "httpx",
    "requests",
    "urllib.request",
    "urllib3",
    "aiohttp",
    "http.client",
    "websockets",
    "ftplib",
    "smtplib",
    "ssl",
)

#: Directories (relative to ``src/pmx``) that may open a socket.
SOCKET_ALLOWED_PREFIXES = ("gateway/", "llm/", "live/", "data/importers/")

#: Modules of the engine proper: pure, replayable, integer-only. The wall-clock and randomness rule applies
#: to these and only these. The impure edges (gateway, llm, live, importers, news fetchers, api, cli, store)
#: are excluded by construction rather than by exemption.
ENGINE_PREFIXES = ("engine/", "agents/", "metrics/", "optimizer/")
ENGINE_FILES = (
    "scoring.py",
    "journal.py",
    "types.py",
    "data/schema.py",
    "data/loader.py",
    "data/resample.py",
    "data/builder.py",
    "data/migrate_v1.py",
    "data/news/linker.py",
    "data/sessions.py",
)

#: Banned wall-clock and identity sources inside the engine.
CLOCK_AND_IDENTITY_MODULES = ("time", "uuid", "secrets")
CLOCK_CALL_RE = re.compile(r"(?<![\w.])(datetime\.(now|utcnow|today)|time\.(time|monotonic|perf_counter)|uuid4)\(")
MODULE_RANDOM_RE = re.compile(
    r"(?<![\w.])random\.(random|Random|seed|choice|choices|shuffle|randint|randrange|gauss|uniform|betavariate|"
    r"getrandbits|sample)\("
)

#: The sealed test fold has exactly one accessor and exactly one caller (CONTRACTS_V2 12.6); the sealed months
#: of a continuous instrument have exactly one accessor too, ``Dataset.sealed_market`` (17.2, ruling R182).
SEALED_RE = re.compile(r"\bopen_sealed_test\b|\b_sealed_ids\b|\bsealed_market\b")
SEALED_ALLOWED = ("optimizer/folds.py", "optimizer/claims.py")

#: Training libraries. Importing one means the module cannot run where a backtest must (CONTRACTS_V2 16.5).
LEARN_MODULES = ("torch", "sklearn", "sentence_transformers", "transformers", "peft")

#: The two directories where training lives (CONTRACTS_V2 16.5 and PLAN_V3_WAVES, "Architecture rules").
LEARN_ALLOWED_PREFIXES = ("learn/", "adversary/train/")

#: A detector reads the dataset and writes JSON; it never journals and never opens the sealed fold.
ANALYSIS_PREFIX = "analysis/"
ANALYSIS_BANNED_IMPORTS = ("pmx.journal", "pmx.optimizer.folds", "pmx.optimizer.claims")
ANALYSIS_BANNED_NAMES = frozenset(
    {"Journal", "read_journal", "write_journal", "journal_hash", "open_sealed_test", "verify_journal"}
)

#: CONTRACTS_V2 16.1 and 16.6 rule 9: one module binds this name, and it is the one that clamps to the
#: envelope. Everything else reads ``Fill.price_bp`` and journals it.
FILL_PRICE_NAME = "fill_price_bp"
FILL_PRICE_ALLOWED = ("engine/liquidity.py",)

#: CONTRACTS_V2 17.7 rule 10: the data layer sits below the engine and never imports it.
DATA_PREFIX = "data/"
DATA_BANNED_IMPORTS = ("pmx.engine", "pmx.agents", "pmx.metrics", "pmx.optimizer")

#: CONTRACTS_V2 17.7 rule 11: session membership has one implementation.
IN_SESSION_NAME = "in_session"
IN_SESSION_ALLOWED = ("data/sessions.py",)


def _v2_python_files() -> Iterator[Path]:
    """Every Python file of the v2 tree, ``pmx.v1`` excluded."""
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith("v1/") or "__pycache__" in rel:
            continue
        yield path


def _rel(path: Path) -> str:
    return path.relative_to(SRC).as_posix()


def _imports(path: Path) -> list[str]:
    """Fully qualified module names imported by ``path`` (``import a.b`` and ``from a.b import c`` alike)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            names.append(node.module)
    return names


def _imports_module(imported: str, target: str) -> bool:
    return imported == target or imported.startswith(target + ".")


def _is_engine_module(rel: str) -> bool:
    return rel in ENGINE_FILES or rel.startswith(ENGINE_PREFIXES)


# --------------------------------------------------------------------------------------------------
# The six plan rules
# --------------------------------------------------------------------------------------------------
def test_rule_1_engine_and_agents_never_import_gateway_or_llm() -> None:
    offenders: list[str] = []
    for path in _v2_python_files():
        rel = _rel(path)
        if not rel.startswith(("engine/", "agents/")):
            continue
        for name in _imports(path):
            if _imports_module(name, "pmx.gateway") or _imports_module(name, "pmx.llm"):
                offenders.append(f"{rel} imports {name}")
    assert offenders == [], offenders


def test_rule_2_calibration_never_imports_execution() -> None:
    path = SRC / "metrics" / "calibration.py"
    if not path.exists():
        return  # the rule is about a file that does not exist yet; it binds the day E3 lands
    bad = [name for name in _imports(path) if _imports_module(name, "pmx.engine.execution")]
    assert bad == [], bad


def test_rule_3_only_claims_reads_the_sealed_test_fold() -> None:
    offenders: list[str] = []
    for path in _v2_python_files():
        rel = _rel(path)
        if rel in SEALED_ALLOWED:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if SEALED_RE.search(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert offenders == [], offenders


def test_rule_4_only_stats_imports_numpy() -> None:
    offenders: list[str] = []
    for path in _v2_python_files():
        rel = _rel(path)
        if rel == "metrics/stats.py":
            continue
        for name in _imports(path):
            if _imports_module(name, "numpy"):
                offenders.append(f"{rel} imports {name}")
    assert offenders == [], offenders


def test_rule_5_only_the_impure_edges_open_sockets() -> None:
    offenders: list[str] = []
    for path in _v2_python_files():
        rel = _rel(path)
        if rel.startswith(SOCKET_ALLOWED_PREFIXES):
            continue
        for name in _imports(path):
            if any(_imports_module(name, module) for module in SOCKET_MODULES):
                offenders.append(f"{rel} imports {name}")
    assert offenders == [], offenders


def test_rule_6_engine_modules_read_no_clock_no_uuid_no_module_randomness() -> None:
    offenders: list[str] = []
    for path in _v2_python_files():
        rel = _rel(path)
        if not _is_engine_module(rel):
            continue
        for name in _imports(path):
            if any(_imports_module(name, module) for module in CLOCK_AND_IDENTITY_MODULES):
                offenders.append(f"{rel} imports {name}")
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if CLOCK_CALL_RE.search(line) or MODULE_RANDOM_RE.search(line):
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert offenders == [], offenders


# --------------------------------------------------------------------------------------------------
# The three rules of amendment C1 (CONTRACTS_V2 16.6)
# --------------------------------------------------------------------------------------------------
def test_rule_7_only_learn_and_adversary_train_import_a_training_library() -> None:
    offenders: list[str] = []
    for path in _v2_python_files():
        rel = _rel(path)
        if rel.startswith(LEARN_ALLOWED_PREFIXES):
            continue
        for name in _imports(path):
            if any(_imports_module(name, module) for module in LEARN_MODULES):
                offenders.append(f"{rel} imports {name}")
    assert offenders == [], offenders


def test_rule_8_analysis_writes_no_journal_and_reads_no_sealed_fold() -> None:
    offenders: list[str] = []
    for path in _v2_python_files():
        rel = _rel(path)
        if not rel.startswith(ANALYSIS_PREFIX):
            continue
        for name in _imports(path):
            if any(_imports_module(name, module) for module in ANALYSIS_BANNED_IMPORTS):
                offenders.append(f"{rel} imports {name}")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in ANALYSIS_BANNED_NAMES:
                offenders.append(f"{rel}:{node.lineno}: names {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in ANALYSIS_BANNED_NAMES:
                offenders.append(f"{rel}:{node.lineno}: names {node.attr}")
            elif isinstance(node, ast.Constant) and node.value == "sealed":
                offenders.append(f'{rel}:{node.lineno}: carries the literal "sealed"')
    assert offenders == [], offenders


def _assigned_names(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """Every name this module *computes a value for*.

    Reading the field, passing it as a keyword and declaring it are all legal: ``pmx.journal``'s ``Filled``
    event declares ``fill_price_bp: int`` with no value and ``pmx.engine.execution`` journals the number it
    was handed. What the rule forbids is binding a value to that name outside ``engine/liquidity.py``, so a
    bare annotation (``AnnAssign`` with no value) is not a binding."""
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [] if node.value is None else [node.target]
        elif isinstance(node, ast.AugAssign | ast.NamedExpr):
            targets = [node.target]
        for target in targets:
            for sub in ast.walk(target):
                if isinstance(sub, ast.Name):
                    yield sub.lineno, sub.id
                elif isinstance(sub, ast.Attribute):
                    yield sub.lineno, sub.attr


def test_rule_9_only_liquidity_computes_a_fill_price() -> None:
    offenders: list[str] = []
    for path in _v2_python_files():
        rel = _rel(path)
        if rel in FILL_PRICE_ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, name in _assigned_names(tree):
            if name == FILL_PRICE_NAME:
                offenders.append(f"{rel}:{lineno}: binds {name}")
    assert offenders == [], offenders


# --------------------------------------------------------------------------------------------------
# The two rules of amendment C1b (CONTRACTS_V2 17.7, ruling R172)
# --------------------------------------------------------------------------------------------------
def test_rule_10_the_data_layer_never_imports_the_engine() -> None:
    offenders: list[str] = []
    for path in _v2_python_files():
        rel = _rel(path)
        if not rel.startswith(DATA_PREFIX):
            continue
        for name in _imports(path):
            if any(_imports_module(name, module) for module in DATA_BANNED_IMPORTS):
                offenders.append(f"{rel} imports {name}")
    assert offenders == [], offenders


def _defined_names(tree: ast.AST) -> Iterator[tuple[int, str]]:
    """Every name a module binds by assignment or by ``def``; a call or an import of the name is not a binding."""
    yield from _assigned_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node.lineno, node.name


def test_rule_11_only_sessions_decides_session_membership() -> None:
    offenders: list[str] = []
    for path in _v2_python_files():
        rel = _rel(path)
        if rel in IN_SESSION_ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for lineno, name in _defined_names(tree):
            if name == IN_SESSION_NAME:
                offenders.append(f"{rel}:{lineno}: binds {name}")
    assert offenders == [], offenders


# --------------------------------------------------------------------------------------------------
# House rules that share the scan
# --------------------------------------------------------------------------------------------------
def _produced_text_files() -> Iterator[Path]:
    roots = (REPO / "src", REPO / "tests", REPO / "schemas", REPO / "docs", REPO / "web" / "src")
    suffixes = {".py", ".md", ".json", ".toml", ".ts", ".tsx", ".css", ".html", ".bat", ".txt", ".jsonl"}
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in suffixes and "node_modules" not in path.parts:
                yield path
    for name in ("README.md", "pyproject.toml", "run.bat", ".gitignore"):
        path = REPO / name
        if path.exists():
            yield path


def test_no_em_dash_anywhere_in_produced_content() -> None:
    offenders: list[str] = []
    for path in _produced_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if EM_DASH in text:
            first = text.index(EM_DASH)
            lineno = text.count("\n", 0, first) + 1
            offenders.append(f"{path.relative_to(REPO).as_posix()}:{lineno}")
    assert offenders == [], offenders


def test_v2_package_inits_are_docstring_only() -> None:
    """``__init__.py`` is a docstring and nothing else, so no package re-exports a name another package owns.

    The top level ``pmx/__init__.py`` is the one exception: it may carry the version constants."""
    offenders: list[str] = []
    for path in _v2_python_files():
        rel = _rel(path)
        if path.name != "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        body = list(tree.body)
        if not body or not (isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)):
            offenders.append(f"{rel}: missing module docstring")
            continue
        rest = body[1:]
        if rel == "__init__.py":
            rest = [node for node in rest if not isinstance(node, ast.Assign | ast.AnnAssign)]
        if rest:
            offenders.append(f"{rel}: carries {type(rest[0]).__name__} beyond the docstring")
    assert offenders == [], offenders


def test_skeleton_matches_the_module_map() -> None:
    """Every package directory of CONTRACTS_V2 section 13 exists with an ``__init__.py``."""
    expected = (
        "data",
        "data/importers",
        "data/news",
        "engine",
        "agents",
        "agents/families",
        "gateway",
        "llm",
        "metrics",
        "optimizer",
        "live",
        "api",
    )
    missing = [rel for rel in expected if not (SRC / rel / "__init__.py").exists()]
    assert missing == [], missing
