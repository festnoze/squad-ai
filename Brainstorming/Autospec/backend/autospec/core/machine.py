"""Legal transitions of a project and of its stories. Nothing moves without going through here."""

from __future__ import annotations

from .models import Phase, ProjectState, Story, StoryStatus

_RESUMABLE = {Phase.BRIEF, Phase.PLAN, Phase.BUILD, Phase.DELIVER}

PHASE_TRANSITIONS: dict[Phase, frozenset[Phase]] = {
    Phase.CREATED: frozenset({Phase.BRIEF, Phase.PLAN, Phase.NEEDS_ATTENTION, Phase.STOPPED, Phase.ERROR}),
    Phase.BRIEF: frozenset({Phase.PLAN, Phase.NEEDS_ATTENTION, Phase.STOPPED, Phase.ERROR}),
    Phase.PLAN: frozenset({Phase.BUILD, Phase.NEEDS_ATTENTION, Phase.STOPPED, Phase.ERROR}),
    Phase.BUILD: frozenset({Phase.DELIVER, Phase.NEEDS_ATTENTION, Phase.STOPPED, Phase.ERROR}),
    Phase.DELIVER: frozenset({Phase.DONE, Phase.NEEDS_ATTENTION, Phase.STOPPED, Phase.ERROR}),
    # A human (or a restart) resumes an interrupted project where it stopped.
    Phase.NEEDS_ATTENTION: frozenset(_RESUMABLE | {Phase.STOPPED}),
    Phase.STOPPED: frozenset(_RESUMABLE),
    Phase.ERROR: frozenset(_RESUMABLE | {Phase.STOPPED}),
    Phase.DONE: frozenset(),
}

STORY_TRANSITIONS: dict[StoryStatus, frozenset[StoryStatus]] = {
    StoryStatus.TODO: frozenset({StoryStatus.IN_PROGRESS}),
    StoryStatus.IN_PROGRESS: frozenset({StoryStatus.DONE, StoryStatus.FAILED, StoryStatus.TODO}),
    StoryStatus.FAILED: frozenset({StoryStatus.TODO}),
    StoryStatus.DONE: frozenset(),
}


class IllegalTransition(RuntimeError):
    pass


def set_phase(state: ProjectState, target: Phase) -> None:
    if target == state.phase:
        return
    if target not in PHASE_TRANSITIONS[state.phase]:
        raise IllegalTransition(f"project {state.id}: {state.phase.value} -> {target.value}")
    state.phase = target


def set_story_status(story: Story, target: StoryStatus) -> None:
    if target == story.status:
        return
    if target not in STORY_TRANSITIONS[story.status]:
        raise IllegalTransition(f"story {story.id}: {story.status.value} -> {target.value}")
    story.status = target


def resume_phase(state: ProjectState) -> Phase:
    """The phase to (re)start from, derived from what the state already holds."""
    if not state.brief.strip():
        return Phase.BRIEF
    if not state.stories:
        return Phase.PLAN
    if any(story.status != StoryStatus.DONE for story in state.stories):
        return Phase.BUILD
    return Phase.DELIVER


def prepare_resume(state: ProjectState) -> None:
    """Make an interrupted or parked project runnable again.

    A story caught IN_PROGRESS by a crash goes back to TODO (its committed
    acceptance tests and attempts are kept). A FAILED story gets a fresh
    attempt budget: resuming is the human's decision to try again.
    """
    for story in state.stories:
        if story.status == StoryStatus.IN_PROGRESS:
            set_story_status(story, StoryStatus.TODO)
        elif story.status == StoryStatus.FAILED:
            set_story_status(story, StoryStatus.TODO)
            story.attempts = 0
    state.error = ""
