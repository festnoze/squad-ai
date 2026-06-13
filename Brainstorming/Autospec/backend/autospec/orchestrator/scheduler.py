"""Dependency-aware story scheduling (pure functions, unit-tested)."""

from __future__ import annotations

from ..models import StoryStatus, UserStory


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


def pending_stories(stories: list[UserStory]) -> list[UserStory]:
    active = {StoryStatus.TODO, StoryStatus.IN_PROGRESS, StoryStatus.RED, StoryStatus.GREEN}
    return [s for s in stories if s.status in active]
