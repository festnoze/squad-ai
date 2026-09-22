"""Wave 1 / P1-C: critical-path ordering of the ready work items.

``streams.fanout`` measures how much work each item blocks transitively and
``scheduler.rank_ready`` turns that into a pick order; ``fanout_bonus_attempts``
grants the extra dev try to the items sitting on the critical path. All three
are pure functions - no pipeline, no I/O.
"""

from dataclasses import dataclass

from autospec.models import Epic, ProjectState, StoryStatus, Task, UserStory
from autospec.orchestrator import scheduler
from autospec.orchestrator import streams as wg


def _state(stories: list[UserStory]) -> ProjectState:
    st = ProjectState(id="p", name="p", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.stories = stories
    return st


def _us(sid: str, *, depends_on=None, priority: int = 3, tasks=None) -> UserStory:
    return UserStory(
        id=sid, epic_id="EPIC-1", title=sid, status=StoryStatus.TODO,
        depends_on=depends_on or [], priority=priority, tasks=tasks or [],
    )


def _graph(stories: list[UserStory], *, break_cycles: bool = True) -> wg.WorkGraph:
    return wg.build_work_graph(_state(stories), break_cycles=break_cycles)


def _items(graph: wg.WorkGraph, ids: list[str]) -> list[wg.WorkItem]:
    return [graph.items[wid] for wid in ids]


@dataclass(frozen=True)
class _PricedItem:
    """A duck-typed work item that DOES carry a kanban priority (a WorkItem
    does not), to exercise the ``getattr`` branch of the sort key."""

    id: str
    priority: int


# ------------------------------------------------------------------ fanout


def test_fanout_linear_chain_counts_transitive_dependents():
    graph = _graph([
        _us("US-1"),
        _us("US-2", depends_on=["US-1"]),
        _us("US-3", depends_on=["US-2"]),
        _us("US-4", depends_on=["US-3"]),
    ])
    assert wg.fanout(graph) == {"US-1": 3, "US-2": 2, "US-3": 1, "US-4": 0}


def test_fanout_diamond_counts_each_item_once():
    graph = _graph([
        _us("US-1"),
        _us("US-2", depends_on=["US-1"]),
        _us("US-3", depends_on=["US-1"]),
        _us("US-4", depends_on=["US-2", "US-3"]),
    ])
    # US-4 is reachable from US-1 through two paths but counts once.
    assert wg.fanout(graph) == {"US-1": 3, "US-2": 1, "US-3": 1, "US-4": 0}


def test_fanout_expands_story_dependency_to_tasks():
    graph = _graph([
        _us("US-1", tasks=[
            Task(id="US-1-T1", story_id="US-1", title="t1"),
            Task(id="US-1-T2", story_id="US-1", title="t2", depends_on=["US-1-T1"]),
        ]),
        _us("US-2", depends_on=["US-1"]),
    ])
    counts = wg.fanout(graph)
    # US-2 depends on the WHOLE US-1, i.e. on both of its tasks.
    assert counts == {"US-1-T1": 2, "US-1-T2": 1, "US-2": 0}


def test_fanout_tolerates_a_cycle():
    graph = _graph(
        [_us("US-1", depends_on=["US-2"]), _us("US-2", depends_on=["US-1"])],
        break_cycles=False,
    )
    assert wg.detect_cycle(graph) is not None  # the raw graph really loops
    # Each item blocks the other, and never itself.
    assert wg.fanout(graph) == {"US-1": 1, "US-2": 1}


def test_fanout_of_an_empty_graph_is_empty():
    assert wg.fanout(_graph([])) == {}


# ------------------------------------------------------------------ rank_ready


def test_rank_ready_linear_chain_puts_the_root_first():
    graph = _graph([
        _us("US-1"),
        _us("US-2", depends_on=["US-1"]),
        _us("US-3", depends_on=["US-2"]),
        _us("US-4", depends_on=["US-3"]),
    ])
    # Fed in the WORST possible order: the ranking must still hoist the root.
    ranked = scheduler.rank_ready(_items(graph, ["US-4", "US-3", "US-2", "US-1"]), graph)
    assert [i.id for i in ranked] == ["US-1", "US-2", "US-3", "US-4"]


def test_rank_ready_diamond_hoists_the_shared_root():
    graph = _graph([
        _us("US-1"),
        _us("US-2", depends_on=["US-1"]),
        _us("US-3", depends_on=["US-1"]),
        _us("US-4", depends_on=["US-2", "US-3"]),
    ])
    ranked = scheduler.rank_ready(_items(graph, ["US-4", "US-2", "US-3", "US-1"]), graph)
    # US-1 (fan-out 3) first, then the fan-out-1 pair in topological order,
    # then the leaf.
    assert [i.id for i in ranked] == ["US-1", "US-2", "US-3", "US-4"]


def test_rank_ready_breaks_fanout_ties_with_priority_then_topological_order():
    graph = _graph([
        _us("US-1"),
        _us("US-2"),
        _us("US-3"),
        _us("US-4"),
    ])
    # All four are independent leaves: fan-out 0 everywhere.
    assert set(wg.fanout(graph).values()) == {0}
    ranked = scheduler.rank_ready(
        _items(graph, ["US-1", "US-2", "US-3", "US-4"]),
        graph,
        priorities={"US-1": 3, "US-2": 1, "US-3": 2, "US-4": 1},
    )
    # Ascending priority, declaration order breaking the 1/1 tie.
    assert [i.id for i in ranked] == ["US-2", "US-4", "US-3", "US-1"]


def test_rank_ready_priority_never_beats_fanout():
    graph = _graph([_us("US-1"), _us("US-2", depends_on=["US-1"])])
    ranked = scheduler.rank_ready(
        _items(graph, ["US-1", "US-2"]),
        graph,
        priorities={"US-1": 5, "US-2": 1},
    )
    # US-2 is the most urgent on paper, but US-1 blocks it: critical path wins.
    assert [i.id for i in ranked] == ["US-1", "US-2"]


def test_rank_ready_reads_priority_off_the_item_via_getattr():
    graph = _graph([_us("US-1"), _us("US-2"), _us("US-3")])
    ranked = scheduler.rank_ready(
        [_PricedItem("US-1", 4), _PricedItem("US-2", 2), _PricedItem("US-3", 2)],
        graph,
    )
    assert [i.id for i in ranked] == ["US-2", "US-3", "US-1"]


def test_rank_ready_sorts_a_priority_less_item_after_a_priced_one():
    graph = _graph([_us("US-1"), _us("US-2")])
    # US-1 has no priority attribute at all, US-2 has the worst one: the
    # declared priority still wins over the unknown.
    ranked = scheduler.rank_ready(
        [graph.items["US-1"], _PricedItem("US-2", 5)],
        graph,
    )
    assert [i.id for i in ranked] == ["US-2", "US-1"]


def test_rank_ready_falls_back_to_topological_order_without_any_signal():
    graph = _graph([_us("US-1"), _us("US-2"), _us("US-3")])
    ranked = scheduler.rank_ready(_items(graph, ["US-3", "US-1", "US-2"]), graph)
    # No fan-out, no priority: the legacy declaration order is preserved.
    assert [i.id for i in ranked] == ["US-1", "US-2", "US-3"]


def test_rank_ready_orders_without_filtering():
    graph = _graph([
        _us("US-1"),
        _us("US-2", depends_on=["US-1"]),
        _us("US-3"),
    ])
    given = _items(graph, ["US-2", "US-3", "US-1"])
    ranked = scheduler.rank_ready(given, graph)
    # Readiness is the caller's job: every item comes back, exactly once.
    assert sorted(i.id for i in ranked) == ["US-1", "US-2", "US-3"]
    assert len(ranked) == len(given)


def test_rank_ready_is_deterministic():
    graph = _graph([
        _us("US-1"),
        _us("US-2", depends_on=["US-1"]),
        _us("US-3", depends_on=["US-1"]),
    ])
    items = _items(graph, ["US-3", "US-2", "US-1"])
    first = [i.id for i in scheduler.rank_ready(items, graph)]
    assert first == [i.id for i in scheduler.rank_ready(items, graph)]
    assert first == [i.id for i in scheduler.rank_ready(list(reversed(items)), graph)]


def test_rank_ready_reuses_precomputed_fanout_counts():
    graph = _graph([_us("US-1"), _us("US-2"), _us("US-3")])
    ranked = scheduler.rank_ready(
        _items(graph, ["US-1", "US-2", "US-3"]),
        graph,
        fanout_counts={"US-3": 7, "US-2": 2},
    )
    # The caller's map is authoritative; a missing id counts as 0.
    assert [i.id for i in ranked] == ["US-3", "US-2", "US-1"]


def test_rank_ready_puts_unknown_items_last_in_their_input_order():
    graph = _graph([_us("US-1")])
    ranked = scheduler.rank_ready(
        [_PricedItem("GHOST-2", 1), _PricedItem("US-1", 1), _PricedItem("GHOST-1", 1)],
        graph,
    )
    # Items absent from the graph have no topological position: they keep
    # their relative input order, behind every known item.
    assert [i.id for i in ranked] == ["US-1", "GHOST-2", "GHOST-1"]


def test_rank_ready_tolerates_a_cycle():
    graph = _graph(
        [
            _us("US-1", depends_on=["US-2"]),
            _us("US-2", depends_on=["US-1"]),
            _us("US-3"),
        ],
        break_cycles=False,
    )
    ranked = scheduler.rank_ready(_items(graph, ["US-3", "US-2", "US-1"]), graph)
    # The two looping items share a fan-out of 1 and go before the free leaf;
    # the tie falls back to the topological position. Nothing hangs.
    assert [i.id for i in ranked] == ["US-1", "US-2", "US-3"]


def test_rank_ready_of_nothing_is_nothing():
    assert scheduler.rank_ready([], _graph([_us("US-1")])) == []


# ------------------------------------------------------------ fanout bonus


def test_fanout_bonus_attempts_grants_one_try_at_the_threshold():
    assert scheduler.fanout_bonus_attempts(5, 5) == 1
    assert scheduler.fanout_bonus_attempts(20, 5) == 1


def test_fanout_bonus_attempts_below_the_threshold_is_zero():
    assert scheduler.fanout_bonus_attempts(4, 5) == 0
    assert scheduler.fanout_bonus_attempts(0, 5) == 0


def test_fanout_bonus_attempts_threshold_zero_never_grants_anything():
    # Threshold 0 (or below) = feature off, the retro-compatible default.
    for value in (0, 1, 5, 999):
        assert scheduler.fanout_bonus_attempts(value, 0) == 0
        assert scheduler.fanout_bonus_attempts(value, -1) == 0
