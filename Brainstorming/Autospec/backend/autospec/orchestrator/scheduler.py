"""Dependency-aware story scheduling (pure functions, unit-tested)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ..models import StoryStatus, UserStory
from .streams import WorkGraph, fanout

# Sort key used when an item exposes no usable kanban priority: unknown
# priorities rank AFTER any declared one, ties then falling back to the
# topological position (so the ordering stays deterministic either way).
_UNKNOWN_PRIORITY = 10**6


def validate_dependencies(stories: list[UserStory]) -> list[str]:
    """Return a list of problems (unknown ids, cycles). Empty list = valid."""
    problems: list[str] = []
    ids = {s.id for s in stories}
    for story in stories:
        for dep in story.depends_on:
            if dep not in ids:
                problems.append(f"{story.id} depends on unknown story {dep}")

    # Cycle detection via iterative DFS coloring.
    graph = {s.id: [d for d in s.depends_on if d in ids] for s in stories}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(graph, WHITE)
    for root in graph:
        if color[root] != WHITE:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        color[root] = GRAY
        while stack:
            node, idx = stack[-1]
            deps = graph[node]
            if idx < len(deps):
                stack[-1] = (node, idx + 1)
                child = deps[idx]
                if color[child] == GRAY:
                    problems.append(f"dependency cycle involving {child}")
                elif color[child] == WHITE:
                    color[child] = GRAY
                    stack.append((child, 0))
            else:
                color[node] = BLACK
                stack.pop()
    return problems


def sanitize_dependencies(stories: list[UserStory]) -> None:
    """Drop references to unknown stories and self-references, in place."""
    ids = {s.id for s in stories}
    for story in stories:
        story.depends_on = [d for d in story.depends_on if d in ids and d != story.id]
    # Break cycles defensively so the pipeline can never deadlock: clear the
    # deps of the stories reported inside a cycle (leaving the dependencies of
    # unrelated stories intact), until validation passes.
    while True:
        cycle_ids = {
            p.rsplit(" ", 1)[-1] for p in validate_dependencies(stories) if "cycle" in p
        }
        if not cycle_ids:
            return
        offenders = [s for s in stories if s.id in cycle_ids and s.depends_on]
        if not offenders:
            # Cannot map the report back to a story (should not happen):
            # fall back to clearing everything rather than looping forever.
            for story in stories:
                story.depends_on = []
            return
        for story in offenders:
            story.depends_on = []


def ready_stories(stories: list[UserStory]) -> list[UserStory]:
    """Stories whose dependencies are all DONE and that are still TODO.

    Kanban ordering: independent ready stories are picked by ascending
    priority (1 = highest), declaration order breaking ties.
    """
    done = {s.id for s in stories if s.status == StoryStatus.DONE}
    ready = [
        s
        for s in stories
        if s.status == StoryStatus.TODO and all(d in done for d in s.depends_on)
    ]
    order = {s.id: i for i, s in enumerate(stories)}
    return sorted(ready, key=lambda s: (s.priority, order[s.id]))


def _priority_of(item: Any, priorities: Mapping[str, int] | None) -> int:
    """The kanban priority to sort ``item`` by (1 = highest), or the unknown
    sentinel. ``priorities`` (optional) maps a work-item id OR its story id to
    a priority, which lets a caller feed the story-level priority of a task -
    a ``Task`` has none of its own. An explicit mapping wins over the
    attribute, and only a real ``int`` is accepted (``bool`` excluded)."""
    if priorities:
        for key in (getattr(item, "id", None), getattr(item, "story_id", None)):
            if key is not None and key in priorities:
                value = priorities[key]
                if isinstance(value, int) and not isinstance(value, bool):
                    return value
    value = getattr(item, "priority", None)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return _UNKNOWN_PRIORITY


def rank_ready(
    items: Iterable[Any],
    graph: WorkGraph,
    *,
    fanout_counts: Mapping[str, int] | None = None,
    priorities: Mapping[str, int] | None = None,
) -> list[Any]:
    """P1-C: order already-ready work items by criticality (pure function).

    This ORDERS only - it never filters: readiness is the caller's job (see
    ``streams.is_ready``), so every item handed in comes back out exactly once.

    Sort key, in order:
    1. transitive fan-out, DESCENDING (the item blocking the most work first -
       the critical path);
    2. declared kanban priority, ASCENDING (1 = highest), read off the item via
       ``getattr`` or from the optional ``priorities`` mapping; items without a
       priority sort last among equals;
    3. the original topological position, i.e. the index in ``graph.order``
       (declaration order), which keeps the legacy behaviour as the tie-break.

    ``fanout_counts`` lets a caller reuse a fan-out map computed once for the
    whole build instead of recomputing it per pick; when omitted it is derived
    from ``graph`` with :func:`..streams.fanout`. An item missing from the
    graph gets a fan-out of 0 and keeps its incoming relative position, after
    every graph item. The sort is stable and deterministic.
    """
    counts = fanout(graph) if fanout_counts is None else fanout_counts
    positions = {wid: index for index, wid in enumerate(graph.order)}
    unknown_base = len(graph.order)

    decorated: list[tuple[int, int, int, int, Any]] = []
    for offset, item in enumerate(items):
        wid = getattr(item, "id", None)
        position = positions.get(wid, unknown_base + offset)
        decorated.append(
            (
                -int(counts.get(wid, 0)),
                _priority_of(item, priorities),
                position,
                offset,
                item,
            )
        )
    decorated.sort(key=lambda row: row[:4])
    return [row[4] for row in decorated]


def fanout_bonus_attempts(fanout: int, threshold: int) -> int:
    """P1-C: the extra dev attempt granted to a high fan-out item.

    Failing an item that transitively blocks ``threshold`` others costs the
    whole iteration, so it is worth one more try than a leaf. Returns 1 when
    ``fanout >= threshold`` and ``threshold > 0``, else 0 - a threshold of 0
    (or below) disables the bonus entirely, which is the retro-compatible
    default."""
    if threshold <= 0:
        return 0
    return 1 if fanout >= threshold else 0


def pending_stories(stories: list[UserStory]) -> list[UserStory]:
    active = {StoryStatus.TODO, StoryStatus.IN_PROGRESS, StoryStatus.RED, StoryStatus.GREEN}
    return [s for s in stories if s.status in active]


def failed_root(node, by_id: dict):
    """The first FAILED dependency reachable from ``node`` (BFS, transitive) —
    the ROOT CAUSE an operator needs when a whole chain gets marked
    « dépendance non satisfaite » : the direct blocker of a deep item is often
    itself only blocked, and the real failure sits levels below (messagerie2 :
    T8 ← T6 ← T5-S1-S1). Duck-typed on ``.depends_on``/``.status`` so it works
    for stories AND stream work items. None when nothing failed upstream."""
    seen: set[str] = set()
    queue = list(getattr(node, "depends_on", ()))
    while queue:
        dep_id = queue.pop(0)
        if dep_id in seen:
            continue
        seen.add(dep_id)
        dep = by_id.get(dep_id)
        if dep is None:
            continue
        if dep.status == StoryStatus.FAILED:
            return dep
        queue.extend(getattr(dep, "depends_on", ()))
    return None
