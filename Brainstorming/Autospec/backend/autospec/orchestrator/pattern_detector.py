"""V3-F5 — Pattern Detector (agent ambient).

Detects the trends nobody sees task by task (vision §12–§13): a fragile
component concentrating failures, an accumulation of workarounds/debt on one
stream, an abnormal recurrence of the same signal. Autospec philosophy —
deterministic first:

1. **Watermark + threshold gate** — the detector is event-driven, never a
   permanent LLM loop. ``ProjectState`` persists a lightweight watermark
   (``pattern_last_obs_seq`` = observation-id allocations consumed,
   ``pattern_last_guard_count`` = guard findings consumed); below
   ``PATTERN_MIN_SIGNALS`` new signals the run is skipped with ZERO LLM call
   (and the watermark does NOT advance, so signals keep accumulating).
2. **Deterministic aggregator** (:func:`aggregate_signals`, pure) — per
   type/stream observation counts weighted by the F2 critic's merge
   recurrences, guard findings this/last iteration, first-attempt failure
   rate, the PO-pipeline calibration counters, debt entries per stream.
3. **One boss-tier LLM call** on the aggregates (``prompts.pattern_detect``,
   persona ``pattern-detector``) formulating at most ``PATTERN_MAX_FINDINGS``
   meta-observations with numeric evidence. :func:`coerce_findings` validates
   the output (summary + evidence mandatory, urgency normalized, stream
   checked against the known ones, confidence derived DETERMINISTICALLY from
   the evidence strength).

The emitted meta-observations (``type=PATTERN``, ``source_role=
"pattern-detector"``) go back through the F2 critic/router chain like any
other observation — the router sends pattern → architecture (+ po when the
urgency is high), so the detector proposes and the PO governs. Fail-open by
contract: any failure means no meta-observation, never a blocked lifecycle.
"""

from __future__ import annotations

import logging

from ..models import (
    EngineeringObservation,
    ObservationStatus,
    PlanCalibration,
    ProjectState,
    StoryStatus,
)
from .knowledge import KnowledgeBase

logger = logging.getLogger(__name__)

_URGENCIES = ("low", "normal", "high", "critical")

# Statuses excluded from the aggregates: a rejected/dismissed observation was
# judged noise — it must not feed a "trend".
_INACTIVE = (ObservationStatus.REJECTED, ObservationStatus.DISMISSED)


# ------------------------------------------------------ watermark & signals

def total_guard_findings(state: ProjectState) -> int:
    """Every anti-cheating guard finding currently recorded on the stories."""
    return sum(len(s.guard_findings) for s in state.stories)


def count_new_signals(state: ProjectState) -> int:
    """New signals since the persisted watermark: observation-id ALLOCATIONS
    (``observation_seq`` — a merged-away duplicate consumed an id too, and a
    repeat IS a strong signal) plus new guard findings. Legacy states default
    the watermark to 0/0, so everything is new on the first run."""
    obs = max(0, state.observation_seq - state.pattern_last_obs_seq)
    guards = max(0, total_guard_findings(state) - state.pattern_last_guard_count)
    return obs + guards


def advance_watermark(state: ProjectState) -> None:
    """Mark every current signal as consumed. Called AFTER an analysis run
    (including the detector's own emissions, which must not count as fresh
    signals and re-trigger the detector next iteration)."""
    state.pattern_last_obs_seq = state.observation_seq
    state.pattern_last_guard_count = total_guard_findings(state)


# ------------------------------------------- deterministic aggregator (US-F5.1)

def _weight(obs: EngineeringObservation) -> int:
    """Repeat weight of one observation: itself + the near-duplicates the F2
    critic merged into it (repeated signal = strong signal)."""
    return 1 + max(0, obs.merged_count)


def aggregate_signals(state: ProjectState, kb: KnowledgeBase) -> dict:
    """US-F5.1 (pure): the deterministic aggregates the LLM stage reads.

    Everything is computed from what already exists — ``state.observations``
    (merge recurrences included), the stories' ``guard_findings`` and
    ``attempts``, ``state.calibration`` (PlanCalibration counters per
    iteration) and ``kb.debt_register`` (stream resolved through the source
    observation). No LLM, no I/O."""
    active = [o for o in state.observations if o.status not in _INACTIVE]

    by_type: dict[str, dict] = {}
    by_stream: dict[str, dict] = {}
    for o in active:
        w = _weight(o)
        t = by_type.setdefault(o.type.value, {"count": 0, "weight": 0})
        t["count"] += 1
        t["weight"] += w
        s = by_stream.setdefault(
            o.stream or "", {"count": 0, "weight": 0, "by_type": {}}
        )
        s["count"] += 1
        s["weight"] += w
        s["by_type"][o.type.value] = s["by_type"].get(o.type.value, 0) + w

    # Recurrences: the top candidate anomalies handed to the LLM stage.
    recurrent = [
        {
            "id": o.id,
            "type": o.type.value,
            "stream": o.stream or "",
            "summary": o.summary[:200],
            "merged_count": o.merged_count,
            "urgency": o.urgency,
        }
        for o in active
        if o.merged_count >= 2
    ]

    guards_by_stream: dict[str, int] = {}
    for story in state.stories:
        if story.guard_findings:
            key = story.stream or ""
            guards_by_stream[key] = guards_by_stream.get(key, 0) + len(
                story.guard_findings
            )
    guards = {
        "total": total_guard_findings(state),
        "by_stream": guards_by_stream,
        "stories_this_iteration": [
            s.id
            for s in state.stories
            if s.guard_findings and s.iteration == state.iteration
        ],
        "stories_last_iteration": [
            s.id
            for s in state.stories
            if s.guard_findings and s.iteration == state.iteration - 1
        ],
    }

    # First-attempt failure rate, derived from the stories' attempt counters:
    # a story that needed a 2nd attempt (or FAILED outright) failed its first.
    measured = [s for s in state.stories if s.attempts >= 1]
    failures = [
        s for s in measured if s.attempts >= 2 or s.status == StoryStatus.FAILED
    ]
    first_attempt = {
        "stories_measured": len(measured),
        "failures": len(failures),
        "failure_rate": round(len(failures) / len(measured), 3) if measured else 0.0,
    }

    calib_fields = list(PlanCalibration.model_fields)
    calib_by_iteration: dict[int, dict] = {}
    calib_totals = dict.fromkeys(calib_fields, 0)
    for it in sorted(state.calibration):
        entry = {f: getattr(state.calibration[it], f) for f in calib_fields}
        calib_by_iteration[it] = entry
        for f in calib_fields:
            calib_totals[f] += entry[f]

    # Debt per stream: a DebtEntry carries no stream — it is resolved through
    # its source observation (untraceable entries land in the "" bucket).
    stream_of_obs = {o.id: (o.stream or "") for o in state.observations}
    debt_by_stream: dict[str, int] = {}
    for entry in kb.debt_register:
        key = stream_of_obs.get(entry.source_observation_id, "")
        debt_by_stream[key] = debt_by_stream.get(key, 0) + 1

    return {
        "iteration": state.iteration,
        "new_signals": count_new_signals(state),
        "observations": {
            "total": len(active),
            "weighted_total": sum(_weight(o) for o in active),
            "by_type": by_type,
            "by_stream": by_stream,
        },
        "recurrent": recurrent,
        "guards": guards,
        "first_attempt": first_attempt,
        "calibration": {
            "by_iteration": calib_by_iteration,
            "totals": calib_totals,
        },
        "debt": {
            "total": len(kb.debt_register),
            "by_stream": debt_by_stream,
        },
    }


# ------------------------------------------------ LLM output coercion (US-F5.2)

def evidence_confidence(evidence: list[str]) -> float:
    """Deterministic confidence from the evidence strength: base 0.4, +0.15
    per evidence line that actually quotes a number (the detector's contract),
    capped at 0.9 — never 1.0, a trend is a hypothesis for the PO/architect."""
    numeric = sum(1 for e in evidence if any(ch.isdigit() for ch in str(e)))
    return min(0.9, 0.4 + 0.15 * numeric)


def known_streams(state: ProjectState) -> set[str]:
    """The stream ids a finding may legitimately point at: the project's
    effective streams plus any stream already carried by an observation."""
    ids = {s.id for s in state.effective_streams()}
    ids.update(o.stream for o in state.observations if o.stream)
    return ids


def coerce_findings(
    reply: dict, *, max_findings: int, known_streams: set[str]
) -> list[dict]:
    """Validate the detector's output into EngineeringObservation kwargs
    (pure, tolerant by contract — an unusable entry is dropped, never raises).

    Mandatory: a non-empty summary AND at least one non-empty evidence line
    (the F2 critic would reject an evidence-less observation anyway). Urgency
    is normalized (unknown → "normal"), the stream is kept only when it names
    a known one, and the confidence is derived deterministically from the
    evidence strength — the LLM does not grade itself."""
    out: list[dict] = []
    patterns = reply.get("patterns")
    if not isinstance(patterns, list):
        return out
    for entry in patterns:
        if len(out) >= max_findings:
            break
        if not isinstance(entry, dict):
            continue
        summary = str(entry.get("summary") or "").strip()
        raw_evidence = entry.get("evidence")
        evidence = (
            [str(e).strip() for e in raw_evidence if str(e).strip()]
            if isinstance(raw_evidence, list)
            else []
        )
        if not summary or not evidence:
            continue
        urgency = str(entry.get("urgency") or "normal").strip().lower()
        if urgency not in _URGENCIES:
            urgency = "normal"
        stream = str(entry.get("stream") or "").strip()
        if stream not in known_streams:
            stream = ""
        raw_reco = entry.get("recommendations")
        recommendations = (
            [str(r).strip() for r in raw_reco if str(r).strip()]
            if isinstance(raw_reco, list)
            else []
        )
        out.append(
            {
                "summary": summary,
                "description": str(entry.get("description") or "").strip(),
                "evidence": evidence,
                "impact": str(entry.get("impact") or "").strip(),
                "urgency": urgency,
                "stream": stream,
                "recommendations": recommendations,
                "confidence": evidence_confidence(evidence),
            }
        )
    return out
