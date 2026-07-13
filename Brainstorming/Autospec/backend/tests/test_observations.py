"""V3-F1 (Engineering Observations, socle) : après chaque work item terminé
(DONE **et** FAILED), un extracteur worker-tier lit la queue de transcription et
émet 0..N EngineeringObservation structurées — fail-open, derrière le flag
OBSERVATIONS (défaut OFF : zéro appel LLM supplémentaire). Les findings E6/S1
sont convertis en observations (source_role evaluator/security) en plus de la
plomberie feedback existante.
"""

import json

import pytest

from autospec.agents.runner import AgentResult, FakeRunner
from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import (
    AcceptanceCriterion,
    EngineeringObservation,
    Epic,
    ObservationStatus,
    ObservationType,
    PipelinePhase,
    ProjectState,
    StoryStatus,
    UserStory,
)
from autospec.orchestrator import streams as work_streams
from autospec.orchestrator.events import bus
from autospec.orchestrator.pipeline import Pipeline, _coerce_observations
from autospec.storage import load_state, save_state, workspace_dir

OBS_REPLY = json.dumps(
    {
        "message": "Deux découvertes durables.",
        "observations": [
            {
                "type": "workaround",
                "summary": "Contournement du parseur de dates",
                "description": "Le dev a remplacé le parseur par une regex.",
                "evidence": ["[dev] la lib dateutil manque, regex utilisée"],
                "impact": "module core — fragilité sur les formats exotiques",
                "confidence": 0.8,
                "urgency": "high",
                "workaround": "regex maison au lieu du parseur",
                "recommendations": ["réintroduire un vrai parseur"],
                "reevaluate_when": "quand dateutil sera installable",
                "source_role": "dev",
            },
            {
                # Champs hors bornes : clampés/normalisés, jamais rejetés.
                "type": "tech_debt",
                "summary": "Duplication du mapping d'erreurs",
                "confidence": 1.4,
                "urgency": "weird",
                "source_role": "alien",
            },
        ],
    },
    ensure_ascii=False,
)

EVAL_FINDINGS = json.dumps(
    {
        "message": "Un bug et une friction UX.",
        "findings": [
            {"id": "FND-1", "severity": "high", "kind": "bug",
             "title": "Crash au démarrage", "detail": "exception non gérée"},
            {"id": "FND-2", "severity": "low", "kind": "ux",
             "title": "Message confus", "detail": "libellé ambigu"},
        ],
    },
    ensure_ascii=False,
)

SEC_FINDINGS = json.dumps(
    {
        "message": "Une faille.",
        "findings": [
            {"id": "SEC-1", "severity": "high", "kind": "security",
             "title": "Injection SQL", "detail": "requête concaténée"},
        ],
    },
    ensure_ascii=False,
)

IMPACT_UPDATE = json.dumps(
    {
        "message": "On corrige via la story non implémentée.",
        "action": "update_story",
        "story_id": "US-1",
        "updates": {"description": "corrigée suite aux findings"},
    },
    ensure_ascii=False,
)


# ------------------------------------------------- US-F1.1 modèles/persistance

def test_legacy_state_without_observations_loads():
    """Un état persisté AVANT V3-F1 (sans observations/observation_seq) doit se
    charger sans erreur, avec les défauts sûrs."""
    ws = workspace_dir("legacy-obs")
    ws.mkdir(parents=True, exist_ok=True)
    legacy = {"id": "legacy-obs", "name": "n", "goal": "g",
              "stories": [{"id": "US-1", "epic_id": "EPIC-1", "title": "S",
                           "acceptance_criteria": ["un critère legacy"]}]}
    (ws / "autospec-state.json").write_text(json.dumps(legacy), encoding="utf-8")

    state = load_state("legacy-obs")

    assert state is not None
    assert state.observations == []
    assert state.observation_seq == 0


def test_observation_full_round_trip_through_storage():
    obs = EngineeringObservation(
        id="OBS-1",
        type=ObservationType.TECH_DEBT,
        summary="Duplication du mapping",
        description="Le mapping d'erreurs est copié dans deux modules.",
        evidence=["pkg/a.py", "pkg/b.py"],
        impact="maintenance double",
        confidence=0.7,
        urgency="high",
        workaround="copier-coller",
        recommendations=["extraire un module partagé"],
        reevaluate_when="au prochain refactor du module erreurs",
        source_role="dev",
        work_item_id="US-1",
        stream="backend",
        iteration=2,
        status=ObservationStatus.NEW,
        routed_to="debt",
        resolution="",
    )
    state = ProjectState(id="rt-obs", name="n", goal="g",
                         observations=[obs], observation_seq=1)

    save_state(state)
    loaded = load_state("rt-obs")

    assert loaded is not None
    assert loaded.observation_seq == 1
    assert loaded.observations == [obs]
    # Round-trip JSON pur (sans passer par le disque) aussi identique.
    again = ProjectState.model_validate_json(state.model_dump_json())
    assert again.observations == [obs]


def test_confidence_is_clamped_like_legacy_scores():
    obs = EngineeringObservation(id="OBS-1", type=ObservationType.RISK,
                                 summary="s", confidence=7.0)
    assert obs.confidence == 1.0
    obs2 = EngineeringObservation(id="OBS-2", type=ObservationType.RISK,
                                  summary="s", confidence=-3)
    assert obs2.confidence == 0.0


# ------------------------------------------------------ US-F1.2 parsing robuste

def test_coerce_observations_drops_malformed_entries_never_raises():
    reply = {
        "observations": [
            {"type": "nonsense", "summary": "type inconnu"},   # type invalide
            {"type": "risk", "summary": ""},                    # summary vide
            "pas un objet",                                     # pas un dict
            {"type": "pattern", "summary": "réservé au detector F5"},
        ]
    }
    assert _coerce_observations(reply, max_items=3) == []
    assert _coerce_observations({"observations": "pas une liste"}, max_items=3) == []
    assert _coerce_observations({}, max_items=3) == []


def test_coerce_observations_caps_and_normalizes():
    entry = {"type": "risk", "summary": "s", "confidence": 9, "urgency": "haute",
             "source_role": "alien", "evidence": ["e", "", 42]}
    reply = {"observations": [dict(entry) for _ in range(5)]}
    out = _coerce_observations(reply, max_items=3)
    assert len(out) == 3
    assert out[0]["confidence"] == 1.0
    assert out[0]["urgency"] == "normal"
    assert out[0]["source_role"] == "dev"
    assert out[0]["evidence"] == ["e", "42"]


# --------------------------------------------------------- US-F1.3 hook pipeline

def _work_item(status=StoryStatus.TODO) -> work_streams.WorkItem:
    return work_streams.WorkItem(
        id="US-1", kind="story", story_id="US-1", stream="backend",
        title="S", status=status, depends_on=(),
    )


def _hook_pipeline(replies, *, story_status=StoryStatus.DONE, last_error=""):
    state = ProjectState(id="obs-proj", name="obs", goal="g")
    state.epics.append(Epic(id="EPIC-1", title="E"))
    story = UserStory(
        id="US-1", epic_id="EPIC-1", title="Additionner", status=story_status,
        acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="la somme vaut 5")],
        last_error=last_error,
    )
    state.stories = [story]
    runner = FakeRunner(replies)
    return Pipeline(state, runner), story, runner


async def test_flag_off_makes_zero_extra_llm_calls():
    # conftest épingle observations_enabled=False : l'extraction doit être un
    # no-op strict (FakeRunner([]) lèverait AgentError au moindre appel).
    pipeline, story, runner = _hook_pipeline([], story_status=StoryStatus.DONE)
    await pipeline._aextract_observations(_work_item(), story, story)
    assert runner.calls == []
    assert pipeline.state.observations == []
    assert pipeline.state.observation_seq == 0


async def test_done_item_yields_observations_and_bus_event(monkeypatch):
    monkeypatch.setattr(settings, "observations_enabled", True)
    pipeline, story, runner = _hook_pipeline([OBS_REPLY], story_status=StoryStatus.DONE)
    queue = bus.subscribe()
    try:
        await pipeline._aextract_observations(_work_item(), story, story)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait()[1])
    finally:
        bus.unsubscribe(queue)

    assert len(runner.calls) == 1
    # Le prompt est en français, marqué observateur, et porte l'item + son AC.
    prompt = runner.calls[0]["prompt"]
    assert "OBSERVATEUR D'INGÉNIERIE" in prompt
    assert "US-1" in prompt and "la somme vaut 5" in prompt
    assert "engineering observer" in runner.calls[0]["system_prompt"]

    obs = pipeline.state.observations
    assert [o.id for o in obs] == ["OBS-1", "OBS-2"]
    assert pipeline.state.observation_seq == 2
    assert obs[0].type == ObservationType.WORKAROUND
    assert obs[0].urgency == "high" and obs[0].confidence == 0.8
    assert obs[0].work_item_id == "US-1"
    assert obs[0].stream == "backend"
    assert obs[0].iteration == pipeline.state.iteration
    assert obs[0].status == ObservationStatus.NEW
    # Entrée hors bornes : clampée, jamais rejetée.
    assert obs[1].confidence == 1.0 and obs[1].urgency == "normal"
    assert obs[1].source_role == "dev"
    # Événement SSE « observation » publié sur le bus.
    published = [e for e in events if e.get("type") == "observation"]
    assert len(published) == 2
    assert published[0]["project_id"] == "obs-proj"
    assert published[0]["observation"]["id"] == "OBS-1"


async def test_failed_item_also_yields_observations(monkeypatch):
    monkeypatch.setattr(settings, "observations_enabled", True)
    pipeline, story, runner = _hook_pipeline(
        [OBS_REPLY], story_status=StoryStatus.FAILED, last_error="assert 4 == 5",
    )
    await pipeline._aextract_observations(_work_item(), story, story)
    assert len(runner.calls) == 1
    # L'échec (le plus riche en découvertes) entre dans le prompt.
    assert "failed" in runner.calls[0]["prompt"]
    assert "assert 4 == 5" in runner.calls[0]["prompt"]
    assert len(pipeline.state.observations) == 2


async def test_non_terminal_item_is_skipped_even_flag_on(monkeypatch):
    # Un item re-queué (TODO) n'est PAS observé : il le sera à son passage terminal.
    monkeypatch.setattr(settings, "observations_enabled", True)
    pipeline, story, runner = _hook_pipeline([], story_status=StoryStatus.TODO)
    await pipeline._aextract_observations(_work_item(), story, story)
    assert runner.calls == []
    assert pipeline.state.observations == []


async def test_malformed_extractor_output_is_fail_open(monkeypatch):
    monkeypatch.setattr(settings, "observations_enabled", True)
    # 1) Pas de JSON du tout → extract_json lève, l'extraction avale et continue.
    pipeline, story, _ = _hook_pipeline(["pas du json"], story_status=StoryStatus.DONE)
    await pipeline._aextract_observations(_work_item(), story, story)  # ne lève pas
    assert pipeline.state.observations == []
    # 2) JSON valide mais entrées invalides → 0 observation, pas d'exception.
    bad = json.dumps({"observations": [{"type": "nonsense", "summary": "x"}]})
    pipeline2, story2, _ = _hook_pipeline([bad], story_status=StoryStatus.DONE)
    await pipeline2._aextract_observations(_work_item(), story2, story2)
    assert pipeline2.state.observations == []
    # 3) Le runner lui-même échoue (FakeRunner vide) → toujours fail-open.
    pipeline3, story3, _ = _hook_pipeline([], story_status=StoryStatus.DONE)
    monkeypatch.setattr(settings, "observations_enabled", True)
    await pipeline3._aextract_observations(_work_item(), story3, story3)
    assert pipeline3.state.observations == []


# ------------------------------ US-F1.3 intégration réelle _abuild_work_item

class _ObsScripted(ScriptedRunner):
    """ScriptedRunner + réponse cannée pour le prompt de l'observateur."""

    def __init__(self, obs_reply: str = OBS_REPLY):
        self.obs_reply = obs_reply
        self.observer_prompts: list[str] = []

    async def arun(self, prompt, system_prompt, cwd=None, session_id=None, model=None):
        if "OBSERVATEUR D'INGÉNIERIE" in prompt:
            self.observer_prompts.append(prompt)
            return AgentResult(text=self.obs_reply, session_id="scripted-session")
        return await super().arun(
            prompt, system_prompt, cwd=cwd, session_id=session_id, model=model
        )


def _streams_state(project_id="obs-wt"):
    state = ProjectState(id=project_id, name="obsapp", goal="g")
    state.epics.append(Epic(id="EPIC-1", title="E"))
    state.stories = [
        UserStory(
            id="US-1", epic_id="EPIC-1", title="US-1",
            gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
        )
    ]
    return state


@pytest.fixture
def streams_on(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)


async def test_build_work_item_done_extracts_observations(streams_on, monkeypatch):
    monkeypatch.setattr(settings, "observations_enabled", True)
    runner = _ObsScripted()
    pipeline = Pipeline(_streams_state("obs-wt-done"), runner)

    await pipeline._abuild_phase()

    assert pipeline.state.story("US-1").status == StoryStatus.DONE
    assert len(runner.observer_prompts) == 1  # un seul appel, à l'issue terminale
    assert [o.work_item_id for o in pipeline.state.observations] == ["US-1", "US-1"]
    # L'appel de l'extracteur est capturé dans le sidecar de l'item (O2).
    recs = pipeline.interactions.for_item("US-1")
    assert any(r.persona == "observer" for r in recs)


async def test_build_work_item_failed_extracts_observations(streams_on, monkeypatch):
    monkeypatch.setattr(settings, "observations_enabled", True)
    monkeypatch.setattr(settings, "dev_max_attempts", 1)
    runner = _ObsScripted()
    pipeline = Pipeline(_streams_state("obs-wt-fail"), runner)

    async def _red(subject, worktree, pkg, is_frontend):
        return False, "rouge : assert 4 == 5"

    monkeypatch.setattr(pipeline, "_arun_item_dev", _red)
    await pipeline._abuild_phase()

    assert pipeline.state.story("US-1").status == StoryStatus.FAILED
    assert len(runner.observer_prompts) == 1
    assert len(pipeline.state.observations) == 2


async def test_build_work_item_flag_off_never_calls_the_observer(streams_on):
    # conftest épingle le flag OFF : le chemin _abuild_work_item ne doit émettre
    # AUCUN appel observateur ni observation (zéro appel LLM supplémentaire).
    runner = _ObsScripted()
    pipeline = Pipeline(_streams_state("obs-wt-off"), runner)

    await pipeline._abuild_phase()

    assert pipeline.state.story("US-1").status == StoryStatus.DONE
    assert runner.observer_prompts == []
    assert pipeline.state.observations == []


# ------------------------------------------------- US-F1.4 raccordement E6/S1

@pytest.fixture
def no_real_run(monkeypatch):
    """Ne jamais lancer le `uv run python main.py` non fiable en test."""

    async def _fake_exercise(self):
        return "(processus terminé, code 0)\nsortie simulée"

    monkeypatch.setattr(Pipeline, "_aexercise_product", _fake_exercise)


def _done_pipeline(replies) -> Pipeline:
    state = ProjectState(
        id="obs-eval", name="todo", goal="g", phase=PipelinePhase.DONE, brief="# Brief",
        epics=[Epic(id="EPIC-1", title="E")],
        stories=[
            UserStory(
                id="US-1", epic_id="EPIC-1", title="Story à venir",
                status=StoryStatus.TODO,
                acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="c")],
            )
        ],
    )
    return Pipeline(state, FakeRunner(replies))


async def test_evaluator_findings_become_typed_observations(no_real_run, monkeypatch):
    monkeypatch.setattr(settings, "observations_enabled", True)
    pipeline = _done_pipeline([EVAL_FINDINGS, IMPACT_UPDATE])

    await pipeline._aevaluate_phase(force=True)

    obs = pipeline.state.observations
    assert len(obs) == 2
    assert all(o.source_role == "evaluator" for o in obs)
    # bug → risk ; ux → improvement ; sévérité → urgence.
    assert obs[0].type == ObservationType.RISK and obs[0].urgency == "high"
    assert obs[0].summary == "Crash au démarrage"
    assert obs[1].type == ObservationType.IMPROVEMENT and obs[1].urgency == "low"
    # La plomberie feedback existante est CONSERVÉE en plus des observations.
    assert any("Crash au démarrage" in f for f in pipeline.state.feedback)
    assert len(pipeline.state.findings) == 2


@pytest.fixture
def no_real_audit(monkeypatch):
    """Ne jamais lancer pip-audit/npm audit contre le workspace en test."""

    async def _fake_audit(self):
        return "(audit simulé : aucune dépendance vulnérable)"

    monkeypatch.setattr(Pipeline, "_arun_dep_audit", _fake_audit)


async def test_security_findings_become_risk_observations(no_real_audit, monkeypatch):
    monkeypatch.setattr(settings, "observations_enabled", True)
    pipeline = _done_pipeline([SEC_FINDINGS, IMPACT_UPDATE])

    await pipeline._asecurity_phase(force=True)

    obs = pipeline.state.observations
    assert len(obs) == 1
    assert obs[0].source_role == "security"
    assert obs[0].type == ObservationType.RISK and obs[0].urgency == "high"
    assert "SEC-1" in obs[0].evidence[0]
    assert any("Injection SQL" in f for f in pipeline.state.feedback)


async def test_findings_conversion_is_flag_gated(no_real_run):
    # Flag OFF (conftest) : les findings suivent la plomberie existante SEULE.
    pipeline = _done_pipeline([EVAL_FINDINGS, IMPACT_UPDATE])
    await pipeline._aevaluate_phase(force=True)
    assert pipeline.state.findings != []
    assert pipeline.state.observations == []
