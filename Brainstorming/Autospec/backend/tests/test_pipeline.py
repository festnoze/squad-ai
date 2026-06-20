import asyncio
import json

import pytest

from autospec.agents.runner import FakeRunner
from autospec.models import (
    ChatRole,
    PipelinePhase,
    PlannedTest,
    ProjectState,
    StoryStatus,
    TestState,
)
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


async def test_budget_stops_auto_spec(green_pytest):
    # A cost-reporting runner: each agent call costs $0.01. With a tiny budget,
    # the auto-spec loop must stop cleanly once usage reaches it.
    class _CostRunner(FakeRunner):
        async def arun(self, *a, **kw):
            res = await super().arun(*a, **kw)
            res.cost_usd = 0.05
            return res

    analyst_reply = json.dumps(
        {
            "message": "Suite.",
            "hypotheses": [{"id": "FH-1", "title": "X", "rationale": "r", "value": 4, "complexity": 2}],
            "selected": "FH-1",
        }
    )
    pm_next = json.dumps({"type": "brief", "message": "next", "brief": "# v2"})
    # Enough replies for several iterations; the budget should cut it short first.
    replies = [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN] + [
        analyst_reply, pm_next, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN,
    ] * 5
    state = ProjectState(id="proj-test", name="x", goal="g", auto_spec=True, budget_usd=0.10)
    pipeline = Pipeline(state, _CostRunner(replies))
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.STOPPED)
    assert pipeline.state.usage.cost_usd >= 0.10
    assert any("Budget atteint" in m.content for m in pipeline.state.chat)


async def test_brainstorm_mode_uses_analyst_facilitation(green_pytest):
    pipeline, runner = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN]
    )
    pipeline.state.spec_mode = "brainstorm"
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    # The very first agent call (spec) used the brainstorming prompt, not the
    # standard Socratic interview.
    spec_prompt = runner.calls[0]["prompt"]
    assert "BRAINSTORMING" in spec_prompt
    assert "DIVERGER" in spec_prompt


async def test_set_spec_mode_validation():
    state = ProjectState(id="proj-test", name="x", goal="g")
    pipeline = Pipeline(state, FakeRunner([]))
    await pipeline.aset_spec_mode("brainstorm")
    assert pipeline.state.spec_mode == "brainstorm"
    await pipeline.aset_spec_mode("interview")
    assert pipeline.state.spec_mode == "interview"
    with pytest.raises(ValueError):
        await pipeline.aset_spec_mode("nope")


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
        return False, "1 failed", {}

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


async def test_pause_blocks_then_resume_completes(green_pytest):
    pipeline, _ = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN]
    )
    # Pause before starting: the plan phase must not run while paused.
    await pipeline.apause()
    pipeline.start()
    await wait_until(lambda: pipeline.state.brief.startswith("# Brief"))
    assert pipeline.state.paused is True
    # Still no plan produced because the loop is gated at the checkpoint.
    await asyncio.sleep(0.05)
    assert pipeline.state.epics == []
    assert pipeline.state.phase != PipelinePhase.DONE

    await pipeline.aresume()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert pipeline.state.paused is False
    assert pipeline.state.story("US-1").status == StoryStatus.DONE


async def test_stop_unblocks_a_paused_pipeline(green_pytest):
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    await pipeline.apause()
    pipeline.start()
    await wait_until(lambda: pipeline.state.brief.startswith("# Brief"))
    await pipeline.astop()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.STOPPED)


async def test_po_refinement_invoked_when_enabled(green_pytest, monkeypatch):
    from autospec.config import settings

    monkeypatch.setattr(settings, "refine_enabled", True)
    monkeypatch.setattr(settings, "refine_po", True)
    monkeypatch.setattr(settings, "refine_dev", False)  # no git in this test
    judge_pass = json.dumps({"score": 92, "verdict": "plan solide"})
    pipeline, _ = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), judge_pass, QA_PLAN, DEV_GREEN]
    )
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert pipeline.state.story("US-1").status == StoryStatus.DONE
    # The judge passed immediately (92 >= 80): 0 refine rounds, plan kept.
    assert any(
        "Plan raffiné en 0 tour(s)" in m.content and "92/100" in m.content
        for m in pipeline.state.chat
    )


async def test_plan_quality_stored_when_refine_enabled(green_pytest, monkeypatch):
    from autospec.config import settings

    monkeypatch.setattr(settings, "refine_enabled", True)
    monkeypatch.setattr(settings, "refine_po", True)
    monkeypatch.setattr(settings, "refine_dev", False)  # no git in this test
    judge = json.dumps({"score": 92, "verdict": "ok"})
    pipeline, _ = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), judge, QA_PLAN, DEV_GREEN]
    )
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    # The refinement score is exposed on the state for the UI.
    assert pipeline.state.plan_quality == 92


async def test_quality_scores_default_minus_one(green_pytest):
    # Refinement is OFF by default: the quality scores stay at their sentinel -1.
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert pipeline.state.plan_quality == -1
    assert pipeline.state.story("US-1").quality_score == -1


async def test_real_pytest_states_map_by_nodeid(monkeypatch):
    from autospec.models import TestState

    # The orchestrator grounds states on REAL pytest outcomes: UT-1's node
    # passed, UT-2's node failed. The suite is red, so the suite-green heuristic
    # does NOT apply — the green/red split comes purely from the real report.
    async def _mixed_pytest(self):
        return False, "1 failed", {
            "tests/unit/a.py::t_ok": "passed",
            "tests/unit/b.py::t_ko": "failed",
        }

    monkeypatch.setattr(Pipeline, "_arun_pytest", _mixed_pytest)
    dev_reply = json.dumps(
        {
            "status": "failed",
            "summary": "partiel",
            "files": [],
            "test_results": [
                {"id": "UT-1", "nodeids": ["tests/unit/a.py::t_ok"]},
                {"id": "UT-2", "nodeids": ["tests/unit/b.py::t_ko"]},
            ],
        }
    )
    # QA runs on attempt 1 only; 2 dev attempts then the story fails.
    pipeline, _ = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, dev_reply, dev_reply]
    )
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    us1 = pipeline.state.story("US-1")
    assert us1.status == StoryStatus.FAILED
    assert us1.test_plan[0].status == TestState.GREEN  # UT-1 node really passed
    assert us1.test_plan[1].status == TestState.RED    # UT-2 node really failed


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


async def test_rebuild_failed_story(green_pytest):
    # 4 replies for the initial build (-> done), 2 more for the rebuild.
    pipeline, _ = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN, QA_PLAN, DEV_GREEN]
    )
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)

    # Pretend the story actually failed after a first attempt.
    us1 = pipeline.state.story("US-1")
    us1.status = StoryStatus.FAILED
    us1.attempts = 1

    await pipeline.arebuild_story("US-1")
    await wait_until(
        lambda: pipeline.state.phase == PipelinePhase.DONE
        and pipeline.state.story("US-1").status == StoryStatus.DONE
    )
    # attempts was reset to 0 then re-incremented once by the successful rebuild.
    assert pipeline.state.story("US-1").attempts == 1


async def test_rebuild_rejects_concurrent_call(green_pytest):
    # TOCTOU guard: a second rebuild while one is in flight must be rejected.
    pipeline, _ = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN, QA_PLAN, DEV_GREEN]
    )
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    pipeline.state.story("US-1").status = StoryStatus.FAILED

    await pipeline.arebuild_story("US-1")  # launches rebuild, sets phase=BUILD synchronously
    assert pipeline.state.phase == PipelinePhase.BUILD
    with pytest.raises(ValueError):
        await pipeline.arebuild_story("US-1")  # rejected while the first is active
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)


async def test_force_done_story(green_pytest):
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)

    us1 = pipeline.state.story("US-1")
    us1.status = StoryStatus.FAILED

    await pipeline.aforce_done("US-1")
    assert us1.status == StoryStatus.DONE
    assert all(t.status == TestState.GREEN for t in us1.test_plan)


async def test_rebuild_rejected_when_pipeline_active(green_pytest):
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)

    # Simulate an active pipeline: rebuild must be refused.
    pipeline.state.phase = PipelinePhase.BUILD
    with pytest.raises(ValueError):
        await pipeline.arebuild_story("US-1")


async def test_rebuild_unknown_story_raises_keyerror(green_pytest):
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    with pytest.raises(KeyError):
        await pipeline.arebuild_story("US-999")


async def test_resume_build_completes_pending_story(green_pytest):
    # 4 replies for the initial build (-> done), 2 more for the resume.
    pipeline, _ = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN, QA_PLAN, DEV_GREEN]
    )
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)

    # Simulate a dormant project: the story was reverted to TODO on restart.
    us1 = pipeline.state.story("US-1")
    us1.status = StoryStatus.TODO
    us1.attempts = 0

    await pipeline.aresume_build()
    await wait_until(
        lambda: pipeline.state.phase == PipelinePhase.DONE
        and pipeline.state.story("US-1").status == StoryStatus.DONE
    )


async def test_resume_build_rejected_when_active(green_pytest):
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)

    # Simulate an active pipeline: resuming the build must be refused.
    pipeline.state.phase = PipelinePhase.BUILD
    with pytest.raises(ValueError):
        await pipeline.aresume_build()


async def test_resume_build_rejected_when_nothing_pending(green_pytest):
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)

    # Every story is DONE: there is nothing left to build (no TODO/RED).
    assert pipeline.state.story("US-1").status == StoryStatus.DONE
    with pytest.raises(ValueError):
        await pipeline.aresume_build()


async def test_retry_failed_resets_and_rebuilds(green_pytest):
    # 4 replies for the initial build (-> done), 2 more for the retry rebuild.
    pipeline, _ = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN, QA_PLAN, DEV_GREEN]
    )
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)

    us1 = pipeline.state.story("US-1")
    us1.status = StoryStatus.FAILED
    us1.last_error = "boom"

    await pipeline.aretry_failed()
    await wait_until(
        lambda: pipeline.state.phase == PipelinePhase.DONE
        and pipeline.state.story("US-1").status == StoryStatus.DONE
    )
    assert pipeline.state.story("US-1").last_error == ""


async def test_retry_failed_rejected_when_no_failure(green_pytest):
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    # All stories DONE -> nothing failed to retry.
    with pytest.raises(ValueError):
        await pipeline.aretry_failed()


def test_fail_stranded_stories_at_iteration_close():
    # Advancing iterations must not strand an attempted-but-unfinished story as a
    # stray TODO: those become FAILED (clear + relaunchable). Fresh, never-tried
    # TODOs and other iterations are left alone.
    from autospec.models import Epic, ProjectState, UserStory

    state = ProjectState(id="strand", name="n", goal="g", iteration=2)
    state.epics = [Epic(id="E", title="e", iteration=2)]
    state.stories = [
        UserStory(id="US-1", epic_id="E", title="done", iteration=2, status=StoryStatus.DONE),
        UserStory(id="US-13", epic_id="E", title="orphan", iteration=2,
                  status=StoryStatus.TODO, attempts=1, last_error="boom"),
        UserStory(id="US-14", epic_id="E", title="fresh", iteration=2,
                  status=StoryStatus.TODO, attempts=0),
        UserStory(id="US-15", epic_id="E", title="red", iteration=2,
                  status=StoryStatus.RED, attempts=2),
        UserStory(id="US-99", epic_id="E", title="other-iter", iteration=3,
                  status=StoryStatus.TODO, attempts=1),
    ]
    pipeline = Pipeline(state, FakeRunner([]))
    n = pipeline._fail_stranded_stories(2)
    assert n == 2
    assert state.story("US-13").status == StoryStatus.FAILED
    assert state.story("US-15").status == StoryStatus.FAILED
    assert state.story("US-14").status == StoryStatus.TODO  # never attempted -> kept
    assert state.story("US-1").status == StoryStatus.DONE
    assert state.story("US-99").status == StoryStatus.TODO  # other iteration untouched


async def test_retry_failed_rejected_when_active(green_pytest):
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    pipeline.state.story("US-1").status = StoryStatus.FAILED
    pipeline.state.phase = PipelinePhase.BUILD  # active -> refused
    with pytest.raises(ValueError):
        await pipeline.aretry_failed()


async def test_architecture_phase_injects_context(green_pytest, monkeypatch):
    from autospec.config import settings

    monkeypatch.setattr(settings, "architecture_enabled", True)
    ARCHITECT = json.dumps({"message": "Design fait.", "design": "## Archi\nservice + repo"})
    pipeline, runner = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), ARCHITECT, QA_PLAN, DEV_GREEN]
    )
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)

    # The architect's design is stored on the state and emitted in the chat.
    assert "service + repo" in pipeline.state.architecture
    assert any(m.role == ChatRole.ARCHITECT for m in pipeline.state.chat)

    # Both the QA and the Dev prompts carry the architecture context.
    qa_prompt = next(c["prompt"] for c in runner.calls if "architecte de tests" in c["prompt"])
    dev_prompt = next(c["prompt"] for c in runner.calls if "PROCESSUS OBLIGATOIRE" in c["prompt"])
    for prompt in (qa_prompt, dev_prompt):
        assert "Contexte architecture" in prompt
        assert "service + repo" in prompt


async def test_architecture_off_by_default(green_pytest):
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    assert pipeline.state.architecture == ""
    assert not any(m.role == ChatRole.ARCHITECT for m in pipeline.state.chat)


async def test_feedback_outside_spec_is_stored(green_pytest):
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    await pipeline.asend_user_message("Le bouton est trop petit")
    assert pipeline.state.feedback == ["Le bouton est trop petit"]


async def test_chat_during_build_is_guidance():
    pipeline, _ = make_pipeline([])
    pipeline.state.phase = PipelinePhase.BUILD
    await pipeline.asend_user_message("utilise des fixtures pytest")
    assert "utilise des fixtures pytest" in pipeline.state.build_guidance
    assert pipeline.state.feedback == []


async def test_chat_outside_build_is_feedback():
    pipeline, _ = make_pipeline([])
    pipeline.state.phase = PipelinePhase.DONE
    await pipeline.asend_user_message("le bouton est trop petit")
    assert pipeline.state.feedback == ["le bouton est trop petit"]
    assert pipeline.state.build_guidance == []


async def test_story_diff_returns_commit():
    from autospec.models import Epic, UserStory
    from autospec.orchestrator import workspace
    from autospec.storage import workspace_dir

    state = ProjectState(id="diff-proj", name="diff", goal="diff demo")
    pipeline = Pipeline(state, FakeRunner([]))
    workspace.scaffold(state)
    state.epics.append(Epic(id="EPIC-1", title="Epic 1"))
    state.stories.append(UserStory(id="US-1", epic_id="EPIC-1", title="s"))

    (workspace_dir("diff-proj") / "demo.py").write_text("x = 1\n", encoding="utf-8")
    await pipeline._acommit_story(workspace_dir("diff-proj"), "US-1")

    res = await pipeline.astory_diff("US-1")
    assert res["available"] is True
    assert "demo.py" in res["diff"]


async def test_story_diff_unavailable_without_commit():
    from autospec.models import Epic, UserStory
    from autospec.orchestrator import workspace

    state = ProjectState(id="diff-proj-2", name="diff", goal="diff demo")
    pipeline = Pipeline(state, FakeRunner([]))
    workspace.scaffold(state)
    state.epics.append(Epic(id="EPIC-1", title="Epic 1"))
    state.stories.append(UserStory(id="US-1", epic_id="EPIC-1", title="s"))

    # No "story US-1 done" commit exists for this workspace.
    res = await pipeline.astory_diff("US-1")
    assert res["available"] is False
    assert res["diff"] == ""


# --------------------------------------------------------- B-IDEA brainstorm assist

def _assess(maturity: str, techniques=None) -> str:
    return json.dumps(
        {"maturity": maturity, "rationale": "r", "techniques": techniques or []}
    )


async def test_brainstorm_assist_structured_goes_straight_to_interview(monkeypatch):
    from autospec.config import settings

    monkeypatch.setattr(settings, "brainstorm_assist_enabled", True)
    pipeline, _ = make_pipeline([_assess("structured")])
    outcome = await pipeline._abrainstorm_assist()
    assert outcome == "interactive"
    assert pipeline.state.idea_maturity == "structured"
    assert pipeline.state.awaiting_brainstorm_decision is False


async def test_brainstorm_assist_vague_offers_and_accept_is_interactive(monkeypatch):
    from autospec.config import settings

    monkeypatch.setattr(settings, "brainstorm_assist_enabled", True)
    pipeline, _ = make_pipeline([_assess("vague", ["What If Scenarios"])])

    task = asyncio.create_task(pipeline._abrainstorm_assist())
    await wait_until(lambda: pipeline.state.awaiting_brainstorm_decision)
    assert pipeline.state.brainstorm_techniques == ["What If Scenarios"]
    await pipeline.aresolve_brainstorm(True)  # user accepts -> interactive
    assert await task == "interactive"
    assert pipeline.state.spec_mode == "brainstorm"
    assert pipeline.state.awaiting_brainstorm_decision is False


async def test_brainstorm_assist_vague_refuse_runs_autonomously(monkeypatch):
    from autospec.config import settings

    monkeypatch.setattr(settings, "brainstorm_assist_enabled", True)
    monkeypatch.setattr(settings, "brainstorm_auto_rounds", 2)
    # assess(vague) -> offer -> refuse -> self-brainstorm: q, AI answer, brief.
    q = json.dumps({"type": "question", "message": "CLI ou web ?"})
    pipeline, _ = make_pipeline([_assess("vague"), q, "Réponse IA (porteur).", PM_BRIEF])

    task = asyncio.create_task(pipeline._abrainstorm_assist())
    await wait_until(lambda: pipeline.state.awaiting_brainstorm_decision)
    await pipeline.aresolve_brainstorm(False)  # user refuses -> autonomous
    assert await task == "done"
    assert pipeline.state.brief.strip()
    # The AI's simulated answer was recorded in the chat (prefixed 🤖).
    assert any(m.role == ChatRole.USER and "🤖" in m.content for m in pipeline.state.chat)


async def test_brainstorm_assist_auto_spec_skips_the_offer(monkeypatch):
    from autospec.config import settings

    monkeypatch.setattr(settings, "brainstorm_assist_enabled", True)
    monkeypatch.setattr(settings, "brainstorm_auto_rounds", 1)
    pipeline, _ = make_pipeline([_assess("vague"), PM_BRIEF], auto_spec=True)
    outcome = await pipeline._abrainstorm_assist()
    assert outcome == "done"
    assert pipeline.state.awaiting_brainstorm_decision is False  # never offered
    assert pipeline.state.brief.strip()


async def test_brainstorm_assist_disabled_keeps_plain_interview(monkeypatch):
    from autospec.config import settings

    monkeypatch.setattr(settings, "brainstorm_assist_enabled", False)
    # Flag off: _aspec_phase must NOT assess — the first reply is the PM brief.
    pipeline, _ = make_pipeline([PM_BRIEF])
    brief = await pipeline._aspec_phase()
    assert brief and brief.strip()
    assert pipeline.state.idea_maturity == ""  # never assessed


async def test_resolve_brainstorm_without_offer_raises():
    pipeline, _ = make_pipeline([])
    with pytest.raises(ValueError):
        await pipeline.aresolve_brainstorm(True)


async def test_workspace_git_is_isolated_from_enclosing_repo(tmp_workspace):
    """Regression: a workspace nested inside an enclosing git repo must get its
    OWN repo. ``_agit_ensure_repo`` used ``--is-inside-work-tree`` (also true for
    nested dirs), so it skipped ``git init`` and every ``git add -A`` / commit
    leaked the user's working changes into the parent repository."""
    import subprocess

    from autospec.orchestrator import workspace

    enclosing = tmp_workspace  # tmp_path; workspace_root == tmp_path/workspace

    def _git(*args, cwd):
        return subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True
        )

    _git("init", cwd=enclosing)
    _git("config", "user.email", "parent@local", cwd=enclosing)
    _git("config", "user.name", "parent", cwd=enclosing)

    state = ProjectState(id="iso-proj", name="iso", goal="iso")
    pipeline = Pipeline(state, FakeRunner([]))
    ws = workspace.scaffold(state)
    assert ws.is_relative_to(enclosing)  # genuinely nested in the enclosing repo

    assert await pipeline._agit_ensure_repo(ws) is True
    assert (ws / ".git").exists()  # an ISOLATED repo, not the parent's

    await pipeline._acommit_story(ws, "US-1")
    # Nothing must have leaked into the enclosing repository.
    assert _git("log", "--oneline", cwd=enclosing).stdout.strip() == ""


async def test_story_diff_unknown_story_raises_keyerror():
    state = ProjectState(id="diff-proj-3", name="diff", goal="diff demo")
    pipeline = Pipeline(state, FakeRunner([]))
    with pytest.raises(KeyError):
        await pipeline.astory_diff("US-999")


async def test_usage_is_accumulated(green_pytest):
    class _CostRunner(FakeRunner):
        async def arun(self, *a, **kw):
            res = await super().arun(*a, **kw)
            res.cost_usd = 0.01
            res.input_tokens = 100
            res.output_tokens = 50
            return res

    state = ProjectState(id="proj-test", name="todo", goal="Une todo-list")
    runner = _CostRunner([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline = Pipeline(state, runner)
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)

    # PM, PO, QA, Dev: four agent calls accumulated on the project state.
    usage = pipeline.state.usage
    assert usage.agent_calls == 4
    assert usage.cost_usd == pytest.approx(0.04)
    assert usage.input_tokens == 400
    assert usage.output_tokens == 200


async def test_usage_zero_by_default(green_pytest):
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)

    # FakeRunner reports no usage, but the call counter still increments.
    usage = pipeline.state.usage
    assert usage.cost_usd == 0.0
    assert usage.agent_calls >= 4


class _FixedCostRunner(FakeRunner):
    """FakeRunner whose every call reports a fixed cost/token charge so we can
    assert exact per-iteration accumulation."""

    async def arun(self, *a, **kw):
        res = await super().arun(*a, **kw)
        res.cost_usd = 0.01
        res.input_tokens = 100
        res.output_tokens = 50
        return res


async def test_iteration_usage_accumulates_for_current_iteration(green_pytest):
    runner = _FixedCostRunner(["a", "b", "c"])
    state = ProjectState(id="proj-it", name="todo", goal="Une todo-list")
    pipeline = Pipeline(state, runner)

    # Three tracked agent calls during the default iteration (1).
    for _ in range(3):
        await pipeline._tracked.arun("p", "s")

    n = state.iteration
    bucket = state.iteration_usage[n]
    assert bucket.agent_calls == 3
    assert bucket.cost_usd == pytest.approx(0.03)
    assert bucket.input_tokens == 300
    assert bucket.output_tokens == 150

    # With only one iteration, the per-iteration bucket equals the global total.
    assert bucket.agent_calls == state.usage.agent_calls
    assert bucket.cost_usd == pytest.approx(state.usage.cost_usd)
    assert bucket.input_tokens == state.usage.input_tokens
    assert bucket.output_tokens == state.usage.output_tokens


async def test_iteration_usage_splits_across_iterations(green_pytest):
    runner = _FixedCostRunner(["a", "b", "c", "d", "e"])
    state = ProjectState(id="proj-split", name="todo", goal="Une todo-list")
    pipeline = Pipeline(state, runner)

    # Two calls during iteration 1.
    await pipeline._tracked.arun("p", "s")
    await pipeline._tracked.arun("p", "s")

    # Bump to a new iteration, then three more calls.
    state.iteration = 2
    for _ in range(3):
        await pipeline._tracked.arun("p", "s")

    b1 = state.iteration_usage[1]
    b2 = state.iteration_usage[2]

    assert b1.agent_calls == 2
    assert b1.cost_usd == pytest.approx(0.02)
    assert b1.input_tokens == 200
    assert b1.output_tokens == 100

    assert b2.agent_calls == 3
    assert b2.cost_usd == pytest.approx(0.03)
    assert b2.input_tokens == 300
    assert b2.output_tokens == 150

    # The global total is the sum of every iteration bucket.
    assert state.usage.agent_calls == b1.agent_calls + b2.agent_calls == 5
    assert state.usage.cost_usd == pytest.approx(b1.cost_usd + b2.cost_usd)
    assert state.usage.input_tokens == b1.input_tokens + b2.input_tokens == 500
    assert state.usage.output_tokens == b1.output_tokens + b2.output_tokens == 250


async def test_fatal_pipeline_error_sets_error_phase(green_pytest):
    # The PO stage receives a non-JSON reply: extract_json raises AgentError,
    # which _alifecycle catches -> phase ERROR + a SYSTEM chat mentioning it.
    pipeline, _ = make_pipeline([PM_BRIEF, "ceci n'est pas du json"])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.ERROR)
    assert pipeline.state.error  # non-empty error message stored on the state
    assert any(
        m.role == ChatRole.SYSTEM and "Erreur pipeline" in m.content
        for m in pipeline.state.chat
    )


def test_apply_test_states_fallbacks():
    # Directly exercise _apply_test_states without a full pipeline run.
    from autospec.models import UserStory

    story = UserStory(
        id="US-1",
        epic_id="EPIC-1",
        title="s",
        test_plan=[
            PlannedTest(id="UT-1"),
            PlannedTest(id="UT-2"),
            PlannedTest(id="UT-3"),
        ],
    )
    state = ProjectState(id="apply-proj", name="n", goal="g")
    pipeline = Pipeline(state, FakeRunner([]))

    real = {
        "tests/a.py::ok": "passed",
        "tests/a.py::ko": "failed",
    }
    reported = [
        # nodeids present in the real report: green/red grounded on reality.
        {"id": "UT-1", "status": "green", "nodeids": ["tests/a.py::ok"]},
        # status would say green but the REAL node failed -> red wins.
        {"id": "UT-2", "status": "green", "nodeids": ["tests/a.py::ko"]},
        # no nodeid in the report, but a declared red status -> fallback red.
        {"id": "UT-3", "status": "red", "nodeids": ["tests/missing.py::x"]},
    ]
    pipeline._apply_test_states(story, reported, real)
    by_id = {t.id: t for t in story.test_plan}
    assert by_id["UT-1"].status == TestState.GREEN  # real passed
    assert by_id["UT-2"].status == TestState.RED     # real failed overrides declared green
    assert by_id["UT-3"].status == TestState.RED     # declared-status fallback

    # A test with neither matching nodeids nor a status stays nonexistent.
    story2 = UserStory(id="US-2", epic_id="EPIC-1", title="s", test_plan=[PlannedTest(id="UT-9")])
    pipeline._apply_test_states(story2, [{"id": "UT-9", "nodeids": []}], real)
    assert story2.test_plan[0].status == TestState.NONEXISTENT


async def test_red_story_is_replanned_then_succeeds(green_pytest, monkeypatch):
    # The first pytest verification is red, the second is green: the story is
    # rescheduled (TODO) then completes (DONE) on the second attempt.
    calls = {"n": 0}

    async def _flaky_pytest(self):
        calls["n"] += 1
        if calls["n"] == 1:
            return False, "x", {}
        return True, "ok", {}

    monkeypatch.setattr(Pipeline, "_arun_pytest", _flaky_pytest)
    # 1 PM + 1 PO + 1 QA (attempt 1 only) + 2 Dev (one per attempt).
    pipeline, _ = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN, DEV_GREEN]
    )
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    us1 = pipeline.state.story("US-1")
    assert us1.status == StoryStatus.DONE
    assert us1.attempts == 2  # failed once (retry), succeeded on the second pass


async def test_plan_deduplicates_story_ids_across_iterations():
    # Iteration 2: the PO reuses "US-1"/"EPIC-1". The pipeline must keep ids
    # unique (no state.story() ambiguity, no feature-file overwrite) and remap
    # the plan's internal depends_on through the renames.
    from autospec.models import Epic, UserStory

    state = ProjectState(id="proj-test", name="todo", goal="g", brief="# Brief", iteration=2)
    state.epics.append(Epic(id="EPIC-1", title="Epic 1"))
    state.stories.append(
        UserStory(id="US-1", epic_id="EPIC-1", title="old", status=StoryStatus.DONE)
    )
    pipeline = Pipeline(state, FakeRunner([po_plan_reply(2)]))
    await pipeline._aplan_phase()

    ids = [s.id for s in state.stories]
    assert len(ids) == 3 and len(set(ids)) == 3
    new1, new2 = state.stories[1], state.stories[2]
    assert new1.id != "US-1"
    assert new2.depends_on == [new1.id]  # intra-plan dep follows the rename
    assert [e.id for e in state.epics] == ["EPIC-1", "EPIC-2"]


async def test_analyst_with_only_shipped_hypotheses_raises_clean_error():
    from autospec.agents.runner import AgentError
    from autospec.models import FeatureHypothesis, HypothesisStatus

    state = ProjectState(id="proj-test", name="x", goal="g")
    state.backlog.append(
        FeatureHypothesis(id="FH-1", title="X", status=HypothesisStatus.DONE)
    )
    reply = json.dumps(
        {"message": "m", "hypotheses": [{"id": "FH-1", "title": "X"}], "selected": "FH-1"}
    )
    pipeline = Pipeline(state, FakeRunner([reply]))
    with pytest.raises(AgentError):
        await pipeline._aanalyze_phase()


async def test_resume_build_picks_up_red_story(green_pytest):
    # 4 replies for the initial build, 1 dev reply for the resume (QA only runs
    # on attempt 1).
    pipeline, _ = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN, DEV_GREEN]
    )
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)

    # Simulate a restart that left the story RED mid-attempt: resume-build must
    # revert it to TODO so the scheduler picks it up again.
    pipeline.state.story("US-1").status = StoryStatus.RED
    await pipeline.aresume_build()
    await wait_until(
        lambda: pipeline.state.phase == PipelinePhase.DONE
        and pipeline.state.story("US-1").status == StoryStatus.DONE
    )


async def test_dev_refine_failure_keeps_story_done(green_pytest, monkeypatch):
    from autospec.config import settings

    monkeypatch.setattr(settings, "refine_enabled", True)
    monkeypatch.setattr(settings, "refine_po", False)
    monkeypatch.setattr(settings, "refine_dev", True)
    judge_low = json.dumps({"score": 10, "verdict": "faible"})
    critic = json.dumps({"reflection": "r", "issues": ["i"], "suggestions": ["s"]})
    # After the dev goes green: judge(10) -> critic -> the revise call has NO
    # queued reply -> AgentError. Refinement is opportunistic: the story must
    # stay DONE instead of being downgraded to TODO/FAILED.
    pipeline, _ = make_pipeline(
        [PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN, judge_low, critic]
    )
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.DONE)
    us1 = pipeline.state.story("US-1")
    assert us1.status == StoryStatus.DONE
    assert us1.attempts == 1


async def test_unexpected_build_error_never_leaves_story_in_progress(monkeypatch):
    # A non-AgentError during verification (e.g. pytest runner missing) must
    # surface as a pipeline ERROR without persisting a transient story status.
    async def _boom(self):
        raise RuntimeError("uv introuvable")

    monkeypatch.setattr(Pipeline, "_arun_pytest", _boom)
    pipeline, _ = make_pipeline([PM_BRIEF, po_plan_reply(1, with_dep=False), QA_PLAN, DEV_GREEN])
    pipeline.start()
    await wait_until(lambda: pipeline.state.phase == PipelinePhase.ERROR)
    assert pipeline.state.story("US-1").status == StoryStatus.TODO


def test_sanitize_keeps_dependencies_unrelated_to_a_cycle():
    # Cycle-breaking must only clear the deps of the cycle's members, not of
    # unrelated stories declared earlier.
    from autospec.models import UserStory
    from autospec.orchestrator import scheduler

    def mk(sid: str, deps: list[str]) -> UserStory:
        return UserStory(id=sid, epic_id="EPIC-1", title=sid, depends_on=deps)

    stories = [mk("US-1", ["US-2"]), mk("US-2", []), mk("US-3", ["US-4"]), mk("US-4", ["US-3"])]
    scheduler.sanitize_dependencies(stories)
    assert stories[0].depends_on == ["US-2"]  # untouched: not part of the cycle
    assert scheduler.validate_dependencies(stories) == []


def test_dev_prompt_includes_guidance():
    from autospec.agents import prompts
    from autospec.models import UserStory

    story = UserStory(id="US-1", epic_id="EPIC-1", title="Story")
    prompt = prompts.dev_story(story, "pkg", "features/us_1.feature", "", "consigne ABC")
    assert "Consignes de l'utilisateur" in prompt
    assert "consigne ABC" in prompt
