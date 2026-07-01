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


def build_work_graph(state: ProjectState) -> WorkGraph:
    """Build the work-item graph for ``state`` (all stories, every iteration).

    Unknown dependency ids are dropped and reported in ``graph.warnings`` rather
    than raising — a malformed agent plan must never crash the pipeline."""
    primary = state.primary_stream_id
    stories_by_id = {s.id: s for s in state.stories}
    task_ids = {t.id for s in state.stories for t in s.tasks}
    # RFC technical-stories: a Technical Story extracted from a container points
    # back via ``parent_id``. Depending on that container therefore also means
    # depending on its child TS' tasks (recursively) — otherwise a dependent could
    # start before the work moved into the TS is done.
    children_by_parent: dict[str, list] = {}
    for s in state.stories:
        if s.parent_id:
            children_by_parent.setdefault(s.parent_id, []).append(s)

    def leaf_task_ids(sid: str, _seen: set[str] | None = None) -> list[str]:
        _seen = _seen if _seen is not None else set()
        if sid in _seen:
            return []
        _seen.add(sid)
        story = stories_by_id.get(sid)
        ids = [t.id for t in story.tasks] if story else []
        for child in children_by_parent.get(sid, ()):
            ids.extend(leaf_task_ids(child.id, _seen))
        return ids

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
                targets = leaf_task_ids(dep) or [dep]
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

    return graph


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
