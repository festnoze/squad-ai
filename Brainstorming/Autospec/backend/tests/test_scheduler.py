from autospec.models import StoryStatus, UserStory
from autospec.orchestrator import scheduler


def story(
    sid: str,
    deps: list[str] | None = None,
    status=StoryStatus.TODO,
    priority: int = 3,
) -> UserStory:
    return UserStory(
        id=sid, epic_id="EPIC-1", title=sid, depends_on=deps or [],
        status=status, priority=priority,
    )


def test_ready_stories_respects_dependencies():
    stories = [story("US-1"), story("US-2", ["US-1"]), story("US-3")]
    ready = scheduler.ready_stories(stories)
    assert [s.id for s in ready] == ["US-1", "US-3"]


def test_ready_stories_unlocks_after_done():
    stories = [story("US-1", status=StoryStatus.DONE), story("US-2", ["US-1"])]
    assert [s.id for s in scheduler.ready_stories(stories)] == ["US-2"]


def test_ready_stories_kanban_priority_order():
    stories = [
        story("US-1", priority=3),
        story("US-2", priority=1),
        story("US-3", priority=2),
        story("US-4", priority=1),
    ]
    assert [s.id for s in scheduler.ready_stories(stories)] == ["US-2", "US-4", "US-3", "US-1"]


def test_validate_detects_unknown_dependency():
    problems = scheduler.validate_dependencies([story("US-1", ["US-99"])])
    assert any("US-99" in p for p in problems)


def test_validate_detects_cycle():
    problems = scheduler.validate_dependencies(
        [story("US-1", ["US-2"]), story("US-2", ["US-1"])]
    )
    assert any("cycle" in p for p in problems)


def test_sanitize_drops_unknown_and_breaks_cycles():
    stories = [story("US-1", ["US-2", "US-99", "US-1"]), story("US-2", ["US-1"])]
    scheduler.sanitize_dependencies(stories)
    assert scheduler.validate_dependencies(stories) == []
    assert scheduler.ready_stories(stories)  # nothing deadlocked


def test_pending_stories_excludes_done_and_failed():
    stories = [
        story("US-1", status=StoryStatus.DONE),
        story("US-2", status=StoryStatus.FAILED),
        story("US-3", status=StoryStatus.RED),
        story("US-4"),
    ]
    assert [s.id for s in scheduler.pending_stories(stories)] == ["US-3", "US-4"]
