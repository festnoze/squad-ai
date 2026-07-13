"""V3-F2 — Observation Critic & Router.

Two stages after the F1 extractor, deterministic first (Autospec philosophy):

1. **Deterministic critic** — rejects evidence-less observations and MERGES
   near-duplicates (token similarity vs the existing non-dismissed/non-rejected
   observations of the same stream): repeated signal = strong signal, so the
   kept observation gains the new evidence and a confidence bump.
2. **LLM critic** — ONE batched checker-tier call per work item (role
   ``observation-critic``, distinct from the extractor: no agent validates its
   own work) confirming that evidence supports each claim and revising
   confidence/urgency. Fail-open: any LLM/parse failure ⇒ every survivor is
   VALIDATED with unchanged confidence.
3. **Deterministic router** — table type→destination (vision §9/§14); the
   memory destinations (debt/risk/architecture) write into the F4 knowledge
   base, "po" queues the observation for F3 governance (status stays ROUTED).
   An optional LLM router (OBSERVATION_ROUTER_LLM) refines low-confidence cases
   only; the deterministic table remains the authority on any failure.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from ..agents import prompts
from ..agents.personas import persona
from ..agents.runner import extract_json
from ..config import settings
from ..models import (
    EngineeringObservation,
    ObservationStatus,
    ObservationType,
    ProjectState,
)
from . import knowledge
from . import policy  # V3-F6: memory writes are policy-gated (ALLOW by default)

logger = logging.getLogger(__name__)

_URGENCIES = ("low", "normal", "high", "critical")
_HIGH_URGENCIES = ("high", "critical")

# Destinations an observation can be routed to (the LLM router is validated
# against this set — an invented destination falls back to the table).
ROUTE_DESTINATIONS = ("po", "architecture", "debt", "risk", "security", "discovery")

# Below this confidence a validated observation is considered ambiguous and is
# submitted to the optional LLM router (when OBSERVATION_ROUTER_LLM=1).
_LLM_ROUTER_CONFIDENCE = 0.5


# ------------------------------------------------ deterministic critic (US-F2.1)

_TOKEN_RE = re.compile(r"[0-9a-zà-öø-ÿœ]+")


def _tokens(text: str) -> set[str]:
    """Normalized word tokens (lowercase, accents kept) for similarity."""
    return set(_TOKEN_RE.findall(text.lower()))


def token_similarity(a: str, b: str) -> float:
    """Jaccard similarity of the two texts' token sets (0.0 when either is empty)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _dedup_text(obs: EngineeringObservation) -> str:
    return f"{obs.summary} {obs.description}"


@dataclass
class CriticResult:
    """Outcome of the deterministic critic over one batch of NEW observations."""

    survivors: list[EngineeringObservation] = field(default_factory=list)
    rejected: list[EngineeringObservation] = field(default_factory=list)
    # (merged-away new observation, kept existing observation) pairs — the new
    # one must be dropped from the state by the caller.
    merged: list[tuple[EngineeringObservation, EngineeringObservation]] = field(
        default_factory=list
    )


def deterministic_critic(
    new_obs: list[EngineeringObservation],
    existing: list[EngineeringObservation],
    *,
    threshold: float,
) -> CriticResult:
    """US-F2.1 (pure): reject evidence-less observations, merge near-duplicates.

    A new observation whose summary+description tokens are > ``threshold``
    Jaccard-similar to an existing NON-dismissed/NON-rejected observation of the
    SAME stream is merged into it: evidence appended, confidence bumped
    (min(1.0, max(old, new) + 0.15)), ``merged_count`` incremented. In-batch
    duplicates merge too (the first survivor becomes the target)."""
    result = CriticResult()
    candidates = [
        o
        for o in existing
        if o.status not in (ObservationStatus.REJECTED, ObservationStatus.DISMISSED)
    ]
    for obs in new_obs:
        if not obs.summary.strip() or not any(str(e).strip() for e in obs.evidence):
            obs.status = ObservationStatus.REJECTED
            obs.resolution = "rejet déterministe : résumé ou preuves manquants"
            result.rejected.append(obs)
            continue
        text = _dedup_text(obs)
        duplicate_of = next(
            (
                cand
                for cand in candidates
                if cand.stream == obs.stream
                and token_similarity(text, _dedup_text(cand)) > threshold
            ),
            None,
        )
        if duplicate_of is not None:
            for e in obs.evidence:
                if e not in duplicate_of.evidence:
                    duplicate_of.evidence.append(e)
            duplicate_of.confidence = min(
                1.0, max(duplicate_of.confidence, obs.confidence) + 0.15
            )
            duplicate_of.merged_count += 1
            result.merged.append((obs, duplicate_of))
            continue
        result.survivors.append(obs)
        candidates.append(obs)  # in-batch dedup: later near-copies merge into it
    return result


# -------------------------------------------------------- LLM critic (US-F2.2)

def apply_critic_verdicts(
    survivors: list[EngineeringObservation], reply: dict
) -> None:
    """Apply the batched critic's verdicts (pure, tolerant by contract).

    Per observation id: ``validate`` → VALIDATED with revised confidence/urgency;
    ``reject`` → REJECTED with the reason. A survivor with no (usable) verdict is
    VALIDATED unchanged — fail-open per item."""
    by_id: dict[str, dict] = {}
    verdicts = reply.get("verdicts")
    if isinstance(verdicts, list):
        for v in verdicts:
            if isinstance(v, dict) and str(v.get("id") or "").strip():
                by_id[str(v["id"]).strip()] = v
    for obs in survivors:
        v = by_id.get(obs.id)
        if not v:
            obs.status = ObservationStatus.VALIDATED
            continue
        verdict = str(v.get("verdict") or "").strip().lower()
        if verdict == "reject":
            obs.status = ObservationStatus.REJECTED
            obs.resolution = str(v.get("reason") or "rejeté par le critique d'observations")
            continue
        obs.status = ObservationStatus.VALIDATED
        try:
            confidence = float(v.get("confidence", obs.confidence))
        except (TypeError, ValueError):
            confidence = obs.confidence
        obs.confidence = max(0.0, min(1.0, confidence))
        urgency = str(v.get("urgency") or obs.urgency).strip().lower()
        if urgency in _URGENCIES:
            obs.urgency = urgency


async def acritic_llm(
    state: ProjectState, survivors: list[EngineeringObservation], arun
) -> None:
    """One BATCHED checker-tier call judging every survivor. Fail-open: any
    LLM/parse failure ⇒ all survivors VALIDATED with unchanged confidence."""
    if not survivors:
        return
    try:
        result = await arun(
            prompts.observation_critic(state, survivors),
            system_prompt=persona("observation-critic"),
        )
        apply_critic_verdicts(survivors, extract_json(result.text))
    except Exception as exc:  # noqa: BLE001 — fail-open: never block the build
        logger.warning("Observation critic failed (%s) — validating survivors as-is", exc)
        for obs in survivors:
            if obs.status == ObservationStatus.NEW:
                obs.status = ObservationStatus.VALIDATED


# --------------------------------------------------------------- router (US-F2.3)

def route_observation(obs: EngineeringObservation) -> list[str]:
    """The deterministic type→destination table (plan V3-F2), primary first.

    | type                             | destination                               |
    |----------------------------------|-------------------------------------------|
    | ambiguity, improvement, limitation | po                                      |
    | refactoring, constraint, pattern | architecture (+ po si urgency >= high)    |
    | tech_debt                        | debt                                      |
    | risk                             | risk                                      |
    | workaround                       | debt (+ po si urgency >= high)            |
    | (source_role == "security")      | security                                  |
    """
    if obs.source_role == "security":
        return ["security"]
    high = obs.urgency in _HIGH_URGENCIES
    if obs.type in (
        ObservationType.AMBIGUITY,
        ObservationType.IMPROVEMENT,
        ObservationType.LIMITATION,
    ):
        return ["po"]
    if obs.type in (
        ObservationType.REFACTORING,
        ObservationType.CONSTRAINT,
        ObservationType.PATTERN,
    ):
        return ["architecture", "po"] if high else ["architecture"]
    if obs.type == ObservationType.TECH_DEBT:
        return ["debt"]
    if obs.type == ObservationType.RISK:
        return ["risk"]
    if obs.type == ObservationType.WORKAROUND:
        return ["debt", "po"] if high else ["debt"]
    return ["po"]  # defensive: an unmapped type is governed, never lost


def coerce_llm_routes(reply: dict) -> dict[str, list[str]]:
    """Validate the optional LLM router's output: id → destinations, keeping
    only known destinations (pure, tolerant — an unusable entry is dropped)."""
    out: dict[str, list[str]] = {}
    routes = reply.get("routes")
    if not isinstance(routes, list):
        return out
    for entry in routes:
        if not isinstance(entry, dict):
            continue
        obs_id = str(entry.get("id") or "").strip()
        raw = entry.get("destinations")
        if not obs_id or not isinstance(raw, list):
            continue
        dests = [
            str(d).strip().lower()
            for d in raw
            if str(d).strip().lower() in ROUTE_DESTINATIONS
        ]
        if dests:
            out[obs_id] = list(dict.fromkeys(dests))
    return out


async def _aroute_llm(
    state: ProjectState,
    validated: list[EngineeringObservation],
    routes: dict[str, list[str]],
    arun,
) -> None:
    """Optional LLM refinement (OBSERVATION_ROUTER_LLM) of the low-confidence
    validated observations' routes. Fail-open: the deterministic table stays."""
    ambiguous = [o for o in validated if o.confidence < _LLM_ROUTER_CONFIDENCE]
    if not ambiguous:
        return
    try:
        result = await arun(
            prompts.observation_route(state, ambiguous),
            system_prompt=persona("observation-critic"),
        )
        overrides = coerce_llm_routes(extract_json(result.text))
        for obs in ambiguous:
            if obs.id in overrides:
                routes[obs.id] = overrides[obs.id]
    except Exception as exc:  # noqa: BLE001 — fail-open: keep the table's routes
        logger.warning("LLM observation router failed (%s) — keeping table routes", exc)


# ---------------------------------------------------------- orchestration

@dataclass
class ProcessOutcome:
    """What one critic→router→knowledge pass did (for logging + SSE)."""

    survivors: list[EngineeringObservation] = field(default_factory=list)
    rejected: list[EngineeringObservation] = field(default_factory=list)
    merged: list[tuple[EngineeringObservation, EngineeringObservation]] = field(
        default_factory=list
    )
    kb_dirty: bool = False

    @property
    def touched(self) -> list[EngineeringObservation]:
        """Every observation this pass changed (survivors + rejects + merge
        targets), deduplicated, for the ``observation_update`` SSE event."""
        seen: dict[str, EngineeringObservation] = {}
        for obs in [*self.survivors, *self.rejected, *(kept for _, kept in self.merged)]:
            seen.setdefault(obs.id, obs)
        return list(seen.values())


async def aprocess_new_observations(
    state: ProjectState,
    new_obs: list[EngineeringObservation],
    kb: knowledge.KnowledgeBase,
    arun,
) -> ProcessOutcome:
    """Run the full F2 chain over freshly extracted observations: deterministic
    critic (merged-away duplicates are REMOVED from the state), batched LLM
    critic, router, then the F4 knowledge writes (US-F4.2). Mutates the
    observations/state/kb in place; the caller persists state + kb."""
    new_ids = {o.id for o in new_obs}
    existing = [o for o in state.observations if o.id not in new_ids]
    result = deterministic_critic(
        new_obs, existing, threshold=settings.observation_dedup_threshold
    )
    if result.merged:
        merged_away = {dropped.id for dropped, _ in result.merged}
        state.observations[:] = [
            o for o in state.observations if o.id not in merged_away
        ]

    await acritic_llm(state, result.survivors, arun)

    validated = [
        o for o in result.survivors if o.status == ObservationStatus.VALIDATED
    ]
    routes = {o.id: route_observation(o) for o in validated}
    if settings.observation_router_llm and validated:
        await _aroute_llm(state, validated, routes, arun)

    outcome = ProcessOutcome(
        survivors=result.survivors,
        rejected=result.rejected,
        merged=result.merged,
    )
    # V3-F6: the router's knowledge writes are policy-gated (ALLOW at default
    # autonomy). When the policy withholds them (explicit autonomy ≤ 1) the
    # observations stay ROUTED — the human curates the memory via the
    # knowledge endpoints instead of the factory writing it unattended.
    memory_allowed = (
        policy.decide("memory_writes", "route_observation", state, {})
        is policy.Decision.ALLOW
    )
    for obs in validated:
        destinations = routes[obs.id]
        obs.status = ObservationStatus.ROUTED
        obs.routed_to = ",".join(destinations)
        wrote = memory_allowed and knowledge.apply_routed_observation(
            kb, obs, destinations
        )
        outcome.kb_dirty = outcome.kb_dirty or wrote
        # A memory-only observation is fully handled; a po-routed one stays
        # ROUTED in the governance queue for F3 (which will set the final state).
        if wrote and "po" not in destinations:
            obs.status = ObservationStatus.PERSISTED
    return outcome
