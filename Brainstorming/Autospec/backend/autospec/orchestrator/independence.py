"""Deterministic task-independence analyzer (refactor P4).

The streams scheduler used to run any two tasks of the same stream in parallel,
even when both edited the SAME files (e.g. two frontend tasks both touching
``App.tsx``). Their worktrees then conflicted on merge and green work was lost.

This module is the *safety floor*: given each task's declared file claims
(``Task.files_hint`` / ``file_globs``), it computes which pairs of tasks could
touch the same file and therefore MUST NOT run concurrently unless one already
depends on the other. It returns, deterministically and WITHOUT any LLM:

- ``conflict_pairs``  : unordered task pairs that overlap on files and have no
  dependency ordering between them — i.e. unsafe to parallelize as-is;
- ``added_deps``      : the ``depends_on`` edges to inject so every conflicting
  pair is serialized (stable: the later-declared task waits for the earlier);
- ``parallel_classes``: groups of task ids that are provably file-disjoint and
  may run together;
- ``warnings``        : tasks with NO declared claims (treated as "claims the
  whole stream" → serialized by default, the safe choice).

An LLM "independence judge" (skill ``task-independence``) may ADD constraints on
top of this, but can never remove a serialization the file overlap proves
necessary. Conservative by design: when disjointness cannot be proven, assume
overlap (favour correctness over parallelism).
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "TaskClaim",
    "IndependenceReport",
    "globs_overlap",
    "claims_overlap",
    "declared_overlap",
    "declared_serialization",
    "analyze",
]

# Characters that start a wildcard region in a glob.
_WILDCARD = set("*?[")


@dataclass(frozen=True)
class TaskClaim:
    """A task reduced to what independence needs: its id, its stream (tasks of
    different streams live in disjoint ``file_root``s and never conflict), the
    file globs it expects to touch, and its declared dependencies."""

    id: str
    stream: str = ""
    file_globs: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()


@dataclass
class IndependenceReport:
    conflict_pairs: list[tuple[str, str]] = field(default_factory=list)
    added_deps: dict[str, tuple[str, ...]] = field(default_factory=dict)
    parallel_classes: list[list[str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _norm(glob: str) -> str:
    return glob.strip().replace("\\", "/").lstrip("./")


def _static_prefix(glob: str) -> str:
    """The leading path that contains no wildcard, truncated at a path segment
    boundary. ``src/components/*.tsx`` → ``src/components/``; ``App.tsx`` → the
    whole literal (no wildcard)."""
    g = _norm(glob)
    cut = len(g)
    for i, ch in enumerate(g):
        if ch in _WILDCARD:
            cut = i
            break
    prefix = g[:cut]
    # Truncate to the last complete segment so "src/comp*" → "src/".
    if cut < len(g) and "/" in prefix:
        prefix = prefix[: prefix.rfind("/") + 1]
    return prefix


def _prefix_related(a: str, b: str) -> bool:
    """True if one path is a (segment-wise) prefix of the other, or they are
    equal — the only way two static prefixes can still share a concrete path."""
    if a == b:
        return True
    lo, hi = (a, b) if len(a) <= len(b) else (b, a)
    if lo == "":
        return True  # an empty static prefix (pure wildcard) matches anything
    if not lo.endswith("/"):
        lo = lo + "/"
    return hi.startswith(lo)


def globs_overlap(g1: str, g2: str) -> bool:
    """Conservatively decide whether two globs could match a common path.

    Proven disjoint only when their static (wildcard-free) prefixes diverge.
    Otherwise assume overlap. An empty glob means "unspecified" → overlaps."""
    a, b = _norm(g1), _norm(g2)
    if not a or not b:
        return True
    if a == b:
        return True
    return _prefix_related(_static_prefix(a), _static_prefix(b))


def claims_overlap(t1: TaskClaim, t2: TaskClaim) -> bool:
    """Whether two tasks could touch a common file.

    DECLARED on both sides → compare the REAL repo-relative paths, *stream-
    agnostic*: two tasks of DIFFERENT streams that both touch a shared root file
    (``README.md``, ``.gitignore``, ``main.py``, ``docker-compose.yml``…) DO
    conflict on merge — the stream is not a safe disjointer for declared paths.

    At least one side UNSPECIFIED ("the whole stream") → only the stream tells us
    anything: different streams live in disjoint ``file_root``s (presumed
    disjoint), the same stream is presumed to overlap (conservative)."""
    if t1.id == t2.id:
        return False
    if t1.file_globs and t2.file_globs:
        return any(globs_overlap(a, b) for a in t1.file_globs for b in t2.file_globs)
    if (t1.stream or "") != (t2.stream or ""):
        return False  # an unspecified claim only spans its own stream's file_root
    return True


def declared_overlap(t1: TaskClaim, t2: TaskClaim) -> bool:
    """Stricter than :func:`claims_overlap`: True only when BOTH tasks have
    DECLARED (non-empty) file globs that overlap on their REAL paths (stream-
    agnostic — a cross-stream shared root file still conflicts). Used by the live
    scheduler guard as a pure backstop — it must never serialize on merely-
    undeclared claims (that is the floor's job via injected ``depends_on``; doing
    it at schedule time without that ordering could deadlock same-stream
    siblings)."""
    if t1.id == t2.id:
        return False
    if not t1.file_globs or not t2.file_globs:
        return False
    return any(globs_overlap(a, b) for a in t1.file_globs for b in t2.file_globs)


def declared_serialization(tasks: list[TaskClaim]) -> dict[str, tuple[str, ...]]:
    """P1: a GLOBAL deterministic pass — the ``depends_on`` edges to inject so
    every pair of tasks whose DECLARED globs overlap (across stories AND streams)
    is serialized, unless already ordered. Unlike :func:`analyze`, it leaves
    UNDECLARED claims untouched (no whole-stream serialization), so it never
    over-serializes or deadlocks: it only closes the gap where two *different*
    stories/streams both declare a shared real file (e.g. ``pyproject.toml`` or
    a repo-root ``README.md``). Stable: the later-declared task waits."""
    deps: dict[str, set[str]] = {t.id: set(t.depends_on) for t in tasks}
    index = {t.id: i for i, t in enumerate(tasks)}
    added: dict[str, set[str]] = {}
    for i in range(len(tasks)):
        for j in range(i + 1, len(tasks)):
            a, b = tasks[i], tasks[j]
            if not declared_overlap(a, b) or _ordered(a.id, b.id, deps):
                continue
            later, earlier = (a.id, b.id) if index[a.id] > index[b.id] else (b.id, a.id)
            deps[later].add(earlier)
            added.setdefault(later, set()).add(earlier)
    return {k: tuple(sorted(v)) for k, v in added.items()}


def _ordered(a: str, b: str, deps: dict[str, set[str]]) -> bool:
    """True if a depends on b or b depends on a (transitively): one is already
    scheduled strictly before the other, so they never co-run."""
    return _reaches(a, b, deps) or _reaches(b, a, deps)


def _reaches(src: str, dst: str, deps: dict[str, set[str]]) -> bool:
    seen: set[str] = set()
    stack = [src]
    while stack:
        cur = stack.pop()
        for nxt in deps.get(cur, ()):  # cur depends_on nxt
            if nxt == dst:
                return True
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return False


def analyze(tasks: list[TaskClaim]) -> IndependenceReport:
    """Compute the deterministic independence report for ``tasks`` (declaration
    order matters: it makes the injected ``depends_on`` stable)."""
    report = IndependenceReport()
    by_id = {t.id: t for t in tasks}
    deps: dict[str, set[str]] = {t.id: set(t.depends_on) for t in tasks}
    index = {t.id: i for i, t in enumerate(tasks)}

    for t in tasks:
        if not t.file_globs:
            report.warnings.append(
                f"tâche {t.id} : aucune revendication de fichiers (file_globs) "
                "→ sérialisée par sécurité (revendique tout le stream)."
            )

    # Conflicts: overlapping & not already ordered. Serialize each by making the
    # later-declared task depend on the earlier one (stable, acyclic).
    for i in range(len(tasks)):
        for j in range(i + 1, len(tasks)):
            a, b = tasks[i], tasks[j]
            if not claims_overlap(a, b):
                continue
            if _ordered(a.id, b.id, deps):
                continue
            report.conflict_pairs.append((a.id, b.id))
            later, earlier = (a.id, b.id) if index[a.id] > index[b.id] else (b.id, a.id)
            deps[later].add(earlier)  # keep the live graph in sync for transitivity

    for tid, dset in deps.items():
        original = set(by_id[tid].depends_on)
        injected = dset - original
        if injected:
            report.added_deps[tid] = tuple(sorted(injected))

    report.parallel_classes = _parallel_classes(tasks, deps)
    return report


def _parallel_classes(tasks: list[TaskClaim], deps: dict[str, set[str]]) -> list[list[str]]:
    """Greedy grouping of tasks that are mutually file-disjoint AND mutually
    unordered — a conservative set of groups safe to launch concurrently. Greedy
    is enough: the scheduler only needs "may these co-run?", not an optimum."""
    classes: list[list[str]] = []
    for t in tasks:
        placed = False
        for cls in classes:
            if all(
                not claims_overlap(t, by) and not _ordered(t.id, by.id, deps)
                for by in (next(x for x in tasks if x.id == cid) for cid in cls)
            ):
                cls.append(t.id)
                placed = True
                break
        if not placed:
            classes.append([t.id])
    return classes
