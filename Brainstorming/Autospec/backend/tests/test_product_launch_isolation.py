from types import SimpleNamespace

import pytest

from autospec.agents.runner import AgentError, FakeRunner
from autospec.models import ProjectState
from autospec.orchestrator import product_launch
from autospec.orchestrator.pipeline import Pipeline


def harness(monkeypatch, *, running=True, status=200, frontend=False):
    sessions = []
    class Runtime:
        def __init__(self, stage, *args, **kwargs):
            self.stage = stage
            self.origin = "http://127.0.0.1:12345"
            self.closed = False
            sessions.append(self)
        def __enter__(self): return self
        def is_running(self): return running
        def close(self): self.closed = True
    class Validator:
        def __init__(self, *a, **kw):
            self.manager = SimpleNamespace(prepare=lambda *a: SimpleNamespace(image="immutable"))
        def build_frontend(self, root):
            import tempfile
            from pathlib import Path
            dist = Path(tempfile.mkdtemp())
            (dist / "dist").mkdir()
            (dist / "dist/index.html").write_text("fresh build")
            return 0, "built", dist, None
    class Client:
        def __init__(self, **kw): assert kw["trust_env"] is False
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *a, **kw): return SimpleNamespace(status_code=status)
    monkeypatch.setattr(product_launch, "RuntimeSession", Runtime)
    monkeypatch.setattr(product_launch, "IsolatedValidator", Validator)
    monkeypatch.setattr(product_launch.httpx, "Client", Client)
    return sessions


def state():
    return ProjectState(id="preview", name="Preview", goal="Preview", technical_stack={"kind": "api"})


def test_preview_waits_for_http_and_cleans_up_on_early_exit(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("pass")
    sessions = harness(monkeypatch, running=False)
    with pytest.raises(AgentError, match="exited"):
        product_launch.open_preview(state(), tmp_path, docker="docker", timeout=1)
    assert sessions[0].closed and not sessions[0].stage.exists()


def test_preview_nominal_owns_copy_and_never_modifies_existing_dist(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("pass")
    front = tmp_path / "frontend"
    (front / "dist").mkdir(parents=True)
    (front / "package.json").write_text("{}")
    (front / "dist/index.html").write_text("original stale build")
    sessions = harness(monkeypatch)
    preview = product_launch.open_preview(state(), tmp_path, docker="docker", timeout=1)
    assert preview.is_running()
    assert (sessions[0].stage / "frontend/dist/index.html").read_text() == "fresh build"
    assert (front / "dist/index.html").read_text() == "original stale build"
    preview.close()
    preview.close()
    assert sessions[0].closed and not sessions[0].stage.exists()


def test_preview_500_never_marks_readiness(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text("pass")
    sessions = harness(monkeypatch, status=500)
    with pytest.raises(AgentError, match="timeout"):
        product_launch.open_preview(state(), tmp_path, docker="docker", timeout=.05)
    assert sessions[0].closed


async def test_container_exit_revokes_running_and_disposes_only_owned_preview():
    pipeline = Pipeline(state(), FakeRunner())
    closed = []
    preview = SimpleNamespace(is_running=lambda: False, close=lambda: closed.append("owned"))
    pipeline._isolated_preview = preview
    pipeline.state.running = True
    await pipeline._awatch_isolated_preview(preview)
    assert closed == ["owned"] and pipeline._isolated_preview is None and not pipeline.state.running


async def test_cleanup_failure_revokes_running_but_preserves_authority_for_retry():
    pipeline = Pipeline(state(), FakeRunner())
    calls = []
    def close():
        calls.append(True)
        if len(calls) == 1:
            raise OSError("Docker unavailable")
    preview = SimpleNamespace(is_running=lambda: False, close=close)
    pipeline._isolated_preview = preview
    pipeline.state.running = True
    await pipeline._awatch_isolated_preview(preview)
    assert not pipeline.state.running and pipeline._isolated_preview is preview
    assert await pipeline._aclose_isolated_preview(preview)
    assert pipeline._isolated_preview is None and len(calls) == 2
