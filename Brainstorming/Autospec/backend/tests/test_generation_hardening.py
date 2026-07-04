"""Durcissement de la génération parallèle (points 2/3/4/5 de la revue
anti-« conflit de merge ») : union déterministe des manifestes de dépendances
au merge, scaffold plugin-style (features auto-découvertes, plus de câblage
dans main.py/App.tsx), canari post-merge (vert+vert=rouge → revert + requeue),
et cohérence zone/stream des globs dès la validation du plan."""

import asyncio
import sys

from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import (
    Epic,
    ProjectState,
    Stream,
    StreamKind,
    StoryStatus,
    UserStory,
)
from autospec.orchestrator import independence, manifests
from autospec.orchestrator import plan_pipeline as pp
from autospec.orchestrator import streams as work_streams
from autospec.orchestrator import workspace
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir

# --------------------------------------------------- point 2 : manifests unit

PYPROJECT_A = """[project]
name = "app"
version = "0.1.0"
dependencies = [
    "fastapi>=0.110",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
]
"""

PYPROJECT_B = """[project]
name = "app"
version = "0.1.0"
dependencies = [
    "redis>=5.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "freezegun>=1.4",
]
"""


def test_merge_pyproject_unions_dependency_lists():
    merged = manifests.merge_pyproject(PYPROJECT_A, PYPROJECT_B)
    assert merged is not None
    assert '"fastapi>=0.110"' in merged and '"redis>=5.0"' in merged
    assert '"freezegun>=1.4"' in merged                 # dev group unioned too
    import tomllib

    data = tomllib.loads(merged)
    assert data["project"]["name"] == "app"             # rest untouched


def test_merge_pyproject_refuses_non_dependency_divergence():
    other = PYPROJECT_B.replace('version = "0.1.0"', 'version = "0.2.0"')
    assert manifests.merge_pyproject(PYPROJECT_A, other) is None
    assert manifests.merge_pyproject(PYPROJECT_A, "pas du toml [") is None


def test_merge_pyproject_ours_pin_wins_on_same_dist():
    theirs = PYPROJECT_A.replace("fastapi>=0.110", "FastAPI==0.99")
    merged = manifests.merge_pyproject(PYPROJECT_A, theirs)
    assert merged is not None
    assert "fastapi>=0.110" in merged and "FastAPI==0.99" not in merged


def test_merge_package_json_unions_deps_and_refuses_other_changes():
    ours = '{"name": "fe", "dependencies": {"react": "^18.2.0"}}'
    theirs = '{"name": "fe", "dependencies": {"axios": "^1.6.0"}}'
    merged = manifests.merge_package_json(ours, theirs)
    assert merged is not None
    import json

    deps = json.loads(merged)["dependencies"]
    assert deps == {"axios": "^1.6.0", "react": "^18.2.0"}
    assert manifests.merge_package_json(ours, '{"name": "autre"}') is None


def test_is_manifest_conflict_only_for_manifests_and_lockfiles():
    assert manifests.is_manifest_conflict(["pyproject.toml", "uv.lock"])
    assert manifests.is_manifest_conflict(["frontend/package.json"])
    assert not manifests.is_manifest_conflict(["pyproject.toml", "app/core.py"])
    assert not manifests.is_manifest_conflict([])


# ------------------------------------------- point 2 : bout-en-bout sur git

def _state(pid: str) -> ProjectState:
    st = ProjectState(id=pid, name="hard", goal="g")
    st.epics.append(Epic(id="EPIC-1", title="E"))
    st.streams = [
        Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True)
    ]
    return st


async def test_manifest_conflict_is_auto_resolved_at_merge(tmp_path, monkeypatch):
    """Deux items parallèles ajoutent chacun une dépendance : le conflit sur
    pyproject.toml est UNION-fusionné au lieu de re-queuer le travail vert."""
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    pipeline = Pipeline(_state("mani-e2e"), ScriptedRunner())
    ws = workspace_dir("mani-e2e")
    ws.mkdir(parents=True, exist_ok=True)
    assert await pipeline._agit_ensure_repo(ws)
    (ws / "pyproject.toml").write_text(PYPROJECT_A.replace(
        '    "fastapi>=0.110",\n', ""), encoding="utf-8")
    await pipeline._agit(ws, "add", "-A")
    await pipeline._agit(ws, "commit", "-m", "base")
    _, base = await pipeline._agit(ws, "rev-parse", "HEAD")
    base = base.strip()

    # Item A ajoute fastapi, mergé le premier.
    from pathlib import Path

    wt_a = Path(tmp_path) / "wtA"
    await pipeline._agit(ws, "worktree", "add", str(wt_a), "-b", "wa", base)
    (wt_a / "pyproject.toml").write_text(PYPROJECT_A, encoding="utf-8")
    await pipeline._agit(wt_a, "add", "-A")
    await pipeline._agit(wt_a, "commit", "-m", "A")
    assert (await pipeline._agit(ws, "merge", "--no-ff", "-m", "merge A", "wa"))[0] == 0

    # Item B (parti de la même base) ajoute redis → conflit sur la même zone.
    wt_b = Path(tmp_path) / "wtB"
    await pipeline._agit(ws, "worktree", "add", str(wt_b), "-b", "wb", base)
    (wt_b / "pyproject.toml").write_text(
        PYPROJECT_A.replace('"fastapi>=0.110"', '"redis>=5.0"'), encoding="utf-8"
    )
    await pipeline._agit(wt_b, "add", "-A")
    await pipeline._agit(wt_b, "commit", "-m", "B")

    merged, conflicts = await pipeline._amerge_work_item(ws, "wb", "B", wt_b)
    assert merged is True and conflicts == []          # auto-résolu, pas requeué
    final = (ws / "pyproject.toml").read_text(encoding="utf-8")
    assert '"fastapi>=0.110"' in final and '"redis>=5.0"' in final


# ------------------------------------------------- point 3 : scaffold plugin

def test_python_scaffold_wires_feature_auto_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    state = ProjectState(id="plug", name="scaffplug", goal="g")
    ws = workspace._scaffold_python(state, ui_tests_enabled=False)
    pkg = workspace.package_name(state)

    main_text = (ws / "main.py").read_text(encoding="utf-8")
    assert f"from {pkg}.features import discover" in main_text
    assert "AUTO-DISCOVERED" in main_text
    assert (ws / pkg / "features" / "__init__.py").exists()

    # La convention marche VRAIMENT : une feature déposée est découverte.
    (ws / pkg / "features" / "hello.py").write_text(
        "def register():\n    return 'hello'\n", encoding="utf-8"
    )
    sys.path.insert(0, str(ws))
    try:
        import importlib

        features = importlib.import_module(f"{pkg}.features")
        hooks = features.discover()
        assert len(hooks) == 1 and hooks[0]() == "hello"
    finally:
        sys.path.remove(str(ws))
        for mod in [m for m in sys.modules if m.startswith(pkg)]:
            sys.modules.pop(mod, None)


def test_frontend_scaffold_auto_discovers_feature_components(tmp_path, monkeypatch):
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    state = ProjectState(id="plug-fe", name="scafffe", goal="g")
    stream = Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend")
    root = workspace.scaffold_frontend(state, stream)

    app = (root / "src" / "App.tsx").read_text(encoding="utf-8")
    assert 'import.meta.glob("./features/*.tsx"' in app
    assert (root / "src" / "features").is_dir()
    tsconfig = (root / "tsconfig.json").read_text(encoding="utf-8")
    assert "vite/client" in tsconfig                   # types du glob Vite


def test_prompts_teach_the_plugin_convention():
    assert "AUTO-DÉCOUVRE" in __import__("autospec.agents.prompts", fromlist=["x"]).sizing_rules()
    from autospec.agents import prompts

    scope = prompts.file_scope_block(["pkg/a.py"])
    assert "AUTO-DÉCOUVERTE" in scope and "features/" in scope
    story = UserStory(id="US-1", epic_id="E1", title="S")
    dev = prompts.dev_story(story, "pkg", "f.feature")
    assert "features/<ta_feature>.py" in dev and "register()" in dev


# --------------------------------------------------- point 4 : canari post-merge

async def test_semantic_conflict_is_reverted_and_requeued(tmp_path, monkeypatch):
    """Vert+vert=rouge : le canari détecte la suite rouge sur le HEAD combiné,
    reverte le merge (HEAD reste vert) et re-queue l'item — qui aboutit à la
    tentative suivante quand la suite combinée passe."""
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)
    monkeypatch.setattr(settings, "dev_max_attempts", 2)
    monkeypatch.setattr(settings, "post_merge_canary", True)
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    state = _state("canary")
    state.stories = [
        UserStory(id="US-1", epic_id="EPIC-1", title="S", stream="backend",
                  gherkin="Feature: F\n  Scenario: S\n    Given a")
    ]
    pipeline = Pipeline(state, ScriptedRunner())
    canary_runs = []

    async def _dev(subject, worktree, pkg, is_frontend):
        (workspace_dir("canary") and None)
        from pathlib import Path

        (Path(worktree) / "f.py").write_text(f"x = {len(canary_runs)}\n", encoding="utf-8")
        return True, ""

    async def _pytest(ws=None):
        if ws is not None:
            return True, "", {}          # suites de worktree (resume/verify)
        canary_runs.append(1)
        # Premier canari (HEAD combiné) rouge, le second vert.
        return (len(canary_runs) > 1), "échec combiné", {}

    monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    story = state.story("US-1")
    assert story.status == StoryStatus.DONE
    assert len(canary_runs) == 2
    cal = state.calibration_for()
    assert cal.canary_reverts == 1
    assert any("conflit sémantique" in l for l in state.sizing_lessons)
    # Le revert est bien dans l'historique du repo partagé.
    ws = workspace_dir("canary")
    _, log = await pipeline._agit(ws, "log", "--oneline")
    assert "Revert" in log


async def test_canary_off_keeps_the_old_behaviour(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)
    monkeypatch.setattr(settings, "post_merge_canary", False)
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    state = _state("canary-off")
    state.stories = [
        UserStory(id="US-1", epic_id="EPIC-1", title="S", stream="backend",
                  gherkin="Feature: F\n  Scenario: S\n    Given a")
    ]
    pipeline = Pipeline(state, ScriptedRunner())
    calls = []

    async def _dev(subject, worktree, pkg, is_frontend):
        return True, ""

    async def _pytest(ws=None):
        if ws is None:
            calls.append(1)              # un appel sans ws = le canari
        return True, "", {}

    monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    assert state.story("US-1").status == StoryStatus.DONE
    assert calls == []                   # flag off → aucune suite rejouée sur HEAD


# ------------------------------------------- point 5 : cohérence zone/stream

def test_zone_mismatches_flags_globs_outside_their_stream():
    roots = {"backend": "", "frontend": "frontend", "": ""}
    claims = [
        independence.TaskClaim(id="T-1", stream="frontend", file_globs=("pkg/api.py",)),
        independence.TaskClaim(id="T-2", stream="frontend", file_globs=("frontend/src/X.tsx",)),
        independence.TaskClaim(id="T-3", stream="backend", file_globs=("frontend/src/Y.tsx",)),
        independence.TaskClaim(id="T-4", stream="backend", file_globs=("pkg/core.py",)),
    ]
    found = independence.zone_mismatches(claims, roots)
    text = "\n".join(found)
    assert "T-1" in text and "hors de «" in text.replace("« ", "« ") or "T-1" in text
    assert "T-3" in text                                # backend qui écrit dans frontend/
    assert "T-2" not in text and "T-4" not in text


# ------------------------------- fails inutiles : JSON, retry, rouge, contrats

def _dev_state(pid: str) -> ProjectState:
    st = _state(pid)
    st.stories = [
        UserStory(id="US-1", epic_id="EPIC-1", title="S", stream="backend",
                  gherkin="Feature: F\n  Scenario: S\n    Given a")
    ]
    return st


async def test_unparseable_dev_reply_does_not_lose_green_work(tmp_path, monkeypatch):
    """La réponse JSON du dev n'est qu'informative : si la suite réelle est
    verte, un JSON illisible ne coûte ni l'attempt ni le worktree."""
    from autospec.agents.runner import FakeRunner

    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    state = _dev_state("json-tol")
    runner = FakeRunner(["voilà c'est fait ! (aucun json)"])
    pipeline = Pipeline(state, runner)

    async def _green(ws=None):
        return True, "", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _green)
    story = state.story("US-1")
    story.attempts = 1
    ok, _ = await pipeline._arun_item_dev(story, tmp_path, "pkg", False)

    assert ok is True                                  # la suite fait foi
    assert not runner.replies                          # un seul appel dev, pas de retry infra


async def test_retry_prompt_carries_the_previous_failure(tmp_path, monkeypatch):
    from autospec.agents.runner import FakeRunner

    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    state = _dev_state("retry-ctx")
    dev_reply = '{"status": "green", "summary": "ok", "files": [], "test_results": []}'
    runner = FakeRunner([dev_reply, dev_reply])
    pipeline = Pipeline(state, runner)

    async def _green(ws=None):
        return True, "", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _green)
    story = state.story("US-1")

    story.attempts, story.last_error = 1, ""
    await pipeline._arun_item_dev(story, tmp_path, "pkg", False)
    assert "TENTATIVE PRÉCÉDENTE" not in runner.calls[0]["prompt"]

    story.attempts, story.last_error = 2, "AssertionError: boom sur test_x"
    await pipeline._arun_item_dev(story, tmp_path, "pkg", False)
    retry_prompt = runner.calls[1]["prompt"]
    assert "TENTATIVE PRÉCÉDENTE" in retry_prompt
    assert "boom sur test_x" in retry_prompt


async def test_dependent_prompt_names_its_dependencies_contracts(tmp_path, monkeypatch):
    from autospec.agents.runner import FakeRunner
    from autospec.models import Task

    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    state = _state("dep-ctx")
    t1 = Task(id="T-1", story_id="US-1", stream="backend", title="Exposer l'API",
              description="Expose GET /add qui renvoie la somme.",
              files_hint=["pkg/api.py"], status=StoryStatus.DONE)
    t2 = Task(id="T-2", story_id="US-1", stream="backend", title="Consommer l'API",
              depends_on=["T-1"])
    state.stories = [UserStory(id="US-1", epic_id="EPIC-1", title="S", tasks=[t1, t2])]
    dev_reply = '{"status": "green", "summary": "ok", "files": [], "test_results": []}'
    runner = FakeRunner([dev_reply])
    pipeline = Pipeline(state, runner)

    async def _green(ws=None):
        return True, "", {}

    monkeypatch.setattr(pipeline, "_arun_pytest", _green)
    # subject synthétisé comme le fait le scheduler
    item = work_streams.build_work_graph(state).items["T-2"]
    subject = pipeline._item_subject(item)
    subject.attempts = 1
    await pipeline._arun_item_dev(subject, tmp_path, "pkg", False)

    prompt = runner.calls[0]["prompt"]
    assert "CONTRATS DES DÉPENDANCES" in prompt
    assert "T-1" in prompt and "Exposer l'API" in prompt
    assert "pkg/api.py" in prompt
    assert "GET /add" in prompt


async def test_red_attempt_is_preserved_and_resumed_incrementally(tmp_path, monkeypatch):
    """P2c : une tentative rouge committe son travail partiel ; la tentative
    suivante REPREND ce worktree (le marqueur de l'essai 1 y est encore) au
    lieu de repartir de zéro."""
    from pathlib import Path

    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)
    monkeypatch.setattr(settings, "dev_max_attempts", 2)
    monkeypatch.setattr(settings, "split_on_failure_enabled", False)
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    state = _dev_state("red-resume")
    pipeline = Pipeline(state, ScriptedRunner())
    seen_marker = []

    async def _dev(subject, worktree, pkg, is_frontend):
        marker = Path(worktree) / "partial.py"
        if marker.exists():                      # tentative 2 : travail repris
            seen_marker.append(True)
            return True, ""
        marker.write_text("WIP = 1\n", encoding="utf-8")
        return False, "AssertionError: presque"

    async def _still_red(subject, worktree, is_frontend):
        return False, "toujours rouge"           # force le dev sur la reprise

    monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
    monkeypatch.setattr(pipeline, "_averify_resumed", _still_red)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    assert seen_marker == [True]                 # l'essai 2 a VU le travail de l'essai 1
    assert state.story("US-1").status == StoryStatus.DONE


def test_validate_skeleton_refuses_out_of_zone_globs():
    skel = pp.S1Skeleton.model_validate(
        {
            "epics": [
                {
                    "id": "EPIC-1",
                    "title": "E",
                    "stories": [
                        {
                            "id": "US-1", "title": "S", "priority": 2,
                            "tasks": [
                                {"id": "T-1", "title": "Front", "stream": "frontend",
                                 "file_globs": ["pkg/api.py"], "estimated_files": 1},
                            ],
                        }
                    ],
                }
            ]
        }
    )
    errors, _ = pp.validate_skeleton(
        skel, stream_roots={"backend": "", "frontend": "frontend", "": ""}
    )
    assert any("T-1" in e and "zone" in e for e in errors)
    # Sans streams déclarés : le check est neutre.
    errors, _ = pp.validate_skeleton(skel, stream_roots=None)
    assert not any("zone" in e for e in errors)


# ------------------------ infra vs sémantique : ne pas jeter du vert sur un
# environnement cassé (venv partagée à moitié détruite, outil absent)

def test_venv_validity_detects_the_half_deleted_state(tmp_path):
    """La venv du bug réel : Lib/ présent mais ni pyvenv.cfg ni python.exe."""
    # Absente → valide (uv la recrée).
    assert Pipeline._venv_is_valid(tmp_path) is True
    # À moitié détruite → invalide.
    (tmp_path / ".venv" / "Lib").mkdir(parents=True)
    assert Pipeline._venv_is_valid(tmp_path) is False
    # Réparée (pyvenv.cfg + interpréteur) → valide.
    (tmp_path / ".venv" / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    (tmp_path / ".venv" / "Scripts").mkdir()
    (tmp_path / ".venv" / "Scripts" / "python.exe").write_text("", encoding="utf-8")
    assert Pipeline._venv_is_valid(tmp_path) is True


def test_guard_purges_a_broken_shared_venv(tmp_path, monkeypatch):
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    pipeline = Pipeline(_state("guard"), ScriptedRunner())
    ws = workspace_dir("guard")
    (ws / ".venv" / "Lib").mkdir(parents=True)          # invalide
    assert pipeline._guard_shared_venv(ws) is True       # purge effectuée
    assert not (ws / ".venv").exists()                   # uv la reconstruira
    # Deuxième passe : plus rien à purger.
    assert pipeline._guard_shared_venv(ws) is False


def test_infra_classifier_separates_env_breakage_from_real_reds():
    P = Pipeline
    # Aucun test collecté + signature d'outil → infra.
    assert P._looks_like_infra_failure("No module named pytest", {}) is True
    assert P._looks_like_infra_failure("error: failed to spawn `python`", {}) is True
    # Des tests ont réellement échoué → PAS infra (vrai conflit sémantique).
    assert P._looks_like_infra_failure("1 failed", {"UT-1": "failed"}) is False
    # Rouge sans signature d'outil ni résultat → prudence : traité comme réel.
    assert P._looks_like_infra_failure("AssertionError: boom", {}) is False


async def test_infra_red_canary_keeps_the_merge_and_does_not_revert(tmp_path, monkeypatch):
    """Le bug messagerie2 : la suite du HEAD combiné est rouge PARCE QUE la venv
    partagée est cassée (aucun test exécuté), pas à cause d'un conflit de code.
    Le canari répare l'environnement, rejoue, redevient vert — le merge est
    CONSERVÉ (pas de revert, pas de requeue), et c'est compté comme infra."""
    monkeypatch.setattr(settings, "streams_enabled", True)
    monkeypatch.setattr(settings, "fake_agents", True)
    monkeypatch.setattr(settings, "post_merge_canary", True)
    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    state = _dev_state("canary-infra")
    pipeline = Pipeline(state, ScriptedRunner())
    shared_runs = []

    async def _dev(subject, worktree, pkg, is_frontend):
        from pathlib import Path

        (Path(worktree) / "f.py").write_text("x = 1\n", encoding="utf-8")
        return True, ""

    async def _pytest(ws=None):
        if ws is not None:
            return True, "", {}                    # worktree : toujours vert
        shared_runs.append(1)
        # 1er canari : rouge d'INFRA (aucun test, signature venv) ; après la
        # reconstruction forcée, vert.
        if len(shared_runs) == 1:
            return False, "No module named pytest", {}
        return True, "", {}

    monkeypatch.setattr(pipeline, "_arun_item_dev", _dev)
    monkeypatch.setattr(pipeline, "_arun_pytest", _pytest)
    await asyncio.wait_for(pipeline._abuild_phase(), timeout=60)

    story = state.story("US-1")
    assert story.status == StoryStatus.DONE
    assert len(shared_runs) == 2                    # rouge d'infra → 1 réparation + 1 rejeu
    cal = state.calibration_for()
    assert cal.canary_reverts == 0                  # AUCUN revert : le code était bon
    assert cal.infra_retries == 1                   # compté comme infra
    # Le HEAD partagé ne contient PAS de revert.
    _, log = await pipeline._agit(workspace_dir("canary-infra"), "log", "--oneline")
    assert "Revert" not in log


def test_every_pipeline_log_line_is_persisted_in_the_timeline(tmp_path, monkeypatch):
    """Le bus SSE est volatile ; chaque ligne `_log` doit AUSSI atterrir dans
    workspace/<projet>/build-monitor.jsonl (kind=log) pour le post-mortem —
    c'est le récit (scope gate, merges, reverts…) qui manquait au diagnostic."""
    import json

    monkeypatch.setattr("autospec.config.settings.workspace_root", tmp_path)
    monkeypatch.delenv("BUILD_MONITOR_DIR", raising=False)
    pipeline = Pipeline(_state("timeline"), ScriptedRunner())
    pipeline._log("streams", "🚧 T-1 a modifié main.py hors périmètre")

    timeline = workspace_dir("timeline") / "build-monitor.jsonl"
    assert timeline.exists()
    events = [json.loads(l) for l in timeline.read_text(encoding="utf-8").splitlines()]
    logs = [e for e in events if e["kind"] == "log"]
    assert logs and logs[-1]["source"] == "streams"
    assert "hors périmètre" in logs[-1]["line"]
