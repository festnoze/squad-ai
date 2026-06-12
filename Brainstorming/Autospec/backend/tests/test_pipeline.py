import json

from autospec.agents.runner import FakeRunner
from autospec.models import ChatRole, PipelinePhase, ProjectState, StoryStatus
from autospec.orchestrator.pipeline import Pipeline

from .conftest import wait_until

PM_QUESTION = json.dumps({"type": "question", "message": "CLI ou web ?"})
PM_BRIEF = json.dumps({"type": "brief", "message": "Brief prêt.", "brief": "# Brief\nUne todo-list CLI."})
QA_PLAN = json.dumps(
    {
        "message": "Décomposition outside-in par couche.",
        "tests": [
            {"id": "UT-1", "layer": "facade", "description": "la façade appelle le service",
             "mocks": ["service"], "file_hint": "tests/unit/test_facade.py", "criteria": ["AC-1"]},
            {"id": "UT-2", "layer": "service", "description": "le service appelle le repository",
             "mocks": ["repository"], "file_hint": "tests/unit/test_service.py", "criteria": ["AC-1"]},
        ],
    }
)
DEV_GREEN = json.dumps({
    "status": "green",
    "summary": "Steps + implémentation, tout est vert.",
    "files": ["todo/core.py"],
    "test_results": [{"id": "UT-1", "status": "green"}, {"id": "UT-2", "status": "green"}],
})


def po_plan_reply(n_stories: int = 2, with_dep: bool = True) -> str:
    stories = []
    for i in range(1, n_stories + 1):
        stories.append(
            {
                "id": f"US-{i}",
                "title": f"Story {i}",
                "description": f"En tant qu'utilisateur, je veux la feature {i}.",
                "acceptance_criteria": [f"critère {i}"],
                "gherkin": f"Feature: F{i}\n  Scenario: S{i}\n    Given a\n    When b\n    Then c",
                "depends_on": ["US-1"] if (with_dep and i > 1) else [],
            }
        )
    return json.dumps({"epics": [{"id": "EPIC-1", "title": "Epic 1", "description": "", "stories": stories}]})


def make_pipeline(replies: list[str], auto_spec: bool = False) -> tuple[Pipeline, FakeRunner]:
    state = ProjectState(id="proj-test", name="todo", goal="Une todo-list", auto_spec=auto_spec)
    runner = FakeRunner(replies)
    return Pipeline(state, runner), runner


async def test_full_pipeline_with_interview(green_pytest):
    pipeline, runner = make_pipeline(
        [PM_QUESTION, PM_BRIEF, po_plan_reply(), QA_PLAN, DEV_GREEN, QA_PLAN, DEV_GREEN]
    )
    pipeline.start()

    # PM asks a question, the user answers, PM produces the brief.
    await wait_until(lambda: any(m.role == ChatRole.PM for m in pipeline.state.chat))
    assert pipeline.state.phase == PipelinePhase.SPEC
    await pipeline.asend_user_message("CLI")

    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert pipeline.state.brief.startswith("# Brief")
    assert len(pipeline.state.epics) == 1
    assert [s.status for s in pipeline.state.stories] == [StoryStatus.DONE, StoryStatus.DONE]

    # US-2 depends on US-1: its dev prompt must come after US-1's.
    dev_prompts = [c["prompt"] for c in runner.calls if "PROCESSUS OBLIGATOIRE" in c["prompt"]]
    assert "US-1" in dev_prompts[0] and "US-2" in dev_prompts[1]

    # QA decomposed the acceptance test outside-in BEFORE the dev worked:
    # the plan is stored on the story and injected into the dev prompt.
    us1 = pipeline.state.story("US-1")
    assert [t.id for t in us1.test_plan] == ["UT-1", "UT-2"]
    assert us1.test_plan[1].mocks == ["repository"]
    assert "UT-1" in dev_prompts[0] and "London school" in dev_prompts[0]
    assert any(m.role == ChatRole.QA for m in pipeline.state.chat)

    # Acceptance criteria are structured (AC-x) and their tests are linked + green.
    from autospec.models import TestState
    crit = us1.acceptance_criteria[0]
    assert crit.id == "AC-1"
    assert {t.id for t in us1.tests_for_criterion("AC-1")} == {"UT-1", "UT-2"}
    assert us1.criterion_state("AC-1") == TestState.GREEN
    assert all(t.status == TestState.GREEN for t in us1.test_plan)


async def test_feature_files_written(green_pytest, tmp_workspace):
    pipeline, _ = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN], auto_spec=True
    )
    pipeline.state.auto_spec = False  # single cycle
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    feature = tmp_workspace / "workspace" / "proj-test" / "features" / "us_1.feature"
    assert feature.exists()
    assert "Feature: F1" in feature.read_text(encoding="utf-8")


async def test_failed_story_blocks_dependents(monkeypatch, tmp_workspace):
    async def _red_pytest(self):
        return False, "1 failed"

    monkeypatch.setattr(Pipeline, "_arun_pytest", _red_pytest)
    # Dev replies green but verification stays red: 2 attempts for US-1
    # (QA only runs on the first attempt), then fail.
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(2), QA_PLAN, DEV_GREEN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    us1, us2 = pipeline.state.story("US-1"), pipeline.state.story("US-2")
    assert us1.status == StoryStatus.FAILED
    assert us1.attempts == 2
    assert us2.status == StoryStatus.FAILED
    assert "Dépendance" in us2.last_error


async def test_auto_spec_loops_until_stopped(green_pytest):
    analyst_reply = json.dumps(
        {
            "message": "Les tags apportent le plus de valeur pour un effort minimal.",
            "hypotheses": [
                {"id": "FH-1", "title": "Tags", "rationale": "demande implicite", "value": 5, "complexity": 2},
                {"id": "FH-2", "title": "Export CSV", "rationale": "utile plus tard", "value": 3, "complexity": 3},
            ],
            "selected": "FH-1",
        }
    )
    pm_next = json.dumps({"type": "brief", "message": "Prochaine feature : tags.", "brief": "# Brief v2\nTags."})

    class StoppingRunner(FakeRunner):
        """Requests a pipeline stop while serving its last queued reply."""

        pipeline: Pipeline

        async def arun(self, *args, **kwargs):
            if len(self.replies) == 1:
                await self.pipeline.astop()
            return await super().arun(*args, **kwargs)

    state = ProjectState(id="proj-test", name="todo", goal="Une todo-list", auto_spec=True)
    runner = StoppingRunner(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN, analyst_reply, pm_next]
    )
    pipeline = Pipeline(state, runner)
    runner.pipeline = pipeline
    pipeline.start()

    # Auto-spec: no question asked, brief produced directly, then the analyst
    # prioritizes the backlog and picks the next feature, the PM writes its
    # brief, and the user stops the loop there.
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.STOPPED)
    assert pipeline.state.iteration == 2
    assert pipeline.state.brief.startswith("# Brief v2")
    assert pipeline.state.story("US-1").status == StoryStatus.DONE

    # The analyst's prioritized backlog is kept on the project state.
    assert [h.id for h in pipeline.state.backlog] == ["FH-1", "FH-2"]
    selected = pipeline.state.backlog[0]
    assert selected.status.value == "selected"
    assert selected.value == 5 and selected.complexity == 2
    assert any(m.role == ChatRole.ANALYST for m in pipeline.state.chat)


async def test_kanban_priority_orders_independent_stories(green_pytest):
    po_reply = json.dumps(
        {"epics": [{"id": "EPIC-1", "title": "Epic 1", "stories": [
            {"id": "US-1", "title": "Basse prio", "description": "d", "acceptance_criteria": ["c"],
             "gherkin": "Feature: A\n  Scenario: s\n    Given a\n    When b\n    Then c",
             "depends_on": [], "priority": 4},
            {"id": "US-2", "title": "Haute prio", "description": "d", "acceptance_criteria": ["c"],
             "gherkin": "Feature: B\n  Scenario: s\n    Given a\n    When b\n    Then c",
             "depends_on": [], "priority": 1},
        ]}]}
    )
    pipeline, runner = make_pipeline([PM_BRIEF, po_reply, QA_PLAN, DEV_GREEN, QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert pipeline.state.story("US-2").priority == 1

    # Both stories are independent: the high-priority one is assigned first.
    dev_prompts = [c["prompt"] for c in runner.calls if "PROCESSUS OBLIGATOIRE" in c["prompt"]]
    assert "US-2" in dev_prompts[0] and "US-1" in dev_prompts[1]


async def test_qa_failure_is_non_fatal(green_pytest):
    # QA replies garbage: the dev still proceeds from the Gherkin alone.
    pipeline, runner = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), "pas un json", DEV_GREEN]
    )
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    us1 = pipeline.state.story("US-1")
    assert us1.status == StoryStatus.DONE
    assert us1.test_plan == []
    dev_prompt = runner.calls[-1]["prompt"]
    assert "PROCESSUS OBLIGATOIRE" in dev_prompt and "London school" not in dev_prompt


async def test_feedback_outside_spec_is_stored(green_pytest):
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    await pipeline.asend_user_message("Le bouton est trop petit")
    assert pipeline.state.feedback == ["Le bouton est trop petit"]
