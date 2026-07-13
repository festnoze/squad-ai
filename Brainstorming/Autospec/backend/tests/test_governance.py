"""V3-F3 (PO Backlog Governor, phase GOVERN) : à la fin de chaque itération, un
appel PO boss-tier décide chaque observation routée « po » (create_task/story/
epic, update/enrich d'une story NON livrée, defer/persist/dismiss), appliquée
DÉTERMINISTIQUEMENT sous garde-fous durs : stories livrées immuables (update →
converti en create_story), critères d'acceptance enrichis-seulement, quotas par
itération, validations du pipeline PO. GOVERNANCE_AUTO=0 (défaut) laisse les
décisions « proposed » — la file d'approbation humaine des endpoints
approve/reject (le policy engine F6 remplacera ce gate binaire).
"""

import json

import httpx
import pytest

from autospec.agents.runner import AgentResult, FakeRunner
from autospec.agents.scripted import ScriptedRunner
from autospec.api import server
from autospec.config import settings
from autospec.models import (
    AcceptanceCriterion,
    EngineeringObservation,
    Epic,
    GovernanceAction,
    GovernanceDecision,
    ObservationStatus,
    ObservationType,
    PipelinePhase,
    ProjectState,
    StoryStatus,
    Task,
    UserStory,
)
from autospec.orchestrator import governance, knowledge
from autospec.orchestrator.events import bus
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import load_state, save_state, workspace_dir


# ------------------------------------------------------------------- helpers

def _obs(oid="OBS-1", *, status=ObservationStatus.ROUTED, routed_to="po",
         obs_type=ObservationType.AMBIGUITY, **kw) -> EngineeringObservation:
    defaults = dict(
        summary="Critère ambigu sur l'arrondi",
        description="Le critère AC-2 contredit l'exemple du brief.",
        evidence=["[dev] extrait de transcription"],
        urgency="high",
        stream="backend",
        iteration=1,
    )
    defaults.update(kw)
    return EngineeringObservation(
        id=oid, type=obs_type, status=status, routed_to=routed_to, **defaults
    )


def _state(pid="gov", *, story_status=StoryStatus.DONE, observations=None) -> ProjectState:
    state = ProjectState(id=pid, name="gov", goal="g")
    state.epics.append(Epic(id="EPIC-1", title="E"))
    state.stories = [
        UserStory(
            id="US-1", epic_id="EPIC-1", title="Story de base", status=story_status,
            description="description d'origine", priority=2,
            acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="contrat vérifié")],
        )
    ]
    state.observations = observations if observations is not None else [_obs()]
    return state


def _decision(state, action, *, obs_id="OBS-1", target="", payload=None,
              rationale="parce que") -> GovernanceDecision:
    state.governance_seq += 1
    decision = GovernanceDecision(
        id=f"GOV-{state.governance_seq}", observation_id=obs_id, action=action,
        target_id=target, payload=payload or {}, rationale=rationale,
        iteration=state.iteration,
    )
    state.governance_log.append(decision)
    return decision


STORY_PAYLOAD = {
    "title": "Clarifier l'arrondi",
    "description": "En tant qu'utilisateur, je veux un arrondi spécifié.",
    "epic_id": "EPIC-1",
    "acceptance_criteria": ["L'arrondi bancaire est appliqué."],
    "gherkin": "Feature: Arrondi\n  Scenario: S\n    Given a\n    When b\n    Then c",
    "priority": 2,
}


# ------------------------------------------- US-F3.1 modèles + état legacy

def test_legacy_state_without_governance_loads():
    ws = workspace_dir("legacy-gov")
    ws.mkdir(parents=True, exist_ok=True)
    legacy = {"id": "legacy-gov", "name": "n", "goal": "g",
              "stories": [{"id": "US-1", "epic_id": "EPIC-1", "title": "S",
                           "acceptance_criteria": ["un critère legacy"]}]}
    (ws / "autospec-state.json").write_text(json.dumps(legacy), encoding="utf-8")

    state = load_state("legacy-gov")

    assert state is not None
    assert state.governance_log == []
    assert state.governance_seq == 0


def test_governance_decision_round_trip_through_storage():
    state = _state("gov-rt")
    decision = _decision(state, GovernanceAction.CREATE_STORY, payload=dict(STORY_PAYLOAD))

    save_state(state)
    loaded = load_state("gov-rt")

    assert loaded is not None
    assert loaded.governance_seq == 1
    assert loaded.governance_log == [decision]
    assert loaded.governance_log[0].action is GovernanceAction.CREATE_STORY


# ------------------------------------------- US-F3.1 phase GOVERN (squelette)

async def test_phase_flag_off_is_strict_noop():
    # conftest épingle governance_enabled=False : aucun appel LLM, aucun état
    # touché (FakeRunner([]) lèverait AgentError au moindre appel).
    pipeline = Pipeline(_state("gov-off"), FakeRunner([]))
    phase_before = pipeline.state.phase

    await pipeline._agovern_phase()

    assert pipeline.state.phase == phase_before
    assert pipeline.state.governance_log == []


async def test_phase_requires_observations_flag_too(monkeypatch):
    monkeypatch.setattr(settings, "governance_enabled", True)  # OBSERVATIONS off
    runner = FakeRunner([])
    pipeline = Pipeline(_state("gov-no-obs"), runner)
    await pipeline._agovern_phase()
    assert runner.calls == []


async def test_phase_noop_without_po_queue_or_pending_ideas(monkeypatch):
    monkeypatch.setattr(settings, "governance_enabled", True)
    monkeypatch.setattr(settings, "observations_enabled", True)
    # Une observation routée mémoire seule (pas « po ») ne déclenche rien.
    state = _state("gov-empty", observations=[
        _obs(routed_to="debt", status=ObservationStatus.PERSISTED)])
    runner = FakeRunner([])
    pipeline = Pipeline(state, runner)

    await pipeline._agovern_phase()

    assert runner.calls == []
    assert pipeline.state.phase != PipelinePhase.GOVERN


# --------------------------------------------- US-F3.2 sortie PO + fail-open

async def test_malformed_po_output_is_fail_open(monkeypatch):
    monkeypatch.setattr(settings, "governance_enabled", True)
    monkeypatch.setattr(settings, "observations_enabled", True)
    state = _state("gov-bad")
    pipeline = Pipeline(state, FakeRunner(["pas du json"]))

    await pipeline._agovern_phase()  # ne lève pas

    assert state.governance_log == []
    assert state.observations[0].status == ObservationStatus.ROUTED  # file intacte
    # 2) JSON valide mais décisions inexploitables → zéro décision, pas d'exception.
    bad = json.dumps({"decisions": [{"observation_id": "OBS-999", "action": "create_story"},
                                    {"observation_id": "OBS-1", "action": "nonsense"},
                                    "pas un objet"]})
    state2 = _state("gov-bad2")
    pipeline2 = Pipeline(state2, FakeRunner([bad]))
    await pipeline2._agovern_phase()
    assert state2.governance_log == []
    # 3) Le runner lui-même échoue → fail-open aussi.
    state3 = _state("gov-bad3")
    pipeline3 = Pipeline(state3, FakeRunner([]))
    await pipeline3._agovern_phase()
    assert state3.governance_log == []


def test_coerce_decisions_one_per_observation():
    state = _state("gov-coerce")
    kb = knowledge.KnowledgeBase()
    reply = {"decisions": [
        {"observation_id": "OBS-1", "action": "dismiss", "rationale": "hors sujet"},
        {"observation_id": "OBS-1", "action": "create_story"},  # doublon ignoré
    ]}
    decisions, warnings = governance.coerce_decisions(state, reply, kb)
    assert [d.id for d in decisions] == ["GOV-1"]
    assert decisions[0].action is GovernanceAction.DISMISS
    assert any("double" in w for w in warnings)


# --------------------------------------- US-F3.3 apply_decision (garde-fous)

def test_update_on_shipped_story_converts_to_create_story():
    state = _state("gov-conv")  # US-1 DONE
    kb = knowledge.KnowledgeBase()
    decision = _decision(state, GovernanceAction.UPDATE_STORY, target="US-1",
                         payload={"description": "nouvelle exigence"})

    outcome = governance.apply_decision(state, kb, decision)

    assert outcome == "converted"
    assert decision.status == "applied"
    assert decision.payload["applied_action"] == "create_story"
    assert "converti en create_story" in decision.rationale
    # La story livrée est INTACTE (description, critères, statut).
    original = state.story("US-1")
    assert original.description == "description d'origine"
    assert [c.text for c in original.acceptance_criteria] == ["contrat vérifié"]
    assert original.status == StoryStatus.DONE
    # La story d'évolution référence l'originale, itération suivante, TODO.
    created = state.story(decision.payload["created_story_id"])
    assert "US-1" in created.description
    assert created.depends_on == ["US-1"]
    assert created.status == StoryStatus.TODO
    assert created.iteration == state.iteration + 1
    assert state.observations[0].status == ObservationStatus.ACTIONED


def test_enrich_on_shipped_story_also_converts():
    state = _state("gov-conv2")
    kb = knowledge.KnowledgeBase()
    decision = _decision(state, GovernanceAction.ENRICH_CRITERIA, target="US-1",
                         payload={"acceptance_criteria": ["nouveau critère"]})
    assert governance.apply_decision(state, kb, decision) == "converted"
    created = state.story(decision.payload["created_story_id"])
    assert [c.text for c in created.acceptance_criteria] == ["nouveau critère"]
    assert [c.text for c in state.story("US-1").acceptance_criteria] == ["contrat vérifié"]


def test_enrich_appends_fresh_ids_never_removes():
    state = _state("gov-enrich", story_status=StoryStatus.TODO)
    kb = knowledge.KnowledgeBase()
    decision = _decision(state, GovernanceAction.ENRICH_CRITERIA, target="US-1",
                         payload={"acceptance_criteria": ["critère ajouté A", "critère ajouté B"]})

    assert governance.apply_decision(state, kb, decision) == "applied"

    story = state.story("US-1")
    assert [c.id for c in story.acceptance_criteria] == ["AC-1", "AC-2", "AC-3"]
    assert story.acceptance_criteria[0].text == "contrat vérifié"  # préservé verbatim
    assert [c.text for c in story.acceptance_criteria[1:]] == ["critère ajouté A", "critère ajouté B"]


def test_update_story_cannot_touch_acceptance_criteria():
    # Un payload d'update qui embarque des acceptance_criteria ne peut PAS les
    # réécrire : seuls description/priority sont applicables.
    state = _state("gov-noac", story_status=StoryStatus.TODO)
    kb = knowledge.KnowledgeBase()
    decision = _decision(state, GovernanceAction.UPDATE_STORY, target="US-1",
                         payload={"description": "desc révisée", "priority": 1,
                                  "acceptance_criteria": []})
    assert governance.apply_decision(state, kb, decision) == "applied"
    story = state.story("US-1")
    assert story.description == "desc révisée" and story.priority == 1
    assert [c.text for c in story.acceptance_criteria] == ["contrat vérifié"]
    # Sans aucun champ modifiable → invalid, rien d'appliqué.
    state.observations.append(_obs("OBS-2"))
    decision2 = _decision(state, GovernanceAction.UPDATE_STORY, obs_id="OBS-2",
                          target="US-1", payload={"acceptance_criteria": []})
    assert governance.apply_decision(state, kb, decision2) == "invalid"
    assert decision2.status == "invalid"
    assert [c.text for c in state.story("US-1").acceptance_criteria] == ["contrat vérifié"]


def test_quota_new_stories_overflows_to_deferred_idea():
    state = _state("gov-quota", observations=[_obs(f"OBS-{i}") for i in range(1, 6)])
    kb = knowledge.KnowledgeBase()
    outcomes = []
    for i in range(1, 5):  # limite GOVERN_MAX_NEW_STORIES=3
        payload = dict(STORY_PAYLOAD, title=f"Story gouvernée {i}")
        decision = _decision(state, GovernanceAction.CREATE_STORY,
                             obs_id=f"OBS-{i}", payload=payload)
        outcomes.append((decision, governance.apply_decision(state, kb, decision)))

    assert [o for _, o in outcomes] == ["applied", "applied", "applied", "converted"]
    assert len(state.stories) == 1 + 3  # US-1 + 3 créations, jamais 4
    fourth = outcomes[3][0]
    assert fourth.status == "applied"
    assert fourth.payload["applied_action"] == "defer"
    assert "quota" in fourth.rationale
    # Le dépassement est documenté ET capitalisé en idée en suspens.
    assert [i.title for i in kb.pending_ideas] == ["Story gouvernée 4"]
    assert state.observations[3].status == ObservationStatus.DEFERRED


def test_quota_new_epics_enforced():
    state = _state("gov-quota-epic", observations=[_obs("OBS-1"), _obs("OBS-2")])
    kb = knowledge.KnowledgeBase()
    d1 = _decision(state, GovernanceAction.CREATE_EPIC, obs_id="OBS-1",
                   payload={"title": "Epic gouverné"})
    d2 = _decision(state, GovernanceAction.CREATE_EPIC, obs_id="OBS-2",
                   payload={"title": "Epic de trop"})
    assert governance.apply_decision(state, kb, d1) == "applied"
    assert governance.apply_decision(state, kb, d2) == "converted"
    assert [e.title for e in state.epics] == ["E", "Epic gouverné"]
    assert d2.payload["applied_action"] == "defer"


def test_create_story_valid_unique_id_existing_epic():
    state = _state("gov-create")
    kb = knowledge.KnowledgeBase()
    decision = _decision(state, GovernanceAction.CREATE_STORY,
                         payload=dict(STORY_PAYLOAD, technical=True,
                                      contract="expose une API d'arrondi", priority=99))

    assert governance.apply_decision(state, kb, decision) == "applied"

    created = state.story(decision.payload["created_story_id"])
    assert created.id == "US-2"  # id unique suivant le schéma existant
    assert created.epic_id == "EPIC-1"
    assert created.status == StoryStatus.TODO
    assert created.iteration == state.iteration + 1
    assert created.priority == 5  # clampé 1..5
    assert created.technical is True and created.contract
    assert [c.id for c in created.acceptance_criteria] == ["AC-1"]


def test_create_story_invalid_payloads_apply_nothing():
    state = _state("gov-invalid", observations=[_obs(f"OBS-{i}") for i in range(1, 4)])
    kb = knowledge.KnowledgeBase()
    # Epic inconnu.
    d1 = _decision(state, GovernanceAction.CREATE_STORY, obs_id="OBS-1",
                   payload=dict(STORY_PAYLOAD, epic_id="EPIC-404"))
    # Dépendance inconnue (intégrité référentielle du pipeline PO).
    d2 = _decision(state, GovernanceAction.CREATE_STORY, obs_id="OBS-2",
                   payload=dict(STORY_PAYLOAD, depends_on=["US-404"]))
    # Titre manquant.
    d3 = _decision(state, GovernanceAction.CREATE_STORY, obs_id="OBS-3",
                   payload={"epic_id": "EPIC-1"})
    for decision in (d1, d2, d3):
        assert governance.apply_decision(state, kb, decision) == "invalid"
        assert decision.status == "invalid"
        assert decision.payload["error"]
    # AUCUNE application partielle : ni story, ni écriture mémoire, et les
    # observations sources restent en file (ROUTED).
    assert [s.id for s in state.stories] == ["US-1"]
    assert kb == knowledge.KnowledgeBase()
    assert all(o.status == ObservationStatus.ROUTED for o in state.observations)


def test_create_task_on_open_story_with_valid_stream_and_deps():
    state = _state("gov-task", story_status=StoryStatus.TODO)
    state.stories[0].tasks.append(
        Task(id="T-1", story_id="US-1", stream="backend", title="socle")
    )
    kb = knowledge.KnowledgeBase()
    decision = _decision(state, GovernanceAction.CREATE_TASK, target="US-1",
                         payload={"title": "brancher l'arrondi", "stream": "backend",
                                  "depends_on": ["T-1"],
                                  "acceptance_criteria": ["l'arrondi est branché"]})

    assert governance.apply_decision(state, kb, decision) == "applied"

    tasks = state.story("US-1").tasks
    assert [t.id for t in tasks] == ["T-1", "T-2"]
    assert tasks[1].depends_on == ["T-1"] and tasks[1].status == StoryStatus.TODO


def test_create_task_guardrails():
    state = _state("gov-task-bad", story_status=StoryStatus.TODO)
    story = state.stories[0]
    # T-1 pointe vers l'id que la nouvelle tâche recevra (T-2) : cycle détecté.
    story.tasks.append(Task(id="T-1", story_id="US-1", title="a", depends_on=["T-2"]))
    state.observations.extend([_obs("OBS-2"), _obs("OBS-3"), _obs("OBS-4")])
    kb = knowledge.KnowledgeBase()

    cyclic = _decision(state, GovernanceAction.CREATE_TASK, target="US-1",
                       payload={"title": "b", "depends_on": ["T-1"]})
    assert governance.apply_decision(state, kb, cyclic) == "invalid"
    assert "cycle" in cyclic.payload["error"]

    bad_stream = _decision(state, GovernanceAction.CREATE_TASK, obs_id="OBS-2",
                           target="US-1", payload={"title": "b", "stream": "warp"})
    assert governance.apply_decision(state, kb, bad_stream) == "invalid"

    unknown_dep = _decision(state, GovernanceAction.CREATE_TASK, obs_id="OBS-3",
                            target="US-1", payload={"title": "b", "depends_on": ["T-404"]})
    assert governance.apply_decision(state, kb, unknown_dep) == "invalid"

    done = _state("gov-task-done")  # US-1 DONE
    done_decision = _decision(done, GovernanceAction.CREATE_TASK, target="US-1",
                              payload={"title": "b"})
    assert governance.apply_decision(done, knowledge.KnowledgeBase(), done_decision) == "invalid"
    assert len(story.tasks) == 1  # aucune application partielle


def test_defer_creates_traced_pending_idea():
    state = _state("gov-defer")
    kb = knowledge.KnowledgeBase()
    decision = _decision(state, GovernanceAction.DEFER,
                         payload={"value_hint": "fort", "reevaluate_when": "après la v2"})

    assert governance.apply_decision(state, kb, decision) == "applied"

    idea = kb.pending_ideas[0]
    assert idea.title == state.observations[0].summary
    assert idea.value_hint == "fort" and idea.reevaluate_when == "après la v2"
    assert idea.source_observation_id == "OBS-1"
    assert state.observations[0].status == ObservationStatus.DEFERRED
    assert decision.payload["kb_dirty"] is True


def test_persist_writes_memory_and_marks_observation():
    state = _state("gov-persist")
    kb = knowledge.KnowledgeBase()
    decision = _decision(state, GovernanceAction.PERSIST, payload={"section": "debt"})

    assert governance.apply_decision(state, kb, decision) == "applied"

    assert kb.debt_register[0].source_observation_id == "OBS-1"
    assert state.observations[0].status == ObservationStatus.PERSISTED
    assert decision.payload["kb_dirty"] is True


def test_dismiss_requires_rationale():
    state = _state("gov-dismiss", observations=[_obs("OBS-1"), _obs("OBS-2")])
    kb = knowledge.KnowledgeBase()
    silent = _decision(state, GovernanceAction.DISMISS, rationale="   ")
    assert governance.apply_decision(state, kb, silent) == "invalid"
    assert state.observations[0].status == ObservationStatus.ROUTED

    motivated = _decision(state, GovernanceAction.DISMISS, obs_id="OBS-2",
                          rationale="doublon d'une story déjà planifiée")
    assert governance.apply_decision(state, kb, motivated) == "applied"
    assert state.observations[1].status == ObservationStatus.DISMISSED
    assert "doublon" in state.observations[1].resolution


def test_unknown_observation_is_invalid():
    state = _state("gov-unknown")
    decision = _decision(state, GovernanceAction.DISMISS, obs_id="OBS-404",
                         rationale="motif")
    assert governance.apply_decision(state, knowledge.KnowledgeBase(), decision) == "invalid"


def test_pending_idea_can_be_actioned_and_is_consumed():
    state = _state("gov-idea", observations=[])
    kb = knowledge.KnowledgeBase(pending_ideas=[
        knowledge.PendingIdea(id="idea-1", title="Exporter en CSV",
                              reevaluate_when="quand la liste existera")
    ])
    state.governance_seq += 1
    decision = GovernanceDecision(
        id="GOV-1", observation_id="idea-1", action=GovernanceAction.CREATE_STORY,
        payload=dict(STORY_PAYLOAD, title="Exporter en CSV"), rationale="condition atteinte",
        iteration=state.iteration,
    )
    state.governance_log.append(decision)

    assert governance.apply_decision(state, kb, decision) == "applied"

    assert kb.pending_ideas == []  # idée consommée
    assert decision.payload["kb_dirty"] is True
    assert any(s.title == "Exporter en CSV" for s in state.stories)


# ------------------------------------------ phase GOVERN (auto et approbation)

GOVERN_REPLY = json.dumps(
    {
        "message": "Une décision.",
        "decisions": [
            {"observation_id": "OBS-1", "action": "create_story", "target_id": "",
             "payload": STORY_PAYLOAD, "rationale": "l'ambiguïté mérite une story"}
        ],
    },
    ensure_ascii=False,
)


@pytest.fixture
def govern_on(monkeypatch):
    monkeypatch.setattr(settings, "governance_enabled", True)
    monkeypatch.setattr(settings, "observations_enabled", True)


async def test_phase_auto_applies_and_publishes(govern_on, monkeypatch):
    monkeypatch.setattr(settings, "governance_auto", True)
    state = _state("gov-auto")
    runner = FakeRunner([GOVERN_REPLY])
    pipeline = Pipeline(state, runner)
    queue = bus.subscribe()
    try:
        await pipeline._agovern_phase()
        events = []
        while not queue.empty():
            events.append(queue.get_nowait()[1])
    finally:
        bus.unsubscribe(queue)

    # Le prompt du gouverneur est en français, marqué, persona po-governor.
    assert len(runner.calls) == 1
    assert "GOUVERNANCE DU BACKLOG" in runner.calls[0]["prompt"]
    assert "OBS-1" in runner.calls[0]["prompt"]

    decision = state.governance_log[0]
    assert decision.status == "applied"
    created = state.story(decision.payload["created_story_id"])
    assert created.status == StoryStatus.TODO and created.iteration == 2
    assert state.observations[0].status == ObservationStatus.ACTIONED
    published = [e for e in events if e.get("type") == "governance_decision"]
    assert published and published[0]["decision"]["id"] == "GOV-1"
    assert not [e for e in events if e.get("type") == "approval_pending"]


async def test_phase_manual_queues_proposed_then_approve_applies(govern_on):
    # GOVERNANCE_AUTO=0 (défaut) : la décision reste « proposed » (LA file
    # d'approbation), rien n'est appliqué ; l'approbation applique — même
    # projet dormant (aucune lifecycle active ici).
    state = _state("gov-manual")
    pipeline = Pipeline(state, FakeRunner([GOVERN_REPLY]))
    queue = bus.subscribe()
    try:
        await pipeline._agovern_phase()
        events = []
        while not queue.empty():
            events.append(queue.get_nowait()[1])
    finally:
        bus.unsubscribe(queue)

    decision = state.governance_log[0]
    assert decision.status == "proposed"
    assert [s.id for s in state.stories] == ["US-1"]  # rien appliqué
    assert state.observations[0].status == ObservationStatus.ROUTED
    pending = [e for e in events if e.get("type") == "approval_pending"]
    assert pending and pending[0]["decision_ids"] == ["GOV-1"]

    approved = await pipeline.aapprove_governance("GOV-1")
    assert approved.status == "applied"
    assert state.story(approved.payload["created_story_id"]).status == StoryStatus.TODO
    with pytest.raises(ValueError):  # déjà traitée
        await pipeline.aapprove_governance("GOV-1")


async def test_reject_dismisses_the_source_observation(govern_on):
    state = _state("gov-rej")
    pipeline = Pipeline(state, FakeRunner([GOVERN_REPLY]))
    await pipeline._agovern_phase()

    rejected = await pipeline.areject_governance("GOV-1", "pas la priorité")

    assert rejected.status == "rejected_by_human"
    assert state.observations[0].status == ObservationStatus.DISMISSED
    assert "pas la priorité" in state.observations[0].resolution
    assert [s.id for s in state.stories] == ["US-1"]


# ----------------------------------------------- US-F3.4 endpoints HTTP

def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _persisted_project(pid: str) -> ProjectState:
    """Un projet DORMANT (état sur disque seulement, hors `pipelines`) portant
    une décision « proposed » — le chemin mi-dormance des endpoints."""
    state = _state(pid)
    _decision(state, GovernanceAction.CREATE_STORY, payload=dict(STORY_PAYLOAD))
    save_state(state)
    return state


async def test_governance_endpoints_list_approve_reject():
    _persisted_project("gov-api")
    async with _client() as client:
        listed = await client.get("/api/projects/gov-api/governance")
        assert listed.status_code == 200
        assert [d["id"] for d in listed.json()["decisions"]] == ["GOV-1"]
        assert listed.json()["decisions"][0]["status"] == "proposed"

        resp = await client.post("/api/projects/gov-api/governance/GOV-1/approve")
        assert resp.status_code == 200
        assert resp.json()["decision"]["status"] == "applied"

        again = await client.post("/api/projects/gov-api/governance/GOV-1/approve")
        assert again.status_code == 409

    # L'application mi-dormance est PERSISTÉE : la story existe au rechargement.
    reloaded = load_state("gov-api")
    created_id = reloaded.governance_log[0].payload["created_story_id"]
    created = reloaded.story(created_id)
    assert created.status == StoryStatus.TODO and created.iteration == 2
    assert reloaded.observations[0].status == ObservationStatus.ACTIONED


async def test_governance_reject_endpoint_and_404s():
    _persisted_project("gov-api-rej")
    async with _client() as client:
        resp = await client.post(
            "/api/projects/gov-api-rej/governance/GOV-1/reject",
            json={"reason": "non prioritaire"},
        )
        assert resp.status_code == 200
        assert resp.json()["decision"]["status"] == "rejected_by_human"

        unknown = await client.post("/api/projects/gov-api-rej/governance/GOV-9/approve")
        assert unknown.status_code == 404
        no_project = await client.get("/api/projects/gov-nope/governance")
        assert no_project.status_code == 404

    reloaded = load_state("gov-api-rej")
    assert reloaded.observations[0].status == ObservationStatus.DISMISSED


# ------------------------------- US-F3.5 bout-en-bout : cycle suivant (N+1)

OBS_REPLY_E2E = json.dumps(
    {
        "message": "Une découverte.",
        "observations": [
            {"type": "ambiguity",
             "summary": "Critère ambigu sur l'arrondi",
             "description": "Le critère contredit l'exemple.",
             "evidence": ["[dev] extrait"],
             "confidence": 0.8, "urgency": "high", "source_role": "dev"}
        ],
    },
    ensure_ascii=False,
)

CRITIC_REPLY_E2E = json.dumps(
    {
        "message": "Preuves solides.",
        "verdicts": [{"id": "OBS-1", "verdict": "validate", "confidence": 0.9,
                      "urgency": "high", "reason": "étayé"}],
    },
    ensure_ascii=False,
)


class _GovScripted(ScriptedRunner):
    """ScriptedRunner + réponses cannées observateur/critique/gouverneur."""

    def __init__(self):
        self.govern_prompts: list[str] = []

    async def arun(self, prompt, system_prompt, cwd=None, session_id=None, model=None):
        if "OBSERVATEUR D'INGÉNIERIE" in prompt:
            return AgentResult(text=OBS_REPLY_E2E, session_id="scripted-session")
        if "CRITIQUE DES OBSERVATIONS" in prompt:
            return AgentResult(text=CRITIC_REPLY_E2E, session_id="scripted-session")
        if "GOUVERNANCE DU BACKLOG" in prompt:
            self.govern_prompts.append(prompt)
            return AgentResult(text=GOVERN_REPLY, session_id="scripted-session")
        return await super().arun(
            prompt, system_prompt, cwd=cwd, session_id=session_id, model=model
        )


async def test_e2e_observation_to_story_built_next_iteration(monkeypatch):
    """Chemin nominal complet : build → observation extraite → validée/routée
    « po » → GOVERN décide create_story (auto) → story TODO à l'itération N+1 →
    reprise du flux existant : elle est CONSTRUITE au cycle suivant."""
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)
    monkeypatch.setattr(settings, "observations_enabled", True)
    monkeypatch.setattr(settings, "observation_critic_enabled", True)
    monkeypatch.setattr(settings, "governance_enabled", True)
    monkeypatch.setattr(settings, "governance_auto", True)
    state = ProjectState(id="gov-e2e", name="gov", goal="g")
    state.epics.append(Epic(id="EPIC-1", title="E"))
    state.stories = [
        UserStory(
            id="US-1", epic_id="EPIC-1", title="US-1",
            gherkin="Feature: F\n  Scenario: S\n    Given a\n    When b\n    Then c",
        )
    ]
    runner = _GovScripted()
    pipeline = Pipeline(state, runner)

    # Itération 1 : build → observation extraite, validée, routée « po ».
    await pipeline._abuild_phase()
    assert state.story("US-1").status == StoryStatus.DONE
    queued = governance.po_queue(state)
    assert len(queued) == 1 and queued[0].routed_to == "po"

    # Phase GOVERN : décision create_story appliquée (mode auto).
    await pipeline._agovern_phase()
    assert len(runner.govern_prompts) == 1
    decision = state.governance_log[0]
    assert decision.status == "applied"
    new_id = decision.payload["created_story_id"]
    created = state.story(new_id)
    assert created.status == StoryStatus.TODO
    assert created.iteration == state.iteration + 1
    assert queued[0].status == ObservationStatus.ACTIONED

    # Cycle suivant : le flux existant (filtre par itération) la construit.
    state.iteration += 1
    await pipeline._abuild_phase()
    assert state.story(new_id).effective_status() == StoryStatus.DONE
