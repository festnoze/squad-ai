from types import SimpleNamespace
import os

import httpx

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
            self.options = kwargs
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
        def get(self, url, **kw):
            sessions[0].readiness_url = url
            return SimpleNamespace(status_code=status)
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
    assert sessions[0].options['application_origin'] is True
    assert sessions[0].options['local_cookie_mode'] is True
    assert (sessions[0].stage / "frontend/dist/index.html").read_text() == "fresh build"
    assert (front / "dist/index.html").read_text() == "original stale build"
    preview.close()
    preview.close()
    assert sessions[0].closed and not sessions[0].stage.exists()


@pytest.mark.parametrize('status', [302, 403, 404, 500])
def test_preview_non_2xx_never_marks_readiness(tmp_path, monkeypatch, status):
    (tmp_path / "main.py").write_text("pass")
    sessions = harness(monkeypatch, status=status)
    with pytest.raises(AgentError, match="timeout"):
        product_launch.open_preview(state(), tmp_path, docker="docker", timeout=.05)
    assert sessions[0].closed


def test_factory_readiness_path_is_exact_same_origin(tmp_path, monkeypatch):
    (tmp_path/'main.py').write_text('pass')
    sessions = harness(monkeypatch)
    preview = product_launch.open_preview(state(), tmp_path, docker='docker', timeout=1, readiness_path='/api/health')
    try:
        assert sessions[0].readiness_url == preview.origin + '/api/health'
    finally:
        preview.close()


@pytest.mark.parametrize('path', ['https://foreign.invalid/', '//foreign.invalid/', '/a/../b', '/a\\b', '/\nsecret'])
def test_preview_forbids_non_factory_readiness_target(tmp_path, monkeypatch, path):
    sessions = harness(monkeypatch)
    with pytest.raises(AgentError, match='readiness path'):
        product_launch.open_preview(state(), tmp_path, docker='docker', timeout=1, readiness_path=path)
    assert not sessions


@pytest.mark.skipif(os.environ.get('AUTOSPEC_REAL_LINUX_VALIDATION') != '1', reason='Opt-in real Linux preview origin/cookie/CSRF transport')
def test_real_preview_origin_and_local_cookie_allow_only_matching_csrf_write(tmp_path):
    from autospec.orchestrator.isolated_validation import IsolatedValidator
    from autospec.orchestrator import acceptance
    root = tmp_path/'product'; root.mkdir()
    (root/'pyproject.toml').write_text('[project]\nname="preview-origin-proof"\nversion="1.0.0"\nrequires-python=">=3.12"\ndependencies=[]\n')
    # Reviewed deterministic fixture source is executed ONLY inside Docker.
    (root/'main.py').write_text('''import os
from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','text/html')
  cookie='session=local-proof; Path=/; HttpOnly; SameSite=Strict'
  if os.environ.get('SESSION_COOKIE_SECURE')!='false':cookie+='; Secure'
  self.send_header('Set-Cookie',cookie);self.end_headers()
  self.wfile.write(b'<form><input name="csrf" value="reviewed-token"></form>')
 def do_POST(self):
  ok=(self.headers.get('Origin')==os.environ.get('APP_ORIGIN') and
      self.headers.get('X-CSRF-Token')=='reviewed-token' and
      'session=local-proof' in self.headers.get('Cookie',''))
  self.send_response(200 if ok else 403);self.end_headers();self.wfile.write(b'accepted' if ok else b'forbidden')
HTTPServer(('127.0.0.1',8000),Handler).serve_forever()
''')
    validator = IsolatedValidator(acceptance.supervisor_root(state().id)/'environments', timeout=300)
    validator.manager.ensure_lock(root, 'python')
    preview = product_launch.open_preview(state(), root, docker='docker', timeout=30, readiness_path='/api/health')
    try:
        with httpx.Client(trust_env=False, timeout=15) as client:
            page = client.get(preview.origin+'/')
            assert page.status_code == 200 and 'reviewed-token' in page.text
            assert 'httponly' in page.headers['set-cookie'].lower() and 'secure' not in page.headers['set-cookie'].lower()
            good = client.post(preview.origin+'/write', headers={'Origin':preview.origin,'X-CSRF-Token':'reviewed-token'})
            assert good.status_code == 200 and good.text == 'accepted'
            assert client.post(preview.origin+'/write', headers={'Origin':'http://foreign.invalid','X-CSRF-Token':'reviewed-token'}).status_code == 403
            assert client.post(preview.origin+'/write', headers={'Origin':preview.origin}).status_code == 403
        config = preview.session.inspect_configuration()
        assert config['network_mode'] == 'none' and config['read_only'] and not config['privileged']
        assert preview.is_running()
    finally:
        preview.close()
    assert not preview.is_running()
    assert not (root/'.venv').exists()


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
