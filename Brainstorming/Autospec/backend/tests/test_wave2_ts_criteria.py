"""FACTORY_IMPROVEMENTS: a Technical Story extracted from a failed task used to
be born with NO acceptance criterion and an EMPTY Gherkin, so the Definition of
Done raised ``no_acceptance_criteria`` on every delivery that split a task.

With ``TS_ACCEPTANCE_CRITERIA`` on, the TS inherits the failed task's criteria
(or gets ONE synthetic criterion derived from its technical contract) plus a
technical Gherkin restating that contract, so the DoD sees a criterion AND the
evidence it demands for one - giving criteria alone would only trade
``no_acceptance_criteria`` for ``no_acceptance_evidence`` (a BLOCKER under
``DOD_STRICT_CRITERIA``).
"""

import pytest

from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import (
    AcceptanceCriterion,
    Epic,
    ProjectState,
    Stream,
    StoryStatus,
    StreamKind,
    Task,
    UserStory,
)
from autospec.orchestrator.delivery_gate import evaluate_definition_of_done
from autospec.orchestrator.pipeline import Pipeline

RAW_SUBTASKS = [
    {"id": "a", "title": "A", "file_globs": ["a.py"]},
    {"id": "b", "title": "B", "file_globs": ["b.py"], "depends_on": ["a"]},
]


@pytest.fixture
def streams_on(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)
    monkeypatch.setattr(settings, "split_on_failure_enabled", True)
    monkeypatch.setattr(settings, "split_max_depth", 1)


def _state(failed: Task, project_id="ts-criteria") -> ProjectState:
    st = ProjectState(id=project_id, name="app", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [
        Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True),
    ]
    st.stories = [
        UserStory(
            id="US-1",
            epic_id="EPIC-1",
            title="US-1",
            acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="le parent est visible")],
            gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
            tasks=[
                failed,
                Task(id="T-2", story_id="US-1", stream="backend", title="T-2"),
            ],
        )
    ]
    return st


def _split(state: ProjectState) -> UserStory:
    pipeline = Pipeline(state, ScriptedRunner())
    assert pipeline._split_task("T-1", RAW_SUBTASKS) is True
    return next(s for s in state.stories if s.technical)


def _dod_issues_for(state: ProjectState, item_id: str) -> list[str]:
    """Every DoD issue code raised ABOUT one item (blockers and warnings)."""
    for story in state.stories:
        story.status = StoryStatus.DONE
        for task in story.tasks:
            task.status = StoryStatus.DONE
    result = evaluate_definition_of_done(state, strict_criteria=True)
    return [i.code for i in result.issues if i.item_id == item_id]


# ------------------------------------------------------- the criteria themselves

def test_a_technical_story_always_has_at_least_one_criterion(streams_on):
    """The failed task has no criterion of its own: the TS derives one from its
    technical contract rather than being born criterion-less."""
    failed = Task(
        id="T-1", story_id="US-1", stream="backend", title="Câbler le repository",
        description="Le repository expose get/save\net persiste en SQLite.",
    )
    state = _state(failed)
    ts = _split(state)

    assert len(ts.acceptance_criteria) >= 1
    criterion = ts.acceptance_criteria[0]
    assert criterion.id == f"{ts.id}.AC-1"
    assert criterion.kind == "nonfunctional"
    assert "Contrat technique" in criterion.text
    # The contract is folded onto ONE line: a multi-line description must not
    # break the Gherkin the criterion is restated in.
    assert "\n" not in criterion.text
    assert "persiste en SQLite" in criterion.text
    assert ts.contract == failed.description        # the contract itself is untouched


def test_the_failed_task_criteria_are_inherited_and_copied(streams_on):
    """When the task DOES carry criteria they are the TS's, deep-copied so
    editing the TS can never mutate the task that produced it."""
    failed = Task(
        id="T-1", story_id="US-1", stream="backend", title="T-1",
        description="contrat",
        acceptance_criteria=[
            AcceptanceCriterion(id="AC-7", text="la facture est calculée", kind="happy"),
            AcceptanceCriterion(id="AC-8", text="un montant négatif est refusé", kind="error"),
        ],
    )
    state = _state(failed)
    ts = _split(state)

    assert [c.id for c in ts.acceptance_criteria] == ["AC-7", "AC-8"]
    assert [c.kind for c in ts.acceptance_criteria] == ["happy", "error"]
    ts.acceptance_criteria[0].text = "MUTÉ"
    assert failed.acceptance_criteria[0].text == "la facture est calculée"
    # Every inherited criterion is restated in the technical Gherkin.
    assert "la facture est calculée" in ts.gherkin
    assert "un montant négatif est refusé" in ts.gherkin


def test_the_technical_gherkin_states_the_contract(streams_on):
    failed = Task(
        id="T-1", story_id="US-1", stream="backend", title="T-1",
        description="le service publie l'événement",
    )
    state = _state(failed)
    ts = _split(state)

    assert ts.gherkin.startswith(f"Feature: {ts.id}")
    assert "Scenario:" in ts.gherkin
    assert "T-1" in ts.gherkin                      # the origin of the extraction
    assert "le service publie l'événement" in ts.gherkin


# ------------------------------------------------------------ the DoD consequence

def test_the_dod_no_longer_flags_the_technical_story(streams_on):
    failed = Task(
        id="T-1", story_id="US-1", stream="backend", title="T-1", description="contrat",
    )
    state = _state(failed)
    ts = _split(state)

    codes = _dod_issues_for(state, ts.id)
    assert "no_acceptance_criteria" not in codes
    # And the warning was not simply traded for the evidence one (which is a
    # BLOCKER in strict mode): the technical Gherkin is that evidence.
    assert "no_acceptance_evidence" not in codes
    assert codes == []


def test_the_flag_off_reproduces_the_historic_warning(streams_on, monkeypatch):
    """OFF = the legacy TS (no criterion, empty Gherkin) - which is exactly the
    delivery warning this change removes."""
    monkeypatch.setattr(settings, "ts_acceptance_criteria", False)
    failed = Task(
        id="T-1", story_id="US-1", stream="backend", title="T-1", description="contrat",
    )
    state = _state(failed)
    ts = _split(state)

    assert ts.acceptance_criteria == []
    assert ts.gherkin == ""
    assert "no_acceptance_criteria" in _dod_issues_for(state, ts.id)


def test_a_deeper_split_gives_each_technical_story_its_own_criterion_id(streams_on):
    """Two TS born in the same project must not share a criterion id (the
    synthetic id is namespaced by the TS id, which is unique project-wide)."""
    failed = Task(
        id="T-1", story_id="US-1", stream="backend", title="T-1", description="contrat un",
    )
    state = _state(failed)
    first = _split(state)

    # A second failure, in the container that kept T-2, extracts another TS.
    state.stories[0].tasks.append(
        Task(id="T-3", story_id="US-1", stream="backend", title="T-3", description="contrat deux")
    )
    pipeline = Pipeline(state, ScriptedRunner())
    assert pipeline._split_task("T-3", RAW_SUBTASKS) is True
    second = next(s for s in state.stories if s.technical and s.id != first.id)

    assert first.acceptance_criteria[0].id != second.acceptance_criteria[0].id
    assert second.acceptance_criteria[0].id == f"{second.id}.AC-1"
