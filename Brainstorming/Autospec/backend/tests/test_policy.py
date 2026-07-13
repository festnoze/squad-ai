"""V3-F6 — Policy Engine d'autonomie (orchestrator/policy.py).

Table de vérité niveaux 0..5 × domaines × actions représentatives, signaux de
rétrogradation déterministes (jamais de promotion), règles DENY dures, compat
GOVERNANCE_AUTO/AMENDMENT_AUTO (lus comme des pins niveau 5), journal
``state.autonomy_log``, branchements pipeline (gouvernance, amendement,
livraison docker, écritures mémoire) et endpoint agrégé ``/approvals``.
"""

from __future__ import annotations

import json

import httpx
import pytest

from autospec.agents.runner import FakeRunner
from autospec.api import server
from autospec.config import _env_level, settings
from autospec.models import (
    AcceptanceCriterion,
    EngineeringObservation,
    Epic,
    GovernanceAction,
    GovernanceDecision,
    ObservationStatus,
    ObservationType,
    ProjectState,
    UserStory,
)
from autospec.orchestrator import knowledge, policy, workspace
from autospec.orchestrator import observations as observations_lib
from autospec.orchestrator.events import bus
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import save_state

ALLOW = policy.Decision.ALLOW
RH = policy.Decision.REQUIRE_HUMAN
DENY = policy.Decision.DENY


# ------------------------------------------------------------------- helpers

def _state(pid="pol", *, iteration=2) -> ProjectState:
    """A signal-free state: iteration ≥ 2 (no first-iteration downgrade), no
    guard findings, no arbitration trace, no budget configured."""
    state = ProjectState(id=pid, name="pol", goal="g")
    state.iteration = iteration
    return state


def _story(sid="US-1", *, iteration=2, **kw) -> UserStory:
    return UserStory(id=sid, epic_id="EPIC-1", title=sid, iteration=iteration, **kw)


# --------------------------------------------- table de vérité (US-F6.1)

# expected decision per (domain, action) at effective levels 0..5.
TRUTH_TABLE = {
    ("backlog_changes", "create_story"): [RH, RH, RH, RH, RH, ALLOW],
    ("backlog_changes", "update_story"): [RH, RH, RH, RH, RH, ALLOW],
    ("backlog_changes", "persist"): [RH, RH, RH, RH, RH, ALLOW],
    ("spec_amendments", "apply_amendment"): [RH, RH, RH, RH, RH, ALLOW],
    ("memory_writes", "route_observation"): [RH, RH, ALLOW, ALLOW, ALLOW, ALLOW],
    ("memory_writes", "persist"): [RH, RH, ALLOW, ALLOW, ALLOW, ALLOW],
    ("delivery", "docker_deploy"): [RH, RH, ALLOW, ALLOW, ALLOW, ALLOW],
    ("delivery", "setup_components"): [RH, RH, RH, RH, RH, ALLOW],
    ("next_feature", "select_hypothesis"): [RH, RH, ALLOW, ALLOW, ALLOW, ALLOW],
}


@pytest.mark.parametrize("level", range(6))
@pytest.mark.parametrize("domain,action", sorted(TRUTH_TABLE))
def test_truth_table(monkeypatch, level, domain, action):
    monkeypatch.setattr(settings, "autonomy_level", level)
    state = _state()
    assert policy.decide(domain, action, state, {}) is TRUTH_TABLE[(domain, action)][level]


def test_default_level_is_todays_behaviour():
    """AUTONOMY_LEVEL par défaut (2) = comportement actuel exactement : backlog
    et amendements human-gated, mémoire/deploy/next-feature automatiques, setup
    des composants derrière le gate UI."""
    state = _state()
    assert policy.decide("backlog_changes", "create_story", state, {}) is RH
    assert policy.decide("spec_amendments", "apply_amendment", state, {}) is RH
    assert policy.decide("memory_writes", "route_observation", state, {}) is ALLOW
    assert policy.decide("delivery", "docker_deploy", state, {}) is ALLOW
    assert policy.decide("delivery", "setup_components", state, {}) is RH
    assert policy.decide("next_feature", "select_hypothesis", state, {}) is ALLOW


@pytest.mark.parametrize("domain,action", [
    ("backlog_changes", "create_story"),
    ("spec_amendments", "apply_amendment"),
    ("delivery", "setup_components"),
])
def test_level4_requires_independent_validation(monkeypatch, domain, action):
    monkeypatch.setattr(settings, "autonomy_level", 4)
    state = _state()
    assert policy.decide(domain, action, state, {}) is RH
    assert policy.decide(domain, action, state, {"judge_validated": True}) is ALLOW
    assert policy.decide(domain, action, state, {"critic_score": 80}) is ALLOW
    assert policy.decide(domain, action, state, {"critic_score": 79}) is RH
    assert policy.decide(domain, action, state, {"critic_score": "n/a"}) is RH


def test_unknown_domain_raises():
    state = _state()
    with pytest.raises(ValueError):
        policy.decide("world_domination", "x", state, {})
    with pytest.raises(ValueError):
        policy.effective_level("nope", state)


# --------------------------------------------- rétrogradations (US-F6.1)

def test_guard_findings_downgrade_current_iteration_only(monkeypatch):
    monkeypatch.setattr(settings, "autonomy_level", 3)
    state = _state("pol-guard")
    state.stories = [_story(iteration=1, guard_findings=["tamper"])]
    # Findings d'une itération PASSÉE : aucun signal.
    assert policy.effective_level("backlog_changes", state) == 3
    state.stories.append(_story("US-2", iteration=2, guard_findings=["tamper"]))
    assert policy.effective_level("backlog_changes", state) == 2
    assert policy.effective_level("spec_amendments", state) == 2
    assert any(
        "[backlog_changes]" in e and "guard findings" in e and "3→2" in e
        for e in state.autonomy_log
    )


def test_arbitration_proxy_downgrades_at_two_events(monkeypatch):
    monkeypatch.setattr(settings, "autonomy_level", 3)
    state = _state("pol-arb")
    one = _story("US-1")
    one.recovery.kind = "arbitration"
    state.stories = [one]
    assert policy.effective_level("backlog_changes", state) == 3  # 1 seul événement
    two = _story("US-2")
    two.last_error = "[arbitrage: contradiction de spec] AC-1 vs AC-2"
    state.stories.append(two)
    assert policy.effective_level("backlog_changes", state) == 2
    assert any("arbitrages wrong-test" in e for e in state.autonomy_log)


def test_first_iteration_downgrade(monkeypatch):
    monkeypatch.setattr(settings, "autonomy_level", 3)
    state = _state("pol-iter1", iteration=1)
    assert policy.effective_level("backlog_changes", state) == 2
    assert policy.effective_level("spec_amendments", state) == 2
    assert any("première itération" in e for e in state.autonomy_log)


@pytest.mark.parametrize("field,budget,spent", [
    ("usd", 10.0, 8.5),
    ("tokens", 1000, 900),
])
def test_budget_downgrade_applies_to_backlog_only(monkeypatch, field, budget, spent):
    monkeypatch.setattr(settings, "autonomy_level", 3)
    state = _state("pol-budget")
    if field == "usd":
        state.budget_usd = budget
        state.usage.cost_usd = spent
    else:
        state.budget_tokens = budget
        state.usage.input_tokens = spent
    assert policy.effective_level("backlog_changes", state) == 2
    assert policy.effective_level("spec_amendments", state) == 3  # non concerné
    assert any("budget consommé" in e for e in state.autonomy_log)


def test_operational_domains_follow_the_dial_directly(monkeypatch):
    """Contrat golden-compat (docstring du module) : les signaux de distrust ne
    rétrogradent PAS memory_writes/delivery/next_feature — ces domaines sont
    automatiques sans gate au niveau par défaut, une rétrogradation globale sur
    tout projet en première itération changerait le comportement flag-ON."""
    monkeypatch.setattr(settings, "autonomy_level", 2)
    state = _state("pol-ops", iteration=1)
    state.stories = [_story(iteration=1, guard_findings=["tamper"])]
    for domain in ("memory_writes", "delivery", "next_feature"):
        assert policy.effective_level(domain, state) == 2
    assert policy.decide("delivery", "docker_deploy", state, {}) is ALLOW
    assert policy.decide("memory_writes", "route_observation", state, {}) is ALLOW
    assert policy.decide("next_feature", "select_hypothesis", state, {}) is ALLOW


def test_downgrades_stack_and_floor_at_zero(monkeypatch):
    monkeypatch.setattr(settings, "autonomy_level", 2)
    state = _state("pol-floor", iteration=1)
    state.stories = [
        _story("US-1", iteration=1, guard_findings=["tamper"]),
        _story("US-2", iteration=1),
        _story("US-3", iteration=1),
    ]
    state.stories[1].recovery.kind = "arbitration"
    state.stories[2].recovery.kind = "arbitration"
    # 3 signaux mais plancher à 0 (2→1→0, le troisième ne s'applique plus).
    assert policy.effective_level("backlog_changes", state) == 0
    logged = [e for e in state.autonomy_log if "[backlog_changes]" in e]
    assert len(logged) == 2 and "2→1" in logged[0] and "1→0" in logged[1]


def test_never_promote_property(monkeypatch):
    """Propriété : quel que soit l'état, effective ≤ recommended."""
    signal_states = [
        _state("pol-np1"),
        _state("pol-np2", iteration=1),
    ]
    dirty = _state("pol-np3")
    dirty.stories = [_story(iteration=2, guard_findings=["x"])]
    dirty.budget_usd, dirty.usage.cost_usd = 1.0, 0.95
    signal_states.append(dirty)
    for level in range(6):
        monkeypatch.setattr(settings, "autonomy_level", level)
        for state in signal_states:
            for domain in policy.DOMAINS:
                assert (
                    policy.effective_level(domain, state)
                    <= policy.recommended_level(domain)
                )


def test_autonomy_log_deduplicated_across_calls(monkeypatch):
    monkeypatch.setattr(settings, "autonomy_level", 3)
    state = _state("pol-dedup", iteration=1)
    policy.decide("backlog_changes", "create_story", state, {})
    first = list(state.autonomy_log)
    policy.decide("backlog_changes", "create_story", state, {})
    policy.effective_level("backlog_changes", state)
    assert state.autonomy_log == first and len(first) == 1


# ------------------------------------------------- clamping & parsing config

def test_levels_clamped_to_valid_range(monkeypatch):
    state = _state()
    monkeypatch.setattr(settings, "autonomy_level", 9)
    assert policy.recommended_level("delivery") == 5
    monkeypatch.setattr(settings, "autonomy_level", -3)
    assert policy.recommended_level("delivery") == 0
    monkeypatch.setattr(settings, "autonomy_level", "abc")
    assert policy.recommended_level("delivery") == 2  # invalide → défaut
    monkeypatch.setattr(settings, "autonomy_level", 1)
    monkeypatch.setattr(settings, "autonomy_delivery", 7)
    assert policy.recommended_level("delivery") == 5  # override clampé
    assert policy.decide("delivery", "docker_deploy", state, {}) is ALLOW


def test_env_level_parsing(monkeypatch):
    monkeypatch.setenv("X_AUTONOMY_T", "3")
    assert _env_level("X_AUTONOMY_T", None) == 3
    monkeypatch.setenv("X_AUTONOMY_T", "9")
    assert _env_level("X_AUTONOMY_T", None) == 5
    monkeypatch.setenv("X_AUTONOMY_T", "-1")
    assert _env_level("X_AUTONOMY_T", None) == 0
    monkeypatch.setenv("X_AUTONOMY_T", "abc")
    assert _env_level("X_AUTONOMY_T", 2) == 2
    monkeypatch.setenv("X_AUTONOMY_T", "")
    assert _env_level("X_AUTONOMY_T", None) is None


# --------------------------------------------------------- règles DENY dures

def test_exhausted_budget_denies_backlog_creations():
    state = _state("pol-deny")
    state.budget_usd, state.usage.cost_usd = 5.0, 5.0
    for action in ("create_story", "create_epic", "create_task"):
        assert policy.decide("backlog_changes", action, state, {}) is DENY
    # Les actions non-créatrices et les autres domaines ne sont pas déniés.
    assert policy.decide("backlog_changes", "update_story", state, {}) is RH
    assert policy.decide("backlog_changes", "dismiss", state, {}) is RH
    assert policy.decide("delivery", "docker_deploy", state, {}) is ALLOW


def test_deny_beats_the_legacy_compat_pin(monkeypatch):
    monkeypatch.setattr(settings, "governance_auto", True)
    state = _state("pol-deny-pin")
    state.budget_tokens = 100
    state.usage.input_tokens, state.usage.output_tokens = 60, 40
    assert policy.decide("backlog_changes", "create_story", state, {}) is DENY


def test_no_budget_configured_never_denies():
    state = _state("pol-nobudget")
    state.usage.cost_usd = 1e6  # dépense énorme mais aucun plafond (0 = no limit)
    assert policy.decide("backlog_changes", "create_story", state, {}) is RH


# ------------------------------------- compat GOVERNANCE_AUTO / AMENDMENT_AUTO

def test_governance_auto_reads_as_backlog_level5_pin(monkeypatch):
    monkeypatch.setattr(settings, "governance_auto", True)
    state = _state("pol-compat-gov", iteration=1)
    state.stories = [_story(iteration=1, guard_findings=["tamper"])]
    # Pin explicite : niveau 5, PAS de rétrogradation (compat octet pour octet).
    assert policy.recommended_level("backlog_changes") == 5
    assert policy.effective_level("backlog_changes", state) == 5
    assert policy.decide("backlog_changes", "create_story", state, {}) is ALLOW
    assert state.autonomy_log == []
    # Le pin ne fuit pas vers les autres domaines.
    assert policy.decide("spec_amendments", "apply_amendment", state, {}) is RH


def test_amendment_auto_reads_as_spec_level5_pin(monkeypatch):
    monkeypatch.setattr(settings, "amendment_auto", True)
    state = _state("pol-compat-am", iteration=1)
    assert policy.effective_level("spec_amendments", state) == 5
    assert policy.decide("spec_amendments", "apply_amendment", state, {}) is ALLOW
    assert policy.decide("backlog_changes", "create_story", state, {}) is RH


# --------------------------------------- branchement gouvernance (US-F6.2)

STORY_PAYLOAD = {
    "title": "Clarifier l'arrondi",
    "description": "Arrondi spécifié.",
    "epic_id": "EPIC-1",
    "acceptance_criteria": ["L'arrondi bancaire est appliqué."],
    "priority": 2,
}

GOVERN_REPLY = json.dumps({
    "message": "Une décision.",
    "decisions": [
        {"observation_id": "OBS-1", "action": "create_story", "target_id": "",
         "payload": STORY_PAYLOAD, "rationale": "story nécessaire"}
    ],
}, ensure_ascii=False)


def _gov_state(pid: str) -> ProjectState:
    state = ProjectState(id=pid, name="gov", goal="g")
    state.iteration = 2  # pas de rétrogradation première-itération
    state.epics.append(Epic(id="EPIC-1", title="E"))
    state.stories = [
        UserStory(
            id="US-1", epic_id="EPIC-1", title="Base", iteration=2,
            acceptance_criteria=[AcceptanceCriterion(id="AC-1", text="c")],
        )
    ]
    state.observations = [
        EngineeringObservation(
            id="OBS-1", type=ObservationType.AMBIGUITY,
            summary="Critère ambigu", evidence=["[dev] extrait"],
            status=ObservationStatus.ROUTED, routed_to="po", iteration=2,
        )
    ]
    return state


@pytest.fixture
def govern_on(monkeypatch):
    monkeypatch.setattr(settings, "governance_enabled", True)
    monkeypatch.setattr(settings, "observations_enabled", True)


async def test_govern_phase_applies_at_autonomy5_without_legacy_flag(govern_on, monkeypatch):
    monkeypatch.setattr(settings, "autonomy_backlog_changes", 5)
    state = _gov_state("pol-gov5")
    pipeline = Pipeline(state, FakeRunner([GOVERN_REPLY]))
    await pipeline._agovern_phase()
    decision = state.governance_log[0]
    assert decision.status == "applied"
    assert state.story(decision.payload["created_story_id"]).iteration == 3
    assert state.observations[0].status == ObservationStatus.ACTIONED


async def test_govern_phase_default_stays_proposed(govern_on):
    state = _gov_state("pol-gov-def")
    pipeline = Pipeline(state, FakeRunner([GOVERN_REPLY]))
    await pipeline._agovern_phase()
    assert state.governance_log[0].status == "proposed"
    assert [s.id for s in state.stories] == ["US-1"]


async def test_govern_phase_denies_creations_on_exhausted_budget(govern_on, monkeypatch):
    monkeypatch.setattr(settings, "autonomy_backlog_changes", 5)
    state = _gov_state("pol-gov-deny")
    state.budget_usd, state.usage.cost_usd = 1.0, 2.0
    pipeline = Pipeline(state, FakeRunner([GOVERN_REPLY]))
    await pipeline._agovern_phase()
    decision = state.governance_log[0]
    assert decision.status == "rejected_by_policy"
    assert [s.id for s in state.stories] == ["US-1"]  # rien créé
    assert state.observations[0].status == ObservationStatus.ROUTED  # intacte


# --------------------------------------- branchement amendement (US-F6.2)

AMEND_PROPOSAL = json.dumps({
    "target": "acceptance_criteria", "before": "AC1 & AC2 en conflit",
    "after": "AC1 clarifié", "rationale": "lever la contradiction",
})
AMEND_SAFE = json.dumps({"weakens": False, "reason": "périmètre préservé"})


def _amend_pipeline(pid: str, monkeypatch, *, iteration=2) -> Pipeline:
    monkeypatch.setattr(settings, "design_amendment_enabled", True)
    monkeypatch.setattr(settings, "amendment_max_depth", 1)
    state = ProjectState(id=pid, name="am", goal="g")
    state.iteration = iteration
    pipeline = Pipeline(state, FakeRunner([AMEND_PROPOSAL, AMEND_SAFE]))
    workspace.scaffold(state)
    return pipeline


def _amend_story() -> UserStory:
    return UserStory(
        id="US-1", epic_id="E-1", title="feature",
        acceptance_criteria=[AcceptanceCriterion(id="AC1", text="returns 42")],
    )


async def test_amendment_default_pending_and_publishes_approval_sse(monkeypatch):
    pipeline = _amend_pipeline("pol-am-def", monkeypatch)
    queue = bus.subscribe()
    try:
        await pipeline._amaybe_propose_amendment(_amend_story(), "AC1", "contradiction")
        events = []
        while not queue.empty():
            events.append(queue.get_nowait()[1])
    finally:
        bus.unsubscribe(queue)
    record = pipeline.state.pending_amendments[0]
    assert record["approved_safe"] is True and not record.get("applied")
    pending = [e for e in events if e.get("type") == "approval_pending"]
    assert pending and pending[0]["kind"] == "amendment" and pending[0]["story_id"] == "US-1"


async def test_amendment_applies_at_autonomy5(monkeypatch):
    monkeypatch.setattr(settings, "autonomy_spec_amendments", 5)
    pipeline = _amend_pipeline("pol-am5", monkeypatch)
    await pipeline._amaybe_propose_amendment(_amend_story(), "AC1", "contradiction")
    assert pipeline.state.pending_amendments[0]["applied"] is True


async def test_amendment_level4_applies_thanks_to_independent_check(monkeypatch):
    """Niveau 4 : l'amendement qui atteint le point d'application a DÉJÀ passé
    le check d'affaiblissement indépendant (judge_validated) → ALLOW."""
    monkeypatch.setattr(settings, "autonomy_spec_amendments", 4)
    pipeline = _amend_pipeline("pol-am4", monkeypatch)
    await pipeline._amaybe_propose_amendment(_amend_story(), "AC1", "contradiction")
    assert pipeline.state.pending_amendments[0]["applied"] is True


async def test_amendment_auto_compat_still_applies_first_iteration(monkeypatch):
    monkeypatch.setattr(settings, "amendment_auto", True)
    pipeline = _amend_pipeline("pol-am-compat", monkeypatch, iteration=1)
    await pipeline._amaybe_propose_amendment(_amend_story(), "AC1", "contradiction")
    assert pipeline.state.pending_amendments[0]["applied"] is True


# ------------------------------- branchements delivery & mémoire (US-F6.2)

async def test_delivery_gates_skip_unattended_docker_below_autonomy(monkeypatch):
    called = []

    async def fake_docker(self):
        called.append(1)
        return True

    monkeypatch.setattr(Pipeline, "_adocker_delivery_phase", fake_docker)
    state = _state("pol-docker")
    pipeline = Pipeline(state, FakeRunner([]))
    monkeypatch.setattr(settings, "autonomy_delivery", 1)
    assert await pipeline._adelivery_gates() is True
    assert called == []  # deploy non lancé : validation humaine requise
    monkeypatch.setattr(settings, "autonomy_delivery", None)
    assert await pipeline._adelivery_gates() is True
    assert called == [1]  # défaut (niveau 2) : ALLOW, comportement actuel


async def test_router_memory_writes_policy_gated(monkeypatch):
    async def failing_arun(*args, **kwargs):  # critic LLM indisponible → fail-open
        raise RuntimeError("no llm")

    def _debt_obs(oid):
        return EngineeringObservation(
            id=oid, type=ObservationType.TECH_DEBT, summary=f"dette {oid}",
            evidence=["[dev] extrait"], stream="backend", iteration=2,
        )

    # Niveau explicite ≤ 1 : l'écriture mémoire est retenue, l'observation
    # reste ROUTED (curation humaine via les endpoints knowledge).
    monkeypatch.setattr(settings, "autonomy_memory_writes", 0)
    state = _state("pol-mem")
    obs = _debt_obs("OBS-1")
    state.observations = [obs]
    kb = knowledge.KnowledgeBase()
    outcome = await observations_lib.aprocess_new_observations(state, [obs], kb, failing_arun)
    assert outcome.kb_dirty is False
    assert kb.debt_register == []
    assert obs.status == ObservationStatus.ROUTED and obs.routed_to == "debt"

    # Défaut : ALLOW — l'écriture a lieu (comportement actuel).
    monkeypatch.setattr(settings, "autonomy_memory_writes", None)
    state2 = _state("pol-mem2")
    obs2 = _debt_obs("OBS-2")
    state2.observations = [obs2]
    kb2 = knowledge.KnowledgeBase()
    outcome2 = await observations_lib.aprocess_new_observations(state2, [obs2], kb2, failing_arun)
    assert outcome2.kb_dirty is True
    assert len(kb2.debt_register) == 1
    assert obs2.status == ObservationStatus.PERSISTED


# ----------------------------------------- endpoint /approvals (US-F6.3)

def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_approvals_unknown_project_404():
    async with _client() as client:
        resp = await client.get("/api/projects/pol-nope/approvals")
        assert resp.status_code == 404


async def test_approvals_empty_project():
    save_state(_state("pol-app-empty"))
    async with _client() as client:
        resp = await client.get("/api/projects/pol-app-empty/approvals")
    assert resp.status_code == 200
    assert resp.json() == {"governance": [], "amendments": [], "count": 0}


async def test_approvals_aggregates_proposed_decisions_and_pending_amendments():
    state = _gov_state("pol-app")
    state.governance_seq += 1
    state.governance_log.append(
        GovernanceDecision(
            id="GOV-1", observation_id="OBS-1",
            action=GovernanceAction.CREATE_STORY, payload=dict(STORY_PAYLOAD),
            rationale="r", status="proposed", iteration=2,
        )
    )
    state.governance_seq += 1
    state.governance_log.append(
        GovernanceDecision(
            id="GOV-2", observation_id="OBS-1",
            action=GovernanceAction.DISMISS, rationale="r",
            status="rejected_by_human", iteration=2,
        )
    )
    state.pending_amendments = [
        {"story_id": "US-1", "target": "acceptance_criteria", "before": "b",
         "after": "a", "rationale": "safe en attente", "approved_safe": True},
        {"story_id": "US-1", "target": "acceptance_criteria", "before": "b",
         "after": "a", "rationale": "affaiblissant", "approved_safe": False},
        {"story_id": "US-1", "target": "acceptance_criteria", "before": "b",
         "after": "a", "rationale": "déjà appliqué", "approved_safe": True,
         "applied": True},
    ]
    save_state(state)
    async with _client() as client:
        resp = await client.get("/api/projects/pol-app/approvals")
    assert resp.status_code == 200
    body = resp.json()
    assert [d["id"] for d in body["governance"]] == ["GOV-1"]
    assert [a["index"] for a in body["amendments"]] == [0]
    assert body["amendments"][0]["rationale"] == "safe en attente"
    assert body["count"] == 2
