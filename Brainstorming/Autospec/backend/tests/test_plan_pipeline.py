"""PO pipeline (RFC po-pipeline-v2): the multi-stage PO — S1 structure +
complexity (deterministic checks + critic-first review), post-S1 size gate,
S2 per-story spec fan-out (auto-repair, resize barrier, ONE transversal
critic), S3 gherkin (AC alignment, complexity-gated critic, mechanical
fallback), merge/degradation, and the §6 measured calibration loop."""

import json

import pytest

from autospec.agents import prompts
from autospec.agents.runner import FakeRunner
from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import ProjectState, StoryStatus, UserStory
from autospec.orchestrator import plan_pipeline as pp
from autospec.orchestrator import refine
from autospec.orchestrator import streams as work_streams
from autospec.orchestrator.pipeline import Pipeline

# ------------------------------------------------------------------- builders

CRITIC_OK = json.dumps({"reflection": "rien", "issues": [], "suggestions": []})
CROSS_OK = json.dumps({"issues": [], "flagged": []})


def story_node(
    sid,
    *,
    title=None,
    complexity="standard",
    est=2,
    deps=(),
    tasks=(),
    ui=False,
    priority=2,
):
    return {
        "id": sid,
        "title": title or f"Story {sid}",
        "depends_on": list(deps),
        "priority": priority,
        "ui": ui,
        "stream": "",
        "complexity": complexity,
        "rationale": "jugement de taille",
        "estimated_files": est,
        "file_globs": [],
        "area": "domaine",
        "tasks": list(tasks),
    }


def task_node(tid, *, complexity="standard", est=1, deps=(), globs=()):
    return {
        "id": tid,
        "title": f"Tâche {tid}",
        "stream": "",
        "depends_on": list(deps),
        "complexity": complexity,
        "rationale": "petite unité",
        "estimated_files": est,
        "file_globs": list(globs),
        "area": "domaine",
    }


def skeleton_reply(stories) -> str:
    return json.dumps(
        {"epics": [{"id": "EPIC-1", "title": "Cœur", "description": "d", "stories": stories}]}
    )


def gk(ac_ids) -> str:
    lines = ["Feature: F"]
    for a in ac_ids:
        lines += [f"  @{a}", f"  Scenario: cas {a}", "    Given a", "    When b", "    Then c"]
    return "\n".join(lines)


def spec_reply(sid, *, tasks=(), verdict="ok", proposal="", gherkin="", description=None) -> str:
    return json.dumps(
        {
            "id": sid,
            "description": description or f"En tant qu'utilisateur, je veux {sid}.",
            "acceptance_criteria": [
                {"id": "AC-1", "text": "le nominal fonctionne", "kind": "happy"},
                {"id": "AC-2", "text": "l'erreur est gérée", "kind": "error"},
            ],
            "tasks": [
                {
                    "id": tid,
                    "description": f"mini-spec {tid}",
                    "acceptance_criteria": [
                        {"id": "AC-1", "text": f"contrat {tid}", "kind": "happy"}
                    ],
                }
                for tid in tasks
            ],
            "resize": {"verdict": verdict, "proposal": proposal},
            "gherkin": gherkin,
        }
    )


def gherkin_reply(sid, ac_ids=("AC-1", "AC-2")) -> str:
    return json.dumps({"id": sid, "gherkin": gk(list(ac_ids))})


def make_state(**kw) -> ProjectState:
    st = ProjectState(id="pp-proj", name="calc", goal="une calculatrice", **kw)
    st.brief = "# Brief\nUne calculatrice."
    return st


@pytest.fixture
def full_mode(monkeypatch):
    monkeypatch.setattr(settings, "po_pipeline_min_leaves", 1)
    monkeypatch.setattr(settings, "po_pipeline_gherkin", True)
    monkeypatch.setattr(settings, "refine_max_rounds", 2)


# --------------------------------------------------- deterministic validation

def test_validate_skeleton_catches_cycle_orphans_budget_and_complex():
    skel = pp.S1Skeleton.model_validate(
        {
            "epics": [
                {
                    "id": "EPIC-1",
                    "title": "E",
                    "stories": [
                        story_node("US-1", deps=("US-2",)),
                        story_node("US-2", deps=("US-1", "US-GHOST")),
                        story_node("US-3", complexity="complex"),          # no tasks
                        story_node("US-4", est=settings.task_file_budget + 5),
                    ],
                }
            ]
        }
    )
    errors, _ = pp.validate_skeleton(skel)
    text = "\n".join(errors)
    assert "cycle" in text
    assert "US-GHOST" in text
    assert "complex" in text and "US-3" in text
    assert "budget" in text and "US-4" in text


def test_validate_skeleton_empty_and_duplicate_ids():
    empty = pp.S1Skeleton.model_validate({"epics": []})
    errors, _ = pp.validate_skeleton(empty)
    assert any("aucune" in e for e in errors)
    dup = pp.S1Skeleton.model_validate(
        {"epics": [{"id": "E1", "title": "E",
                    "stories": [story_node("US-1"), story_node("US-1")]}]}
    )
    errors, _ = pp.validate_skeleton(dup)
    assert any("dupliqué" in e for e in errors)


def test_validate_skeleton_confronts_globs_with_real_repo():
    """Iteration ≥ 2: file_globs are required, root-wide globs refused, and a
    glob matching nothing in the real tree is a warning (new file?)."""
    repo = ["calc/core.py", "tests/test_core.py", "main.py"]
    stories = [
        story_node("US-1"),                                     # missing globs
        dict(story_node("US-2"), file_globs=["**"]),            # root-wide
        dict(story_node("US-3"), file_globs=["calc/nope.py"]),  # matches nothing
        dict(story_node("US-4"), file_globs=["calc/core.py"]),  # fine
    ]
    skel = pp.S1Skeleton.model_validate(
        {"epics": [{"id": "E1", "title": "E", "stories": stories}]}
    )
    errors, warnings = pp.validate_skeleton(skel, repo_files=repo)
    text = "\n".join(errors)
    assert "US-1" in text and "obligatoire" in text
    assert "US-2" in text and "trop large" in text
    assert any("US-3" in w and "ne matche aucun" in w for w in warnings)
    assert not any("US-4" in e for e in errors)


def test_validate_skeleton_fourre_tout_heuristics():
    stories = [
        story_node("US-1", title="Gérer les comptes et les paiements et les mails"),
        story_node("US-2", tasks=[task_node(f"T-{i}") for i in range(1, 9)]),
    ]
    skel = pp.S1Skeleton.model_validate(
        {"epics": [{"id": "E1", "title": "E", "stories": stories}]}
    )
    _, warnings = pp.validate_skeleton(skel)
    assert any("US-1" in w and "responsabilités" in w for w in warnings)
    assert any("US-2" in w and "fourre-tout" in w for w in warnings)


def test_validate_story_spec_coverage_taxonomy_and_task_integrity():
    skel_story = pp.S1Story.model_validate(story_node("US-1", tasks=[task_node("T-1")]))
    spec = pp.S2StorySpec.model_validate(
        {
            "id": "US-1",
            "description": "d",
            "acceptance_criteria": [
                {"id": "AC-1", "text": "ok", "kind": "happy"},
                {"id": "AC-1", "text": "dup", "kind": "banana"},
            ],
            "tasks": [{"id": "T-GHOST", "description": "d"}],
            "resize": {"verdict": "peut-être"},
        }
    )
    errors = pp.validate_story_spec(spec, skel_story)
    text = "\n".join(errors)
    assert "dupliqué" in text
    assert "banana" in text
    assert "aucun critère « error »" in text
    assert "T-GHOST" in text                      # unknown task
    assert "T-1" in text and "sans mini-spec" in text
    assert "peut-être" in text                    # invalid resize verdict


def test_validate_gherkin_alignment_and_forbidden_ui_steps():
    ok = gk(["AC-1", "AC-2"])
    assert pp.validate_gherkin(ok, ["AC-1", "AC-2"]) == []
    # Missing/mismatched tags break the 1-for-1 alignment.
    errs = pp.validate_gherkin(gk(["AC-1"]), ["AC-1", "AC-2"])
    assert any("alignement" in e for e in errs)
    # UI step in a non-UI story is refused; allowed when ui=True.
    ui_text = ok + "\n    When je clique sur le bouton"
    assert any("interdit" in e for e in pp.validate_gherkin(ui_text, ["AC-1", "AC-2"]))
    assert pp.validate_gherkin(ui_text, ["AC-1", "AC-2"], ui=True) == []
    # No Feature/Scenario at all.
    errs = pp.validate_gherkin("du texte", ["AC-1"])
    assert any("Feature" in e for e in errs) and any("Scenario" in e for e in errs)


def test_fallback_gherkin_is_never_empty_and_tags_every_criterion():
    crits = [
        pp.S2Criterion(id="AC-1", text="a", kind="happy"),
        pp.S2Criterion(id="AC-2", text="b", kind="error"),
    ]
    text = pp.fallback_gherkin("US-1", "Ma story", crits)
    assert pp.validate_gherkin(text, ["AC-1", "AC-2"]) == []
    assert pp.fallback_gherkin("US-1", "", []).startswith("Feature:")


# --------------------------------------------------------- maker + auto-repair

def _parse_upper(text: str):
    """Toy parse fn: accepts only 'OK', reports the reply otherwise."""
    return ("OK", []) if text == "OK" else (None, [f"attendu OK, reçu {text}"])


async def test_amake_validated_accepts_first_valid_reply():
    runner = FakeRunner(["OK"])
    obj, err = await pp.amake_validated(
        runner, prompt="P", system_prompt="S", parse=_parse_upper
    )
    assert obj == "OK" and err == ""
    assert len(runner.calls) == 1


async def test_amake_validated_repairs_once_with_the_validation_error():
    runner = FakeRunner(["KO", "OK"])
    obj, err = await pp.amake_validated(
        runner, prompt="P", system_prompt="S", parse=_parse_upper
    )
    assert obj == "OK" and err == ""
    repair_prompt = runner.calls[1]["prompt"]
    assert "AUTO-RÉPARATION" in repair_prompt
    assert "attendu OK, reçu KO" in repair_prompt


async def test_amake_validated_gives_up_after_one_repair():
    runner = FakeRunner(["KO", "KO2"])
    obj, err = await pp.amake_validated(
        runner, prompt="P", system_prompt="S", parse=_parse_upper
    )
    assert obj is None and "KO2" in err
    assert len(runner.calls) == 2


# ------------------------------------------------------- critic-first refine

CRITIC_ISSUES = json.dumps(
    {"reflection": "r", "issues": ["problème"], "suggestions": ["corrige"]}
)


async def _run_critic_first(runner, **kw):
    calls = {"revise": 0}

    async def _revise(prev, critique):
        calls["revise"] += 1
        return f"{prev}+rev{calls['revise']}"

    kw.setdefault("revise", _revise)
    outcome = await refine.arefine_critic_first(
        runner, kind="artefact", criteria="critères", initial_text="v0", **kw
    )
    return outcome, calls


async def test_critic_first_empty_critique_accepts_with_zero_rounds():
    runner = FakeRunner([CRITIC_OK])
    outcome, calls = await _run_critic_first(runner)
    assert outcome.stopped_reason == "critic_empty"
    assert outcome.rounds == 0 and outcome.text == "v0"
    assert calls["revise"] == 0
    assert len(runner.calls) == 1  # no opening judge


async def test_critic_first_distinguishes_critic_failure_from_satisfaction():
    outcome, calls = await _run_critic_first(FakeRunner([]))  # call raises
    assert outcome.stopped_reason == "critic_error"
    assert outcome.text == "v0" and calls["revise"] == 0


async def test_critic_first_revises_until_satisfied_and_bounded(monkeypatch):
    monkeypatch.setattr(settings, "refine_max_rounds", 2)
    outcome, calls = await _run_critic_first(FakeRunner([CRITIC_ISSUES, CRITIC_OK]))
    assert outcome.stopped_reason == "critic_empty"
    assert outcome.rounds == 1 and outcome.text == "v0+rev1"
    # Never-satisfied critic: hard cap.
    outcome, calls = await _run_critic_first(
        FakeRunner([CRITIC_ISSUES, CRITIC_ISSUES, CRITIC_ISSUES])
    )
    assert outcome.stopped_reason == "max_rounds"
    assert outcome.rounds == 2 and calls["revise"] == 2


async def test_critic_first_rejected_revision_keeps_previous():
    async def _accept(_):
        return False

    outcome, _ = await _run_critic_first(
        FakeRunner([CRITIC_ISSUES]), accept=_accept
    )
    assert outcome.stopped_reason == "rejected"
    assert outcome.text == "v0"


# ------------------------------------------------------------- full pipeline

async def test_full_pipeline_produces_enriched_legacy_shaped_plan(full_mode):
    replies = [
        skeleton_reply([story_node("US-1"), story_node("US-2", deps=("US-1",))]),
        CRITIC_OK,                       # S1 structure critic satisfied
        spec_reply("US-1"),
        spec_reply("US-2"),
        CROSS_OK,                        # transversal critic satisfied
        gherkin_reply("US-1"),
        gherkin_reply("US-2"),
    ]
    runner = FakeRunner(replies)
    plan, report = await pp.arun_po_pipeline(runner, make_state(), "calc")
    assert not runner.replies            # exactly the expected calls, no more
    assert report.mode == "full" and report.leaves == 2
    stories = plan["epics"][0]["stories"]
    assert [s["id"] for s in stories] == ["US-1", "US-2"]
    s1 = stories[0]
    assert s1["complexity"] == "standard" and s1["estimated_files"] == 2
    assert s1["acceptance_criteria"][0] == {
        "id": "AC-1", "text": "le nominal fonctionne", "kind": "happy"
    }
    assert "@AC-1" in s1["gherkin"] and "@AC-2" in s1["gherkin"]
    assert stories[1]["depends_on"] == ["US-1"]
    assert not s1["spec_incomplete"]


async def test_merged_mode_small_skeleton_one_pass_per_story(monkeypatch):
    monkeypatch.setattr(settings, "po_pipeline_min_leaves", 4)  # 2 leaves < 4
    replies = [
        skeleton_reply([story_node("US-1"), story_node("US-2")]),
        CRITIC_OK,
        spec_reply("US-1", gherkin=gk(["AC-1", "AC-2"])),
        spec_reply("US-2", gherkin=gk(["AC-1", "AC-2"])),
    ]
    runner = FakeRunner(replies)
    plan, report = await pp.arun_po_pipeline(runner, make_state(), "calc")
    assert not runner.replies            # no resize barrier, no cross critic, no S3
    assert report.mode == "merged"
    stories = plan["epics"][0]["stories"]
    assert all("@AC-1" in s["gherkin"] for s in stories)
    # The merged prompt asks for the gherkin in the same pass.
    assert "tagué" in runner.calls[2]["prompt"]


async def test_resize_split_goes_through_the_common_splitting_brain(full_mode):
    decompose = json.dumps(
        {
            "message": "deux responsabilités",
            "tasks": [
                {"id": "T-a", "title": "Calcul", "file_globs": ["calc/core.py"], "depends_on": []},
                {"id": "T-b", "title": "Persistance", "file_globs": ["calc/store.py"], "depends_on": ["T-a"]},
            ],
        }
    )
    replies = [
        skeleton_reply([story_node("US-BIG")]),
        CRITIC_OK,
        spec_reply("US-BIG", verdict="split", proposal="calcul + persistance"),
        decompose,                                        # common brain (proactive)
        spec_reply("US-BIG", tasks=("US-BIG-R1", "US-BIG-R2")),  # re-spec once
        CROSS_OK,
        gherkin_reply("US-BIG"),
    ]
    runner = FakeRunner(replies)
    plan, report = await pp.arun_po_pipeline(runner, make_state(), "calc")
    assert not runner.replies
    # The split used the proactive decompose_finer prompt (same brain as reactive).
    split_prompt = runner.calls[3]["prompt"]
    assert "DÉCOUPAGE PLUS FIN (resize)" in split_prompt
    assert "RÈGLES DE DÉCOUPE" in split_prompt
    story = plan["epics"][0]["stories"][0]
    assert [t["id"] for t in story["tasks"]] == ["US-BIG-R1", "US-BIG-R2"]
    assert story["tasks"][1]["depends_on"] == ["US-BIG-R1"]   # remapped
    assert story["tasks"][0]["file_globs"] == ["calc/core.py"]
    assert report.resizes and "US-BIG" in report.resizes[0]


async def test_resize_merge_fuses_two_adjacent_trivial_stories(full_mode):
    replies = [
        skeleton_reply(
            [
                story_node("US-1", complexity="trivial", est=1),
                story_node("US-2", complexity="trivial", est=1),
                story_node("US-3", deps=("US-2",)),
            ]
        ),
        CRITIC_OK,
        spec_reply("US-1", verdict="merge"),
        spec_reply("US-2", verdict="merge"),
        spec_reply("US-3"),
        spec_reply("US-1"),   # the merged story re-runs S2 once
        CROSS_OK,
        gherkin_reply("US-1"),
        gherkin_reply("US-3"),
    ]
    runner = FakeRunner(replies)
    plan, report = await pp.arun_po_pipeline(runner, make_state(), "calc")
    assert not runner.replies
    stories = plan["epics"][0]["stories"]
    assert [s["id"] for s in stories] == ["US-1", "US-3"]
    assert "+" in stories[0]["title"]                      # fused title
    assert stories[1]["depends_on"] == ["US-1"]            # dep rewired to the merged story
    assert any("merge" in r for r in report.resizes)


async def test_cross_critic_triggers_targeted_remake_only(full_mode):
    flagged = json.dumps(
        {
            "issues": ["US-1 et US-2 se chevauchent sur la persistance"],
            "flagged": [{"id": "US-2", "reason": "chevauchement avec US-1"}],
        }
    )
    replies = [
        skeleton_reply([story_node("US-1"), story_node("US-2")]),
        CRITIC_OK,
        spec_reply("US-1"),
        spec_reply("US-2"),
        flagged,
        spec_reply("US-2", description="En tant qu'utilisateur, je veux la version corrigée."),
        gherkin_reply("US-1"),
        gherkin_reply("US-2"),
    ]
    runner = FakeRunner(replies)
    plan, report = await pp.arun_po_pipeline(runner, make_state(), "calc")
    assert not runner.replies
    remake_prompt = runner.calls[5]["prompt"]
    assert "RE-SPÉCIFICATION CIBLÉE" in remake_prompt
    assert "chevauchement" in remake_prompt
    stories = {s["id"]: s for s in plan["epics"][0]["stories"]}
    assert "corrigée" in stories["US-2"]["description"]
    assert report.flagged == ["US-2: chevauchement avec US-1"]
    assert report.cross_issues


async def test_s2_failure_degrades_to_mono_pass_then_flagged_skeleton(
    full_mode, monkeypatch
):
    monkeypatch.setattr(settings, "po_pipeline_gherkin", False)  # cut S3
    bad = "{}"
    replies = [
        skeleton_reply([story_node("US-1")]),
        CRITIC_OK,
        bad, bad,          # S2 maker + repair fail
        bad, bad,          # mono-pass (merged) attempt + repair fail
        CROSS_OK,
    ]
    runner = FakeRunner(replies)
    plan, report = await pp.arun_po_pipeline(runner, make_state(), "calc")
    assert not runner.replies
    story = plan["epics"][0]["stories"][0]
    assert story["spec_incomplete"] is True
    assert story["gherkin"].startswith("Feature:")        # never empty
    assert any(d.startswith("S2:US-1") for d in report.degradations)
    assert any(d.startswith("S2-mono:US-1") for d in report.degradations)


async def test_s2_failure_recovers_via_single_node_mono_pass(full_mode, monkeypatch):
    monkeypatch.setattr(settings, "po_pipeline_gherkin", False)
    bad = "{}"
    replies = [
        skeleton_reply([story_node("US-1")]),
        CRITIC_OK,
        bad, bad,                                            # S2 fails
        spec_reply("US-1", gherkin=gk(["AC-1", "AC-2"])),    # mono-pass succeeds
        CROSS_OK,
    ]
    runner = FakeRunner(replies)
    plan, report = await pp.arun_po_pipeline(runner, make_state(), "calc")
    story = plan["epics"][0]["stories"][0]
    assert story["spec_incomplete"] is False                 # recovered
    assert story["acceptance_criteria"][0]["kind"] == "happy"
    assert len(report.degradations) == 1                     # counted once


async def test_s3_failure_falls_back_to_mechanical_gherkin(full_mode):
    bad_gherkin = json.dumps({"id": "US-1", "gherkin": "pas un gherkin"})
    replies = [
        skeleton_reply([story_node("US-1")]),
        CRITIC_OK,
        spec_reply("US-1"),
        CROSS_OK,
        bad_gherkin, bad_gherkin,        # S3 maker + repair fail
    ]
    runner = FakeRunner(replies)
    plan, report = await pp.arun_po_pipeline(runner, make_state(), "calc")
    story = plan["epics"][0]["stories"][0]
    assert pp.validate_gherkin(story["gherkin"], ["AC-1", "AC-2"]) == []
    assert any(d.startswith("S3:US-1") for d in report.degradations)


async def test_s3_gherkin_flag_off_derives_gherkin_from_criteria(
    full_mode, monkeypatch
):
    monkeypatch.setattr(settings, "po_pipeline_gherkin", False)
    replies = [
        skeleton_reply([story_node("US-1")]),
        CRITIC_OK,
        spec_reply("US-1"),
        CROSS_OK,
    ]
    runner = FakeRunner(replies)
    plan, _ = await pp.arun_po_pipeline(runner, make_state(), "calc")
    assert not runner.replies            # no S3 call
    story = plan["epics"][0]["stories"][0]
    assert "@AC-1" in story["gherkin"] and "@AC-2" in story["gherkin"]


async def test_s3_llm_critic_is_reserved_for_complex_stories(full_mode):
    """The S1 complexity field drives the effort: a `complex` story's gherkin
    gets the LLM critic (and one re-make); standard stories stop at the
    deterministic gate (covered by test_full_pipeline...: no critic call)."""
    critic_review = json.dumps(
        {"reflection": "r", "issues": ["le scénario 2 n'est pas exécutable"], "suggestions": []}
    )
    replies = [
        skeleton_reply(
            [story_node("US-1", complexity="complex",
                        tasks=[task_node("T-1"), task_node("T-2")])]
        ),
        CRITIC_OK,
        spec_reply("US-1", tasks=("T-1", "T-2")),
        CROSS_OK,
        gherkin_reply("US-1"),
        critic_review,                    # gherkin critic (complex only)
        gherkin_reply("US-1"),            # re-make after the critique
    ]
    runner = FakeRunner(replies)
    plan, _ = await pp.arun_po_pipeline(runner, make_state(), "calc")
    assert not runner.replies
    assert "boucle de raffinement" in runner.calls[5]["prompt"]
    remake_prompt = runner.calls[6]["prompt"]
    assert "exécutable" in remake_prompt


# -------------------------------------------------- pipeline integration

def make_pipeline(replies, **state_kw):
    state = make_state(**state_kw)
    runner = FakeRunner(replies)
    return Pipeline(state, runner), runner


async def test_aplan_phase_flag_off_keeps_the_legacy_mono_pass(monkeypatch):
    monkeypatch.setattr(settings, "po_pipeline", "off")
    legacy = json.dumps(
        {
            "epics": [
                {"id": "EPIC-1", "title": "E", "description": "",
                 "stories": [{"id": "US-1", "title": "S",
                              "description": "d", "acceptance_criteria": ["c"],
                              "gherkin": "Feature: F\n  Scenario: S\n    Given a",
                              "depends_on": [], "priority": 1}]}
            ]
        }
    )
    pipeline, runner = make_pipeline([legacy])
    await pipeline._aplan_phase()
    assert "SQUELETTE" not in runner.calls[0]["prompt"]      # mono-pass prompt
    story = pipeline.state.stories[0]
    assert story.complexity == "" and story.estimated_files == 0
    assert story.acceptance_criteria[0].kind == ""           # legacy untouched


async def test_aplan_phase_pipeline_on_materializes_enriched_stories(
    full_mode, monkeypatch
):
    monkeypatch.setattr(settings, "po_pipeline", "on")
    replies = [
        skeleton_reply(
            [story_node("US-1", tasks=[task_node("T-1", globs=("calc/a.py",)),
                                       task_node("T-2", deps=("T-1",), globs=("calc/b.py",))])]
        ),
        CRITIC_OK,
        spec_reply("US-1", tasks=("T-1", "T-2")),
        CROSS_OK,
        gherkin_reply("US-1"),
    ]
    pipeline, runner = make_pipeline(replies)
    await pipeline._aplan_phase()
    assert not runner.replies
    story = pipeline.state.stories[0]
    assert story.complexity == "standard" and story.estimated_files == 2
    assert story.acceptance_criteria[0].id == "AC-1"          # ids PRESERVED
    assert story.acceptance_criteria[0].kind == "happy"
    assert "@AC-1" in story.gherkin
    # Tasks are materialized even with streams OFF (the pipeline owns granularity).
    assert [t.id for t in story.tasks] == ["T-1", "T-2"]
    assert story.tasks[1].depends_on == ["T-1"]
    assert story.tasks[0].complexity == "standard"
    assert story.tasks[0].files_hint == ["calc/a.py"]
    assert story.tasks[0].acceptance_criteria[0].kind == "happy"
    assert any("Pipeline PO" in m.content for m in pipeline.state.chat)


async def test_aplan_phase_s1_failure_falls_back_to_legacy_po(monkeypatch):
    monkeypatch.setattr(settings, "po_pipeline", "on")
    legacy = json.dumps(
        {"epics": [{"id": "EPIC-1", "title": "E", "description": "",
                    "stories": [{"id": "US-1", "title": "S", "description": "d",
                                 "acceptance_criteria": ["c"], "gherkin": "Feature: F",
                                 "depends_on": [], "priority": 1}]}]}
    )
    pipeline, runner = make_pipeline(["{}", "{}", legacy])   # S1 + repair fail
    await pipeline._aplan_phase()
    assert not runner.replies
    story = pipeline.state.stories[0]
    assert story.id == "US-1" and story.complexity == ""     # legacy plan won
    legacy_prompt = runner.calls[2]["prompt"]
    assert "PO/Scrum Master" in legacy_prompt and "SQUELETTE" not in legacy_prompt


async def test_scripted_end_to_end_merged_mode(monkeypatch):
    """AUTOSPEC_FAKE_AGENTS-style e2e: the ScriptedRunner drives S1 + the S1
    critic + the merged S2 pass (2 leaves < default K=4) without any LLM."""
    monkeypatch.setattr(settings, "po_pipeline", "on")
    monkeypatch.setattr(settings, "po_pipeline_min_leaves", 4)
    state = make_state()
    pipeline = Pipeline(state, ScriptedRunner())
    await pipeline._aplan_phase()
    assert [s.id for s in state.stories] == ["US-1", "US-2"]
    for story in state.stories:
        assert story.complexity in ("trivial", "standard")
        assert {c.kind for c in story.acceptance_criteria} == {"happy", "error"}
        assert "@AC-1" in story.gherkin
        assert story.spec_incomplete is False
    assert state.stories[1].depends_on == ["US-1"]


def test_scripted_resize_split_case():
    """The RFC's scripted resize case: a story whose id contains SPLIT gets a
    split verdict from the scripted S2 reply."""
    state = make_state()
    p = prompts.po_spec_story(state, story_node("US-SPLIT-1"), "calc")
    reply = json.loads(ScriptedRunner._reply_for(p))
    assert reply["resize"]["verdict"] == "split"
    p = prompts.po_spec_story(state, story_node("US-1"), "calc")
    reply = json.loads(ScriptedRunner._reply_for(p))
    assert reply["resize"]["verdict"] == "ok"


# ------------------------------------------------------ §6 calibration loop

async def test_reactive_split_emits_calibration_counter_and_sizing_lesson(
    monkeypatch,
):
    monkeypatch.setattr(settings, "split_on_failure_enabled", True)
    monkeypatch.setattr(settings, "split_max_depth", 1)
    state = make_state()
    state.stories = [
        UserStory(
            id="US-1", epic_id="EPIC-1", title="Trop grosse unité",
            gherkin="Feature: F\n  Scenario: S\n    Given a",
            status=StoryStatus.FAILED, last_error="tests rouges",
        )
    ]
    pipeline = Pipeline(state, ScriptedRunner())
    story = state.story("US-1")
    item = work_streams.WorkItem(
        id="US-1", kind="story", story_id="US-1", stream="backend",
        title="US-1", status=StoryStatus.FAILED, depends_on=(),
    )
    assert await pipeline._amaybe_split_on_failure(item, story, story, force=True)
    cal = state.calibration_for()
    assert cal.reactive_splits == 1
    assert state.sizing_lessons and "sous-dimensionnée" in state.sizing_lessons[0]
    assert "Trop grosse unité" in state.sizing_lessons[0]


def test_sizing_lessons_are_injected_into_the_next_s1_prompt():
    state = make_state()
    assert "LEÇONS DE DIMENSIONNEMENT" not in prompts.po_structure(state, "calc")
    state.sizing_lessons = ["Itération 1 : « X » sous-dimensionnée — découper plus fin."]
    p = prompts.po_structure(state, "calc")
    assert "LEÇONS DE DIMENSIONNEMENT" in p
    assert "sous-dimensionnée" in p


def test_over_budget_dev_files_are_counted_as_calibration_signal():
    state = make_state()
    story = UserStory(id="US-1", epic_id="E1", title="S")
    state.stories = [story]
    pipeline = Pipeline(state, FakeRunner([]))
    pipeline._observe_file_budget(story, {"files": ["f"] * (settings.task_file_budget + 1)})
    assert state.calibration_for(1).over_budget_tasks == 1
    pipeline._observe_file_budget(story, {"files": ["f"]})
    assert state.calibration_for(1).over_budget_tasks == 1   # under budget: unchanged


async def test_degradations_increment_the_calibration_counters(
    full_mode, monkeypatch
):
    monkeypatch.setattr(settings, "po_pipeline", "on")
    monkeypatch.setattr(settings, "po_pipeline_gherkin", False)
    bad = "{}"
    replies = [
        skeleton_reply([story_node("US-1")]),
        CRITIC_OK,
        bad, bad, bad, bad,              # S2 + mono-pass both fail
        CROSS_OK,
    ]
    pipeline, _ = make_pipeline(replies)
    await pipeline._aplan_phase()
    assert pipeline.state.calibration_for().degradations == 2
    assert pipeline.state.stories[0].spec_incomplete is True


# ------------------------------------------------------------- config gating

def test_po_pipeline_flag_is_off_by_default_and_safe_on_garbage(monkeypatch):
    assert settings.po_pipeline == "off"        # pinned by conftest
    assert settings.po_pipeline_on() is False
    monkeypatch.setattr(settings, "po_pipeline", "banana")
    assert settings.po_pipeline_on() is False   # malformed value stays OFF
    monkeypatch.setattr(settings, "po_pipeline", "on")
    assert settings.po_pipeline_on() is True


def test_repo_file_tree_lists_files_and_skips_noise(tmp_path):
    (tmp_path / "calc").mkdir()
    (tmp_path / "calc" / "core.py").write_text("x", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    files = pp.repo_file_tree(tmp_path)
    assert files == ["calc/core.py"]


def test_sizing_rules_is_the_single_shared_brain():
    """§5: the same fragment feeds S1, its critic, the cross critic and the
    reactive decompose_finer — one definition of « bonne taille »."""
    fragment = "RÈGLES DE DÉCOUPE"
    state = make_state()
    assert fragment in prompts.po_structure(state, "calc")
    assert fragment in prompts.structure_criteria()
    assert fragment in prompts.po_cross_review([])
    story = UserStory(id="US-1", epic_id="E1", title="S")
    assert fragment in prompts.decompose_finer(story, "calc")
    assert fragment in prompts.decompose_finer(story, "calc", proactive=True)
