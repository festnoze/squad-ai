"""V3-F3 — PO Backlog Governor (phase GOVERN).

The heart of the observation loop: after each iteration the PO receives the
implementation feedback (po-routed observations + pending ideas whose
re-evaluation condition may be met) and GOVERNS the backlog — create tasks/
stories/epics, update or enrich NON-shipped stories, defer, persist, dismiss.
The LLM proposes; THIS module applies deterministically under hard guardrails
that are never delegated to the model (vision §2/§10):

- a shipped story (DONE/GREEN) and its acceptance criteria are an immutable,
  verified contract: any update targeting one is auto-CONVERTED into a new
  evolution story referencing the original;
- acceptance criteria are only ever ENRICHED (appended with fresh ids) — the
  Amendment workflow (W5.1) keeps the monopoly on weakening a spec;
- per-iteration quotas (GOVERN_MAX_NEW_STORIES/EPICS/UPDATES) bound the
  governor's write amplitude; beyond quota a decision is auto-DEFERRED into
  the pending ideas (documented in its rationale), never silently applied;
- creations are validated with the PO-pipeline validators (referential
  integrity, acyclic dependencies) — an invalid payload marks the decision
  ``invalid`` and applies NOTHING (no partial application).

Approval gating (V3-F6): the pipeline gates every unattended application
through the policy engine (``policy.decide("backlog_changes", …)``): ALLOW
applies now, REQUIRE_HUMAN (the default-autonomy verdict) leaves the decision
``proposed`` in ``state.governance_log`` — that status IS the human approval
queue consumed by the approve/reject endpoints — and DENY marks it
``rejected_by_policy``. The deprecated GOVERNANCE_AUTO=1 flag still works
(read as an AUTONOMY_BACKLOG_CHANGES=5 pin).
"""

from __future__ import annotations

import logging

from ..config import settings
from ..models import (
    AcceptanceCriterion,
    EngineeringObservation,
    Epic,
    GovernanceAction,
    GovernanceDecision,
    ObservationStatus,
    ProjectState,
    StoryStatus,
    Task,
    UserStory,
)
from . import knowledge as knowledge_lib
from .observations import route_observation
from .plan_pipeline import S1Epic, S1Skeleton, S1Story, _detect_cycle, validate_skeleton

logger = logging.getLogger(__name__)

# A shipped story is an immutable contract (DONE merged, GREEN verified-awaiting
# merge): updates targeting one are converted into a new evolution story.
_SHIPPED_STATES = (StoryStatus.DONE, StoryStatus.GREEN)

# The F4 memory destinations a PERSIST decision may write to.
_MEMORY_SECTIONS = ("debt", "risk", "architecture")

# Quota buckets: which applied action consumes which per-iteration budget.
_QUOTA_STORIES = ("create_story",)
_QUOTA_EPICS = ("create_epic",)
_QUOTA_UPDATES = ("update_story", "enrich_criteria", "create_task")


# ------------------------------------------------------------- governance queue

def po_queue(state: ProjectState) -> list[EngineeringObservation]:
    """The observations awaiting governance: routed to "po" by F2 and still
    ROUTED (F3 sets the terminal status once a decision is applied)."""
    return [
        o
        for o in state.observations
        if o.status == ObservationStatus.ROUTED
        and "po" in [d.strip() for d in o.routed_to.split(",") if d.strip()]
    ]


def _quota_limits(cfg=None) -> dict[str, int]:
    cfg = cfg or settings
    return {
        "stories": cfg.govern_max_new_stories,
        "epics": cfg.govern_max_new_epics,
        "updates": cfg.govern_max_updates,
    }


def _quota_used(state: ProjectState, iteration: int) -> dict[str, int]:
    """Deterministic quota accounting from the permanent governance log: what
    THIS iteration's APPLIED decisions already consumed. ``applied_action`` is
    the action that was actually applied (a converted update counts as a story
    creation; a quota-deferred creation counts as nothing)."""
    used = {"stories": 0, "epics": 0, "updates": 0}
    for d in state.governance_log:
        if d.iteration != iteration or d.status != "applied":
            continue
        applied = str(d.payload.get("applied_action") or d.action.value)
        if applied in _QUOTA_STORIES:
            used["stories"] += 1
        elif applied in _QUOTA_EPICS:
            used["epics"] += 1
        elif applied in _QUOTA_UPDATES:
            used["updates"] += 1
    return used


def quotas_remaining(state: ProjectState, iteration: int | None = None, cfg=None) -> dict[str, int]:
    """Remaining per-iteration creation/update budget (for the PO prompt)."""
    iteration = state.iteration if iteration is None else iteration
    used = _quota_used(state, iteration)
    limits = _quota_limits(cfg)
    return {key: max(0, limits[key] - used[key]) for key in limits}


# ------------------------------------------------------------ output coercion

def coerce_decisions(
    state: ProjectState, reply: dict, kb: knowledge_lib.KnowledgeBase
) -> tuple[list[GovernanceDecision], list[str]]:
    """US-F3.2: validate the governor's raw JSON into ``proposed`` decisions
    (allocating "GOV-<n>" ids). Tolerant by contract: a malformed list or entry
    yields fewer (or zero) decisions plus a warning line, never an exception —
    governance is fail-open, the iteration always completes."""
    warnings: list[str] = []
    decisions: list[GovernanceDecision] = []
    raw = reply.get("decisions")
    if not isinstance(raw, list):
        return [], (["sortie sans liste `decisions` exploitable"] if raw is not None else [])
    known = {o.id for o in po_queue(state)} | {i.id for i in kb.pending_ideas}
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            warnings.append("entrée de décision non-objet ignorée")
            continue
        obs_id = str(entry.get("observation_id") or "").strip()
        try:
            action = GovernanceAction(str(entry.get("action") or "").strip().lower())
        except ValueError:
            warnings.append(f"{obs_id or '?'} : action inconnue « {entry.get('action')} »")
            continue
        if obs_id not in known:
            warnings.append(f"observation/idée inconnue « {obs_id or '?'} » — décision ignorée")
            continue
        if obs_id in seen:  # one decision per observation (plan V3-F3)
            warnings.append(f"{obs_id} : décision en double ignorée")
            continue
        seen.add(obs_id)
        payload = entry.get("payload")
        state.governance_seq += 1
        decisions.append(
            GovernanceDecision(
                id=f"GOV-{state.governance_seq}",
                observation_id=obs_id,
                action=action,
                target_id=str(entry.get("target_id") or "").strip(),
                payload=payload if isinstance(payload, dict) else {},
                rationale=str(entry.get("rationale") or "").strip(),
                status="proposed",
                iteration=state.iteration,
            )
        )
    return decisions, warnings


# --------------------------------------------------------- application helpers

def _find_observation(state: ProjectState, obs_id: str) -> EngineeringObservation | None:
    return next((o for o in state.observations if o.id == obs_id), None)


def _find_idea(kb: knowledge_lib.KnowledgeBase, idea_id: str):
    return next((i for i in kb.pending_ideas if i.id == idea_id), None)


def _find_story(state: ProjectState, story_id: str) -> UserStory | None:
    return next((s for s in state.stories if s.id == story_id), None)


def _seq_id(prefix: str, taken: set[str]) -> str:
    """The first unused ``{prefix}-{n}`` id — the existing plan id scheme."""
    n = len(taken) + 1
    while f"{prefix}-{n}" in taken:
        n += 1
    return f"{prefix}-{n}"


def _str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def _clamp_priority(value, default: int = 3) -> int:
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return default


def _next_ac_ids(story: UserStory, count: int) -> list[str]:
    """Fresh, collision-free AC ids continuing the story's numbering."""
    taken = {c.id for c in story.acceptance_criteria}
    out: list[str] = []
    n = len(taken)
    for _ in range(count):
        n += 1
        while f"AC-{n}" in taken:
            n += 1
        taken.add(f"AC-{n}")
        out.append(f"AC-{n}")
    return out


def _shipped(story: UserStory) -> bool:
    return (
        story.status in _SHIPPED_STATES
        or story.effective_status() in _SHIPPED_STATES
    )


def _mark_invalid(decision: GovernanceDecision, reason: str) -> str:
    """Terminal ``invalid``: NOTHING was applied (the source observation stays
    in the queue untouched — no partial application, ever)."""
    decision.status = "invalid"
    decision.payload = {**decision.payload, "error": reason}
    logger.warning("Governance decision %s invalid: %s", decision.id, reason)
    return "invalid"


def _build_story(
    state: ProjectState, payload: dict, *, cfg=None
) -> tuple[UserStory | None, str]:
    """Build + validate ONE governance-created story (nothing is appended here
    — the caller commits only on success). Returns ``(story, "")`` or
    ``(None, reason)``. Validation reuses the PO-pipeline validators (unique
    ids, referential integrity, acyclic dependencies)."""
    cfg = cfg or settings
    title = str(payload.get("title") or "").strip()
    if not title:
        return None, "payload sans `title`"
    epic_id = str(payload.get("epic_id") or "").strip()
    epic = next((e for e in state.epics if e.id == epic_id), None)
    if epic is None:
        return None, f"epic inconnu « {epic_id or '(vide)'} »"
    stream = str(payload.get("stream") or "").strip()
    valid_streams = {s.id for s in state.effective_streams()} | {""}
    if stream not in valid_streams:
        return None, f"stream inconnu « {stream} »"
    depends_on = _str_list(payload.get("depends_on"))
    taken = {s.id for s in state.stories}
    story_id = _seq_id("US", taken)
    criteria = _str_list(payload.get("acceptance_criteria"))
    story = UserStory(
        id=story_id,
        epic_id=epic_id,
        title=title,
        description=str(payload.get("description") or ""),
        acceptance_criteria=[
            AcceptanceCriterion(id=f"AC-{i}", text=text)
            for i, text in enumerate(criteria, start=1)
        ],
        gherkin=str(payload.get("gherkin") or ""),
        depends_on=depends_on,
        priority=_clamp_priority(payload.get("priority", 3)),
        status=StoryStatus.TODO,
        # Picked up by the NEXT cycle (Continue Build / next plan pool).
        iteration=state.iteration + 1,
        stream=stream,
        ui=bool(payload.get("ui", False)),
        technical=bool(payload.get("technical", False)),
        contract=str(payload.get("contract") or ""),
    )
    # PO-pipeline validators (US-F3.3): unique ids, referential integrity of
    # depends_on against the existing backlog, acyclic dependency graph.
    skeleton = S1Skeleton(
        epics=[
            S1Epic(
                id=epic.id,
                title=epic.title,
                stories=[
                    S1Story(
                        id=story_id,
                        title=title,
                        depends_on=depends_on,
                        priority=story.priority,
                        stream=stream,
                    )
                ],
            )
        ]
    )
    errors, _warnings = validate_skeleton(
        skeleton,
        existing_story_ids={s.id for s in state.stories},
        budget=cfg.task_file_budget,
    )
    if errors:
        return None, "; ".join(errors)
    return story, ""


def _conversion_payload(story: UserStory, decision: GovernanceDecision) -> dict:
    """The create_story payload of an UPDATE/ENRICH auto-converted off a
    shipped story: a refactoring/evolution story referencing the original."""
    payload = decision.payload
    criteria = _str_list(payload.get("acceptance_criteria")) or [
        f"L'évolution demandée sur {story.id} est livrée sans régresser ses critères existants."
    ]
    description = str(payload.get("description") or "").strip()
    return {
        "title": str(payload.get("title") or "").strip()
        or f"Évolution de {story.id} — {story.title}",
        "description": (
            f"Story d'évolution de {story.id} (« {story.title} ») : les critères "
            f"d'acceptance d'une story livrée sont un contrat vérifié et immuable."
            + (f"\n{description}" if description else "")
        ),
        "epic_id": story.epic_id,
        "acceptance_criteria": criteria,
        "priority": payload.get("priority", story.priority),
        "stream": story.stream,
        "depends_on": [story.id],
        "ui": story.ui,
    }


def _defer_to_pending(
    state: ProjectState,
    kb: knowledge_lib.KnowledgeBase,
    decision: GovernanceDecision,
    obs: EngineeringObservation | None,
    idea,
) -> None:
    """Apply a DEFER: a new PendingIdea (or the re-deferred existing idea)."""
    payload = decision.payload
    if idea is not None:
        # Re-deferred idea: refresh its re-evaluation condition, keep the entry.
        idea.value_hint = str(payload.get("value_hint") or idea.value_hint)
        idea.reevaluate_when = str(payload.get("reevaluate_when") or idea.reevaluate_when)
        return
    kb.pending_ideas.append(
        knowledge_lib.PendingIdea(
            title=str(payload.get("title") or (obs.summary if obs else decision.id)),
            detail=(obs.description if obs else "") or str(payload.get("detail") or ""),
            value_hint=str(payload.get("value_hint") or ""),
            reevaluate_when=str(payload.get("reevaluate_when") or "")
            or (obs.reevaluate_when if obs else ""),
            source_observation_id=obs.id if obs else "",
            iteration=decision.iteration,
        )
    )


# ------------------------------------------------------------- apply_decision

def apply_decision(
    state: ProjectState,
    kb: knowledge_lib.KnowledgeBase,
    decision: GovernanceDecision,
    cfg=None,
) -> str:
    """US-F3.3: apply ONE governance decision deterministically, under the
    hard guardrails (see module docstring). Returns:

    - ``"applied"``   — applied as decided;
    - ``"converted"`` — applied after a deterministic conversion (update on a
      shipped story → new evolution story; quota overflow → auto-defer), the
      conversion documented in the decision's rationale;
    - ``"invalid"``   — nothing applied at all (reason in ``payload["error"]``).

    Side channel for callers: ``payload["applied_action"]`` records what was
    actually applied and ``payload["kb_dirty"]`` flags a knowledge-base write.
    """
    cfg = cfg or settings
    obs = _find_observation(state, decision.observation_id)
    idea = None if obs is not None else _find_idea(kb, decision.observation_id)
    if obs is None and idea is None:
        return _mark_invalid(decision, f"observation/idée inconnue « {decision.observation_id} »")

    action = decision.action
    converted = False

    # --- guardrail 1: shipped stories (and their ACs) are immutable ---------
    if action in (GovernanceAction.UPDATE_STORY, GovernanceAction.ENRICH_CRITERIA):
        story = _find_story(state, decision.target_id)
        if story is None:
            return _mark_invalid(decision, f"story inconnue « {decision.target_id or '(vide)'} »")
        if _shipped(story):
            decision.payload = _conversion_payload(story, decision)
            action = GovernanceAction.CREATE_STORY
            converted = True
            decision.rationale = (
                f"{decision.rationale} [converti en create_story : {story.id} est "
                f"livrée — ses critères sont un contrat immuable]"
            ).strip()

    # --- guardrail 2: per-iteration quotas (overflow ⇒ documented auto-defer)
    limits = _quota_limits(cfg)
    used = _quota_used(state, decision.iteration)
    bucket = (
        "stories" if action.value in _QUOTA_STORIES
        else "epics" if action.value in _QUOTA_EPICS
        else "updates" if action.value in _QUOTA_UPDATES
        else ""
    )
    if bucket and used[bucket] >= limits[bucket]:
        decision.rationale = (
            f"{decision.rationale} [quota d'itération atteint "
            f"({bucket} : {limits[bucket]}) → différé en idée en suspens]"
        ).strip()
        action = GovernanceAction.DEFER
        converted = True

    # --- dispatch (validate FIRST, mutate only on success) ------------------
    kb_dirty = False
    resolution_status = ObservationStatus.ACTIONED
    detail = ""

    if action == GovernanceAction.CREATE_STORY:
        story, error = _build_story(state, decision.payload, cfg=cfg)
        if story is None:
            return _mark_invalid(decision, error)
        state.stories.append(story)
        decision.payload = {**decision.payload, "created_story_id": story.id}
        detail = f"story {story.id} créée (itération {story.iteration})"

    elif action == GovernanceAction.CREATE_EPIC:
        title = str(decision.payload.get("title") or "").strip()
        if not title:
            return _mark_invalid(decision, "payload sans `title`")
        epic_id = _seq_id("EPIC", {e.id for e in state.epics})
        state.epics.append(
            Epic(
                id=epic_id,
                title=title,
                description=str(decision.payload.get("description") or ""),
                iteration=state.iteration + 1,
            )
        )
        decision.payload = {**decision.payload, "created_epic_id": epic_id}
        detail = f"epic {epic_id} créé"

    elif action == GovernanceAction.CREATE_TASK:
        story = _find_story(state, decision.target_id)
        if story is None:
            return _mark_invalid(decision, f"story inconnue « {decision.target_id or '(vide)'} »")
        if _shipped(story):
            return _mark_invalid(decision, f"{story.id} est livrée — pas de nouvelle tâche dessus")
        title = str(decision.payload.get("title") or "").strip()
        if not title:
            return _mark_invalid(decision, "payload sans `title`")
        stream = str(decision.payload.get("stream") or "").strip()
        if stream not in ({s.id for s in state.effective_streams()} | {""}):
            return _mark_invalid(decision, f"stream inconnu « {stream} »")
        all_tasks = state.all_tasks()
        task_ids = {t.id for t in all_tasks}
        depends_on = _str_list(decision.payload.get("depends_on"))
        unknown = [d for d in depends_on if d not in task_ids]
        if unknown:
            return _mark_invalid(decision, f"dépendance(s) de tâche inconnue(s) : {', '.join(unknown)}")
        task_id = _seq_id("T", task_ids)
        edges = {t.id: list(t.depends_on) for t in all_tasks}
        edges[task_id] = depends_on
        cycle = _detect_cycle(edges)
        if cycle:
            return _mark_invalid(decision, "cycle de dépendances entre tâches : " + " → ".join(cycle))
        criteria = _str_list(decision.payload.get("acceptance_criteria"))
        story.tasks.append(
            Task(
                id=task_id,
                story_id=story.id,
                stream=stream,
                title=title,
                description=str(decision.payload.get("description") or ""),
                acceptance_criteria=[
                    AcceptanceCriterion(id=f"AC-{i}", text=text)
                    for i, text in enumerate(criteria, start=1)
                ],
                depends_on=depends_on,
                status=StoryStatus.TODO,
            )
        )
        decision.payload = {**decision.payload, "created_task_id": task_id}
        detail = f"tâche {task_id} ajoutée à {story.id}"

    elif action == GovernanceAction.UPDATE_STORY:
        story = _find_story(state, decision.target_id)  # non-shipped (checked above)
        if story is None:  # defensive: guardrail 1 already rejected this
            return _mark_invalid(decision, f"story inconnue « {decision.target_id} »")
        description = decision.payload.get("description")
        priority = decision.payload.get("priority")
        if description is None and priority is None:
            return _mark_invalid(decision, "payload sans champ modifiable (`description`/`priority`)")
        if description is not None:
            story.description = str(description)
        if priority is not None:
            story.priority = _clamp_priority(priority, story.priority)
        # Acceptance criteria are NEVER touched here (enrich_criteria appends).
        detail = f"story {story.id} mise à jour"

    elif action == GovernanceAction.ENRICH_CRITERIA:
        story = _find_story(state, decision.target_id)  # non-shipped (checked above)
        if story is None:  # defensive: guardrail 1 already rejected this
            return _mark_invalid(decision, f"story inconnue « {decision.target_id} »")
        new_texts = _str_list(decision.payload.get("acceptance_criteria"))
        if not new_texts:
            return _mark_invalid(decision, "payload sans `acceptance_criteria` à ajouter")
        # ENRICH ONLY: fresh ids appended, the existing criteria stay verbatim.
        for ac_id, text in zip(_next_ac_ids(story, len(new_texts)), new_texts):
            story.acceptance_criteria.append(AcceptanceCriterion(id=ac_id, text=text))
        detail = f"{len(new_texts)} critère(s) ajouté(s) à {story.id}"

    elif action == GovernanceAction.DEFER:
        _defer_to_pending(state, kb, decision, obs, idea)
        kb_dirty = True
        resolution_status = ObservationStatus.DEFERRED
        detail = "différé en idée en suspens"
        idea = None  # a re-deferred idea must stay in pending_ideas

    elif action == GovernanceAction.PERSIST:
        if obs is not None:
            section = str(decision.payload.get("section") or "").strip().lower()
            destinations = (
                [section]
                if section in _MEMORY_SECTIONS
                else [d for d in route_observation(obs) if d in _MEMORY_SECTIONS]
                or ["architecture"]
            )
            knowledge_lib.apply_routed_observation(kb, obs, destinations)
            detail = "mémorisé (" + ", ".join(destinations) + ")"
        else:  # an archived pending idea becomes a durable architecture note
            kb.architecture_notes.append(
                knowledge_lib.MemoryEntry(
                    text=f"[idée archivée] {idea.title}" + (f" — {idea.detail}" if idea.detail else ""),
                    kind="pending_idea",
                    source_observation_id=idea.source_observation_id,
                    iteration=decision.iteration,
                )
            )
            detail = "idée archivée en note d'architecture"
        kb_dirty = True
        resolution_status = ObservationStatus.PERSISTED

    elif action == GovernanceAction.DISMISS:
        if not decision.rationale.strip():
            return _mark_invalid(decision, "dismiss sans rationale (motif obligatoire)")
        resolution_status = ObservationStatus.DISMISSED
        detail = "écarté"

    else:  # pragma: no cover — every enum member is handled above
        return _mark_invalid(decision, f"action non gérée « {action.value} »")

    # --- commit: decision journal + source observation/idea resolution ------
    decision.status = "applied"
    decision.payload = {
        **decision.payload,
        "applied_action": action.value,
        **({"kb_dirty": True} if kb_dirty else {}),
    }
    if obs is not None:
        obs.status = resolution_status
        obs.resolution = f"{decision.id} {action.value}" + (f" — {detail}" if detail else "")
        if decision.rationale:
            obs.resolution += f" ({decision.rationale[:300]})"
    if idea is not None:
        # The pending idea was decided (actioned/persisted/dismissed): consume it.
        kb.pending_ideas[:] = [i for i in kb.pending_ideas if i.id != idea.id]
        decision.payload["kb_dirty"] = True
    return "converted" if converted else "applied"


# --------------------------------------------------- approval queue (US-F3.4)

def find_decision(state: ProjectState, decision_id: str) -> GovernanceDecision:
    """One decision by id. Raises KeyError when unknown (API → 404)."""
    for decision in state.governance_log:
        if decision.id == decision_id:
            return decision
    raise KeyError(decision_id)


def approve(
    state: ProjectState,
    kb: knowledge_lib.KnowledgeBase,
    decision_id: str,
    cfg=None,
) -> GovernanceDecision:
    """Approve one ``proposed`` decision and APPLY it now (works mid-dormancy —
    no live lifecycle needed). Raises KeyError (unknown) / ValueError (already
    handled). The human approval satisfies the F6 policy by definition
    (REQUIRE_HUMAN means exactly this endpoint), so no policy re-check here."""
    decision = find_decision(state, decision_id)
    if decision.status != "proposed":
        raise ValueError(f"décision {decision_id} déjà traitée (statut : {decision.status})")
    apply_decision(state, kb, decision, cfg)
    return decision


def reject(
    state: ProjectState,
    kb: knowledge_lib.KnowledgeBase,
    decision_id: str,
    reason: str = "",
) -> GovernanceDecision:
    """Reject one ``proposed`` decision: ``rejected_by_human`` + the source
    observation DISMISSED with the resolution. A pending idea source stays in
    the ideas (the human refused the PO's proposal, not the idea itself)."""
    decision = find_decision(state, decision_id)
    if decision.status != "proposed":
        raise ValueError(f"décision {decision_id} déjà traitée (statut : {decision.status})")
    decision.status = "rejected_by_human"
    if reason.strip():
        decision.rationale = f"{decision.rationale} [rejet humain : {reason.strip()}]".strip()
    obs = _find_observation(state, decision.observation_id)
    if obs is not None:
        obs.status = ObservationStatus.DISMISSED
        obs.resolution = f"{decision.id} rejetée par l'humain" + (
            f" : {reason.strip()}" if reason.strip() else ""
        )
    return decision
