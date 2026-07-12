"""ST-3: the unified work-item dependency graph.

A *work item* is the smallest schedulable unit: a task (when a US is decomposed
into tasks), or a taskless US itself. This module turns a ``ProjectState`` into a
graph of work items with resolved cross-level dependencies, so the (future)
stream-aware scheduler can pick the items that are *ready* (all dependencies
done) and run independent ones in parallel.

Dependency semantics:
- A US-level ``depends_on`` references other US. Depending on a US that is itself
  decomposed means depending on ALL of its tasks (the whole US must be done).
- A task ``depends_on`` references other tasks (possibly cross-stream). A task
  also inherits its parent US's ``depends_on`` (the US-level ordering applies to
  every task under it).

This is a strict generalization of today's story DAG: with no tasks and no
streams, every US is a work item whose deps are its ``depends_on`` — exactly the
current build ordering. So building this graph on a legacy project is a no-op
change in meaning; only the (later) scheduler will start using it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import ProjectState, StoryStatus

__all__ = [
    "WorkItem",
    "WorkGraph",
    "build_work_graph",
    "detect_cycle",
    "cycle_nodes",
    "transitive_dependents",
    "dependency_targets",
    "ready_items",
    "is_ready",
    "blocked_by",
    "validate",
]

_DONE: tuple[StoryStatus, ...] = (StoryStatus.DONE,)


@dataclass(frozen=True)
class WorkItem:
    """A schedulable unit. ``id`` is the task id (kind ``"task"``) or the story
    id (kind ``"story"``). ``depends_on`` is RESOLVED to other work-item ids."""

    id: str
    kind: str  # "task" | "story"
    story_id: str
    stream: str
    title: str
    status: StoryStatus
    depends_on: tuple[str, ...]


@dataclass
class WorkGraph:
    items: dict[str, WorkItem] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)  # stable declaration order
    warnings: list[str] = field(default_factory=list)

    def __iter__(self):
        for wid in self.order:
            yield self.items[wid]


def _children_by_parent(state: ProjectState) -> dict[str, list]:
    children: dict[str, list] = {}
    for story in state.stories:
        if story.parent_id:
            children.setdefault(story.parent_id, []).append(story)
    return children


def _leaf_task_ids(
    sid: str,
    stories_by_id: dict[str, object],
    children_by_parent: dict[str, list],
    _seen: set[str] | None = None,
) -> list[str]:
    _seen = _seen if _seen is not None else set()
    if sid in _seen:
        return []
    _seen.add(sid)
    story = stories_by_id.get(sid)
    ids = [t.id for t in getattr(story, "tasks", [])] if story else []
    for child in children_by_parent.get(sid, ()):
        ids.extend(_leaf_task_ids(child.id, stories_by_id, children_by_parent, _seen))
    return ids


def dependency_targets(dep_id: str, owner: str, state: ProjectState) -> tuple[str, ...]:
    """Resolve one declared dependency to concrete work-item ids.

    Story dependencies expand to the story's leaf tasks, including tasks from
    nested Technical Stories. Unknown ids and self-dependencies resolve to empty.
    """
    if dep_id == owner:
        return ()
    stories_by_id = {s.id: s for s in state.stories}
    task_ids = {t.id for s in state.stories for t in s.tasks}
    if dep_id in task_ids:
        return (dep_id,)
    if dep_id not in stories_by_id:
        return ()
    children = _children_by_parent(state)
    targets = _leaf_task_ids(dep_id, stories_by_id, children) or [dep_id]
    return tuple(t for t in targets if t != owner)


def build_work_graph(state: ProjectState, *, break_cycles: bool = True) -> WorkGraph:
    """Build the work-item graph for ``state`` (all stories, every iteration).

    Unknown dependency ids are dropped and reported in ``graph.warnings`` rather
    than raising — a malformed agent plan must never crash the pipeline. With
    ``break_cycles`` (default) dependency cycles are defensively broken at
    ingestion (see :func:`_break_cycles`); pass ``False`` to obtain the RAW
    graph when the caller wants to *detect* a cycle and act on it (e.g. the
    split-snapshot rollback)."""
    primary = state.primary_stream_id
    stories_by_id = {s.id: s for s in state.stories}
    task_ids = {t.id for s in state.stories for t in s.tasks}
    # RFC technical-stories: a Technical Story extracted from a container points
    # back via ``parent_id``. Depending on that container therefore also means
    # depending on its child TS' tasks (recursively) — otherwise a dependent could
    # start before the work moved into the TS is done.
    children_by_parent = _children_by_parent(state)

    graph = WorkGraph()

    def resolve(dep_ids: list[str], *, owner: str, ctx: str) -> tuple[str, ...]:
        out: list[str] = []
        seen: set[str] = set()
        for dep in dep_ids:
            if dep == owner:  # ignore an item depending on itself
                continue
            if dep in task_ids:
                targets = [dep]
            elif dep in stories_by_id:
                # Depending on a decomposed US == depending on ALL its tasks AND
                # the tasks of any Technical Story extracted from it (recursive).
                targets = _leaf_task_ids(dep, stories_by_id, children_by_parent) or [dep]
            else:
                graph.warnings.append(f"{ctx} : dépendance inconnue « {dep} » ignorée")
                continue
            for t in targets:
                if t != owner and t not in seen:
                    seen.add(t)
                    out.append(t)
        return tuple(out)

    for story in state.stories:
        if story.tasks:
            for task in story.tasks:
                deps = resolve(
                    [*task.depends_on, *story.depends_on],
                    owner=task.id,
                    ctx=f"tâche {task.id}",
                )
                item = WorkItem(
                    id=task.id,
                    kind="task",
                    story_id=story.id,
                    stream=task.stream or primary,
                    title=task.title or task.id,
                    status=task.status,
                    depends_on=deps,
                )
                graph.items[item.id] = item
                graph.order.append(item.id)
        else:
            deps = resolve(story.depends_on, owner=story.id, ctx=f"US {story.id}")
            item = WorkItem(
                id=story.id,
                kind="story",
                story_id=story.id,
                stream=story.stream or primary,
                title=story.title or story.id,
                status=story.status,
                depends_on=deps,
            )
            graph.items[item.id] = item
            graph.order.append(item.id)

    if break_cycles:
        _break_cycles(graph)
    return graph


def _break_cycles(graph: WorkGraph) -> None:
    """Defensively break dependency cycles in the work graph.

    Same policy as ``scheduler.sanitize_dependencies`` at story level: a
    malformed agent plan — or a failure-split whose remapped deps loop across
    stories (e.g. ``TS-1-T4 → TS-1-T2-S1 → US-1-T3 → US-1-T1 → TS-1-T4``) —
    must never deadlock or mass-fail the build. Each detected cycle loses its
    closing back-edge (recorded in ``graph.warnings``); items then build in
    declaration order like any other."""
    from dataclasses import replace

    for _ in range(len(graph.items) + 1):
        cycle = detect_cycle(graph)
        if not cycle:
            return
        # ``cycle`` is [a, …, z, a]: the edge z → a closes the loop.
        src_id, dst_id = cycle[-2], cycle[-1]
        src = graph.items[src_id]
        graph.items[src_id] = replace(
            src, depends_on=tuple(d for d in src.depends_on if d != dst_id)
        )
        graph.warnings.append(
            f"cycle de dépendances cassé : arête {src_id} → {dst_id} supprimée"
            f" ({' → '.join(cycle)})"
        )


def detect_cycle(graph: WorkGraph) -> list[str] | None:
    """Return a dependency cycle (as a list of work-item ids) if one exists,
    else None. Three-colour DFS over ``depends_on`` edges."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[str, int] = {wid: WHITE for wid in graph.items}
    stack: list[str] = []

    def visit(wid: str) -> list[str] | None:
        colour[wid] = GREY
        stack.append(wid)
        for dep in graph.items[wid].depends_on:
            if dep not in graph.items:
                continue
            if colour[dep] == GREY:  # back edge -> cycle
                return stack[stack.index(dep):] + [dep]
            if colour[dep] == WHITE:
                found = visit(dep)
                if found:
                    return found
        colour[wid] = BLACK
        stack.pop()
        return None

    for wid in graph.order:
        if colour[wid] == WHITE:
            found = visit(wid)
            if found:
                return found
    return None


def cycle_nodes(graph: WorkGraph) -> set[str]:
    """Return the exact work-item ids in a detected dependency cycle."""
    cycle = detect_cycle(graph)
    if not cycle:
        return set()
    return set(cycle[:-1] if len(cycle) > 1 and cycle[0] == cycle[-1] else cycle)


def transitive_dependents(graph: WorkGraph, roots: set[str]) -> set[str]:
    """Return every item that depends, directly or indirectly, on ``roots``."""
    reverse: dict[str, list[str]] = {}
    for item in graph:
        for dep in item.depends_on:
            reverse.setdefault(dep, []).append(item.id)
    out: set[str] = set()
    stack = list(roots)
    while stack:
        root = stack.pop()
        for dependent in reverse.get(root, ()):
            if dependent in out or dependent in roots:
                continue
            out.add(dependent)
            stack.append(dependent)
    return out


def is_ready(
    item: WorkItem,
    by_id: dict[str, WorkItem],
    *,
    done_statuses: tuple[StoryStatus, ...] = _DONE,
) -> bool:
    """A work item is ready to be picked when it is still TODO and every known
    dependency is done. (Unknown deps were already dropped + warned.)"""
    if item.status != StoryStatus.TODO:
        return False
    return all(
        by_id[d].status in done_statuses
        for d in item.depends_on
        if d in by_id
    )


def blocked_by(
    item: WorkItem,
    by_id: dict[str, WorkItem],
    *,
    done_statuses: tuple[StoryStatus, ...] = _DONE,
) -> list[str]:
    """The unmet dependency ids holding this item back (for the UI / ST-14)."""
    return [
        d
        for d in item.depends_on
        if d in by_id and by_id[d].status not in done_statuses
    ]


def ready_items(
    state: ProjectState,
    *,
    done_statuses: tuple[StoryStatus, ...] = _DONE,
) -> list[WorkItem]:
    """The work items ready to start now, in stable declaration order."""
    graph = build_work_graph(state)
    return [
        graph.items[wid]
        for wid in graph.order
        if is_ready(graph.items[wid], graph.items, done_statuses=done_statuses)
    ]


def validate(state: ProjectState) -> list[str]:
    """Collect warnings about the work graph: dangling deps + a cycle, if any."""
    graph = build_work_graph(state)
    warnings = list(graph.warnings)
    cycle = detect_cycle(graph)
    if cycle:
        warnings.append("cycle de dépendances : " + " → ".join(cycle))
    return warnings
