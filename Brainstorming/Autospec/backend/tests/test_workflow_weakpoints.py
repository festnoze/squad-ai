"""Tests RÉELS des points faibles du workflow révélés par le build messagerie2
(2026-07-04) : environnement partagé détruit à travers une jonction, sorties de
vérification muettes, et auto-réparation frontend. Contrairement aux tests
hermétiques voisins, le premier test exerce un VRAI dépôt git + de vraies
jonctions — l'interaction exacte qui a corrompu l'install partagée."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from autospec.agents.scripted import ScriptedRunner
from autospec.config import settings
from autospec.models import ProjectState, StoryStatus, Stream, StreamKind, UserStory
from autospec.orchestrator import scheduler
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir

GIT = shutil.which("git")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(GIT), "-c", "user.email=t@test", "-c", "user.name=autospec-test", *args],
        cwd=str(repo), capture_output=True, text=True, encoding="utf-8",
    )


@pytest.mark.skipif(GIT is None, reason="git indisponible sur ce runner")
async def test_real_worktree_remove_preserves_shared_node_modules(tmp_path):
    """Le bug messagerie2 : `git worktree remove --force` traverse la jonction
    node_modules du worktree et détruit l'install PARTAGÉE. Le chemin réel
    `_aworktree_remove` (détachement + git + rmtree défensif) doit supprimer le
    worktree ET laisser la cible intacte."""
    repo = tmp_path / "repo"
    repo.mkdir()
    assert _git(repo, "init").returncode == 0
    (repo / "frontend").mkdir()
    (repo / "frontend" / "package.json").write_text("{}", encoding="utf-8")
    (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    _git(repo, "add", "-A")
    assert _git(repo, "commit", "-m", "init").returncode == 0
    # L'install partagée (non suivie par git), avec un vrai contenu à protéger.
    shared = repo / "frontend" / "node_modules"
    (shared / "vite").mkdir(parents=True)
    (shared / "vite" / "package.json").write_text("{}", encoding="utf-8")
    (shared / ".bin").mkdir()

    wt = tmp_path / "wt"
    assert _git(repo, "worktree", "add", str(wt), "-b", "autospec/wi-weak").returncode == 0
    if not Pipeline._link_node_modules(wt / "frontend" / "node_modules", shared):
        pytest.skip("jonction/symlink indisponible sur ce runner")

    pipeline = Pipeline(ProjectState(id="wk-wt", name="w", goal="g"), ScriptedRunner())
    await pipeline._aworktree_remove(repo, wt, "autospec/wi-weak")

    assert not wt.exists()                                # worktree bien supprimé
    assert (shared / "vite" / "package.json").exists()    # cible INTACTE
    assert (shared / ".bin").exists()
    # La branche a aussi été nettoyée (chemin keep_branch=False).
    assert "autospec/wi-weak" not in _git(repo, "branch", "--list").stdout


# ---------------------- cause racine d'une chaîne « dépendance non satisfaite »

def test_failed_root_walks_the_dependency_chain():
    """messagerie2 : T8 était « bloqué par T6, T7 » (tous todo) alors que la
    vraie cause était T5-S1-S1, deux niveaux plus bas. failed_root doit
    remonter la chaîne jusqu'à l'item réellement FAILED."""
    a = UserStory(id="A", epic_id="E", title="racine", status=StoryStatus.FAILED)
    a.last_error = "boom originel"
    b = UserStory(id="B", epic_id="E", title="milieu", status=StoryStatus.TODO, depends_on=["A"])
    c = UserStory(id="C", epic_id="E", title="feuille", status=StoryStatus.TODO, depends_on=["B"])
    by_id = {s.id: s for s in (a, b, c)}
    root = scheduler.failed_root(c, by_id)
    assert root is a
    # Pas d'échec en amont → None (et jamais d'exception sur un id inconnu).
    d = UserStory(id="D", epic_id="E", title="libre", status=StoryStatus.TODO,
                  depends_on=["B", "inconnu"])
    b2 = UserStory(id="B", epic_id="E", title="ok", status=StoryStatus.DONE)
    assert scheduler.failed_root(d, {"B": b2}) is None


# --------------------- worktrees hors %TEMP% (piège du chemin court 8.3 « ~ »)

def test_new_worktree_path_avoids_short_temp_paths(tmp_path, monkeypatch):
    """messagerie2 T5-S1-S1 : un worktree sous %TEMP% (C:\\Users\\E6FB4~1.MIL\\…)
    fait échouer Vite/Vitest (« Failed to load url …%7E…setupTests.ts ») — la
    même branche est verte sous un chemin sans « ~ ». Les worktrees doivent
    vivre à côté des workspaces, en chemin long résolu."""
    monkeypatch.setattr(settings, "workspace_root", tmp_path)
    p = Pipeline._new_worktree_path()
    assert p.exists()
    assert p.parent == (tmp_path / "_worktrees").resolve()
    assert "~" not in str(p)
    assert p.name.startswith("autospec-wt-")


# ------------------- beacon de code obsolète (backend reload=False, cf. P2)

async def test_health_exposes_loaded_vs_on_disk_source_stamps():
    """4 rounds de build ont rejoué le même échec sur un processus chargé AVANT
    les fixes, sans aucun moyen de le voir : /api/health doit exposer le stamp
    des sources CHARGÉES et celui du disque pour rendre l'obsolescence visible."""
    import httpx

    from autospec.api import server

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        data = (await client.get("/api/health")).json()
    assert data["ok"] is True
    assert data["source_stamp"]  # figé à l'import
    # Le disque ne peut être que plus récent ou égal (format ISO comparable).
    assert data["source_stamp_now"] >= data["source_stamp"]
    assert data["started_at"] > 0


# ------------------------- vérification frontend : sortie rouge actionnable

class _FakeProc:
    def __init__(self, returncode: int, stdout: str):
        self.returncode = returncode
        self.stdout = stdout


def _fe_state(pid: str) -> ProjectState:
    st = ProjectState(id=pid, name="fe", goal="g")
    st.streams = [
        Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend"),
    ]
    return st


def _fe_pipeline(tmp_path, monkeypatch, pid: str) -> Pipeline:
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "workspace_root", tmp_path)
    pipeline = Pipeline(_fe_state(pid), ScriptedRunner())
    (workspace_dir(pid) / "frontend").mkdir(parents=True, exist_ok=True)

    async def _noop(root):
        return None

    monkeypatch.setattr(pipeline, "_aensure_frontend_node_modules", _noop)
    return pipeline


def _report_arg(cmd) -> str | None:
    for a in cmd:
        if str(a).startswith("--outputFile.json="):
            return str(a).split("=", 1)[1]
    return None


async def test_red_frontend_verify_carries_the_failure_digest(tmp_path, monkeypatch):
    """Un rouge Vitest ne doit JAMAIS se résumer à « JSON report written to … » :
    le digest du rapport (nom du test + message) doit être dans la sortie —
    c'est ce vide qui a fait tourner T5-S1-S1 en aveugle."""
    pipeline = _fe_pipeline(tmp_path, monkeypatch, "wk-digest")
    payload = {
        "testResults": [{
            "name": "src/tokenStorage.test.ts",
            "assertionResults": [{
                "ancestorTitles": ["tokenStorage"], "title": "persiste les jetons",
                "status": "failed",
                "failureMessages": ["AssertionError: expected 2 to be 3"],
            }],
        }],
    }

    def fake_run(cmd, **kw):
        path = _report_arg(cmd)
        if path:  # le run vitest
            Path(path).write_text(json.dumps(payload), encoding="utf-8")
            return _FakeProc(1, f"JSON report written to {path}")
        return _FakeProc(0, "build ok")  # jamais atteint : tests rouges

    monkeypatch.setattr("autospec.orchestrator.pipeline.subprocess.run", fake_run)

    ok, output, results = await pipeline._arun_frontend_tests()
    assert ok is False
    assert "échecs Vitest" in output
    assert "expected 2 to be 3" in output
    assert "tokenStorage > persiste les jetons" in output
    assert results["src/tokenStorage.test.ts::tokenStorage > persiste les jetons"] == "failed"


async def test_red_frontend_verify_names_an_empty_suite(tmp_path, monkeypatch):
    """Rouge SANS aucun test collecté et sans signature d'infra : la sortie doit
    au moins le DIRE, pas rester muette."""
    pipeline = _fe_pipeline(tmp_path, monkeypatch, "wk-empty")

    def fake_run(cmd, **kw):
        path = _report_arg(cmd)
        if path:
            Path(path).write_text(json.dumps({"testResults": []}), encoding="utf-8")
            return _FakeProc(1, f"JSON report written to {path}")
        return _FakeProc(0, "build ok")

    monkeypatch.setattr("autospec.orchestrator.pipeline.subprocess.run", fake_run)

    ok, output, results = await pipeline._arun_frontend_tests()
    assert ok is False
    assert results == {}
    assert "SANS test collecté" in output


async def test_frontend_startup_error_self_heals_and_replays(tmp_path, monkeypatch):
    """Le mode d'échec exact de messagerie2 : vitest meurt au chargement de la
    config (node_modules cassé). Le harnais doit réinstaller puis rejouer UNE
    fois — et rendre VERT sans consommer de tentative dev."""
    pipeline = _fe_pipeline(tmp_path, monkeypatch, "wk-heal")
    calls = {"runs": 0, "installs": 0}
    green = {
        "testResults": [{
            "name": "src/App.test.tsx",
            "assertionResults": [
                {"ancestorTitles": ["App"], "title": "renders", "status": "passed"},
            ],
        }],
    }

    def fake_run(cmd, **kw):
        path = _report_arg(cmd)
        if path:
            calls["runs"] += 1
            if calls["runs"] == 1:  # node_modules cassé : startup error, pas de rapport
                return _FakeProc(1, (
                    "failed to load config from vite.config.ts\n"
                    "Error [ERR_MODULE_NOT_FOUND]: Cannot find package 'vite'"
                ))
            Path(path).write_text(json.dumps(green), encoding="utf-8")
            return _FakeProc(0, f"ok\nJSON report written to {path}")
        return _FakeProc(0, "build ok")  # tsc && vite build après le vert

    async def fake_install(root, *, use_ci):
        calls["installs"] += 1
        return True

    monkeypatch.setattr("autospec.orchestrator.pipeline.subprocess.run", fake_run)
    monkeypatch.setattr(pipeline, "_anpm_install_in", fake_install)

    ok, output, results = await pipeline._arun_frontend_tests()
    assert ok is True
    assert calls == {"runs": 2, "installs": 1}  # une réparation, un replay
    assert results["src/App.test.tsx::App > renders"] == "passed"


async def test_frontend_real_red_does_not_trigger_the_heal(tmp_path, monkeypatch):
    """Des tests qui ont VRAIMENT tourné et échoué ne déclenchent PAS la
    réinstallation : l'auto-réparation est réservée aux pannes d'environnement."""
    pipeline = _fe_pipeline(tmp_path, monkeypatch, "wk-noheal")
    payload = {
        "testResults": [{
            "name": "src/x.test.ts",
            "assertionResults": [
                {"ancestorTitles": [], "title": "t", "status": "failed",
                 "failureMessages": ["boom"]},
            ],
        }],
    }
    calls = {"installs": 0}

    def fake_run(cmd, **kw):
        path = _report_arg(cmd)
        if path:
            Path(path).write_text(json.dumps(payload), encoding="utf-8")
            return _FakeProc(1, f"JSON report written to {path}")
        return _FakeProc(0, "build ok")

    async def fake_install(root, *, use_ci):
        calls["installs"] += 1
        return True

    monkeypatch.setattr("autospec.orchestrator.pipeline.subprocess.run", fake_run)
    monkeypatch.setattr(pipeline, "_anpm_install_in", fake_install)

    ok, _, _ = await pipeline._arun_frontend_tests()
    assert ok is False
    assert calls["installs"] == 0
