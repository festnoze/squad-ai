"""V3-F8 — Codebase Cartographer (carte locale du code généré).

Deterministic first: the module graph (internal imports), per-file fan-in/
fan-out, hot files (highest fan-in), sizes and orphan modules are computed by
pure parsing — Python via :mod:`ast`, TypeScript/JS via import regexes. NO LLM
is needed to build or render the map. An optional worker-tier stage then
summarizes each component (role, observed conventions) into the F4
``component_memory`` (kind="cartography", replace-not-append), so the summaries
flow to the dev prompts through the existing knowledge_block — the cartographer
writes into the EXISTING memory, never a new store (vision §5).

The map itself is deliberately NOT persisted in ``ProjectState`` (it is derived
data, rebuilt from the workspace); only its fingerprint is, so an unchanged
workspace costs strictly zero work. Everything is fail-open: an unparseable
file is skipped with a warning, a missing workspace yields an empty map.
"""

from __future__ import annotations

import ast
import hashlib
import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field

from ..agents import prompts
from ..agents.personas import persona
from ..agents.runner import extract_json
from ..config import settings
from ..models import Stream, backend_stream_for
from .knowledge import KnowledgeBase, MemoryEntry
from . import toolchain

logger = logging.getLogger(__name__)

# The MemoryEntry.kind reserved for cartographer summaries — replace-not-append
# semantics key on it (no unbounded growth of the component memory).
CARTOGRAPHY_KIND = "cartography"

# Directories never scanned (generated/vendored/VCS trees).
SKIP_DIRS = frozenset(
    {
        ".git", ".venv", "venv", "node_modules", "__pycache__",
        ".pytest_cache", "dist", "build", ".autospec", ".claude", "target",
    }
)

_TS_EXTS = (".ts", ".tsx", ".js", ".jsx")

# Frontend language keys not covered by toolchain.is_frontend (defensive).
_TS_LANGS = frozenset({"ts", "tsx", "typescript", "js", "javascript", "node", "react", "vue"})

# Relative import specifiers only — external packages are not internal edges.
_TS_FROM_RE = re.compile(r"""from\s+['"](\.[^'"]+)['"]""")
_TS_BARE_RE = re.compile(r"""import\s+['"](\.[^'"]+)['"]""")
_TS_CALL_RE = re.compile(r"""(?:require|import)\(\s*['"](\.[^'"]+)['"]\s*\)""")

# Cap on the number of files fingerprinted/scanned — the map must stay cheap.
_MAX_FILES = 5000

# Autospec's own volatile bookkeeping (state/knowledge sidecars, monitors) is
# rewritten constantly by the orchestrator: the fs-fallback fingerprint must
# ignore it, or every _sync() would look like a code change.
_FP_SKIP_FILES = frozenset(
    {"build-monitor.jsonl", ".report.json", "plan_breach.json"}
)


def _is_bookkeeping(name: str) -> bool:
    return name in _FP_SKIP_FILES or name.startswith("autospec-")


# ------------------------------------------------------------------- models

class StreamMap(BaseModel):
    """The module graph of ONE stream (its ``file_root`` zone)."""

    stream_id: str = ""
    language: str = ""
    file_root: str = ""            # workspace-relative ("" = repo root)
    file_count: int = 0
    total_lines: int = 0
    edges: list[tuple[str, str]] = Field(default_factory=list)  # (src, dst) rel paths
    fan_in: dict[str, int] = Field(default_factory=dict)
    fan_out: dict[str, int] = Field(default_factory=dict)
    orphans: list[str] = Field(default_factory=list)   # no in/out edges
    warnings: list[str] = Field(default_factory=list)  # unparseable files, …

    def hot_files(self, n: int) -> list[tuple[str, int]]:
        """Top-``n`` files by fan-in (>0), deterministically ordered."""
        ranked = sorted(self.fan_in.items(), key=lambda kv: (-kv[1], kv[0]))
        return [(f, c) for f, c in ranked if c > 0][: max(0, n)]


class CodeMap(BaseModel):
    """Per-stream module graphs of the generated project (NOT persisted)."""

    streams: dict[str, StreamMap] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        return all(m.file_count == 0 for m in self.streams.values())


# ----------------------------------------------------- in-process map registry
# The last built map per project, so the prompt seams (po_structure S1, dev
# knowledge_context) can read it without threading it through every signature.
# Derived data only: losing it on restart is harmless (next refresh rebuilds).

_MAPS: dict[str, CodeMap] = {}


def set_current_map(project_id: str, code_map: CodeMap) -> None:
    _MAPS[project_id] = code_map


def current_map(project_id: str) -> CodeMap | None:
    return _MAPS.get(project_id)


def clear_current_map(project_id: str) -> None:
    _MAPS.pop(project_id, None)


# --------------------------------------------------------------- file walking

def _is_test_path(rel: Path) -> bool:
    parts = {p.lower() for p in rel.parts}
    if parts & {"tests", "test", "__tests__"}:
        return True
    name = rel.name.lower()
    return name.startswith("test_") or ".test." in name or ".spec." in name


def _walk_files(root: Path, exts: tuple[str, ...], *, exclude_roots: list[Path],
                include_tests: bool) -> list[Path]:
    """Source files under ``root`` (sorted, bounded), skipping vendored dirs,
    other streams' zones and (optionally) test files. Never raises."""
    out: list[Path] = []
    try:
        for p in sorted(root.rglob("*")):
            if len(out) >= _MAX_FILES:
                break
            if not p.is_file() or p.suffix.lower() not in exts:
                continue
            rel = p.relative_to(root)
            if any(part in SKIP_DIRS for part in rel.parts):
                continue
            if any(p.is_relative_to(ex) for ex in exclude_roots):
                continue
            if not include_tests and _is_test_path(rel):
                continue
            out.append(p)
    except OSError as exc:
        logger.warning("Cartographer walk failed under %s: %s", root, exc)
    return out


def _count_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


# ------------------------------------------------------- Python module graph

def _py_module_name(rel: Path) -> str:
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _py_import_targets(tree: ast.AST, module: str) -> list[str]:
    """Candidate dotted names imported by one parsed file. For ``from X import
    n`` both ``X.n`` (submodule) and ``X`` are candidates — the resolver keeps
    the most specific one that exists."""
    targets: list[str] = []
    pkg_parts = module.split(".")[:-1] if module else []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import — resolve against this file's package
                base_parts = pkg_parts[: len(pkg_parts) - (node.level - 1)]
                if node.level - 1 > len(pkg_parts):
                    continue  # beyond the scanned root
                base = ".".join(base_parts + node.module.split(".")) if node.module \
                    else ".".join(base_parts)
            else:
                base = node.module or ""
            if not base:
                continue
            for alias in node.names:
                targets.append(f"{base}.{alias.name}")
            targets.append(base)
    return targets


def _py_resolve(target: str, index: dict[str, str]) -> str | None:
    """Longest dotted prefix of ``target`` present in the module index."""
    parts = target.split(".")
    while parts:
        hit = index.get(".".join(parts))
        if hit is not None:
            return hit
        parts.pop()
    return None


def _scan_python(root: Path, *, exclude_roots: list[Path], include_tests: bool,
                 smap: StreamMap) -> None:
    files = _walk_files(root, (".py",), exclude_roots=exclude_roots,
                        include_tests=include_tests)
    index: dict[str, str] = {}
    rels: dict[Path, str] = {}
    for f in files:
        rel = f.relative_to(root)
        rels[f] = rel.as_posix()
        dotted = _py_module_name(rel)
        if dotted:
            index[dotted] = rel.as_posix()
    edges: set[tuple[str, str]] = set()
    for f in files:
        src = rels[f]
        smap.file_count += 1
        smap.total_lines += _count_lines(f)
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError) as exc:
            smap.warnings.append(f"{src} : fichier Python non analysable ({exc.__class__.__name__})")
            continue
        module = _py_module_name(f.relative_to(root))
        seen: set[str] = set()
        for target in _py_import_targets(tree, module):
            if target in seen:
                continue
            seen.add(target)
            dst = _py_resolve(target, index)
            if dst is not None and dst != src:
                edges.add((src, dst))
    _finish_graph(smap, sorted(rels.values()), sorted(edges))


# --------------------------------------------------------- TS/JS module graph

def _ts_resolve(spec: str, src_rel: Path, known: set[str]) -> str | None:
    """Resolve one RELATIVE import specifier against the scanned file set."""
    raw = (src_rel.parent / spec)
    # normalize ../ and ./ without touching the filesystem
    parts: list[str] = []
    for part in raw.as_posix().split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None  # escapes the stream root — not internal
            parts.pop()
        else:
            parts.append(part)
    base = "/".join(parts)
    candidates = [base] if base.lower().endswith(_TS_EXTS) else []
    candidates += [f"{base}{ext}" for ext in _TS_EXTS]
    candidates += [f"{base}/index{ext}" for ext in _TS_EXTS]
    for cand in candidates:
        if cand in known:
            return cand
    return None


def _scan_ts(root: Path, *, exclude_roots: list[Path], include_tests: bool,
             smap: StreamMap) -> None:
    files = _walk_files(root, _TS_EXTS, exclude_roots=exclude_roots,
                        include_tests=include_tests)
    rels = {f: f.relative_to(root) for f in files}
    known = {rel.as_posix() for rel in rels.values()}
    edges: set[tuple[str, str]] = set()
    for f in files:
        rel = rels[f]
        src = rel.as_posix()
        smap.file_count += 1
        smap.total_lines += _count_lines(f)
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            smap.warnings.append(f"{src} : fichier illisible ({exc.__class__.__name__})")
            continue
        specs: set[str] = set()
        for regex in (_TS_FROM_RE, _TS_BARE_RE, _TS_CALL_RE):
            specs.update(regex.findall(text))
        for spec in specs:
            dst = _ts_resolve(spec, rel, known)
            if dst is not None and dst != src:
                edges.add((src, dst))
    _finish_graph(smap, sorted(known), sorted(edges))


def _scan_sizes_only(root: Path, exts: tuple[str, ...], *, exclude_roots: list[Path],
                     include_tests: bool, smap: StreamMap) -> None:
    """Languages without a graph parser (go/rust/sql…): sizes only."""
    for f in _walk_files(root, exts, exclude_roots=exclude_roots,
                         include_tests=include_tests):
        smap.file_count += 1
        smap.total_lines += _count_lines(f)


def _finish_graph(smap: StreamMap, all_files: list[str],
                  edges: list[tuple[str, str]]) -> None:
    smap.edges = list(edges)
    smap.fan_in = {f: 0 for f in all_files}
    smap.fan_out = {f: 0 for f in all_files}
    for src, dst in edges:
        smap.fan_out[src] = smap.fan_out.get(src, 0) + 1
        smap.fan_in[dst] = smap.fan_in.get(dst, 0) + 1
    smap.orphans = [
        f for f in all_files
        if smap.fan_in.get(f, 0) == 0 and smap.fan_out.get(f, 0) == 0
    ]


# --------------------------------------------------------------- map builder

_SIZE_ONLY_EXTS = {"go": (".go",), "rust": (".rs",), "sql": (".sql",)}


def build_code_map(
    workspace_path: Path | str,
    streams: list[Stream] | None = None,
    *,
    include_tests: bool = True,
) -> CodeMap:
    """The deterministic per-stream module graph of a workspace. Pure and
    fail-open: unparseable files are skipped with a warning, a missing or empty
    workspace yields an empty map, nothing here ever raises."""
    ws = Path(workspace_path)
    code_map = CodeMap()
    if not ws.is_dir():
        return code_map
    streams = list(streams or []) or [backend_stream_for()]
    roots = {s.id: ws / (s.file_root or "").strip().strip("/\\") for s in streams}
    for stream in streams:
        root = roots[stream.id]
        smap = StreamMap(
            stream_id=stream.id,
            language=(stream.language or "python"),
            file_root=(stream.file_root or "").strip().strip("/\\"),
        )
        code_map.streams[stream.id] = smap
        if not root.is_dir():
            continue
        # A root-level stream must not swallow the other streams' zones.
        exclude_roots = [
            other for sid, other in roots.items()
            if sid != stream.id and other != root and other.is_relative_to(root)
        ]
        lang = (stream.language or "python").strip().lower()
        try:
            if toolchain.is_frontend(lang) or lang in _TS_LANGS:
                _scan_ts(root, exclude_roots=exclude_roots,
                         include_tests=include_tests, smap=smap)
            elif lang in ("", "python"):
                _scan_python(root, exclude_roots=exclude_roots,
                             include_tests=include_tests, smap=smap)
            else:
                _scan_sizes_only(
                    root, _SIZE_ONLY_EXTS.get(lang, (".py",)),
                    exclude_roots=exclude_roots, include_tests=include_tests,
                    smap=smap,
                )
        except Exception as exc:  # noqa: BLE001 — a broken zone must not kill the map
            logger.warning("Cartographer scan failed for stream %s: %s", stream.id, exc)
            smap.warnings.append(f"scan interrompu : {exc}")
    for smap in code_map.streams.values():
        for warning in smap.warnings:
            logger.warning("Cartographer [%s]: %s", smap.stream_id, warning)
    return code_map


# --------------------------------------------------------------- fingerprint

def map_fingerprint(workspace_path: Path | str) -> str:
    """Cheap change detection for the whole workspace. Prefers git (HEAD +
    porcelain status — builds commit, so this captures every change); falls
    back to a file count + size + mtime hash. "" only when the workspace is
    missing (a caller must not skip on it)."""
    ws = Path(workspace_path)
    if not ws.is_dir():
        return ""
    if (ws / ".git").exists():
        try:
            head = subprocess.run(
                ["git", "-C", str(ws), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=20,
            )
            if head.returncode == 0:
                status = subprocess.run(
                    ["git", "-C", str(ws), "status", "--porcelain"],
                    capture_output=True, text=True, timeout=20,
                )
                raw = head.stdout.strip() + "\n" + (
                    status.stdout if status.returncode == 0 else "?"
                )
                return "git:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("Cartographer git fingerprint failed for %s: %s", ws, exc)
    digest = hashlib.sha1()
    count = 0
    try:
        for p in sorted(ws.rglob("*")):
            if count >= _MAX_FILES:
                break
            if not p.is_file():
                continue
            rel = p.relative_to(ws)
            if any(part in SKIP_DIRS for part in rel.parts) or _is_bookkeeping(rel.name):
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            digest.update(f"{rel.as_posix()}|{st.st_size}|{st.st_mtime_ns}\n".encode("utf-8"))
            count += 1
    except OSError as exc:
        logger.warning("Cartographer fingerprint walk failed for %s: %s", ws, exc)
    return f"fs:{count}:{digest.hexdigest()[:16]}"


# ------------------------------------------------------------ prompt blocks

def map_block(code_map: CodeMap | None, *, stream: str = "",
              hot_n: int | None = None, max_chars: int = 1800) -> str:
    """Bounded, deterministic French summary of the map (no LLM): module
    counts and sizes per component, top hot files with fan-in counts, orphans.
    "" when the map is empty/absent — callers inject it unconditionally."""
    if code_map is None:
        return ""
    n = settings.cartographer_hot_files if hot_n is None else hot_n
    items = sorted(
        (sid, m) for sid, m in code_map.streams.items()
        if (not stream or sid == stream) and m.file_count > 0
    )
    if not items:
        return ""
    lines = ["\nCarte du code (dépendances réelles du repo généré) :"]
    for sid, m in items:
        lines.append(
            f"- {sid} ({m.file_root or 'racine'}) : {m.file_count} module(s), "
            f"{m.total_lines} ligne(s), {len(m.edges)} dépendance(s) interne(s)."
        )
        hot = m.hot_files(n)
        if hot:
            joined = ", ".join(f"{f} (fan-in {c})" for f, c in hot)
            lines.append(f"  Fichiers à fort fan-in — prudence : {joined}")
        if m.orphans:
            shown = ", ".join(m.orphans[:n])
            more = ", …" if len(m.orphans) > n else ""
            lines.append(f"  Modules orphelins (ni importés ni importeurs) : {shown}{more}")
    text = "\n".join(lines) + "\n"
    return text[:max_chars]


def hot_files_line(project_id: str, stream: str) -> str:
    """The dev-prompt caution line for one stream's hot files, from the
    in-process registry. "" when no map / no hot file — safe to concatenate."""
    code_map = current_map(project_id)
    if code_map is None:
        return ""
    smap = code_map.streams.get(stream)
    if smap is None:
        return ""
    hot = smap.hot_files(settings.cartographer_hot_files)
    if not hot:
        return ""
    joined = ", ".join(f"{f} (fan-in {c})" for f, c in hot)
    return (
        f"\nFichiers à fort fan-in — prudence : {joined} (beaucoup de modules en "
        "dépendent : ne change pas leurs signatures/contrats sans nécessité).\n"
    )


# --------------------------------------------- LLM stage (component summaries)

async def asummarize_components(
    kb: KnowledgeBase,
    code_map: CodeMap,
    arun: Callable[..., Awaitable[Any]],
    *,
    iteration: int = 0,
) -> bool:
    """US-F8.2: ONE worker-tier call over the deterministic map digest →
    per-component role/convention summaries, each written into the F4
    ``component_memory`` as a MemoryEntry(kind="cartography") that REPLACES the
    component's previous cartography entries (no unbounded growth). Fail-open:
    any LLM/parse failure leaves the base untouched and returns False; the
    deterministic map stays fully usable either way."""
    digest = map_block(code_map)
    if not digest:
        return False
    try:
        result = await arun(
            prompts.cartographer_summarize(digest),
            system_prompt=persona("cartographer"),
        )
        raw = extract_json(result.text).get("components")
        summaries: list[tuple[str, str]] = []
        if isinstance(raw, list):
            for item in raw:
                if not isinstance(item, dict):
                    continue
                sid = str(item.get("stream") or item.get("component") or "").strip()
                summary = str(item.get("summary") or "").strip()
                if sid and summary and sid in code_map.streams:
                    summaries.append((sid, summary[:600]))
        if not summaries:
            return False
        for sid, summary in summaries:
            bucket = kb.component_memory.setdefault(sid, [])
            bucket[:] = [e for e in bucket if e.kind != CARTOGRAPHY_KIND]
            bucket.append(
                MemoryEntry(text=summary, kind=CARTOGRAPHY_KIND, iteration=iteration)
            )
        return True
    except Exception as exc:  # noqa: BLE001 — fail-open: memory untouched
        logger.warning("Cartographer component summaries failed: %s", exc)
        return False
