"""Lot 1 (ST-1/ST-2/ST-3): stream + task model and the work-item graph."""

from autospec.models import (
    BackendLanguage,
    Epic,
    ProjectState,
    Stream,
    StoryStatus,
    StreamKind,
    Task,
    UserStory,
    backend_stream_for,
)
from autospec.orchestrator import streams as wg


def _state(stories: list[UserStory], streams: list[Stream] | None = None) -> ProjectState:
    st = ProjectState(id="p", name="p", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.stories = stories
    if streams is not None:
        st.streams = streams
    return st


def _us(sid: str, *, status=StoryStatus.TODO, depends_on=None, stream="", tasks=None) -> UserStory:
    return UserStory(
        id=sid, epic_id="EPIC-1", title=sid, status=status,
        depends_on=depends_on or [], stream=stream, tasks=tasks or [],
    )


def _task(tid: str, story_id: str, *, stream="", status=StoryStatus.TODO, depends_on=None) -> Task:
    return Task(id=tid, story_id=story_id, stream=stream, title=tid,
                status=status, depends_on=depends_on or [])


# ------------------------------------------------------------------ ST-1 streams

def test_backend_stream_for_carries_language_and_is_primary():
    s = backend_stream_for(BackendLanguage.GO)
    assert s.id == "backend" and s.kind == StreamKind.BACKEND and s.primary
    assert s.language == "go"


def test_primary_stream_id_defaults_to_backend_when_none_declared():
    assert _state([]).primary_stream_id == "backend"


def test_primary_stream_id_picks_declared_primary_then_backend_kind():
    front = Stream(id="frontend", kind=StreamKind.FRONTEND)
    back = Stream(id="api", kind=StreamKind.BACKEND, primary=True)
    assert _state([], streams=[front, back]).primary_stream_id == "api"
    # No explicit primary -> the backend-kind stream wins.
    back2 = Stream(id="srv", kind=StreamKind.BACKEND)
    assert _state([], streams=[front, back2]).primary_stream_id == "srv"


def test_stream_resolution():
    st = _state([], streams=[
        Stream(id="backend", kind=StreamKind.BACKEND, primary=True),
        Stream(id="frontend", kind=StreamKind.FRONTEND),
    ])
    assert st.stream("").id == "backend"                  # "" -> primary
    assert st.stream("frontend").kind == StreamKind.FRONTEND
    assert st.stream("ghost").kind == StreamKind.BACKEND  # unknown -> safe fallback


def test_effective_streams_synthesizes_a_backend_when_none_declared():
    st = ProjectState(id="p", name="p", goal="g", backend_language=BackendLanguage.RUST)
    streams = st.effective_streams()
    assert len(streams) == 1 and streams[0].id == "backend" and streams[0].language == "rust"


# ----------------------------------------------------------- ST-2 task / US status

def test_effective_status_without_tasks_is_the_stored_status():
    assert _us("US-1", status=StoryStatus.RED).effective_status() == StoryStatus.RED


def test_effective_status_derived_from_tasks():
    done = [_task("T1", "US-1", status=StoryStatus.DONE), _task("T2", "US-1", status=StoryStatus.DONE)]
    assert _us("US-1", tasks=done).effective_status() == StoryStatus.DONE

    mixed = [_task("T1", "US-1", status=StoryStatus.DONE), _task("T2", "US-1", status=StoryStatus.IN_PROGRESS)]
    assert _us("US-1", tasks=mixed).effective_status() == StoryStatus.IN_PROGRESS

    failed = [_task("T1", "US-1", status=StoryStatus.DONE), _task("T2", "US-1", status=StoryStatus.FAILED)]
    assert _us("US-1", tasks=failed).effective_status() == StoryStatus.FAILED

    fresh = [_task("T1", "US-1"), _task("T2", "US-1")]
    assert _us("US-1", tasks=fresh).effective_status() == StoryStatus.TODO


def test_project_task_lookup():
    st = _state([_us("US-1", tasks=[_task("T1", "US-1")])])
    assert st.task("T1").id == "T1"
    assert [t.id for t in st.all_tasks()] == ["T1"]


# ------------------------------------------------------------- ST-3 work graph

def test_taskless_stories_are_work_items_with_us_dependencies():
    st = _state([_us("US-1", status=StoryStatus.DONE), _us("US-2", depends_on=["US-1"])])
    graph = wg.build_work_graph(st)
    assert set(graph.items) == {"US-1", "US-2"}
    assert graph.items["US-2"].depends_on == ("US-1",)
    assert graph.items["US-2"].kind == "story"
    # US-1 done -> US-2 becomes the only ready item.
    assert [i.id for i in wg.ready_items(st)] == ["US-2"]


def test_us_dependency_on_decomposed_story_expands_to_all_its_tasks():
    us_a = _us("US-A", tasks=[_task("A1", "US-A"), _task("A2", "US-A")])
    us_b = _us("US-B", depends_on=["US-A"])
    graph = wg.build_work_graph(_state([us_a, us_b]))
    assert set(graph.items["US-B"].depends_on) == {"A1", "A2"}


def test_cross_stream_task_deps_and_inherited_us_deps():
    # US-1 done (taskless). US-2 has a back task and a front task that depends on
    # it; both inherit US-2's US-level dep on US-1.
    us1 = _us("US-1", status=StoryStatus.DONE)
    back = _task("T-back", "US-2", stream="backend")
    front = _task("T-front", "US-2", stream="frontend", depends_on=["T-back"])
    us2 = _us("US-2", depends_on=["US-1"], tasks=[back, front])
    st = _state([us1, us2], streams=[
        Stream(id="backend", kind=StreamKind.BACKEND, primary=True),
        Stream(id="frontend", kind=StreamKind.FRONTEND),
    ])
    graph = wg.build_work_graph(st)
    assert set(graph.items["T-back"].depends_on) == {"US-1"}          # inherited
    assert set(graph.items["T-front"].depends_on) == {"T-back", "US-1"}
    assert graph.items["T-front"].stream == "frontend"
    # Only the back task is ready (front waits on it); US-1 is already done.
    assert [i.id for i in wg.ready_items(st)] == ["T-back"]
    # Once the back task is done, the front task becomes ready.
    back.status = StoryStatus.DONE
    assert [i.id for i in wg.ready_items(st)] == ["T-front"]


def test_blocked_by_lists_unmet_dependencies():
    st = _state([_us("US-1"), _us("US-2", depends_on=["US-1"])])
    graph = wg.build_work_graph(st)
    assert wg.blocked_by(graph.items["US-2"], graph.items) == ["US-1"]


def test_unknown_dependency_is_dropped_with_a_warning():
    st = _state([_us("US-1", depends_on=["ghost"])])
    graph = wg.build_work_graph(st)
    assert graph.items["US-1"].depends_on == ()
    assert any("ghost" in w for w in graph.warnings)
    assert [i.id for i in wg.ready_items(st)] == ["US-1"]  # ready despite the dangling dep


def test_cycle_detection():
    t1 = _task("T1", "US-1", depends_on=["T2"])
    t2 = _task("T2", "US-1", depends_on=["T1"])
    st = _state([_us("US-1", tasks=[t1, t2])])
    cycle = wg.detect_cycle(wg.build_work_graph(st))
    assert cycle is not None and set(cycle) >= {"T1", "T2"}
    assert any("cycle" in w for w in wg.validate(st))


def test_no_cycle_returns_none():
    st = _state([_us("US-1", status=StoryStatus.DONE), _us("US-2", depends_on=["US-1"])])
    assert wg.detect_cycle(wg.build_work_graph(st)) is None
    assert wg.validate(st) == []
