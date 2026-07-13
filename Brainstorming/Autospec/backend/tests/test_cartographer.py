"""V3-F8 (Codebase Cartographer) : graphe de modules déterministe (imports
Python via AST, imports TS/JS relatifs via regex) → fan-in/fan-out, fichiers
« chauds », orphelins, tailles ; empreinte de workspace (skip complet si
inchangée) ; bloc de carte borné pour les prompts (S1 + dev) ; étage LLM
optionnel écrivant des résumés par composant dans la component_memory F4
(kind="cartography", remplace-sans-empiler, fail-open) — le tout derrière
CARTOGRAPHER (+ KNOWLEDGE/GOVERNANCE).
"""

import json

import pytest

from autospec.agents import prompts
from autospec.agents.personas import persona
from autospec.agents.runner import FakeRunner
from autospec.config import PERSONA_TIERS, settings
from autospec.models import ProjectState, Stream, StreamKind
from autospec.orchestrator import cartographer, knowledge
from autospec.orchestrator.cartographer import (
    CodeMap,
    build_code_map,
    map_block,
    map_fingerprint,
)
from autospec.orchestrator.knowledge import KnowledgeBase, MemoryEntry
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir

SUMMARY_REPLY = json.dumps(
    {
        "message": "Carte résumée.",
        "components": [
            {"stream": "backend", "summary": "Cœur métier : pkg/core.py concentre le fan-in."}
        ],
    }
)


@pytest.fixture(autouse=True)
def _clear_map_registry():
    cartographer._MAPS.clear()
    yield
    cartographer._MAPS.clear()


# ------------------------------------------------------- synthetic workspaces

def _py_ws(base):
    """Mini-workspace Python : api → core, api → util, util → core (relatif),
    un orphelin, un fichier incassable, du bruit .venv/.git à ignorer."""
    ws = base / "ws-py"
    (ws / "pkg").mkdir(parents=True)
    (ws / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (ws / "pkg" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (ws / "pkg" / "api.py").write_text(
        "from pkg.core import VALUE\nimport pkg.util\nimport json\n", encoding="utf-8"
    )
    (ws / "pkg" / "util.py").write_text("from . import core\n", encoding="utf-8")
    (ws / "pkg" / "orphan.py").write_text("X = 2\n", encoding="utf-8")
    (ws / "pkg" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    (ws / ".venv" / "lib").mkdir(parents=True)
    (ws / ".venv" / "lib" / "hidden.py").write_text("import pkg.core\n", encoding="utf-8")
    (ws / ".git").mkdir()  # dossier VCS jamais scanné (pas un vrai repo)
    return ws


def _ts_ws(base):
    """Mini-workspace TS : App → Button, App → utils, Button → utils (relatif
    ../), un orphelin, node_modules ignoré, imports externes ignorés."""
    ws = base / "ws-ts"
    (ws / "src" / "components").mkdir(parents=True)
    (ws / "src" / "lib").mkdir(parents=True)
    (ws / "src" / "App.tsx").write_text(
        'import React from "react";\n'
        'import Button from "./components/Button";\n'
        'import { helper } from "./lib/utils";\n',
        encoding="utf-8",
    )
    (ws / "src" / "components" / "Button.tsx").write_text(
        'import { helper } from "../lib/utils";\n', encoding="utf-8"
    )
    (ws / "src" / "lib" / "utils.ts").write_text(
        "export const helper = 1;\n", encoding="utf-8"
    )
    (ws / "src" / "Lonely.tsx").write_text("export default 1;\n", encoding="utf-8")
    (ws / "node_modules" / "react").mkdir(parents=True)
    (ws / "node_modules" / "react" / "index.js").write_text(
        'require("./cjs");\n', encoding="utf-8"
    )
    return ws


def _py_stream():
    return Stream(id="backend", language="python", primary=True)


def _ts_stream():
    return Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="")


# ----------------------------------------------------- graphe Python (AST)

def test_python_graph_edges_fans_and_hot_files(tmp_path):
    ws = _py_ws(tmp_path)
    cm = build_code_map(ws, [_py_stream()])
    m = cm.streams["backend"]

    assert ("pkg/api.py", "pkg/core.py") in m.edges
    assert ("pkg/api.py", "pkg/util.py") in m.edges
    # Import relatif `from . import core` résolu vers le module frère.
    assert ("pkg/util.py", "pkg/core.py") in m.edges
    assert m.fan_in["pkg/core.py"] == 2
    assert m.fan_out["pkg/api.py"] == 2
    # core.py est le fichier le plus « chaud ».
    assert m.hot_files(3)[0] == ("pkg/core.py", 2)
    # Tailles : compte des fichiers et des lignes non nuls.
    assert m.file_count == 6 and m.total_lines > 0


def test_python_orphans_unparseable_and_skipped_dirs(tmp_path):
    ws = _py_ws(tmp_path)
    cm = build_code_map(ws, [_py_stream()])
    m = cm.streams["backend"]

    # Orphelins : ni importés ni importeurs ; les nœuds du graphe n'y sont pas.
    assert "pkg/orphan.py" in m.orphans
    assert "pkg/core.py" not in m.orphans and "pkg/api.py" not in m.orphans
    # Fichier incassable : sauté avec avertissement, AUCUNE arête, pas de crash.
    assert any("broken.py" in w for w in m.warnings)
    assert not any(src == "pkg/broken.py" for src, _ in m.edges)
    # .venv/.git jamais scannés : le faux importeur caché n'ajoute pas de fan-in.
    assert not any(".venv" in f for f in m.fan_in)


def test_python_import_of_stdlib_is_not_an_edge(tmp_path):
    ws = _py_ws(tmp_path)
    cm = build_code_map(ws, [_py_stream()])
    # `import json` (externe) ne crée aucune arête interne.
    assert all(dst.startswith("pkg/") for _, dst in cm.streams["backend"].edges)


def test_include_tests_flag_skips_test_files(tmp_path):
    ws = _py_ws(tmp_path)
    (ws / "tests").mkdir()
    (ws / "tests" / "test_core.py").write_text("import pkg.core\n", encoding="utf-8")
    with_tests = build_code_map(ws, [_py_stream()])
    without = build_code_map(ws, [_py_stream()], include_tests=False)
    assert with_tests.streams["backend"].fan_in["pkg/core.py"] == 3
    assert without.streams["backend"].fan_in["pkg/core.py"] == 2
    assert not any("tests/" in f for f in without.streams["backend"].fan_in)


# ------------------------------------------------------- graphe TS (regex)

def test_ts_graph_relative_imports_only(tmp_path):
    ws = _ts_ws(tmp_path)
    cm = build_code_map(ws, [_ts_stream()])
    m = cm.streams["frontend"]

    assert ("src/App.tsx", "src/components/Button.tsx") in m.edges
    assert ("src/App.tsx", "src/lib/utils.ts") in m.edges
    assert ("src/components/Button.tsx", "src/lib/utils.ts") in m.edges
    # utils.ts est le fichier chaud ; les imports externes (react) sont ignorés.
    assert m.fan_in["src/lib/utils.ts"] == 2
    assert m.hot_files(1) == [("src/lib/utils.ts", 2)]
    assert "src/Lonely.tsx" in m.orphans
    # node_modules jamais scanné.
    assert not any("node_modules" in f for f in m.fan_in)


# ----------------------------------------------- robustesse / carte vide

def test_missing_or_empty_workspace_yields_empty_map(tmp_path):
    cm = build_code_map(tmp_path / "does-not-exist", [_py_stream()])
    assert cm.is_empty() and map_block(cm) == ""
    empty = tmp_path / "empty"
    empty.mkdir()
    cm2 = build_code_map(empty, [_py_stream()])
    assert cm2.is_empty()


def test_root_stream_excludes_other_streams_zone(tmp_path):
    ws = _py_ws(tmp_path)
    fe = ws / "frontend" / "src"
    fe.mkdir(parents=True)
    (fe / "App.tsx").write_text('import { x } from "./x";\n', encoding="utf-8")
    (fe / "x.ts").write_text("export const x = 1;\n", encoding="utf-8")
    # Un .py DANS la zone frontend : seul l'exclusion de zone l'écarte du backend.
    (fe / "helper.py").write_text("import pkg.core\n", encoding="utf-8")
    streams = [
        _py_stream(),
        Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend"),
    ]
    cm = build_code_map(ws, streams)
    # La zone frontend n'est PAS avalée par le stream racine…
    assert not any(f.startswith("frontend/") for f in cm.streams["backend"].fan_in)
    assert cm.streams["backend"].fan_in["pkg/core.py"] == 2  # api + util seulement
    # …et le stream frontend la cartographie bien (chemins relatifs à SA racine).
    assert cm.streams["frontend"].fan_in["src/x.ts"] == 1


# ------------------------------------------------------------- empreinte

def test_fingerprint_stable_then_changes_on_edit(tmp_path):
    ws = _py_ws(tmp_path)
    fp1 = map_fingerprint(ws)
    fp2 = map_fingerprint(ws)
    assert fp1 and fp1 == fp2 and fp1.startswith("fs:")
    (ws / "pkg" / "new_module.py").write_text("Y = 3\n", encoding="utf-8")
    assert map_fingerprint(ws) != fp1
    # Workspace absent : "" (l'appelant ne doit pas sauter dessus).
    assert map_fingerprint(tmp_path / "nope") == ""


def test_fingerprint_broken_git_falls_back_to_fs_hash(tmp_path):
    # Un dossier .git factice (pas un vrai repo) : git échoue → repli fichiers.
    ws = _py_ws(tmp_path)
    assert map_fingerprint(ws).startswith("fs:")


# ------------------------------------------------------------- map_block

def test_map_block_bounded_stable_and_filterable(tmp_path):
    cm = build_code_map(_py_ws(tmp_path), [_py_stream()])
    block = map_block(cm)
    assert "Carte du code" in block
    assert "pkg/core.py (fan-in 2)" in block
    assert "Fichiers à fort fan-in — prudence" in block
    assert "orphelins" in block and "pkg/orphan.py" in block
    # Déterministe et borné.
    assert block == map_block(cm)
    assert len(block) <= 1800
    # Filtre par stream : un stream inconnu ⇒ "".
    assert map_block(cm, stream="ghost") == ""
    assert map_block(cm, stream="backend") == block


def test_map_block_empty_map_is_empty_string():
    assert map_block(CodeMap()) == ""
    assert map_block(None) == ""


# ------------------------------------------- étage LLM (résumés composants)

def test_cartographer_persona_is_worker_tier():
    assert PERSONA_TIERS["cartographer"] == "worker"


async def test_summaries_replace_previous_cartography_entries(tmp_path):
    cm = build_code_map(_py_ws(tmp_path), [_py_stream()])
    kb = KnowledgeBase()
    kb.component_memory["backend"] = [
        MemoryEntry(text="ancien résumé de carte", kind="cartography"),
        MemoryEntry(text="contrainte à conserver", kind="constraint"),
    ]
    runner = FakeRunner([SUMMARY_REPLY])

    changed = await cartographer.asummarize_components(kb, cm, runner.arun, iteration=2)

    assert changed is True
    assert len(runner.calls) == 1
    assert runner.calls[0]["system_prompt"] == persona("cartographer")
    assert "CARTOGRAPHE" in runner.calls[0]["prompt"]
    entries = kb.component_memory["backend"]
    cartography = [e for e in entries if e.kind == "cartography"]
    # Remplace-sans-empiler : UNE seule entrée cartography (la nouvelle).
    assert len(cartography) == 1
    assert cartography[0].text.startswith("Cœur métier")
    assert cartography[0].iteration == 2
    # Les autres kinds (contraintes, workarounds) ne sont jamais touchés.
    assert any(e.kind == "constraint" for e in entries)


async def test_summaries_fail_open_on_bad_json(tmp_path):
    cm = build_code_map(_py_ws(tmp_path), [_py_stream()])
    kb = KnowledgeBase()
    kb.component_memory["backend"] = [MemoryEntry(text="ancien", kind="cartography")]
    runner = FakeRunner(["pas du json"])
    assert await cartographer.asummarize_components(kb, cm, runner.arun) is False
    # Mémoire intouchée (l'ancienne entrée survit à l'échec).
    assert kb.component_memory["backend"][0].text == "ancien"


async def test_summaries_fail_open_on_agent_error(tmp_path):
    cm = build_code_map(_py_ws(tmp_path), [_py_stream()])
    kb = KnowledgeBase()
    runner = FakeRunner([])  # lève AgentError
    assert await cartographer.asummarize_components(kb, cm, runner.arun) is False
    assert kb.component_memory == {}


async def test_summaries_ignore_unknown_streams(tmp_path):
    cm = build_code_map(_py_ws(tmp_path), [_py_stream()])
    kb = KnowledgeBase()
    reply = json.dumps({"components": [{"stream": "ghost", "summary": "hors carte"}]})
    runner = FakeRunner([reply])
    assert await cartographer.asummarize_components(kb, cm, runner.arun) is False
    assert kb.component_memory == {}


# ------------------------------------------------------- hook pipeline (F8)

@pytest.fixture
def carto_on(monkeypatch):
    monkeypatch.setattr(settings, "cartographer_enabled", True)
    monkeypatch.setattr(settings, "knowledge_enabled", True)
    monkeypatch.setattr(settings, "cartographer_llm_enabled", False)
    monkeypatch.setattr(settings, "cartographer_hot_files", 5)


def _carto_pipeline(replies, project_id="carto-proj"):
    state = ProjectState(id=project_id, name="n", goal="g")
    runner = FakeRunner(list(replies))
    return Pipeline(state, runner), runner


def _seed_workspace(project_id):
    ws = workspace_dir(project_id)
    (ws / "pkg").mkdir(parents=True)
    (ws / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (ws / "pkg" / "core.py").write_text("VALUE = 1\n", encoding="utf-8")
    (ws / "pkg" / "api.py").write_text("from pkg.core import VALUE\n", encoding="utf-8")
    return ws


async def test_hook_flag_off_is_strict_noop():
    # CARTOGRAPHER épinglé OFF par conftest : zéro appel, zéro empreinte.
    pipeline, runner = _carto_pipeline([SUMMARY_REPLY])
    _seed_workspace(pipeline.state.id)
    await pipeline._arefresh_code_map()
    assert runner.calls == []
    assert pipeline._code_map is None
    assert pipeline.state.code_map_fingerprint == ""
    assert cartographer.current_map(pipeline.state.id) is None


async def test_hook_requires_knowledge_or_governance(monkeypatch):
    # CARTOGRAPHER=1 mais KNOWLEDGE et GOVERNANCE off ⇒ strict no-op (il écrit
    # la component_memory : sans base de connaissance vivante, il ne tourne pas).
    monkeypatch.setattr(settings, "cartographer_enabled", True)
    pipeline, runner = _carto_pipeline([SUMMARY_REPLY])
    _seed_workspace(pipeline.state.id)
    await pipeline._arefresh_code_map()
    assert runner.calls == []
    assert pipeline._code_map is None
    assert pipeline.state.code_map_fingerprint == ""


async def test_hook_builds_map_and_stores_fingerprint(carto_on):
    pipeline, runner = _carto_pipeline([])
    _seed_workspace(pipeline.state.id)
    await pipeline._arefresh_code_map()
    assert pipeline._code_map is not None
    m = pipeline._code_map.streams["backend"]
    assert m.fan_in["pkg/core.py"] == 1
    assert pipeline.state.code_map_fingerprint.startswith(("fs:", "git:"))
    # La carte est publiée au registre pour les seams de prompts.
    assert cartographer.current_map(pipeline.state.id) is pipeline._code_map
    # CARTOGRAPHER_LLM off : aucun appel agent.
    assert runner.calls == []


async def test_hook_unchanged_fingerprint_full_skip(carto_on, monkeypatch):
    pipeline, runner = _carto_pipeline([SUMMARY_REPLY])
    _seed_workspace(pipeline.state.id)
    await pipeline._arefresh_code_map()
    first_map = pipeline._code_map

    # Workspace inchangé + LLM réactivé : NI rebuild NI appel LLM.
    monkeypatch.setattr(settings, "cartographer_llm_enabled", True)
    rebuilds: list[int] = []
    real_build = cartographer.build_code_map

    def _spy(*args, **kwargs):
        rebuilds.append(1)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(cartographer, "build_code_map", _spy)
    await pipeline._arefresh_code_map()
    assert rebuilds == []  # aucun rebuild : skip complet sur empreinte identique
    assert pipeline._code_map is first_map
    assert runner.calls == []


async def test_hook_changed_fingerprint_rebuilds(carto_on):
    pipeline, runner = _carto_pipeline([])
    ws = _seed_workspace(pipeline.state.id)
    await pipeline._arefresh_code_map()
    fp1 = pipeline.state.code_map_fingerprint

    (ws / "pkg" / "extra.py").write_text("import pkg.core\n", encoding="utf-8")
    await pipeline._arefresh_code_map()
    assert pipeline.state.code_map_fingerprint != fp1
    assert pipeline._code_map.streams["backend"].fan_in["pkg/core.py"] == 2


async def test_hook_llm_stage_writes_component_memory(carto_on, monkeypatch):
    monkeypatch.setattr(settings, "cartographer_llm_enabled", True)
    pipeline, runner = _carto_pipeline([SUMMARY_REPLY])
    _seed_workspace(pipeline.state.id)
    await pipeline._arefresh_code_map()

    assert len(runner.calls) == 1
    assert runner.calls[0]["system_prompt"] == persona("cartographer")
    kb = knowledge.load_knowledge(pipeline.state.id)
    entries = kb.component_memory.get("backend", [])
    assert [e.kind for e in entries] == ["cartography"]
    assert entries[0].text.startswith("Cœur métier")


async def test_hook_llm_failure_is_fail_open(carto_on, monkeypatch):
    monkeypatch.setattr(settings, "cartographer_llm_enabled", True)
    pipeline, runner = _carto_pipeline(["pas du json"])
    _seed_workspace(pipeline.state.id)
    await pipeline._arefresh_code_map()
    # La carte déterministe reste utilisable, la mémoire est intouchée.
    assert pipeline._code_map is not None
    assert pipeline.state.code_map_fingerprint != ""
    kb = knowledge.load_knowledge(pipeline.state.id)
    assert kb.component_memory == {}


def test_legacy_state_loads_without_fingerprint():
    state = ProjectState.model_validate({"id": "old", "name": "n", "goal": "g"})
    assert state.code_map_fingerprint == ""


# ------------------------------------------------------- injections prompts

async def test_po_structure_injects_map_block_when_on(carto_on, tmp_path):
    state = ProjectState(id="carto-s1", name="n", goal="g", brief="un brief")
    cm = build_code_map(_py_ws(tmp_path), [_py_stream()])
    cartographer.set_current_map(state.id, cm)

    prompt = prompts.po_structure(state, "pkg")
    assert "Carte du code" in prompt
    assert "pkg/core.py (fan-in 2)" in prompt


def test_po_structure_without_cartographer_is_unchanged(tmp_path):
    # Flag OFF (conftest) : même carte enregistrée, prompt sans bloc de carte.
    state = ProjectState(id="carto-s1-off", name="n", goal="g", brief="un brief")
    cm = build_code_map(_py_ws(tmp_path), [_py_stream()])
    cartographer.set_current_map(state.id, cm)
    assert "Carte du code" not in prompts.po_structure(state, "pkg")


async def test_dev_knowledge_context_carries_hot_files_line(carto_on, tmp_path, monkeypatch):
    state = ProjectState(id="carto-dev", name="n", goal="g")
    cm = build_code_map(_py_ws(tmp_path), [_py_stream()])
    cartographer.set_current_map(state.id, cm)

    block = prompts.knowledge_context(state, stream="backend", audience="dev")
    assert "Fichiers à fort fan-in — prudence" in block
    assert "pkg/core.py (fan-in 2)" in block
    # Le stream "" retombe sur le stream primaire (backend).
    assert "pkg/core.py" in prompts.knowledge_context(state, audience="dev")
    # Cartographe OFF ⇒ la ligne disparaît (bloc identique à l'existant F4.3).
    monkeypatch.setattr(settings, "cartographer_enabled", False)
    assert "fort fan-in" not in prompts.knowledge_context(
        state, stream="backend", audience="dev"
    )
