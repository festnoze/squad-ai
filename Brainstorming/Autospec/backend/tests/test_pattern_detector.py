"""V3-F5 (Pattern Detector, agent ambient) : agrégateur déterministe pur
(observations pondérées par récurrence, guard findings, taux d'échec 1re
tentative, calibration, dette par stream), gate de seuil sur watermark
persistant (< PATTERN_MIN_SIGNALS ⇒ zéro appel LLM), un seul appel boss-tier
fail-open, et émission de méta-observations type=PATTERN repassant par la
chaîne critique/routeur F2 — le tout derrière PATTERN_DETECTOR (+OBSERVATIONS).
"""

import json

import pytest

from autospec.agents.personas import persona
from autospec.agents.runner import FakeRunner
from autospec.config import PERSONA_TIERS, settings
from autospec.models import (
    EngineeringObservation,
    Epic,
    ObservationStatus,
    ObservationType,
    PlanCalibration,
    ProjectState,
    StoryStatus,
    UserStory,
)
from autospec.orchestrator import knowledge, pattern_detector
from autospec.orchestrator.events import bus
from autospec.orchestrator.governance import po_queue
from autospec.orchestrator.knowledge import DebtEntry
from autospec.orchestrator.pipeline import Pipeline


def _obs(
    oid,
    *,
    obs_type=ObservationType.TECH_DEBT,
    summary="Duplication du mapping d'erreurs",
    stream="backend",
    merged_count=0,
    status=ObservationStatus.PERSISTED,
    urgency="normal",
) -> EngineeringObservation:
    return EngineeringObservation(
        id=oid,
        type=obs_type,
        summary=summary,
        evidence=["preuve : extrait de transcription"],
        stream=stream,
        merged_count=merged_count,
        status=status,
        urgency=urgency,
    )


def _story(sid, *, iteration, stream="", attempts=0,
           status=StoryStatus.DONE, guards=()) -> UserStory:
    return UserStory(
        id=sid, epic_id="EPIC-1", title=sid, iteration=iteration,
        stream=stream, attempts=attempts, status=status,
        guard_findings=list(guards),
    )


def _synthetic() -> tuple[ProjectState, knowledge.KnowledgeBase]:
    """Un état synthétique couvrant 3 itérations (US-F5.1)."""
    state = ProjectState(id="pat-agg", name="n", goal="g", iteration=3)
    state.stories = [
        _story("US-1", iteration=1, stream="backend", attempts=1),
        _story("US-2", iteration=2, stream="backend", attempts=2,
               guards=["tamper US-2"]),
        _story("US-3", iteration=3, stream="frontend", attempts=3,
               status=StoryStatus.FAILED,
               guards=["scope US-3", "tamper US-3"]),
        _story("US-4", iteration=3, stream="backend", attempts=1),
    ]
    state.observations = [
        _obs("OBS-1", merged_count=2),  # récurrence forte (poids 3)
        _obs("OBS-2", obs_type=ObservationType.WORKAROUND,
             summary="Contournement du parseur de dates", stream="frontend"),
        _obs("OBS-3", obs_type=ObservationType.RISK,
             summary="Cas limite non couvert", stream="frontend",
             status=ObservationStatus.REJECTED),  # exclue des agrégats
    ]
    state.observation_seq = 3
    state.calibration = {
        2: PlanCalibration(reactive_splits=1),
        3: PlanCalibration(reactive_splits=2, scope_violations=1),
    }
    kb = knowledge.KnowledgeBase()
    kb.debt_register = [
        DebtEntry(title="dette a", source_observation_id="OBS-1"),
        DebtEntry(title="dette b", source_observation_id="OBS-1"),
        DebtEntry(title="dette orpheline", source_observation_id=""),
    ]
    return state, kb


# ------------------------------------------- US-F5.1 agrégateur déterministe

def test_aggregate_counts_by_type_with_merge_weight():
    state, kb = _synthetic()
    agg = pattern_detector.aggregate_signals(state, kb)
    obs = agg["observations"]
    # OBS-3 rejetée exclue ; OBS-1 pèse 1 + merged_count(2) = 3.
    assert obs["total"] == 2
    assert obs["weighted_total"] == 4
    assert obs["by_type"] == {
        "tech_debt": {"count": 1, "weight": 3},
        "workaround": {"count": 1, "weight": 1},
    }


def test_aggregate_counts_by_stream():
    state, kb = _synthetic()
    agg = pattern_detector.aggregate_signals(state, kb)
    assert agg["observations"]["by_stream"] == {
        "backend": {"count": 1, "weight": 3, "by_type": {"tech_debt": 3}},
        "frontend": {"count": 1, "weight": 1, "by_type": {"workaround": 1}},
    }


def test_aggregate_recurrent_lists_merged_count_ge_2_only():
    state, kb = _synthetic()
    agg = pattern_detector.aggregate_signals(state, kb)
    assert [r["id"] for r in agg["recurrent"]] == ["OBS-1"]
    assert agg["recurrent"][0]["merged_count"] == 2
    assert agg["recurrent"][0]["stream"] == "backend"


def test_aggregate_guard_findings_this_and_last_iteration():
    state, kb = _synthetic()
    guards = pattern_detector.aggregate_signals(state, kb)["guards"]
    assert guards["total"] == 3
    assert guards["by_stream"] == {"backend": 1, "frontend": 2}
    assert guards["stories_this_iteration"] == ["US-3"]   # itération 3
    assert guards["stories_last_iteration"] == ["US-2"]   # itération 2


def test_aggregate_first_attempt_failure_rate():
    state, kb = _synthetic()
    fa = pattern_detector.aggregate_signals(state, kb)["first_attempt"]
    # US-2 (2 tentatives) et US-3 (FAILED) ont raté leur 1re tentative.
    assert fa == {"stories_measured": 4, "failures": 2, "failure_rate": 0.5}


def test_aggregate_first_attempt_rate_zero_when_nothing_measured():
    state = ProjectState(id="pat-empty", name="n", goal="g")
    fa = pattern_detector.aggregate_signals(state, knowledge.KnowledgeBase())[
        "first_attempt"
    ]
    assert fa == {"stories_measured": 0, "failures": 0, "failure_rate": 0.0}


def test_aggregate_calibration_split_counts_and_totals():
    state, kb = _synthetic()
    calib = pattern_detector.aggregate_signals(state, kb)["calibration"]
    assert calib["by_iteration"][2]["reactive_splits"] == 1
    assert calib["by_iteration"][3]["reactive_splits"] == 2
    assert calib["by_iteration"][3]["scope_violations"] == 1
    assert calib["totals"]["reactive_splits"] == 3
    assert calib["totals"]["scope_violations"] == 1
    assert calib["totals"]["canary_reverts"] == 0


def test_aggregate_debt_per_stream_via_source_observation():
    state, kb = _synthetic()
    debt = pattern_detector.aggregate_signals(state, kb)["debt"]
    # Le stream d'une DebtEntry est résolu via son observation source ;
    # une entrée introuvable tombe dans le bucket "".
    assert debt == {"total": 3, "by_stream": {"backend": 2, "": 1}}


# --------------------------------------------------- watermark & seuil (gate)

def test_count_new_signals_sums_observations_and_guards():
    state, _ = _synthetic()
    # Watermark vierge : 3 allocations d'observations + 3 guard findings.
    assert pattern_detector.count_new_signals(state) == 6


def test_advance_watermark_consumes_everything():
    state, _ = _synthetic()
    pattern_detector.advance_watermark(state)
    assert state.pattern_last_obs_seq == 3
    assert state.pattern_last_guard_count == 3
    assert pattern_detector.count_new_signals(state) == 0
    # Un nouveau guard finding redevient un signal.
    state.stories[0].guard_findings.append("nouveau signalement")
    assert pattern_detector.count_new_signals(state) == 1


def test_legacy_state_without_watermark_fields_loads():
    raw = json.dumps({"id": "legacy", "name": "n", "goal": "g"})
    state = ProjectState.model_validate_json(raw)
    assert state.pattern_last_obs_seq == 0
    assert state.pattern_last_guard_count == 0
    assert pattern_detector.count_new_signals(state) == 0


# ------------------------------------------------ coercition de la sortie LLM

def _finding(**over) -> dict:
    base = {
        "summary": "Le stream backend concentre la dette récurrente",
        "description": "Accumulation transverse.",
        "evidence": ["6 observations tech_debt sur backend", "3 fusions"],
        "impact": "backend fragile",
        "urgency": "high",
        "stream": "backend",
        "recommendations": ["Créer une TS d'assainissement"],
    }
    base.update(over)
    return base


def test_evidence_confidence_is_deterministic_from_numeric_evidence():
    assert pattern_detector.evidence_confidence([]) == pytest.approx(0.4)
    assert pattern_detector.evidence_confidence(["aucune donnée chiffrée"]) == pytest.approx(0.4)
    assert pattern_detector.evidence_confidence(["3 fusions"]) == pytest.approx(0.55)
    assert pattern_detector.evidence_confidence(["3 fusions", "taux 0.5"]) == pytest.approx(0.7)
    # Cap à 0.9 : une tendance reste une hypothèse.
    many = [f"{i} signaux" for i in range(10)]
    assert pattern_detector.evidence_confidence(many) == pytest.approx(0.9)


def test_coerce_findings_valid_entry():
    out = pattern_detector.coerce_findings(
        {"patterns": [_finding()]}, max_findings=3, known_streams={"backend"}
    )
    assert len(out) == 1
    f = out[0]
    assert f["summary"] == "Le stream backend concentre la dette récurrente"
    assert f["urgency"] == "high" and f["stream"] == "backend"
    assert f["confidence"] == pytest.approx(0.7)  # 2 preuves chiffrées
    assert f["recommendations"] == ["Créer une TS d'assainissement"]


def test_coerce_findings_drops_unusable_and_caps():
    reply = {
        "patterns": [
            _finding(summary="  "),                    # sans résumé
            _finding(evidence=[]),                     # sans preuve
            _finding(evidence="pas une liste"),        # preuves invalides
            "pas un objet",
            _finding(summary="motif 1"),
            _finding(summary="motif 2"),
            _finding(summary="motif 3 (au-delà du cap)"),
        ]
    }
    out = pattern_detector.coerce_findings(
        reply, max_findings=2, known_streams={"backend"}
    )
    assert [f["summary"] for f in out] == ["motif 1", "motif 2"]


def test_coerce_findings_normalizes_urgency_and_unknown_stream():
    out = pattern_detector.coerce_findings(
        {"patterns": [_finding(urgency="apocalyptique", stream="lune")]},
        max_findings=3,
        known_streams={"backend"},
    )
    assert out[0]["urgency"] == "normal"
    assert out[0]["stream"] == ""


def test_coerce_findings_tolerates_malformed_reply():
    assert pattern_detector.coerce_findings(
        {"patterns": "rien"}, max_findings=3, known_streams=set()
    ) == []
    assert pattern_detector.coerce_findings(
        {}, max_findings=3, known_streams=set()
    ) == []


def test_known_streams_merges_effective_streams_and_observations():
    state, _ = _synthetic()
    ids = pattern_detector.known_streams(state)
    assert {"backend", "frontend"} <= ids


# --------------------------------------------------- hook pipeline (US-F5.2)

PATTERN_REPLY = json.dumps(
    {
        "message": "Un motif transverse.",
        "patterns": [
            {
                "summary": "Le stream backend accumule un signal récurrent transverse",
                "description": "La même dette revient d'itération en itération.",
                "evidence": ["6 observations pondérées sur backend",
                             "3 guard findings"],
                "impact": "backend fragile",
                "urgency": "high",
                "stream": "backend",
                "recommendations": ["Créer une TS d'harmonisation"],
            }
        ],
    },
    ensure_ascii=False,
)

EMPTY_REPLY = json.dumps({"message": "Rien de transverse.", "patterns": []},
                         ensure_ascii=False)

CRITIC_REPLY = json.dumps(
    {
        "message": "Jugement rendu.",
        "verdicts": [
            {"id": "OBS-7", "verdict": "validate", "confidence": 0.8,
             "urgency": "high", "reason": "preuves chiffrées"}
        ],
    },
    ensure_ascii=False,
)


def _detector_state(n_obs=6) -> ProjectState:
    """Un état avec ``n_obs`` allocations d'observations (autant de signaux)."""
    state = ProjectState(id="pat-proj", name="pat", goal="g")
    state.epics.append(Epic(id="EPIC-1", title="E"))
    for i in range(n_obs):
        state.observation_seq += 1
        state.observations.append(
            _obs(
                f"OBS-{state.observation_seq}",
                summary=f"dette numéro {i} sur le mapping du module",
                status=ObservationStatus.NEW,
            )
        )
    return state


def _detector_pipeline(replies, *, n_obs=6):
    state = _detector_state(n_obs)
    runner = FakeRunner(replies)
    return Pipeline(state, runner), runner


@pytest.fixture
def detector_on(monkeypatch):
    monkeypatch.setattr(settings, "observations_enabled", True)
    monkeypatch.setattr(settings, "pattern_detector_enabled", True)
    monkeypatch.setattr(settings, "pattern_min_signals", 5)
    monkeypatch.setattr(settings, "pattern_max_findings", 3)
    monkeypatch.setattr(settings, "observation_dedup_threshold", 0.75)


async def test_flag_off_hook_is_strict_noop():
    # PATTERN_DETECTOR épinglé OFF par conftest : aucun appel, aucun watermark.
    pipeline, runner = _detector_pipeline([PATTERN_REPLY])
    await pipeline._adetect_patterns()
    assert runner.calls == []
    assert pipeline.state.pattern_last_obs_seq == 0
    assert pipeline.state.observation_seq == 6  # rien émis


async def test_detector_requires_observations_flag(monkeypatch):
    monkeypatch.setattr(settings, "pattern_detector_enabled", True)
    monkeypatch.setattr(settings, "observations_enabled", False)
    pipeline, runner = _detector_pipeline([PATTERN_REPLY])
    await pipeline._adetect_patterns()
    assert runner.calls == []
    assert pipeline.state.pattern_last_obs_seq == 0


async def test_below_threshold_makes_zero_llm_call(detector_on):
    # 4 signaux < seuil 5 : zéro appel ET watermark intact (les signaux
    # continuent de s'accumuler pour la prochaine itération).
    pipeline, runner = _detector_pipeline([PATTERN_REPLY], n_obs=4)
    await pipeline._adetect_patterns()
    assert runner.calls == []
    assert pipeline.state.pattern_last_obs_seq == 0


async def test_above_threshold_one_boss_call_and_watermark_advances(detector_on):
    pipeline, runner = _detector_pipeline([EMPTY_REPLY])
    await pipeline._adetect_patterns()

    # UN appel, persona pattern-detector, agrégats dans le prompt.
    assert len(runner.calls) == 1
    assert runner.calls[0]["system_prompt"] == persona("pattern-detector")
    assert "DÉTECTEUR DE MOTIFS" in runner.calls[0]["prompt"]
    assert '"new_signals": 6' in runner.calls[0]["prompt"]
    # Zéro motif → zéro méta-observation, mais le watermark a avancé.
    assert pipeline.state.observation_seq == 6
    assert pipeline.state.pattern_last_obs_seq == 6

    # Second run sans nouveau signal : AUCUN appel supplémentaire.
    runner.queue(PATTERN_REPLY)
    await pipeline._adetect_patterns()
    assert len(runner.calls) == 1


async def test_emission_creates_pattern_observation(detector_on):
    # Critique F2 épinglé OFF (conftest) : la méta-observation reste NEW —
    # on vérifie l'émission brute (type, source, confiance déterministe).
    pipeline, runner = _detector_pipeline([PATTERN_REPLY])
    queue = bus.subscribe()
    try:
        await pipeline._adetect_patterns()
        events = []
        while not queue.empty():
            events.append(queue.get_nowait()[1])
    finally:
        bus.unsubscribe(queue)

    obs = pipeline.state.observations[-1]
    assert obs.id == "OBS-7"
    assert obs.type == ObservationType.PATTERN
    assert obs.source_role == "pattern-detector"
    assert obs.work_item_id == ""
    assert obs.stream == "backend"
    assert obs.urgency == "high"                     # reprise du motif LLM
    assert obs.confidence == pytest.approx(0.7)      # 2 preuves chiffrées
    assert obs.status == ObservationStatus.NEW
    # Watermark : inclut la propre émission du détecteur (pas d'auto-déclenche).
    assert pipeline.state.pattern_last_obs_seq == 7
    # Événement SSE ``observation`` publié pour la méta-observation.
    published = [e for e in events if e.get("type") == "observation"]
    assert [e["observation"]["id"] for e in published] == ["OBS-7"]


async def test_meta_observation_goes_through_critic_and_router(detector_on, monkeypatch):
    # Chaîne F2 active : détecteur → critique batché → routeur — pattern à
    # urgence haute ⇒ architecture + po, donc file de gouvernance F3.
    monkeypatch.setattr(settings, "observation_critic_enabled", True)
    pipeline, runner = _detector_pipeline([PATTERN_REPLY, CRITIC_REPLY])

    await pipeline._adetect_patterns()

    assert len(runner.calls) == 2  # détecteur + critique, pas un de plus
    assert "CRITIQUE DES OBSERVATIONS" in runner.calls[1]["prompt"]
    obs = next(o for o in pipeline.state.observations if o.id == "OBS-7")
    assert obs.type == ObservationType.PATTERN
    assert obs.status == ObservationStatus.ROUTED
    assert obs.routed_to == "architecture,po"
    # La méta-observation atteint la file de gouvernance du PO (F3).
    assert obs in po_queue(pipeline.state)
    # Et la note d'architecture F4 est écrite (destination architecture).
    kb = knowledge.load_knowledge("pat-proj")
    assert any(
        n.source_observation_id == "OBS-7" for n in kb.architecture_notes
    )


async def test_malformed_llm_output_is_fail_open(detector_on):
    pipeline, runner = _detector_pipeline(["pas du json"])
    await pipeline._adetect_patterns()
    # Aucune méta-observation, pas d'exception, watermark avancé quand même
    # (les mêmes signaux saturés ne re-paient pas un appel à chaque itération).
    assert pipeline.state.observation_seq == 6
    assert all(o.type != ObservationType.PATTERN for o in pipeline.state.observations)
    assert pipeline.state.pattern_last_obs_seq == 6


async def test_llm_failure_is_fail_open(detector_on):
    # FakeRunner vide → AgentError : le hook n'explose jamais (fail-open).
    pipeline, runner = _detector_pipeline([])
    await pipeline._adetect_patterns()
    assert pipeline.state.observation_seq == 6
    assert pipeline.state.pattern_last_obs_seq == 6


async def test_max_findings_cap_is_enforced(detector_on, monkeypatch):
    monkeypatch.setattr(settings, "pattern_max_findings", 1)
    finding = json.loads(PATTERN_REPLY)
    finding["patterns"] = [
        dict(finding["patterns"][0], summary=f"motif transverse distinct {i}")
        for i in range(3)
    ]
    pipeline, runner = _detector_pipeline([json.dumps(finding, ensure_ascii=False)])
    await pipeline._adetect_patterns()
    patterns = [
        o for o in pipeline.state.observations if o.type == ObservationType.PATTERN
    ]
    assert len(patterns) == 1


def test_pattern_detector_registered_as_boss_tier():
    assert PERSONA_TIERS["pattern-detector"] == "boss"
    assert persona("pattern-detector") != persona("observer")
