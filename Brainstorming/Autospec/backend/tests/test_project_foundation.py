"""The foundation must be usable before spending a business-development call."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import BackendLanguage, PipelinePhase, ProjectState, Stream, StreamKind
from autospec.orchestrator import bootstrap, stack, toolchain, workspace
from autospec.orchestrator.pipeline import Pipeline, DeliveryBlocked


@pytest.mark.parametrize("language,goal", [
    ("python", "Une API FastAPI"), ("go", "Une API en Go"),
    ("rust", "Une API Rust"), ("node", "Une API Node.js"),
])
async def test_explicit_language_does_not_need_an_agent(language, goal, monkeypatch):
    monkeypatch.setattr(settings, "project_bootstrap", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = ProjectState(id="explicit", name="app", goal=goal, product_profile="api")
    pipeline = Pipeline(state, FakeRunner([]))
    assert await pipeline._aselect_stack()
    assert state.backend_language.value == language
    assert state.technical_stack["backend"] == language
    assert state.technical_stack["source"] == "explicit"
    assert len(state.streams) == 1


def test_unsupported_explicit_framework_is_not_silently_replaced():
    state = ProjectState(id="unsupported", name="app", goal="Application Django et Vue")
    with pytest.raises(ValueError, match="sans template"):
        stack.resolve(state)


@pytest.mark.parametrize("prose", [
    "Chaque vue : chargement, vide, erreur récupérable et succès distincts.",
    "Une vue doit présenter les tickets du client.",
    "La vue détail conserve le brouillon après un conflit.",
    "Cette vue présente un tableau de bord.",
    "Vue d'ensemble des tickets.", "Une vue d’ensemble du support.",
    "Du point de vue du client, les notes internes restent invisibles.",
    "Préparer les tickets en vue de leur traitement.",
])
@pytest.mark.parametrize("requested", [{}, {"kind": "frontend", "frontend": "react"}, {
    "backend": "python", "framework": "fastapi", "frontend": "react",
    "database": "sqlite", "kind": "fullstack",
}])
def test_french_view_prose_is_not_a_vue_framework_choice(prose, requested):
    state = ProjectState(id="french-view", name="support", goal="Application React avec API Python",
                         brief=prose, technical_stack=requested)
    assert stack.resolve(state)["frontend"] == "react"


@pytest.mark.parametrize("choice", [
    "Frontend Vue", "UI Vue uniquement", "Framework : Vue", "Stack : Vue",
    "Application en Vue", "Utiliser Vue", "Vue 3", "Vue", "Vue frontend",
    "Une application Vue.js", "Une Vue.js", "La Vue.js", "Framework Vue.js",
    "Vue.js d'ensemble", "Chaque vue est construite avec Vue",
    "Une vue d'ensemble, puis frontend Vue.js", "Frontend Vue et API Python",
])
@pytest.mark.parametrize("requested", [{}, {"kind": "frontend", "frontend": "react"}, {
    "backend": "python", "framework": "fastapi", "frontend": "react",
    "database": "sqlite", "kind": "fullstack",
}])
def test_vue_choice_is_rejected_even_with_french_prose_and_existing_contract(choice, requested):
    state = ProjectState(id="vue-choice", name="support", goal="Interface de support",
                         brief=f"Chaque vue possède des états distincts.\n{choice}", technical_stack=requested)
    with pytest.raises(ValueError, match="Stack explicite 'vue.*sans template"):
        stack.resolve(state)


@pytest.mark.parametrize("excluded", ["sans Vue", "sans Vue.js", "without Vue", "not Vue.js"])
def test_excluded_vue_choice_does_not_override_react(excluded):
    state = ProjectState(id="excluded-vue", name="support", goal=f"Frontend React uniquement, {excluded}")
    assert stack.resolve(state)["frontend"] == "react"


async def test_support_brief_view_prose_selects_explicit_stack_without_an_agent(monkeypatch):
    monkeypatch.setattr(settings, "project_bootstrap", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    # Representative extract, deliberately not dependent on a repository document.
    brief = """Construire Relais Support, application de support mono-organisation en français.
Stack : Python/FastAPI, SQLite, React/TypeScript/Vite.
Cinq vues maximum : connexion, mes tickets, détail, tableau de bord, administration.
Chaque vue : chargement, vide, erreur récupérable et succès distincts.
Brouillon conservé après refus/conflit/panne réseau, effacé au logout/expiration.
Frontend par domaines auth/tickets/users ; client HTTP commun.
Backend : routeurs/schémas, services, accès DB et configuration séparés.
"""
    requested = {"backend": "python", "framework": "fastapi", "frontend": "react",
                 "database": "sqlite", "kind": "fullstack"}
    state = ProjectState(id="support-view", name="Relais Support", goal="Support client",
                         brief=brief, product_profile="fullstack", technical_stack=requested)
    runner = FakeRunner([])  # Any unexpected LLM call fails: no canned responses.
    pipeline = Pipeline(state, runner)
    assert await pipeline._aselect_stack()
    assert state.technical_stack == {**requested, "source": "explicit"}
    assert [stream.language for stream in state.streams] == ["python", "react"]


@pytest.mark.parametrize("goal", [
    "API backend en Java", "A backend written in TypeScript", "Service REST en C#",
    "Une API en C++", "Serveur web .NET", "Backend en PHP", "CLI en Ruby",
    "Java backend with React", "Une API dans le langage Java", "Le langage en C++",
    "Backend TypeScript et frontend React", "API Python et service Java",
])
def test_explicit_unsupported_backend_language_is_not_silently_replaced(goal):
    state = ProjectState(id="unsupported-language", name="app", goal=goal)
    with pytest.raises(ValueError, match="Langage backend explicite.*sans template"):
        stack.resolve(state)


@pytest.mark.parametrize("goal,backend", [
    ("API Python et frontend React en TypeScript", "python"),
    ("Frontend uniquement en React et TypeScript", "none"),
    ("Une interface React utilisant le langage TypeScript, backend Python", "python"),
    ("API Node.js en JavaScript", "node"), ("A JavaScript backend with React", "node"),
    ("Une API backend en JavaScript", "node"), ("Service en JavaScript", "node"),
    ("A CLI written in JavaScript", "node"),
    ("API Python et frontend React en JavaScript", "python"),
    ("JavaScript frontend avec API Python", "python"),
    ("Rust API without a JavaScript backend", "rust"),
    ("API Python sans Java", "python"), ("API Python sans C#", "python"),
    ("API Python sans C++", "python"), ("API Python sans .NET", "python"),
    ("API Python sans PHP", "python"), ("API Python sans Ruby", "python"),
    ("API Python sans TypeScript", "python"), ("Python API without Java", "python"),
    ("Une API Python avec un catalogue de cours Java", "python"),
])
def test_frontend_typescript_javascript_and_excluded_backend_languages_are_allowed(goal, backend):
    state = ProjectState(id="allowed-language-context", name="app", goal=goal)
    assert stack.resolve(state)["backend"] == backend


@pytest.mark.parametrize("goal,partial", [
    ("UI Vue uniquement", {"kind": "frontend"}),
    ("Frontend Angular", {"kind": "frontend", "frontend": "react"}),
    ("API Django et frontend React", {"frontend": "react"}),
    ("API Express avec React", {"frontend": "react"}),
    ("Frontend Svelte et API Python", {"framework": "fastapi"}),
])
def test_partial_contract_does_not_hide_unsupported_explicit_framework(goal, partial):
    state = ProjectState(id="partial-unsupported", name="app", goal=goal, technical_stack=partial)
    with pytest.raises(ValueError, match="sans template"):
        stack.resolve(state)


@pytest.mark.parametrize("goal", [
    "Application React uniquement, sans backend",
    "Frontend uniquement en React",
    "Un frontend seul pour une interface de présentation",
    "Build a frontend-only React dashboard",
    "Build only a frontend in React",
    "Create a React interface without a backend",
])
def test_explicit_frontend_only_phrase_does_not_invent_backend(goal):
    state = ProjectState(id="frontend-phrase", name="app", goal=goal, product_profile="fullstack")
    decision = stack.resolve(state)
    assert decision["kind"] == "frontend"
    assert decision["frontend"] == "react"
    assert decision["backend"] == decision["framework"] == decision["database"] == "none"


def test_cli_without_backend_is_not_a_frontend_request():
    state = ProjectState(id="cli-no-backend", name="app", goal="CLI sans backend en Python")
    assert stack.resolve(state)["kind"] == "cli"


@pytest.mark.parametrize("database", ["SQLite", "PostgreSQL"])
def test_frontend_only_does_not_silently_drop_an_explicit_database(database):
    state = ProjectState(id="frontend-db", name="app", goal=f"Frontend React uniquement avec {database}")
    with pytest.raises(ValueError, match="base de données serveur"):
        stack.resolve(state)


def test_storage_favors_python_when_no_language_was_requested():
    state = ProjectState(id="storage", name="app", goal="CRUD web avec base de données", backend_language=BackendLanguage.GO)
    decision = stack.resolve(state)
    assert decision["backend"] == "python"
    assert decision["database"] == "sqlite"
    assert decision["frontend"] == "react"


def test_english_go_is_not_a_language_request():
    assert stack.explicit_backend("Go ahead and build a small API") == ""
    assert stack.explicit_backend("Backend Go, frontend React") == "go"


@pytest.mark.parametrize("goal,backend", [
    ("Une API Rust sans Python", "rust"),
    ("API FastAPI sans Django", "python"),
    ("Build an API in Go without Flask", "go"),
    ("Node.js API, not Python", "node"),
])
def test_excluded_technology_is_not_a_required_stack(goal, backend):
    state = ProjectState(id="excluded", name="app", goal=goal)
    assert stack.resolve(state)["backend"] == backend


@pytest.mark.parametrize("goal", [
    "API Python sans base de données", "API Python pas de SQLite",
    "Python API without persistence", "Python API with no database",
])
def test_explicitly_excluded_database_does_not_create_sqlite(goal):
    state = ProjectState(id="without-db", name="app", goal=goal)
    assert stack.resolve(state)["database"] == "none"


@pytest.mark.parametrize("framework,backend", [("fastapi", "python"), ("axum", "rust"), ("node:http", "node"), ("net/http", "go")])
def test_explicit_framework_selects_its_matching_backend(framework, backend):
    state = ProjectState(id="explicit-framework", name="app", goal="API", backend_language=BackendLanguage.GO,
                         technical_stack={"framework": framework})
    chosen = stack.resolve(state)
    assert chosen["backend"] == backend
    assert chosen["source"] == "explicit"


@pytest.mark.parametrize("root", ["../outside", "frontend/../../outside", "/outside", "C:\\outside", "C:outside", "\\\\server\\share", "frontend:alternate"])
def test_stream_escape_is_rejected_before_scaffolding(root):
    state = ProjectState(id="unsafe-stream", name="app", goal="React fullstack",
                         streams=[Stream(id="frontend", kind=StreamKind.FRONTEND, file_root=root, language="react")])
    with pytest.raises(ValueError, match="hors du projet"):
        stack.resolve(state)


def test_explicit_unsupported_database_pair_fails_before_scaffold():
    state = ProjectState(id="sqlite-go", name="app", goal="API en Go et SQLite")
    with pytest.raises(ValueError, match="Python/FastAPI"):
        stack.resolve(state)


@pytest.mark.parametrize("kind", ["cli", "library", "frontend"])
def test_non_api_contract_does_not_invent_health_endpoint(kind):
    state = ProjectState(id="contract", name="app", goal="app", technical_stack={"kind": kind})
    state.technical_stack = stack.resolve(state)
    assert "/api/health" not in stack.contract(state)


@pytest.mark.parametrize("goal,technical_stack", [
    ("React", {"kind": "frontend"}),
    ("Application React uniquement, sans backend", {}),
])
async def test_frontend_only_has_no_backend_stream(monkeypatch, goal, technical_stack):
    monkeypatch.setattr(settings, "project_bootstrap", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = ProjectState(id="frontend-only", name="app", goal=goal, technical_stack=technical_stack)
    pipeline = Pipeline(state, FakeRunner([]))
    assert await pipeline._aselect_stack()
    assert state.technical_stack["backend"] == "none"
    assert len(state.streams) == 1
    assert state.primary_stream_id == "frontend"
    assert await pipeline._aselect_stack()  # persisted stack remains resumable


async def test_partial_streams_are_reconciled_with_stack(monkeypatch):
    monkeypatch.setattr(settings, "project_bootstrap", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = ProjectState(id="streams", name="app", goal="API Rust avec interface React",
                         streams=[Stream(id="backend", kind=StreamKind.BACKEND, language="python", primary=True)])
    pipeline = Pipeline(state, FakeRunner([]))
    assert await pipeline._aselect_stack()
    assert [s.language for s in state.streams] == ["rust", "react"]


def test_interrupted_bootstrap_is_recoverable(monkeypatch):
    from autospec.api import server
    monkeypatch.setattr(server, "pipelines", {})
    state = ProjectState(id="recovery", name="app", goal="API", phase=PipelinePhase.SPEC, bootstrap_status="verifying")
    server.recover_projects([state])
    assert state.phase == PipelinePhase.STOPPED
    assert state.bootstrap_status == "failed"
    assert not state.delivery_ready


def test_node_toolchain_never_dispatches_python():
    assert toolchain.run_command("node")[1:] == ["main.js"]
    assert toolchain.test_command("node", "")[1:] == ["--test", "--test-reporter=tap"]
    assert toolchain.parse_results("node", "ok 1 - health\nnot ok 2 - broken", "") == {
        "health": "passed", "broken": "failed",
    }


async def test_bootstrap_failure_stops_before_plan(monkeypatch):
    monkeypatch.setattr(settings, "project_bootstrap", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = ProjectState(id="preflight-fail", name="app", goal="API Python", brief="API", product_profile="auto")
    pipeline = Pipeline(state, FakeRunner([]))
    monkeypatch.setattr(bootstrap, "verify", AsyncMock(return_value=bootstrap.BootstrapResult(False, "uv absent", infra=True)))
    plan = AsyncMock()
    monkeypatch.setattr(pipeline, "_aplan_phase", plan)
    await pipeline._alifecycle()
    assert state.bootstrap_status == "failed"
    assert state.phase == PipelinePhase.NEEDS_ATTENTION
    plan.assert_not_awaited()
    assert "uv absent" in state.bootstrap_detail


@pytest.mark.parametrize("goal,link_relative", [
    ("API Python et frontend React", "frontend/src"),
    ("API Python et frontend React", "frontend/src/features"),
    ("API Python", "app"),
    ("API Python", "tests/steps"),
    ("API Rust", "src"),
])
async def test_lifecycle_scaffold_rejects_nested_external_junction_before_bootstrap(
    goal, link_relative, monkeypatch, tmp_path,
):
    """The real lifecycle scaffolds BEFORE prepare; guarding prepare is too late."""
    import os
    import subprocess
    from autospec.storage import workspace_dir

    monkeypatch.setattr(settings, "project_bootstrap", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = ProjectState(id="scaffold-escape", name="app", goal=goal, brief=goal)
    ws = workspace_dir(state.id)
    external = tmp_path / "external-project"
    external.mkdir()
    sentinel = external / "keep.txt"
    sentinel.write_text("unrelated project", encoding="utf-8")
    link = ws / link_relative
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            raise
        # Windows directory junctions do not need the symlink privilege.
        created = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(external)], capture_output=True, text=True)
        assert created.returncode == 0, created.stderr
    pipeline = Pipeline(state, FakeRunner([]))
    preflight, plan = AsyncMock(), AsyncMock()
    monkeypatch.setattr(pipeline, "_abootstrap_phase", preflight)
    monkeypatch.setattr(pipeline, "_aplan_phase", plan)

    await pipeline._alifecycle()

    assert state.phase == PipelinePhase.ERROR
    assert "hors du projet" in state.error
    preflight.assert_not_awaited()
    plan.assert_not_awaited()
    assert list(external.iterdir()) == [sentinel]
    assert sentinel.read_text(encoding="utf-8") == "unrelated project"


@pytest.mark.parametrize("root", ["../outside", "/outside", "C:\\outside", "C:outside", "\\\\server\\share", "frontend:alternate", "."])
def test_frontend_scaffold_rejects_unsafe_root_without_stack_selection(root):
    state = ProjectState(id="direct-scaffold", name="app", goal="frontend")
    stream = Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root=root)
    with pytest.raises(ValueError, match="hors du projet|sous-dossier"):
        workspace.scaffold_frontend(state, stream)


async def test_failed_initialization_can_resume_without_stories(monkeypatch):
    state = ProjectState(id="retry-bootstrap", name="app", goal="API", brief="API", phase=PipelinePhase.NEEDS_ATTENTION, bootstrap_status="failed")
    pipeline = Pipeline(state, FakeRunner([]))
    resumed = AsyncMock()
    monkeypatch.setattr(pipeline, "_alifecycle", resumed)
    await pipeline.aresume_build()
    await pipeline._task
    resumed.assert_awaited_once()


@pytest.mark.parametrize("failure", ["exception", "cancel", "result"])
async def test_successful_legacy_bootstrap_survives_failed_resume_and_reload(monkeypatch, failure):
    monkeypatch.setattr(settings, "project_bootstrap", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = ProjectState(id="known-good", name="app", goal="API", bootstrap_status="ready",
                         bootstrap_fingerprint="a" * 64)
    pipeline = Pipeline(state, FakeRunner([]))
    snapshots = []
    monkeypatch.setattr(pipeline, "_sync", lambda: snapshots.append(state.model_dump()))
    monkeypatch.setattr(bootstrap, "prepare", lambda *_: bootstrap.BootstrapResult(True, "existing", fingerprint="a" * 64))
    initial = AsyncMock()
    monkeypatch.setattr(bootstrap, "verify", initial)

    async def broken(*args, **kwargs):
        assert kwargs["repair_dependencies"] is True
        assert snapshots[0]["bootstrap_status"] == "preparing"
        assert snapshots[0]["bootstrap_verified_once"] is True
        if failure == "exception":
            raise RuntimeError("temporary runtime failure")
        if failure == "cancel":
            raise asyncio.CancelledError
        return bootstrap.BootstrapResult(False, "temporary runtime failure")

    monkeypatch.setattr(bootstrap, "verify_runtime", broken)
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await pipeline._abootstrap_phase()
    else:
        assert not await pipeline._abootstrap_phase()
    assert state.bootstrap_status == "failed"
    assert state.bootstrap_verified_once
    assert state.bootstrap_fingerprint == "a" * 64

    reloaded = ProjectState.model_validate_json(state.model_dump_json())
    resumed = Pipeline(reloaded, FakeRunner([]))
    runtime = AsyncMock(return_value=bootstrap.BootstrapResult(True, "recovered", fingerprint="a" * 64))
    monkeypatch.setattr(bootstrap, "verify_runtime", runtime)
    assert await resumed._abootstrap_phase()
    assert runtime.await_args.kwargs["repair_dependencies"] is True
    assert reloaded.bootstrap_status == "ready" and reloaded.bootstrap_verified_once
    initial.assert_not_awaited()


@pytest.mark.parametrize("ok,skipped", [(False, False), (True, True), (True, False)])
async def test_only_a_successful_first_gate_marks_bootstrap_verified(monkeypatch, ok, skipped):
    monkeypatch.setattr(settings, "project_bootstrap", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    # A scaffold fingerprint alone is not proof of a passed preflight.
    state = ProjectState(id="first-gate", name="app", goal="API", bootstrap_status="failed",
                         bootstrap_fingerprint="b" * 64)
    pipeline = Pipeline(state, FakeRunner([]))
    monkeypatch.setattr(bootstrap, "prepare", lambda *_: bootstrap.BootstrapResult(True, "existing", fingerprint="b" * 64))
    initial = AsyncMock(return_value=bootstrap.BootstrapResult(ok, "first result", skipped=skipped, fingerprint="b" * 64))
    runtime = AsyncMock()
    monkeypatch.setattr(bootstrap, "verify", initial)
    monkeypatch.setattr(bootstrap, "verify_runtime", runtime)
    assert await pipeline._abootstrap_phase() is ok
    assert state.bootstrap_verified_once is (ok and not skipped)
    initial.assert_awaited_once()
    runtime.assert_not_awaited()


def test_restart_recovery_retains_successful_bootstrap_history(monkeypatch):
    from autospec.api import server
    monkeypatch.setattr(server, "pipelines", {})
    state = ProjectState(id="verified-recovery", name="app", goal="API", phase=PipelinePhase.SPEC,
                         bootstrap_status="verifying", bootstrap_verified_once=True)
    server.recover_projects([state])
    assert state.bootstrap_status == "failed"
    assert state.bootstrap_verified_once


async def test_explicit_restart_clears_bootstrap_verification_history(monkeypatch):
    from autospec.orchestrator import pipeline as pipeline_module
    state = ProjectState(id="reset-foundation", name="app", goal="API", brief="API Python",
                         phase=PipelinePhase.DONE, bootstrap_status="ready",
                         bootstrap_fingerprint="a" * 64, bootstrap_verified_once=True)
    pipeline = Pipeline(state, FakeRunner([]))
    monkeypatch.setattr(pipeline, "start", lambda: None)
    monkeypatch.setattr(pipeline, "astop_app", AsyncMock())
    monkeypatch.setattr(pipeline_module, "force_delete_workspace", lambda *args, **kwargs: True)
    await pipeline.arestart_from_scratch()
    assert not state.bootstrap_verified_once
    assert state.bootstrap_status == state.bootstrap_fingerprint == ""


async def test_stack_cannot_change_after_preflight():
    state = ProjectState(id="immutable", name="app", goal="API", bootstrap_status="ready")
    pipeline = Pipeline(state, FakeRunner([]))
    with pytest.raises(ValueError, match="déjà créé"):
        await pipeline.aset_language("go")


async def test_empty_plan_never_becomes_success():
    state = ProjectState(id="empty-plan", name="app", goal="API")
    pipeline = Pipeline(state, FakeRunner(['{"epics": []}']))
    with pytest.raises(DeliveryBlocked):
        await pipeline._aplan_phase()
    assert pipeline._delivery_blocked
    assert not state.delivery_ready


def test_explicit_docker_disable_overrides_profile(monkeypatch):
    monkeypatch.setenv("DOCKER_DELIVERY", "0")
    monkeypatch.setattr(settings, "docker_delivery", False)
    pipeline = Pipeline(ProjectState(id="off", name="app", goal="API", product_profile="api"), FakeRunner([]))
    assert pipeline._setting("docker_delivery") is False


async def test_preflight_cancellation_is_wired_to_stop(monkeypatch):
    monkeypatch.setattr(settings, "project_bootstrap", True)
    monkeypatch.setattr(settings, "fake_agents", False)
    state = ProjectState(id="cancel", name="app", goal="API Python")
    pipeline = Pipeline(state, FakeRunner([]))
    assert await pipeline._aselect_stack()
    workspace.scaffold(state)
    entered = asyncio.Event()

    async def verify(state, ws, *, timeout_s, cancel):
        entered.set()
        await cancel.wait()
        return bootstrap.BootstrapResult(False, "cancelled")

    monkeypatch.setattr(bootstrap, "verify", verify)
    task = asyncio.create_task(pipeline._abootstrap_phase())
    await asyncio.wait_for(entered.wait(), 5)
    pipeline._signal_stop()
    assert not await asyncio.wait_for(task, 5)


def test_generated_suite_is_bounded_and_kills_on_timeout(monkeypatch, tmp_path):
    import sys
    import time
    monkeypatch.setattr(settings, "test_suite_timeout_s", 0.2)
    pipeline = Pipeline(ProjectState(id="timeout", name="app", goal="CLI"), FakeRunner([]))
    started = time.monotonic()
    result = pipeline._run_suite_process([sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, {})
    assert result.returncode != 0
    assert "timeout" in result.stdout
    assert time.monotonic() - started < 10


async def test_generated_tests_do_not_inherit_server_secrets(monkeypatch, tmp_path):
    import subprocess
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_URL", "server-secret-db")
    monkeypatch.setattr(settings, "fake_agents", False)
    pipeline = Pipeline(ProjectState(id="secret", name="app", goal="CLI"), FakeRunner([]))
    captured = {}

    def run(cmd, cwd, env):
        captured.update(env)
        return subprocess.CompletedProcess(cmd, 0, stdout="")

    monkeypatch.setattr(pipeline, "_run_suite_process", run)
    await pipeline._arun_pytest(ws=tmp_path)
    assert "ANTHROPIC_API_KEY" not in captured
    assert "DATABASE_URL" not in captured


async def test_native_bootstrapped_app_is_actually_smoke_checked(monkeypatch):
    from autospec.models import StoryStatus, UserStory
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "smoke_run", True)
    state = ProjectState(id="native-smoke", name="app", goal="API Go", backend_language=BackendLanguage.GO,
                         technical_stack={"backend": "go", "kind": "api"}, bootstrap_status="ready",
                         stories=[UserStory(id="US-1", epic_id="E1", title="API", status=StoryStatus.DONE)])
    pipeline = Pipeline(state, FakeRunner([]))
    verifier = AsyncMock(return_value=bootstrap.BootstrapResult(False, "binary absent", infra=True))
    monkeypatch.setattr(bootstrap, "verify_runtime", verifier)
    assert not await pipeline._asmoke_phase()
    verifier.assert_awaited_once()
    assert pipeline._delivery_blocked


def test_recovered_react_contract_keeps_stream_routing_enabled(monkeypatch):
    monkeypatch.setattr(settings, "streams_enabled", False)
    state = ProjectState(id="streams-recovered", name="app", goal="web", technical_stack={"frontend": "react"})
    assert Pipeline(state, FakeRunner([]))._setting("streams_enabled")


async def test_frontend_only_run_uses_preview_not_python(monkeypatch):
    from unittest.mock import Mock
    state = ProjectState(id="fe-run", name="app", goal="React", technical_stack={"kind": "frontend"},
                         streams=[Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend", primary=True)])
    pipeline = Pipeline(state, FakeRunner([]))
    preview, backend = Mock(), Mock()
    monkeypatch.setattr(pipeline, "_stream_preview_output", preview)
    monkeypatch.setattr(pipeline, "_stream_run_output", backend)
    await pipeline.arun_app()
    await pipeline._stream_task
    preview.assert_called_once()
    backend.assert_not_called()


async def test_frontend_runtime_does_not_reserve_a_backend_port(monkeypatch):
    from autospec.orchestrator import runtime_acceptance
    state = ProjectState(id="fe-runtime", name="app", goal="React", technical_stack={"kind": "frontend"})
    pipeline = Pipeline(state, FakeRunner([]))
    guard = AsyncMock(return_value=(False, "foreign backend"))
    monkeypatch.setattr(pipeline, "_aensure_own_port_free", guard)
    monkeypatch.setattr(runtime_acceptance, "should_run", lambda *a, **kw: (True, ""))
    monkeypatch.setattr(runtime_acceptance, "arun_runtime_acceptance", AsyncMock(return_value=runtime_acceptance.RuntimeAcceptanceResult(True, "ok")))
    assert await pipeline._aruntime_acceptance_phase()
    guard.assert_not_awaited()
