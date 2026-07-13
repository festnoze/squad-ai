"""V3-F4 (mémoire logicielle) : modèles KnowledgeBase, persistance atomique dans
``autospec-knowledge.json`` (fichier absent/corrompu → base vide, fail-open),
écritures depuis le routeur F2 tracées par ``source_observation_id``, endpoint de
lecture GET /api/projects/{id}/knowledge (US-F4.1/F4.2) ; injection bornée dans
les prompts dev/po/architecte/qa derrière KNOWLEDGE/GOVERNANCE, flag OFF ⇒
prompts identiques (US-F4.3) ; compaction worker-tier au-delà du plafond de
section + endpoints PATCH/DELETE d'édition humaine (US-F4.4).
"""

import json

import httpx

from autospec.agents import prompts
from autospec.agents.runner import FakeRunner
from autospec.api import server
from autospec.config import settings
from autospec.models import (
    EngineeringObservation,
    Epic,
    ObservationStatus,
    ObservationType,
    ProjectState,
)
from autospec.orchestrator import knowledge
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import save_state, workspace_dir


def _obs(oid="OBS-1", *, obs_type=ObservationType.TECH_DEBT, **kw) -> EngineeringObservation:
    defaults = dict(
        summary="Duplication du mapping d'erreurs",
        description="Le mapping est copié dans deux modules.",
        evidence=["pkg/a.py", "pkg/b.py"],
        impact="maintenance double",
        confidence=0.7,
        urgency="high",
        stream="backend",
        iteration=2,
    )
    defaults.update(kw)
    return EngineeringObservation(id=oid, type=obs_type, **defaults)


def _full_base() -> knowledge.KnowledgeBase:
    return knowledge.KnowledgeBase(
        component_memory={
            "backend": [knowledge.MemoryEntry(text="contrainte API", kind="constraint",
                                              source_observation_id="OBS-1", iteration=1)]
        },
        architecture_notes=[knowledge.MemoryEntry(text="note archi", kind="refactoring")],
        adrs=[knowledge.ADR(title="Choisir SQLite", decision="SQLite en dev",
                            context="simplicité", source_observation_id="OBS-2")],
        debt_register=[knowledge.DebtEntry(title="dette", detail="raccourci",
                                           interest="s'aggrave à chaque story",
                                           source_observation_id="OBS-3", iteration=1)],
        risk_register=[knowledge.RiskEntry(title="risque", likelihood="high",
                                           mitigation="ajouter un test")],
        pending_ideas=[knowledge.PendingIdea(title="idée", value_hint="fort",
                                             reevaluate_when="après la v2")],
    )


# ---------------------------------------------------- US-F4.1 persistance

def test_round_trip_through_disk():
    kb = _full_base()
    knowledge.save_knowledge("kb-rt", kb)
    loaded = knowledge.load_knowledge("kb-rt")
    assert loaded == kb
    # Traçabilité complète observation → mémoire sur chaque section.
    assert loaded.component_memory["backend"][0].source_observation_id == "OBS-1"
    assert loaded.adrs[0].source_observation_id == "OBS-2"
    assert loaded.debt_register[0].source_observation_id == "OBS-3"


def test_missing_file_yields_empty_base():
    assert knowledge.load_knowledge("kb-missing") == knowledge.KnowledgeBase()


def test_corrupt_file_yields_empty_base_fail_open():
    ws = workspace_dir("kb-corrupt")
    ws.mkdir(parents=True, exist_ok=True)
    (ws / knowledge.KNOWLEDGE_FILENAME).write_text("{pas du json", encoding="utf-8")
    assert knowledge.load_knowledge("kb-corrupt") == knowledge.KnowledgeBase()
    # Mauvais schéma (JSON valide mais types faux) → même contrat fail-open.
    (ws / knowledge.KNOWLEDGE_FILENAME).write_text(
        json.dumps({"debt_register": "pas une liste"}), encoding="utf-8"
    )
    assert knowledge.load_knowledge("kb-corrupt") == knowledge.KnowledgeBase()


def test_save_is_atomic_no_temp_leftovers():
    knowledge.save_knowledge("kb-atomic", _full_base())
    ws = workspace_dir("kb-atomic")
    # Le fichier final est en place et valide ; aucun .tmp ne fuit dans le
    # workspace (l'écriture passe par le répertoire temporaire frère, comme
    # l'état) ni n'y reste après succès.
    assert (ws / knowledge.KNOWLEDGE_FILENAME).exists()
    assert list(ws.glob("*.tmp")) == []
    tmp_root = ws.parent / ".autospec-tmp"
    assert not tmp_root.exists() or list(tmp_root.iterdir()) == []
    payload = json.loads((ws / knowledge.KNOWLEDGE_FILENAME).read_text(encoding="utf-8"))
    assert payload["debt_register"][0]["title"] == "dette"


def test_legacy_partial_file_loads_with_defaults():
    ws = workspace_dir("kb-partial")
    ws.mkdir(parents=True, exist_ok=True)
    (ws / knowledge.KNOWLEDGE_FILENAME).write_text(
        json.dumps({"debt_register": [{"id": "d-1", "title": "vieille dette"}]}),
        encoding="utf-8",
    )
    kb = knowledge.load_knowledge("kb-partial")
    assert kb.debt_register[0].title == "vieille dette"
    assert kb.pending_ideas == [] and kb.adrs == []


# --------------------------------------- US-F4.2 écritures depuis le routeur

def test_tech_debt_writes_a_traced_debt_entry():
    kb = knowledge.KnowledgeBase()
    obs = _obs(reevaluate_when="à chaque nouvelle story du module")

    wrote = knowledge.apply_routed_observation(kb, obs, ["debt"])

    assert wrote
    entry = kb.debt_register[0]
    assert entry.title == obs.summary
    assert entry.detail == obs.description
    assert entry.interest == "à chaque nouvelle story du module"
    assert entry.urgency == "high"
    assert entry.source_observation_id == "OBS-1"
    assert entry.iteration == 2
    assert entry.created_at > 0


def test_risk_writes_a_risk_entry_with_likelihood_and_mitigation():
    kb = knowledge.KnowledgeBase()
    obs = _obs(
        obs_type=ObservationType.RISK, confidence=0.9,
        recommendations=["ajouter un test de charge", "documenter la limite"],
    )
    knowledge.apply_routed_observation(kb, obs, ["risk"])
    entry = kb.risk_register[0]
    assert entry.likelihood == "high"
    assert entry.mitigation == "ajouter un test de charge; documenter la limite"
    assert entry.source_observation_id == "OBS-1"
    # Buckets déterministes de vraisemblance.
    assert knowledge._likelihood(0.5) == "medium"
    assert knowledge._likelihood(0.1) == "low"


def test_stream_constraint_goes_to_component_memory():
    kb = knowledge.KnowledgeBase()
    obs = _obs(obs_type=ObservationType.CONSTRAINT, stream="frontend",
               summary="L'API impose un format de date ISO")
    knowledge.apply_routed_observation(kb, obs, ["architecture"])
    assert kb.architecture_notes == []
    entry = kb.component_memory["frontend"][0]
    assert entry.kind == "constraint"
    assert "format de date ISO" in entry.text
    assert entry.source_observation_id == "OBS-1"


def test_global_refactoring_and_pattern_go_to_architecture_notes():
    kb = knowledge.KnowledgeBase()
    knowledge.apply_routed_observation(
        kb, _obs("OBS-1", obs_type=ObservationType.REFACTORING), ["architecture"]
    )
    knowledge.apply_routed_observation(
        kb, _obs("OBS-2", obs_type=ObservationType.PATTERN, stream=""), ["architecture"]
    )
    # Contrainte SANS stream : note d'architecture globale aussi.
    knowledge.apply_routed_observation(
        kb, _obs("OBS-3", obs_type=ObservationType.CONSTRAINT, stream=""), ["architecture"]
    )
    assert [e.kind for e in kb.architecture_notes] == ["refactoring", "pattern", "constraint"]
    assert kb.component_memory == {}


def test_stream_workaround_writes_debt_plus_component_trace():
    kb = knowledge.KnowledgeBase()
    obs = _obs(obs_type=ObservationType.WORKAROUND,
               workaround="regex maison au lieu du parseur")
    knowledge.apply_routed_observation(kb, obs, ["debt", "po"])
    assert kb.debt_register[0].detail == obs.description
    trace = kb.component_memory["backend"][0]
    assert "workaround actif" in trace.text and "regex maison" in trace.text
    assert trace.source_observation_id == "OBS-1"


def test_non_memory_destinations_write_nothing():
    kb = knowledge.KnowledgeBase()
    assert not knowledge.apply_routed_observation(kb, _obs(), ["po"])
    assert not knowledge.apply_routed_observation(kb, _obs(), ["security"])
    assert kb == knowledge.KnowledgeBase()


# ----------------------------------------------------- API lecture (US-F4.1)

def _client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=server.app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_get_knowledge_endpoint_returns_the_base():
    save_state(ProjectState(id="kb-api", name="n", goal="g"))
    kb = knowledge.KnowledgeBase()
    knowledge.apply_routed_observation(kb, _obs(), ["debt"])
    knowledge.save_knowledge("kb-api", kb)

    async with _client() as client:
        resp = await client.get("/api/projects/kb-api/knowledge")

    assert resp.status_code == 200
    body = resp.json()
    assert body["debt_register"][0]["source_observation_id"] == "OBS-1"
    assert set(body) == {
        "component_memory", "architecture_notes", "adrs",
        "debt_register", "risk_register", "pending_ideas",
    }


async def test_get_knowledge_empty_base_when_nothing_persisted():
    save_state(ProjectState(id="kb-api-empty", name="n", goal="g"))
    async with _client() as client:
        resp = await client.get("/api/projects/kb-api-empty/knowledge")
    assert resp.status_code == 200
    assert resp.json() == knowledge.KnowledgeBase().model_dump(mode="json")


async def test_get_knowledge_unknown_project_is_404():
    async with _client() as client:
        resp = await client.get("/api/projects/kb-nope/knowledge")
    assert resp.status_code == 404


# ------------------------------------------- US-F4.3 injection dans les prompts

def _mem_entry(text, kind="constraint", ts=0.0):
    return knowledge.MemoryEntry(text=text, kind=kind, created_at=ts or 1.0)


def test_knowledge_block_dev_audience_stream_memory_newest_first():
    kb = knowledge.KnowledgeBase(component_memory={
        "backend": [_mem_entry("ancienne contrainte", ts=1.0),
                    _mem_entry("workaround regex actif", kind="workaround", ts=2.0)],
        "frontend": [_mem_entry("contrainte front", ts=3.0)],
    })
    block = prompts.knowledge_block(kb, stream="backend", audience="dev")
    assert "Mémoire logicielle du projet" in block
    # Mémoire du stream ciblé UNIQUEMENT, la plus récente d'abord.
    assert "contrainte front" not in block
    assert block.index("workaround regex actif") < block.index("ancienne contrainte")


def test_knowledge_block_qa_audience_constraints_and_limitations_only():
    kb = knowledge.KnowledgeBase(component_memory={
        "backend": [_mem_entry("contrainte API ISO", kind="constraint"),
                    _mem_entry("limite du parseur", kind="limitation"),
                    _mem_entry("piste de refacto", kind="refactoring")],
    })
    block = prompts.knowledge_block(kb, stream="backend", audience="qa")
    assert "contrainte API ISO" in block and "limite du parseur" in block
    assert "piste de refacto" not in block


def test_knowledge_block_po_audience_ideas_top_debt_high_risks():
    kb = knowledge.KnowledgeBase(
        pending_ideas=[knowledge.PendingIdea(title="Exporter en CSV",
                                             reevaluate_when="après la v2")],
        debt_register=[
            knowledge.DebtEntry(title=f"dette {i}", urgency="low", created_at=float(i))
            for i in range(1, 7)
        ] + [knowledge.DebtEntry(title="dette critique", urgency="critical", created_at=0.5)],
        risk_register=[
            knowledge.RiskEntry(title="risque fort", likelihood="high"),
            knowledge.RiskEntry(title="risque faible", likelihood="low", urgency="low"),
        ],
    )
    block = prompts.knowledge_block(kb, audience="po")
    assert "Exporter en CSV" in block and "après la v2" in block
    # Top-5 dette par urgence : la critique passe devant, la plus vieille low sort.
    assert "dette critique" in block and "dette 1" not in block
    assert "risque fort" in block and "risque faible" not in block


def test_knowledge_block_architect_audience_accepted_adrs_and_notes():
    kb = knowledge.KnowledgeBase(
        adrs=[knowledge.ADR(title="SQLite en dev", decision="SQLite", status="accepted"),
              knowledge.ADR(title="Proposition GraphQL", decision="?", status="proposed")],
        architecture_notes=[_mem_entry("note archi", kind="refactoring")],
    )
    block = prompts.knowledge_block(kb, audience="architect")
    assert "SQLite en dev" in block and "note archi" in block
    assert "GraphQL" not in block  # seuls les ADRs acceptés sont injectés


def test_knowledge_block_is_capped_and_empty_when_nothing_relevant():
    kb = knowledge.KnowledgeBase(component_memory={
        "backend": [_mem_entry(f"contrainte {i}", ts=float(i)) for i in range(15)]
    })
    block = prompts.knowledge_block(kb, stream="backend", audience="dev")
    assert block.count("\n- ") == settings.knowledge_inject_max  # jamais > plafond
    assert prompts.knowledge_block(kb, stream="frontend", audience="dev") == ""
    assert prompts.knowledge_block(knowledge.KnowledgeBase(), audience="po") == ""


def _project_with_kb(pid: str) -> ProjectState:
    state = ProjectState(id=pid, name="n", goal="g", brief="# Brief")
    state.epics.append(Epic(id="EPIC-1", title="E"))
    save_state(state)
    kb = knowledge.KnowledgeBase(
        debt_register=[knowledge.DebtEntry(title="dette connue", urgency="high")],
        component_memory={"backend": [_mem_entry("contrainte connue")]},
        architecture_notes=[_mem_entry("note archi connue")],
    )
    knowledge.save_knowledge(pid, kb)
    return state


def test_flag_off_prompts_are_byte_identical(monkeypatch):
    """AC US-F4.3 : flag OFF ⇒ prompts identiques à avant. Équivalence golden :
    avec les flags OFF et une mémoire non vide sur disque, le prompt est
    STRICTEMENT ÉGAL à celui produit sans aucune mémoire (bloc vide) — la
    mémoire n'a laissé aucune trace."""
    state = _project_with_kb("kb-golden")
    # conftest épingle knowledge_enabled/governance_enabled à False.
    off_po = prompts.po_plan(state, "pkg")
    off_arch = prompts.architect_design(state, "pkg")
    off_s1 = prompts.po_structure(state, "pkg")
    assert "Mémoire logicielle" not in off_po + off_arch + off_s1

    # Même prompt quand l'injection est active mais la base VIDE : le chemin
    # flag-off est bien byte-identique au chemin « aucune connaissance ».
    monkeypatch.setattr(settings, "knowledge_enabled", True)
    ws = workspace_dir("kb-golden")
    (ws / knowledge.KNOWLEDGE_FILENAME).unlink()
    assert prompts.po_plan(state, "pkg") == off_po
    assert prompts.architect_design(state, "pkg") == off_arch
    assert prompts.po_structure(state, "pkg") == off_s1


def test_flag_on_injects_audience_blocks(monkeypatch):
    state = _project_with_kb("kb-inject")
    monkeypatch.setattr(settings, "knowledge_enabled", True)
    assert "dette connue" in prompts.po_plan(state, "pkg")
    assert "note archi connue" in prompts.architect_design(state, "pkg")
    ctx = prompts.knowledge_context(state, stream="backend", audience="dev")
    assert "contrainte connue" in ctx


def test_governance_flag_alone_activates_injection(monkeypatch):
    # KNOWLEDGE=0 mais GOVERNANCE=1 ⇒ injection considérée active.
    state = _project_with_kb("kb-gov-on")
    assert prompts.knowledge_context(state, audience="po") == ""
    monkeypatch.setattr(settings, "governance_enabled", True)
    assert "dette connue" in prompts.knowledge_context(state, audience="po")


# ----------------------------------------------------- US-F4.4 compaction

COMPACT_REPLY = json.dumps(
    {"message": "Synthèse.", "entries": ["synthèse des vieilles contraintes"]},
    ensure_ascii=False,
)


async def test_compaction_reduces_oversized_section_keeping_newest():
    kb = knowledge.KnowledgeBase(architecture_notes=[
        _mem_entry(f"note {i}", ts=float(i)) for i in range(12)
    ])
    runner = FakeRunner([COMPACT_REPLY])

    changed = await knowledge.acompact_knowledge(kb, runner.arun, max_per_section=10)

    assert changed
    assert "MÉMOIRE LOGICIELLE" in runner.calls[0]["prompt"]
    notes = kb.architecture_notes
    # 12 entrées, plafond 10 : les 5 plus récentes verbatim, les 7 anciennes
    # synthétisées en 1 — la section repasse sous le plafond.
    assert len(notes) == 6
    assert notes[0].kind == "synthèse" and "synthèse des vieilles" in notes[0].text
    assert [n.text for n in notes[1:]] == [f"note {i}" for i in range(7, 12)]


async def test_compaction_is_fail_open_and_lazy():
    # Section sous le plafond : AUCUN appel LLM (FakeRunner vide lèverait).
    small = knowledge.KnowledgeBase(architecture_notes=[_mem_entry("note")])
    runner = FakeRunner([])
    assert await knowledge.acompact_knowledge(small, runner.arun, max_per_section=10) is False
    assert runner.calls == []
    # Appel en échec → section conservée telle quelle (fail-open).
    big = knowledge.KnowledgeBase(architecture_notes=[
        _mem_entry(f"note {i}") for i in range(12)
    ])
    assert await knowledge.acompact_knowledge(big, runner.arun, max_per_section=10) is False
    assert len(big.architecture_notes) == 12
    # Synthèse qui ne réduit pas → refusée, section intacte.
    bloated = FakeRunner([json.dumps({"entries": [f"e{i}" for i in range(30)]})])
    assert await knowledge.acompact_knowledge(big, bloated.arun, max_per_section=10) is False
    assert len(big.architecture_notes) == 12


async def test_govern_phase_triggers_compaction(monkeypatch):
    """AC US-F4.4 : le dépassement de plafond déclenche la fusion en fin de
    phase GOVERN (appel worker-tier), et la base compactée est persistée."""
    monkeypatch.setattr(settings, "governance_enabled", True)
    monkeypatch.setattr(settings, "observations_enabled", True)
    monkeypatch.setattr(settings, "knowledge_max_per_section", 10)
    state = ProjectState(id="kb-compact-phase", name="n", goal="g")
    state.epics.append(Epic(id="EPIC-1", title="E"))
    state.observations = [EngineeringObservation(
        id="OBS-1", type=ObservationType.AMBIGUITY, summary="ambiguïté",
        evidence=["e"], status=ObservationStatus.ROUTED, routed_to="po",
    )]
    knowledge.save_knowledge("kb-compact-phase", knowledge.KnowledgeBase(
        architecture_notes=[_mem_entry(f"note {i}", ts=float(i)) for i in range(12)]
    ))
    govern_reply = json.dumps({"decisions": [
        {"observation_id": "OBS-1", "action": "dismiss", "rationale": "bruit"}
    ]}, ensure_ascii=False)
    pipeline = Pipeline(state, FakeRunner([govern_reply, COMPACT_REPLY]))

    await pipeline._agovern_phase()

    saved = knowledge.load_knowledge("kb-compact-phase")
    assert len(saved.architecture_notes) == 6
    assert saved.architecture_notes[0].kind == "synthèse"


# ------------------------------------- US-F4.4 endpoints PATCH/DELETE

async def test_patch_knowledge_entry_edits_text_fields():
    save_state(ProjectState(id="kb-edit", name="n", goal="g"))
    kb = knowledge.KnowledgeBase(
        debt_register=[knowledge.DebtEntry(id="debt-1", title="dette", urgency="low")]
    )
    knowledge.save_knowledge("kb-edit", kb)

    async with _client() as client:
        resp = await client.patch(
            "/api/projects/kb-edit/knowledge/debt_register/debt-1",
            json={"title": "dette requalifiée", "urgency": "high"},
        )
        assert resp.status_code == 200
        assert resp.json()["entry"]["title"] == "dette requalifiée"

        # Aucun champ éditable fourni → 422 ; entrée/section inconnue → 404.
        empty = await client.patch(
            "/api/projects/kb-edit/knowledge/debt_register/debt-1", json={}
        )
        assert empty.status_code == 422
        missing = await client.patch(
            "/api/projects/kb-edit/knowledge/debt_register/debt-404", json={"title": "x"}
        )
        assert missing.status_code == 404
        bad_section = await client.patch(
            "/api/projects/kb-edit/knowledge/nonsense/debt-1", json={"title": "x"}
        )
        assert bad_section.status_code == 404

    saved = knowledge.load_knowledge("kb-edit")
    assert saved.debt_register[0].title == "dette requalifiée"
    assert saved.debt_register[0].urgency == "high"
    assert saved.debt_register[0].id == "debt-1"  # la traçabilité est immuable


async def test_delete_knowledge_entry_stops_injection(monkeypatch):
    save_state(ProjectState(id="kb-del", name="n", goal="g"))
    kb = knowledge.KnowledgeBase(component_memory={
        "backend": [knowledge.MemoryEntry(id="mem-1", text="contrainte à retirer",
                                          kind="constraint")]
    })
    knowledge.save_knowledge("kb-del", kb)
    monkeypatch.setattr(settings, "knowledge_enabled", True)
    state = ProjectState(id="kb-del", name="n", goal="g")
    assert "contrainte à retirer" in prompts.knowledge_context(
        state, stream="backend", audience="dev"
    )

    async with _client() as client:
        resp = await client.delete("/api/projects/kb-del/knowledge/component_memory/mem-1")
        assert resp.status_code == 200
        again = await client.delete("/api/projects/kb-del/knowledge/component_memory/mem-1")
        assert again.status_code == 404

    # L'entrée supprimée n'est PLUS injectée (AC US-F4.4).
    assert prompts.knowledge_context(state, stream="backend", audience="dev") == ""
    assert knowledge.load_knowledge("kb-del").component_memory == {}
