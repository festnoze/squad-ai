import pytest

from autospec.core import machine
from autospec.core.models import AcceptanceCriterion, Phase, ProjectState, Story, StoryStatus


def _story(sid="US-1", status=StoryStatus.TODO, attempts=0):
    return Story(id=sid, epic_id="EPIC-1", title="t", status=status, attempts=attempts,
                 criteria=[AcceptanceCriterion(id=f"{sid}.AC-1", text="c")])


def _state(**kwargs):
    return ProjectState(id="p", name="P", package="p", **kwargs)


def test_happy_path_phases_are_legal():
    state = _state()
    for phase in (Phase.BRIEF, Phase.PLAN, Phase.BUILD, Phase.DELIVER, Phase.DONE):
        machine.set_phase(state, phase)
    assert state.phase == Phase.DONE


def test_skipping_a_phase_is_illegal():
    state = _state()
    with pytest.raises(machine.IllegalTransition, match="created -> build"):
        machine.set_phase(state, Phase.BUILD)


def test_done_is_final():
    state = _state(phase=Phase.DONE)
    with pytest.raises(machine.IllegalTransition):
        machine.set_phase(state, Phase.BUILD)


@pytest.mark.parametrize("parked", [Phase.NEEDS_ATTENTION, Phase.STOPPED, Phase.ERROR])
def test_parked_project_resumes_into_any_working_phase(parked):
    for target in (Phase.BRIEF, Phase.PLAN, Phase.BUILD, Phase.DELIVER):
        state = _state(phase=parked)
        machine.set_phase(state, target)
        assert state.phase == target


def test_setting_the_same_phase_is_a_no_op():
    state = _state(phase=Phase.DONE)
    machine.set_phase(state, Phase.DONE)
    assert state.phase == Phase.DONE


def test_story_lifecycle():
    story = _story()
    machine.set_story_status(story, StoryStatus.IN_PROGRESS)
    machine.set_story_status(story, StoryStatus.DONE)
    with pytest.raises(machine.IllegalTransition, match="US-1: done -> todo"):
        machine.set_story_status(story, StoryStatus.TODO)


def test_story_cannot_finish_without_being_started():
    with pytest.raises(machine.IllegalTransition):
        machine.set_story_status(_story(), StoryStatus.DONE)


@pytest.mark.parametrize("state_kwargs, expected", [
    ({}, Phase.BRIEF),
    ({"brief": "b"}, Phase.PLAN),
    ({"brief": "b", "stories": [_story(status=StoryStatus.DONE), _story("US-2")]}, Phase.BUILD),
    ({"brief": "b", "stories": [_story(status=StoryStatus.DONE)]}, Phase.DELIVER),
])
def test_resume_phase_is_derived_from_content(state_kwargs, expected):
    assert machine.resume_phase(_state(**state_kwargs)) == expected


def test_prepare_resume_requeues_interrupted_and_failed_stories():
    interrupted = _story("US-1", StoryStatus.IN_PROGRESS, attempts=2)
    failed = _story("US-2", StoryStatus.FAILED, attempts=3)
    done = _story("US-3", StoryStatus.DONE, attempts=1)
    state = _state(brief="b", stories=[interrupted, failed, done], error="boom")

    machine.prepare_resume(state)

    assert [s.status for s in state.stories] == [StoryStatus.TODO, StoryStatus.TODO, StoryStatus.DONE]
    assert interrupted.attempts == 2, "an interruption is not a new chance"
    assert failed.attempts == 0, "resuming a failed story is a human decision to retry"
    assert done.attempts == 1
    assert state.error == ""
