"""V3-F4 — Software Knowledge Base (mémoire logicielle multi-niveaux par projet).

Persists the knowledge that must NOT become a task (vision §11): component
memory, architecture notes, ADRs, debt register, risk register, pending ideas.
Stored per project in ``autospec-knowledge.json`` next to ``autospec-state.json``
(same atomic-write pattern), deliberately OUTSIDE ``ProjectState``: a different
lifecycle (survives iterations, grows slowly, compacts cleanly).

Writes go only through the F2 Router (US-F4.2) and the F3 PO governor — the
Coding Agent never writes into the memory directly (vision §9). Every entry
carries ``source_observation_id``/``iteration``/``created_at`` so the chain
observation → memory stays fully traceable.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Iterable

from pydantic import BaseModel, Field

from ..agents import prompts
from ..agents.personas import persona
from ..agents.runner import extract_json
from ..config import settings
from ..models import EngineeringObservation, ObservationType, new_id
from ..storage import save_project_file, workspace_dir

logger = logging.getLogger(__name__)

KNOWLEDGE_FILENAME = "autospec-knowledge.json"


class MemoryEntry(BaseModel):
    """One durable note (component memory or architecture note)."""

    id: str = Field(default_factory=lambda: new_id("mem"))
    text: str
    kind: str = ""               # observation type that produced it (constraint…)
    source_observation_id: str = ""
    iteration: int = 0
    created_at: float = Field(default_factory=time.time)


class ADR(BaseModel):
    """An Architecture Decision Record. Proposed by the loop, validated by the
    architect at a later ``_aarchitect_phase`` (accepted/superseded — F4.3+)."""

    id: str = Field(default_factory=lambda: new_id("adr"))
    title: str
    decision: str = ""
    context: str = ""
    status: str = "proposed"     # proposed | accepted | superseded
    source_observation_id: str = ""
    iteration: int = 0
    created_at: float = Field(default_factory=time.time)


class DebtEntry(BaseModel):
    """One technical-debt register entry."""

    id: str = Field(default_factory=lambda: new_id("debt"))
    title: str
    detail: str = ""
    effort_estimate: str = ""    # sizing hint ("" = not estimated yet)
    interest: str = ""           # « s'aggrave si… » — what makes it worse
    urgency: str = "normal"
    source_observation_id: str = ""
    iteration: int = 0
    created_at: float = Field(default_factory=time.time)


class RiskEntry(BaseModel):
    """One risk register entry."""

    id: str = Field(default_factory=lambda: new_id("risk"))
    title: str
    detail: str = ""
    likelihood: str = ""         # low | medium | high ("" = unknown)
    mitigation: str = ""
    urgency: str = "normal"
    source_observation_id: str = ""
    iteration: int = 0
    created_at: float = Field(default_factory=time.time)


class PendingIdea(BaseModel):
    """An idea deliberately NOT turned into work yet (fed by F3's DEFER)."""

    id: str = Field(default_factory=lambda: new_id("idea"))
    title: str
    detail: str = ""
    value_hint: str = ""
    reevaluate_when: str = ""
    source_observation_id: str = ""
    iteration: int = 0
    created_at: float = Field(default_factory=time.time)


class KnowledgeBase(BaseModel):
    """The whole per-project software memory (one JSON file)."""

    component_memory: dict[str, list[MemoryEntry]] = Field(default_factory=dict)
    architecture_notes: list[MemoryEntry] = Field(default_factory=list)
    adrs: list[ADR] = Field(default_factory=list)
    debt_register: list[DebtEntry] = Field(default_factory=list)
    risk_register: list[RiskEntry] = Field(default_factory=list)
    pending_ideas: list[PendingIdea] = Field(default_factory=list)


# ------------------------------------------------------------- persistence

def load_knowledge(project_id: str) -> KnowledgeBase:
    """The project's knowledge base, or an EMPTY base when the file is missing
    or corrupt (fail-open: a broken memory must never break the pipeline)."""
    path = workspace_dir(project_id) / KNOWLEDGE_FILENAME
    if not path.exists():
        return KnowledgeBase()
    try:
        return KnowledgeBase.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — corrupt memory ⇒ empty base, never a crash
        logger.warning("Failed to load knowledge base for %s: %s", project_id, exc)
        return KnowledgeBase()


def save_knowledge(project_id: str, kb: KnowledgeBase) -> None:
    """Atomically persist the knowledge base (same pattern as the state file)."""
    save_project_file(project_id, KNOWLEDGE_FILENAME, kb.model_dump_json(indent=2))


# ------------------------------------------------ router writes (US-F4.2)

def _likelihood(confidence: float) -> str:
    """Deterministic likelihood bucket from the critic-revised confidence."""
    if confidence >= 0.75:
        return "high"
    if confidence >= 0.4:
        return "medium"
    return "low"


def _memory_text(obs: EngineeringObservation) -> str:
    text = f"[{obs.type.value}] {obs.summary}"
    if obs.description:
        text += f" — {obs.description}"
    return text


def apply_routed_observation(
    kb: KnowledgeBase, obs: EngineeringObservation, destinations: list[str]
) -> bool:
    """US-F4.2: write one ROUTED observation into the knowledge base. Returns
    True when at least one entry was written. Only the memory destinations
    (debt/risk/architecture) write; "po" (F3 governance queue) and "security"
    (already inside the S1 pipeline) leave the base untouched."""
    wrote = False
    if "debt" in destinations:
        kb.debt_register.append(
            DebtEntry(
                title=obs.summary,
                detail=obs.description or obs.workaround,
                interest=obs.reevaluate_when or obs.impact,
                urgency=obs.urgency,
                source_observation_id=obs.id,
                iteration=obs.iteration,
            )
        )
        wrote = True
        # A stream-tied workaround is ALSO an active constraint of that
        # component: trace it in the component memory so F4.3 can inject
        # « contraintes + workarounds actifs » into the stream's dev prompt.
        if obs.type == ObservationType.WORKAROUND and obs.stream and obs.workaround:
            kb.component_memory.setdefault(obs.stream, []).append(
                MemoryEntry(
                    text=f"[workaround actif] {obs.workaround} ({obs.summary})",
                    kind=obs.type.value,
                    source_observation_id=obs.id,
                    iteration=obs.iteration,
                )
            )
    if "risk" in destinations:
        kb.risk_register.append(
            RiskEntry(
                title=obs.summary,
                detail=obs.description or obs.impact,
                likelihood=_likelihood(obs.confidence),
                mitigation="; ".join(obs.recommendations),
                urgency=obs.urgency,
                source_observation_id=obs.id,
                iteration=obs.iteration,
            )
        )
        wrote = True
    if "architecture" in destinations:
        entry = MemoryEntry(
            text=_memory_text(obs),
            kind=obs.type.value,
            source_observation_id=obs.id,
            iteration=obs.iteration,
        )
        # A stream-tied constraint belongs to THAT component's memory; global
        # refactoring/pattern signals go to the architecture notes.
        if obs.type == ObservationType.CONSTRAINT and obs.stream:
            kb.component_memory.setdefault(obs.stream, []).append(entry)
        else:
            kb.architecture_notes.append(entry)
        wrote = True
    return wrote


# ------------------------------------- human edition endpoints (US-F4.4)

SECTIONS = (
    "component_memory",
    "architecture_notes",
    "adrs",
    "debt_register",
    "risk_register",
    "pending_ideas",
)

# The fields a human may PATCH on an entry (text/status-like fields only —
# traceability fields id/source_observation_id/iteration/created_at are
# immutable). Applied per entry: only the fields the model actually has.
EDITABLE_FIELDS = frozenset(
    {
        "text", "title", "detail", "kind", "status", "urgency",
        "value_hint", "reevaluate_when", "mitigation", "likelihood",
        "interest", "effort_estimate", "decision", "context",
    }
)


def _section_lists(kb: KnowledgeBase, section: str) -> list[list]:
    """The mutable entry list(s) behind one section name (component_memory has
    one list per stream). Raises KeyError for an unknown section."""
    if section == "component_memory":
        return list(kb.component_memory.values())
    if section not in SECTIONS:
        raise KeyError(section)
    return [getattr(kb, section)]


def find_entry(kb: KnowledgeBase, section: str, entry_id: str):
    """One entry by section + id. Raises KeyError (unknown section or entry)."""
    for entries in _section_lists(kb, section):
        for entry in entries:
            if entry.id == entry_id:
                return entry
    raise KeyError(entry_id)


def edit_entry(kb: KnowledgeBase, section: str, entry_id: str, fields: dict):
    """US-F4.4: apply a human PATCH to one entry (allowlisted text/status
    fields only). Raises KeyError (unknown section/entry) or ValueError when no
    given field is editable on that entry. Returns the updated entry."""
    entry = find_entry(kb, section, entry_id)
    applied = False
    for key, value in fields.items():
        if key in EDITABLE_FIELDS and hasattr(entry, key) and value is not None:
            setattr(entry, key, str(value))
            applied = True
    if not applied:
        raise ValueError(
            f"aucun champ éditable pour cette entrée (autorisés : "
            f"{', '.join(sorted(EDITABLE_FIELDS))})"
        )
    return entry


def delete_entry(kb: KnowledgeBase, section: str, entry_id: str) -> None:
    """US-F4.4: remove one entry (a deleted entry is no longer injected).
    Raises KeyError when the section or entry is unknown."""
    for entries in _section_lists(kb, section):
        for i, entry in enumerate(entries):
            if entry.id == entry_id:
                del entries[i]
                if section == "component_memory":  # prune empty stream buckets
                    kb.component_memory = {
                        k: v for k, v in kb.component_memory.items() if v
                    }
                return
    raise KeyError(entry_id)


# --------------------------------------------------- compaction (US-F4.4)

def _entry_text(entry) -> str:
    """One entry flattened to a single synthesis-input line."""
    text = getattr(entry, "text", "") or getattr(entry, "title", "")
    detail = getattr(entry, "detail", "") or getattr(entry, "decision", "")
    kind = getattr(entry, "kind", "") or getattr(entry, "urgency", "")
    out = f"[{kind}] {text}" if kind else text
    if detail:
        out += f" — {detail}"
    return out[:400]


def _compactable_sections(
    kb: KnowledgeBase,
) -> Iterable[tuple[str, list, Callable[[str, int], object]]]:
    """(label, entries, make_synthetic) triples for every compactable section.
    ADRs are deliberately EXCLUDED: they are decision records, not notes — a
    superseded ADR is history, never synthesized away."""
    def _mem(text: str, merged: int) -> MemoryEntry:
        return MemoryEntry(text=f"{text} (synthèse de {merged} entrées)", kind="synthèse")

    def _debt(text: str, merged: int) -> DebtEntry:
        return DebtEntry(title=text, detail=f"(synthèse de {merged} entrées)")

    def _risk(text: str, merged: int) -> RiskEntry:
        return RiskEntry(title=text, detail=f"(synthèse de {merged} entrées)")

    def _idea(text: str, merged: int) -> PendingIdea:
        return PendingIdea(title=text, detail=f"(synthèse de {merged} entrées)")

    for stream, entries in kb.component_memory.items():
        yield f"component_memory/{stream}", entries, _mem
    yield "architecture_notes", kb.architecture_notes, _mem
    yield "debt_register", kb.debt_register, _debt
    yield "risk_register", kb.risk_register, _risk
    yield "pending_ideas", kb.pending_ideas, _idea


async def acompact_knowledge(kb: KnowledgeBase, arun, *, max_per_section: int | None = None) -> bool:
    """US-F4.4: compact every knowledge section exceeding
    KNOWLEDGE_MAX_PER_SECTION — the NEWEST half of the cap is kept verbatim,
    the older rest is synthesized into fewer entries by ONE worker-tier call
    per oversized section (persona ``knowledge-curator``). Fail-open: any
    LLM/parse failure skips that section's compaction. Returns True when the
    base changed (the caller persists)."""
    cap = settings.knowledge_max_per_section if max_per_section is None else max_per_section
    changed = False
    for label, entries, make in _compactable_sections(kb):
        if len(entries) <= cap:
            continue
        keep = entries[-(max(1, cap // 2)):]  # newest kept verbatim (append order)
        old = entries[: len(entries) - len(keep)]
        try:
            result = await arun(
                prompts.knowledge_compact(label, [_entry_text(e) for e in old]),
                system_prompt=persona("knowledge-curator"),
            )
            raw = extract_json(result.text).get("entries")
            texts = (
                [str(t).strip() for t in raw if str(t).strip()]
                if isinstance(raw, list)
                else []
            )
            if not texts or len(texts) >= len(old):
                raise ValueError("la synthèse ne réduit pas la section")
            entries[:] = [make(t, len(old)) for t in texts] + keep
            changed = True
            logger.info(
                "Knowledge section %s compacted: %d old entries → %d synthetic",
                label, len(old), len(texts),
            )
        except Exception as exc:  # noqa: BLE001 — fail-open: skip this section
            logger.warning("Knowledge compaction failed for %s: %s", label, exc)
    return changed
