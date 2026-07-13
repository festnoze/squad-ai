"""V3-F2 (Observation Critic & Router) : critique déterministe (rejet sans
preuve, fusion des quasi-doublons), critique LLM batché fail-open (rôle
``observation-critic`` distinct de l'extracteur), puis routeur déterministe
type→destination avec écritures mémoire F4 — le tout derrière OBSERVATIONS +
OBSERVATION_CRITIC (défaut critique ON, mais chaîne inerte sans OBSERVATIONS).
"""

import json

import pytest

from autospec.agents.personas import persona
from autospec.agents.runner import FakeRunner
from autospec.config import PERSONA_TIERS, settings
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
from autospec.orchestrator import knowledge, observations
from autospec.orchestrator import streams as work_streams
from autospec.orchestrator.events import bus
from autospec.orchestrator.pipeline import Pipeline


def _obs(
    oid="OBS-1",
    *,
    obs_type=ObservationType.TECH_DEBT,
    summary="Duplication du mapping d'erreurs entre deux modules",
    description="",
    evidence=None,
    stream="backend",
    urgency="normal",
    confidence=0.5,
    source_role="dev",
    **kw,
) -> EngineeringObservation:
    return EngineeringObservation(
        id=oid,
        type=obs_type,
        summary=summary,
        description=description,
        evidence=["preuve : extrait de transcription"] if evidence is None else evidence,
        stream=stream,
        urgency=urgency,
        confidence=confidence,
        source_role=source_role,
        **kw,
    )


# ---------------------------------------------- US-F2.1 critique déterministe

def test_token_similarity_bounds():
    assert observations.token_similarity("le mapping d'erreurs", "le mapping d'erreurs") == 1.0
    assert observations.token_similarity("alpha beta", "gamma delta") == 0.0
    assert observations.token_similarity("", "quelque chose") == 0.0
    # Casse et ponctuation neutralisées.
    assert observations.token_similarity("Mapping, Erreurs !", "mapping erreurs") == 1.0


def test_reject_when_summary_or_evidence_missing():
    no_evidence = _obs("OBS-1", evidence=[])
    blank_evidence = _obs("OBS-2", evidence=["   "])
    no_summary = _obs("OBS-3", summary="   ")

    result = observations.deterministic_critic(
        [no_evidence, blank_evidence, no_summary], [], threshold=0.75
    )

    assert result.survivors == []
    assert result.rejected == [no_evidence, blank_evidence, no_summary]
    for obs in result.rejected:
        assert obs.status == ObservationStatus.REJECTED
        assert "rejet déterministe" in obs.resolution


def test_near_duplicate_merges_into_existing_and_boosts_confidence():
    kept = _obs("OBS-1", confidence=0.6, evidence=["preuve initiale"])
    dup = _obs(
        "OBS-2",
        summary="Duplication du mapping d'erreurs entre deux modules du backend",
        confidence=0.8,
        evidence=["preuve initiale", "nouvelle preuve"],
    )

    result = observations.deterministic_critic([dup], [kept], threshold=0.75)

    assert result.survivors == [] and result.rejected == []
    assert result.merged == [(dup, kept)]
    # Signal répété = signal fort : preuve ajoutée (sans doublon), confiance
    # accrue min(1.0, max(old, new) + 0.15), trace de fusion comptée.
    assert kept.evidence == ["preuve initiale", "nouvelle preuve"]
    assert kept.confidence == pytest.approx(0.95)
    assert kept.merged_count == 1


def test_merge_confidence_is_capped_at_one():
    kept = _obs("OBS-1", confidence=0.9)
    dup = _obs("OBS-2", confidence=0.95)
    observations.deterministic_critic([dup], [kept], threshold=0.5)
    assert kept.confidence == 1.0


def test_duplicate_of_other_stream_or_rejected_is_not_merged():
    other_stream = _obs("OBS-1", stream="frontend")
    rejected = _obs("OBS-2", status=ObservationStatus.REJECTED)
    dismissed = _obs("OBS-3", status=ObservationStatus.DISMISSED)
    new = _obs("OBS-4")

    result = observations.deterministic_critic(
        [new], [other_stream, rejected, dismissed], threshold=0.5
    )

    assert result.survivors == [new]
    assert result.merged == []


def test_in_batch_duplicates_merge_into_the_first_survivor():
    first = _obs("OBS-1", confidence=0.5)
    second = _obs("OBS-2", confidence=0.5, evidence=["autre preuve"])

    result = observations.deterministic_critic([first, second], [], threshold=0.75)

    assert result.survivors == [first]
    assert result.merged == [(second, first)]
    assert first.merged_count == 1
    assert "autre preuve" in first.evidence


def test_dissimilar_observations_all_survive():
    a = _obs("OBS-1", summary="Le parseur de dates est fragile")
    b = _obs("OBS-2", summary="Aucun cache sur la route la plus chargée")
    result = observations.deterministic_critic([a, b], [], threshold=0.75)
    assert result.survivors == [a, b]


# --------------------------------------------------- US-F2.2 critique LLM batché

def _critic_reply(*verdicts) -> str:
    return json.dumps({"message": "Jugement rendu.", "verdicts": list(verdicts)},
                      ensure_ascii=False)


async def test_llm_critic_is_one_batched_call_and_applies_verdicts():
    state = ProjectState(id="crit", name="n", goal="g")
    a = _obs("OBS-1", confidence=0.5, urgency="normal")
    b = _obs("OBS-2", obs_type=ObservationType.RISK,
             summary="Cas limite non couvert par les tests", confidence=0.9)
    runner = FakeRunner([
        _critic_reply(
            {"id": "OBS-1", "verdict": "validate", "confidence": 0.85,
             "urgency": "high", "reason": "preuves solides"},
            {"id": "OBS-2", "verdict": "reject", "reason": "spéculatif, aucune preuve"},
        )
    ])

    await observations.acritic_llm(state, [a, b], runner.arun)

    # UN SEUL appel batché pour N observations, rôle observation-critic (jamais
    # l'extracteur : personne ne valide son propre travail).
    assert len(runner.calls) == 1
    prompt = runner.calls[0]["prompt"]
    assert "CRITIQUE DES OBSERVATIONS" in prompt
    assert "OBS-1" in prompt and "OBS-2" in prompt
    assert runner.calls[0]["system_prompt"] == persona("observation-critic")
    assert persona("observation-critic") != persona("observer")

    assert a.status == ObservationStatus.VALIDATED
    assert a.confidence == 0.85 and a.urgency == "high"
    assert b.status == ObservationStatus.REJECTED
    assert b.resolution == "spéculatif, aucune preuve"


async def test_llm_critic_clamps_and_normalizes_revisions():
    state = ProjectState(id="crit2", name="n", goal="g")
    a = _obs("OBS-1", confidence=0.5, urgency="normal")
    runner = FakeRunner([
        _critic_reply({"id": "OBS-1", "verdict": "validate",
                       "confidence": 7, "urgency": "bizarre"})
    ])
    await observations.acritic_llm(state, [a], runner.arun)
    assert a.status == ObservationStatus.VALIDATED
    assert a.confidence == 1.0        # clampée 0..1
    assert a.urgency == "normal"      # urgence inconnue ignorée


async def test_llm_critic_missing_verdict_validates_unchanged():
    state = ProjectState(id="crit3", name="n", goal="g")
    a = _obs("OBS-1", confidence=0.4)
    b = _obs("OBS-2", confidence=0.6,
             summary="Le module de cache n'a aucune invalidation")
    runner = FakeRunner([
        _critic_reply({"id": "OBS-2", "verdict": "validate", "confidence": 0.7})
    ])
    await observations.acritic_llm(state, [a, b], runner.arun)
    # OBS-1 sans verdict : fail-open par item, VALIDATED confidence inchangée.
    assert a.status == ObservationStatus.VALIDATED and a.confidence == 0.4
    assert b.confidence == 0.7


async def test_llm_critic_failure_is_fail_open():
    state = ProjectState(id="crit4", name="n", goal="g")
    survivors = [_obs("OBS-1", confidence=0.4), _obs("OBS-2", confidence=0.9)]
    # 1) Le runner échoue (FakeRunner vide → AgentError).
    await observations.acritic_llm(state, survivors, FakeRunner([]).arun)
    assert all(o.status == ObservationStatus.VALIDATED for o in survivors)
    assert [o.confidence for o in survivors] == [0.4, 0.9]  # inchangées
    # 2) Réponse non-JSON → même contrat.
    survivors2 = [_obs("OBS-3")]
    await observations.acritic_llm(state, survivors2, FakeRunner(["pas du json"]).arun)
    assert survivors2[0].status == ObservationStatus.VALIDATED


def test_observation_critic_registered_as_checker_tier():
    assert PERSONA_TIERS["observation-critic"] == "checker"


# ------------------------------------------------- US-F2.3 routeur déterministe

@pytest.mark.parametrize(
    "obs_type, urgency, expected",
    [
        (ObservationType.AMBIGUITY, "normal", ["po"]),
        (ObservationType.AMBIGUITY, "critical", ["po"]),
        (ObservationType.IMPROVEMENT, "normal", ["po"]),
        (ObservationType.IMPROVEMENT, "high", ["po"]),
        (ObservationType.LIMITATION, "low", ["po"]),
        (ObservationType.LIMITATION, "high", ["po"]),
        (ObservationType.REFACTORING, "normal", ["architecture"]),
        (ObservationType.REFACTORING, "high", ["architecture", "po"]),
        (ObservationType.REFACTORING, "critical", ["architecture", "po"]),
        (ObservationType.CONSTRAINT, "low", ["architecture"]),
        (ObservationType.CONSTRAINT, "high", ["architecture", "po"]),
        (ObservationType.PATTERN, "normal", ["architecture"]),
        (ObservationType.PATTERN, "critical", ["architecture", "po"]),
        (ObservationType.TECH_DEBT, "normal", ["debt"]),
        (ObservationType.TECH_DEBT, "critical", ["debt"]),
        (ObservationType.RISK, "normal", ["risk"]),
        (ObservationType.RISK, "high", ["risk"]),
        (ObservationType.WORKAROUND, "low", ["debt"]),
        (ObservationType.WORKAROUND, "normal", ["debt"]),
        (ObservationType.WORKAROUND, "high", ["debt", "po"]),
        (ObservationType.WORKAROUND, "critical", ["debt", "po"]),
    ],
)
def test_routing_table_is_exhaustive(obs_type, urgency, expected):
    obs = _obs(obs_type=obs_type, urgency=urgency)
    assert observations.route_observation(obs) == expected


@pytest.mark.parametrize("obs_type", list(ObservationType))
def test_security_source_role_always_routes_to_security(obs_type):
    obs = _obs(obs_type=obs_type, urgency="critical", source_role="security")
    assert observations.route_observation(obs) == ["security"]


def test_coerce_llm_routes_drops_unknown_destinations():
    reply = {
        "routes": [
            {"id": "OBS-1", "destinations": ["po", "lune", "po"]},
            {"id": "OBS-2", "destinations": ["nulle-part"]},
            {"id": "", "destinations": ["po"]},
            "pas un objet",
        ]
    }
    assert observations.coerce_llm_routes(reply) == {"OBS-1": ["po"]}
    assert observations.coerce_llm_routes({"routes": "rien"}) == {}


# ------------------------------------- chaîne complète (aprocess) + transitions

def _chain_state(obs_list) -> ProjectState:
    state = ProjectState(id="chain", name="n", goal="g")
    state.observations.extend(obs_list)
    state.observation_seq = len(obs_list)
    return state


async def test_process_routes_and_persists_statuses(monkeypatch):
    monkeypatch.setattr(settings, "observation_dedup_threshold", 0.75)
    debt = _obs("OBS-1", obs_type=ObservationType.TECH_DEBT)          # → debt seul
    workaround = _obs(
        "OBS-2", obs_type=ObservationType.WORKAROUND, urgency="high",
        summary="Contournement du parseur de dates par une regex",
        workaround="regex maison",
    )                                                                  # → debt + po
    state = _chain_state([debt, workaround])
    kb = knowledge.KnowledgeBase()
    runner = FakeRunner([
        _critic_reply(
            {"id": "OBS-1", "verdict": "validate", "confidence": 0.8, "urgency": "normal"},
            {"id": "OBS-2", "verdict": "validate", "confidence": 0.9, "urgency": "high"},
        )
    ])

    outcome = await observations.aprocess_new_observations(
        state, [debt, workaround], kb, runner.arun
    )

    # NEW → VALIDATED → ROUTED, puis PERSISTED seulement sans destination po.
    assert debt.status == ObservationStatus.PERSISTED
    assert debt.routed_to == "debt"
    assert workaround.status == ObservationStatus.ROUTED  # po = file F3, pas PERSISTED
    assert workaround.routed_to == "debt,po"              # représentation multi-destination
    assert outcome.kb_dirty
    assert [d.source_observation_id for d in kb.debt_register] == ["OBS-1", "OBS-2"]


async def test_process_removes_merged_duplicates_from_state(monkeypatch):
    monkeypatch.setattr(settings, "observation_dedup_threshold", 0.75)
    kept = _obs("OBS-1", confidence=0.5)
    kept.status = ObservationStatus.PERSISTED   # déjà passée par la chaîne
    dup = _obs("OBS-2", confidence=0.6, evidence=["nouvelle preuve"])
    state = _chain_state([kept, dup])
    kb = knowledge.KnowledgeBase()

    outcome = await observations.aprocess_new_observations(
        state, [dup], kb, FakeRunner([]).arun
    )

    # Le doublon fusionné DISPARAÎT de l'état ; la cible garde la trace.
    assert [o.id for o in state.observations] == ["OBS-1"]
    assert kept.merged_count == 1 and "nouvelle preuve" in kept.evidence
    assert outcome.merged == [(dup, kept)]
    assert not outcome.kb_dirty
    # Aucun survivant → AUCUN appel LLM critique (pas d'appel gaspillé).
    assert outcome.survivors == []


async def test_process_rejected_survivor_is_not_routed():
    reject = _obs("OBS-1")
    state = _chain_state([reject])
    kb = knowledge.KnowledgeBase()
    runner = FakeRunner([
        _critic_reply({"id": "OBS-1", "verdict": "reject", "reason": "non étayé"})
    ])

    await observations.aprocess_new_observations(state, [reject], kb, runner.arun)

    assert reject.status == ObservationStatus.REJECTED
    assert reject.routed_to == ""
    assert kb.debt_register == []


async def test_llm_router_refines_low_confidence_routes(monkeypatch):
    monkeypatch.setattr(settings, "observation_router_llm", True)
    ambiguous = _obs("OBS-1", obs_type=ObservationType.TECH_DEBT, confidence=0.3)
    state = _chain_state([ambiguous])
    kb = knowledge.KnowledgeBase()
    runner = FakeRunner([
        _critic_reply({"id": "OBS-1", "verdict": "validate", "confidence": 0.3}),
        json.dumps({"message": "ok", "routes": [{"id": "OBS-1", "destinations": ["po"]}]}),
    ])

    await observations.aprocess_new_observations(state, [ambiguous], kb, runner.arun)

    assert len(runner.calls) == 2
    assert "ROUTEUR DES OBSERVATIONS" in runner.calls[1]["prompt"]
    assert ambiguous.routed_to == "po"       # la table (debt) est supplantée
    assert ambiguous.status == ObservationStatus.ROUTED
    assert kb.debt_register == []            # plus d'écriture mémoire


async def test_llm_router_failure_keeps_table_routes(monkeypatch):
    monkeypatch.setattr(settings, "observation_router_llm", True)
    ambiguous = _obs("OBS-1", obs_type=ObservationType.TECH_DEBT, confidence=0.3)
    state = _chain_state([ambiguous])
    kb = knowledge.KnowledgeBase()
    # Un seul reply : le critique passe, le routeur LLM échoue → table conservée.
    runner = FakeRunner([
        _critic_reply({"id": "OBS-1", "verdict": "validate", "confidence": 0.3})
    ])

    await observations.aprocess_new_observations(state, [ambiguous], kb, runner.arun)

    assert ambiguous.routed_to == "debt"
    assert ambiguous.status == ObservationStatus.PERSISTED
    assert len(kb.debt_register) == 1


async def test_llm_router_not_consulted_for_confident_routes(monkeypatch):
    monkeypatch.setattr(settings, "observation_router_llm", True)
    confident = _obs("OBS-1", obs_type=ObservationType.RISK, confidence=0.9,
                     summary="Cas limite non couvert")
    state = _chain_state([confident])
    runner = FakeRunner([
        _critic_reply({"id": "OBS-1", "verdict": "validate", "confidence": 0.9})
    ])

    await observations.aprocess_new_observations(
        state, [confident], knowledge.KnowledgeBase(), runner.arun
    )

    assert len(runner.calls) == 1  # critique seul : pas d'appel routeur
    assert confident.routed_to == "risk"


# ------------------------------------------------- intégration pipeline (F1→F2)

OBS_REPLY = json.dumps(
    {
        "message": "Deux découvertes.",
        "observations": [
            {
                "type": "workaround",
                "summary": "Contournement du parseur de dates",
                "description": "Regex maison au lieu du parseur.",
                "evidence": ["[dev] dateutil manquant, regex utilisée"],
                "confidence": 0.8,
                "urgency": "high",
                "workaround": "regex maison au lieu du parseur",
                "source_role": "dev",
            },
            {
                "type": "tech_debt",
                "summary": "Mapping d'erreurs recopié dans deux modules",
                "evidence": ["pkg/a.py", "pkg/b.py"],
                "confidence": 0.6,
                "urgency": "normal",
                "source_role": "dev",
            },
        ],
    },
    ensure_ascii=False,
)

CRITIC_REPLY = _critic_reply(
    {"id": "OBS-1", "verdict": "validate", "confidence": 0.9, "urgency": "high",
     "reason": "preuve concrète"},
    {"id": "OBS-2", "verdict": "validate", "confidence": 0.7, "urgency": "normal",
     "reason": "chemins fournis"},
)


def _work_item(status=StoryStatus.DONE) -> work_streams.WorkItem:
    return work_streams.WorkItem(
        id="US-1", kind="story", story_id="US-1", stream="backend",
        title="S", status=status, depends_on=(),
    )


def _hook_pipeline(replies, *, story_status=StoryStatus.DONE):
    state = ProjectState(id="f2-proj", name="f2", goal="g")
    state.epics.append(Epic(id="EPIC-1", title="E"))
    story = UserStory(
        id="US-1", epic_id="EPIC-1", title="Additionner", status=story_status,
        acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="la somme vaut 5")],
    )
    state.stories = [story]
    runner = FakeRunner(replies)
    return Pipeline(state, runner), story, runner


async def test_full_chain_from_extraction(monkeypatch):
    monkeypatch.setattr(settings, "observations_enabled", True)
    monkeypatch.setattr(settings, "observation_critic_enabled", True)
    pipeline, story, runner = _hook_pipeline([OBS_REPLY, CRITIC_REPLY])
    queue = bus.subscribe()
    try:
        await pipeline._aextract_observations(_work_item(), story, story)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait()[1])
    finally:
        bus.unsubscribe(queue)

    # Extracteur + critique batché = 2 appels, pas un de plus.
    assert len(runner.calls) == 2
    obs = pipeline.state.observations
    assert [o.id for o in obs] == ["OBS-1", "OBS-2"]
    # workaround high → debt + po : reste ROUTED (file de gouvernance F3).
    assert obs[0].status == ObservationStatus.ROUTED
    assert obs[0].routed_to == "debt,po"
    assert obs[0].confidence == 0.9  # révisée par le critique
    # tech_debt → debt seul : écrit en mémoire → PERSISTED.
    assert obs[1].status == ObservationStatus.PERSISTED
    assert obs[1].routed_to == "debt"
    # La base de connaissance F4 est écrite et tracée.
    kb = knowledge.load_knowledge("f2-proj")
    assert [d.source_observation_id for d in kb.debt_register] == ["OBS-1", "OBS-2"]
    assert kb.component_memory["backend"][0].source_observation_id == "OBS-1"
    # Événement SSE observation_update publié avec le lot touché.
    updates = [e for e in events if e.get("type") == "observation_update"]
    assert len(updates) == 1
    assert {o["id"] for o in updates[0]["observations"]} == {"OBS-1", "OBS-2"}


async def test_critic_flag_off_keeps_f1_behavior(monkeypatch):
    # OBSERVATIONS=1 mais OBSERVATION_CRITIC épinglé OFF (conftest) : mode F1
    # pur — extraction seule, statut NEW, zéro appel critique, pas de mémoire.
    monkeypatch.setattr(settings, "observations_enabled", True)
    pipeline, story, runner = _hook_pipeline([OBS_REPLY])

    await pipeline._aextract_observations(_work_item(), story, story)

    assert len(runner.calls) == 1
    assert all(o.status == ObservationStatus.NEW for o in pipeline.state.observations)
    assert knowledge.load_knowledge("f2-proj").debt_register == []


async def test_critic_failure_still_routes_fail_open(monkeypatch):
    # Le critique LLM échoue (une seule réponse en file) : les survivants sont
    # VALIDATED tels quels puis routés — le build n'est jamais bloqué.
    monkeypatch.setattr(settings, "observations_enabled", True)
    monkeypatch.setattr(settings, "observation_critic_enabled", True)
    pipeline, story, runner = _hook_pipeline([OBS_REPLY])

    await pipeline._aextract_observations(_work_item(), story, story)

    obs = pipeline.state.observations
    assert obs[0].status == ObservationStatus.ROUTED and obs[0].confidence == 0.8
    assert obs[1].status == ObservationStatus.PERSISTED and obs[1].confidence == 0.6


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

IMPACT_UPDATE = json.dumps(
    {"message": "On corrige.", "action": "update_story", "story_id": "US-1",
     "updates": {"description": "corrigée"}},
    ensure_ascii=False,
)


@pytest.fixture
def no_real_run(monkeypatch):
    async def _fake_exercise(self):
        return "(processus terminé, code 0)\nsortie simulée"

    monkeypatch.setattr(Pipeline, "_aexercise_product", _fake_exercise)


async def test_findings_conversion_also_goes_through_the_chain(no_real_run, monkeypatch):
    monkeypatch.setattr(settings, "observations_enabled", True)
    monkeypatch.setattr(settings, "observation_critic_enabled", True)
    state = ProjectState(
        id="f2-eval", name="todo", goal="g", phase=PipelinePhase.DONE, brief="# Brief",
        epics=[Epic(id="EPIC-1", title="E")],
        stories=[UserStory(id="US-1", epic_id="EPIC-1", title="S",
                           status=StoryStatus.TODO,
                           acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="c")])],
    )
    critic = _critic_reply(
        {"id": "OBS-1", "verdict": "validate", "confidence": 0.9, "urgency": "high"},
        {"id": "OBS-2", "verdict": "validate", "confidence": 0.6, "urgency": "low"},
    )
    pipeline = Pipeline(state, FakeRunner([EVAL_FINDINGS, critic, IMPACT_UPDATE]))

    await pipeline._aevaluate_phase(force=True)

    obs = pipeline.state.observations
    assert len(obs) == 2
    # bug → risk → registre de risques → PERSISTED ; ux → improvement → po.
    assert obs[0].status == ObservationStatus.PERSISTED and obs[0].routed_to == "risk"
    assert obs[1].status == ObservationStatus.ROUTED and obs[1].routed_to == "po"
    kb = knowledge.load_knowledge("f2-eval")
    assert [r.source_observation_id for r in kb.risk_register] == ["OBS-1"]
    assert kb.risk_register[0].likelihood == "high"
