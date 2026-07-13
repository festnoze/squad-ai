"""Full-stack integration gate + fix-until-green repair loop.

After a build, the delivered app is REALLY exercised (smoke run, runtime
integration : backend servant le frontend buildé, sondes API/DB). When a gate
fails while the unit suite is green — a wiring bug no mocked test sees (the
messagerie2 blank page) — a Dev agent is dispatched with the failure report and
the gate is re-run, up to ``INTEGRATION_FIX_ATTEMPTS`` times, before the
project is parked in needs_attention."""

import pytest

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import ProjectState, StoryStatus, UserStory
from autospec.orchestrator import runtime_acceptance
from autospec.orchestrator.pipeline import Pipeline
from autospec.orchestrator.runtime_acceptance import RuntimeAcceptanceResult
from autospec.storage import workspace_dir


def _state(pid: str) -> ProjectState:
    st = ProjectState(id=pid, name="app", goal="g")
    st.stories = [UserStory(id="US-1", epic_id="E", title="t", status=StoryStatus.DONE)]
    return st


@pytest.fixture
def repair_env(monkeypatch):
    """Common wiring: gates on, demo off, git faked, pytest green."""
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "runtime_acceptance_enabled", True)
    monkeypatch.setattr(settings, "integration_fix_attempts", 2)
    git_calls: list[tuple[str, ...]] = []

    async def _agit_snapshot(self, ws, label):
        git_calls.append(("snapshot", label))
        return True

    async def _agit(self, ws, *args):
        git_calls.append(args)
        return 0, ""

    async def _arun_pytest(self, ws=None):
        return True, "all green", {}

    async def _stop(self):
        return None

    monkeypatch.setattr(Pipeline, "_agit_snapshot", _agit_snapshot)
    monkeypatch.setattr(Pipeline, "_agit", _agit)
    monkeypatch.setattr(Pipeline, "_arun_pytest", _arun_pytest)
    # Finding 1 : les gates arrêtent l'app propre + vérifient le port. En test on
    # neutralise l'arrêt et on considère le port libre (aucun tiers).
    monkeypatch.setattr(Pipeline, "astop_app", _stop)
    monkeypatch.setattr(Pipeline, "_port_is_free", staticmethod(lambda port: True))
    return git_calls


def _fake_gate(monkeypatch, results: list[RuntimeAcceptanceResult]):
    """Queue runtime-acceptance results (last one repeats)."""
    queue = list(results)

    async def _fake(state, ws, *, enabled=None, timeout_s=None):
        return queue.pop(0) if len(queue) > 1 else queue[0]

    monkeypatch.setattr(runtime_acceptance, "arun_runtime_acceptance", _fake)


# ------------------------------------------------------- runtime integration gate

async def test_runtime_gate_repairs_until_green(monkeypatch, repair_env):
    """Gate KO → agent Dev de réparation → gate re-testé VERT → livraison OK."""
    _fake_gate(monkeypatch, [
        RuntimeAcceptanceResult(ok=False, detail="asset /assets/index.js servi en text/html"),
        RuntimeAcceptanceResult(ok=True, detail="OK"),
    ])
    runner = FakeRunner(['{"status": "fixed", "summary": "montage /assets ajouté", "files": []}'])
    state = _state("fix-ok")
    pipeline = Pipeline(state, runner)

    assert await pipeline._aruntime_acceptance_phase() is True
    assert pipeline._delivery_blocked is False
    assert not state.regressions
    # The repair agent received the REAL failure report, in the workspace.
    assert len(runner.calls) == 1
    prompt = runner.calls[0]["prompt"]
    assert "text/html" in prompt
    assert "GATE D'INTÉGRATION" in prompt
    assert runner.calls[0]["cwd"] is not None


async def test_runtime_gate_blocks_after_exhausted_attempts(monkeypatch, repair_env):
    monkeypatch.setattr(settings, "integration_fix_attempts", 2)
    _fake_gate(monkeypatch, [RuntimeAcceptanceResult(ok=False, detail="page vide sur /")])
    runner = FakeRunner([
        '{"status": "fixed", "summary": "essai 1", "files": []}',
        '{"status": "fixed", "summary": "essai 2", "files": []}',
    ])
    state = _state("fix-ko")
    pipeline = Pipeline(state, runner)

    assert await pipeline._aruntime_acceptance_phase() is False
    assert pipeline._delivery_blocked is True
    assert len(runner.calls) == 2  # every attempt consumed before giving up
    assert any("Runtime acceptance échoué" in issue for issue in state.delivery_issues)


async def test_repair_rolls_back_when_fix_breaks_the_suite(monkeypatch, repair_env):
    """La réparation ne doit JAMAIS troquer un gate vert contre une suite rouge."""
    git_calls = repair_env

    async def _red_pytest(self, ws=None):
        return False, "1 failed", {}

    monkeypatch.setattr(Pipeline, "_arun_pytest", _red_pytest)
    monkeypatch.setattr(settings, "integration_fix_attempts", 1)
    _fake_gate(monkeypatch, [RuntimeAcceptanceResult(ok=False, detail="page vide")])
    runner = FakeRunner(['{"status": "fixed", "summary": "s", "files": []}'])
    state = _state("fix-rollback")
    pipeline = Pipeline(state, runner)

    assert await pipeline._aruntime_acceptance_phase() is False
    assert pipeline._delivery_blocked is True
    assert ("reset", "--hard", "HEAD") in git_calls
    assert ("clean", "-fd") in git_calls


async def test_repair_disabled_blocks_immediately(monkeypatch, repair_env):
    monkeypatch.setattr(settings, "integration_fix_attempts", 0)
    _fake_gate(monkeypatch, [RuntimeAcceptanceResult(ok=False, detail="KO")])
    runner = FakeRunner([])
    state = _state("fix-off")
    pipeline = Pipeline(state, runner)

    assert await pipeline._aruntime_acceptance_phase() is False
    assert pipeline._delivery_blocked is True
    assert runner.calls == []  # no repair agent dispatched


async def test_repair_skipped_without_git(monkeypatch, repair_env):
    async def _no_git(self, ws, label):
        return False

    monkeypatch.setattr(Pipeline, "_agit_snapshot", _no_git)
    _fake_gate(monkeypatch, [RuntimeAcceptanceResult(ok=False, detail="KO")])
    runner = FakeRunner([])
    state = _state("fix-nogit")
    pipeline = Pipeline(state, runner)

    assert await pipeline._aruntime_acceptance_phase() is False
    assert runner.calls == []


# ------------------------------------------------------ finding 4 : infra result

async def test_runtime_infra_result_skips_repair_loop(monkeypatch, repair_env):
    """Un résultat infra=True (exit 2 : playwright/node absent) ne dépêche AUCUN
    agent — needs_attention direct, sans consommer de tentative."""
    _fake_gate(monkeypatch, [
        RuntimeAcceptanceResult(ok=False, detail="playwright manquant", infra=True),
    ])
    runner = FakeRunner([])
    state = _state("rt-infra-skip")
    pipeline = Pipeline(state, runner)

    assert await pipeline._aruntime_acceptance_phase() is False
    assert pipeline._delivery_blocked is True
    assert runner.calls == []  # aucun agent de réparation
    assert any("infra" in r.lower() for r in state.regressions)


async def test_runtime_external_port_is_infra(monkeypatch, repair_env):
    """Finding 1 : port tenu par un tiers → infra, pas de réparation."""
    monkeypatch.setattr(Pipeline, "_port_is_free", staticmethod(lambda port: False))
    _fake_gate(monkeypatch, [RuntimeAcceptanceResult(ok=False, detail="peu importe")])
    runner = FakeRunner([])
    state = _state("rt-port-busy")
    pipeline = Pipeline(state, runner)

    assert await pipeline._aruntime_acceptance_phase() is False
    assert pipeline._delivery_blocked is True
    assert runner.calls == []
    assert any("process externe" in r for r in state.regressions)


# ------------------------------------------- finding 3 : frontend suite in guard

async def test_repair_checks_frontend_suite(monkeypatch, repair_env):
    """La réparation doit exiger la suite FRONTEND verte aussi : pytest vert mais
    Vitest/build rouge => rollback (le filet n'est pas backend-only)."""
    from autospec.models import Stream, StreamKind

    git_calls = repair_env
    monkeypatch.setattr(settings, "integration_fix_attempts", 1)

    async def _red_frontend(self, ws=None):
        return False, "vitest: 1 failed", {}

    monkeypatch.setattr(Pipeline, "_arun_frontend_tests", _red_frontend)
    _fake_gate(monkeypatch, [RuntimeAcceptanceResult(ok=False, detail="page vide")])
    runner = FakeRunner(['{"status": "fixed", "summary": "s", "files": []}'])
    state = _state("rt-fe-guard")
    state.streams = [Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend")]
    pipeline = Pipeline(state, runner)

    assert await pipeline._aruntime_acceptance_phase() is False
    assert pipeline._delivery_blocked is True
    # Rollback déclenché par la suite frontend rouge malgré pytest vert.
    assert ("reset", "--hard", "HEAD") in git_calls


async def test_repair_passes_when_both_suites_green(monkeypatch, repair_env):
    """pytest ET frontend verts → la réparation est acceptée et le gate revalidé."""
    from autospec.models import Stream, StreamKind

    monkeypatch.setattr(settings, "integration_fix_attempts", 1)

    async def _green_frontend(self, ws=None):
        return True, "vitest ok + build ok", {}

    monkeypatch.setattr(Pipeline, "_arun_frontend_tests", _green_frontend)
    _fake_gate(monkeypatch, [
        RuntimeAcceptanceResult(ok=False, detail="page vide"),
        RuntimeAcceptanceResult(ok=True, detail="OK"),
    ])
    runner = FakeRunner(['{"status": "fixed", "summary": "s", "files": []}'])
    state = _state("rt-fe-green")
    state.streams = [Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend")]
    pipeline = Pipeline(state, runner)

    assert await pipeline._aruntime_acceptance_phase() is True
    assert pipeline._delivery_blocked is False


# ------------------------------------------------------------------- smoke gate

async def test_smoke_gate_repairs_until_green(monkeypatch, repair_env):
    monkeypatch.setattr(settings, "smoke_run", True)
    state = _state("smoke-fix-ok")
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("print('hi')", encoding="utf-8")
    (ws / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    outcomes = [(False, "aucun serveur à l'écoute"), (True, "serveur à l'écoute sur :8000")]
    monkeypatch.setattr(
        Pipeline, "_smoke_run_python",
        lambda self, ws: outcomes.pop(0) if len(outcomes) > 1 else outcomes[0],
    )
    runner = FakeRunner(['{"status": "fixed", "summary": "uvicorn.run ajouté", "files": []}'])
    pipeline = Pipeline(state, runner)

    assert await pipeline._asmoke_phase() is True
    assert pipeline._delivery_blocked is False
    assert len(runner.calls) == 1
    assert "aucun serveur" in runner.calls[0]["prompt"]


async def test_smoke_gate_still_blocks_when_repair_fails(monkeypatch, repair_env):
    monkeypatch.setattr(settings, "smoke_run", True)
    monkeypatch.setattr(settings, "integration_fix_attempts", 1)
    state = _state("smoke-fix-ko")
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("print('hi')", encoding="utf-8")
    (ws / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    monkeypatch.setattr(Pipeline, "_smoke_run_python", lambda self, ws: (False, "n'écoute pas"))
    runner = FakeRunner(['{"status": "failed", "summary": "s", "files": []}'])
    pipeline = Pipeline(state, runner)

    assert await pipeline._asmoke_phase() is False
    assert pipeline._delivery_blocked is True
    assert any("Smoke run échoué" in r for r in state.regressions)


# ------------------------------------------- prompt_builder routing (docker gate)

async def test_repair_routes_to_custom_prompt_builder(monkeypatch, repair_env):
    """_arepair_delivery accepte un prompt_builder ad hoc (ex. dev_fix_deploy pour
    le gate Docker) : l'agent Dev reçoit CE prompt, pas dev_fix_integration."""
    monkeypatch.setattr(settings, "integration_fix_attempts", 1)

    def _custom_builder(package_name, report, architecture="", attempt=1,
                        max_attempts=1, knowledge=""):
        # V3-F4.3 : le contrat prompt_builder porte aussi `knowledge` (comme
        # dev_fix_integration / dev_fix_deploy).
        return f"PROMPT DOCKER SPÉCIFIQUE :: {report}"

    async def _averify():
        return True, "conteneur sain, réseau OK"

    runner = FakeRunner(['{"status": "fixed", "summary": "s", "files": []}'])
    state = _state("repair-custom-prompt")
    pipeline = Pipeline(state, runner)

    ok, detail = await pipeline._arepair_delivery(
        "docker", "health check KO", _averify, prompt_builder=_custom_builder
    )

    assert ok is True
    assert detail == "conteneur sain, réseau OK"
    assert len(runner.calls) == 1
    prompt = runner.calls[0]["prompt"]
    assert prompt.startswith("PROMPT DOCKER SPÉCIFIQUE ::")
    assert "health check KO" in prompt
    # Le prompt d'intégration par défaut n'a PAS été utilisé.
    assert "GATE D'INTÉGRATION" not in prompt


async def test_repair_default_prompt_builder_is_integration(monkeypatch, repair_env):
    """Sans prompt_builder, le chemin par défaut reste dev_fix_integration
    (aucune régression pour les callers existants smoke/runtime)."""
    monkeypatch.setattr(settings, "integration_fix_attempts", 1)

    async def _averify():
        return True, "OK"

    runner = FakeRunner(['{"status": "fixed", "summary": "s", "files": []}'])
    state = _state("repair-default-prompt")
    pipeline = Pipeline(state, runner)

    ok, _ = await pipeline._arepair_delivery("integration", "asset en text/html", _averify)

    assert ok is True
    assert len(runner.calls) == 1
    prompt = runner.calls[0]["prompt"]
    # La signature textuelle de dev_fix_integration.
    assert "GATE D'INTÉGRATION" in prompt
    assert "asset en text/html" in prompt


# ------------------------------------------------------------------ configuration

def test_runtime_acceptance_defaults_on(monkeypatch):
    """L'intégration complète est un gate PAR DÉFAUT : sans variable d'env, un
    projet web/fullstack livré doit être vérifié de bout en bout."""
    monkeypatch.delenv("RUNTIME_ACCEPTANCE", raising=False)
    monkeypatch.delenv("PRESET", raising=False)
    from autospec.config import Settings

    assert Settings().runtime_acceptance_enabled is True


def test_integration_fix_attempts_default(monkeypatch):
    monkeypatch.delenv("INTEGRATION_FIX_ATTEMPTS", raising=False)
    monkeypatch.delenv("PRESET", raising=False)
    from autospec.config import Settings

    assert Settings().integration_fix_attempts == 2
