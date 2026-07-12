"""Docker delivery gate: build → deploy on the shared ``autospec-net`` network →
network-verify (health + cross-container reachability) → fix-until-green.

Two layers are covered, and NO real docker is ever touched:

* **Module layer** (``orchestrator.docker_deploy``) — every ``subprocess.run`` /
  ``Popen`` the module makes is monkeypatched, exactly like ``test_runtime_acceptance``
  fakes exit codes. We drive ``docker_available`` / ``ensure_network`` /
  ``wait_healthy`` / ``check_cross_reachability`` / ``allocate_host_port`` / name
  sanitisation / ``should_run`` / ``probe`` off scripted daemon output.
* **Phase layer** (``Pipeline._adocker_delivery_phase``) — reuses the
  ``repair_env`` fixture pattern (git faked, pytest green) + ``FakeRunner`` and a
  queued ``deploy_and_verify`` helper à la ``_fake_gate``. ``deploy_and_verify`` /
  ``docker_available`` are stubbed at the pipeline layer so no docker binary is
  ever invoked."""

import subprocess

import pytest

from autospec.agents.runner import FakeRunner
from autospec.config import settings
from autospec.models import BackendLanguage, ProjectState, StoryStatus, Stream, StreamKind, UserStory
from autospec.orchestrator import docker_deploy
from autospec.orchestrator.docker_deploy import DockerDeployResult
from autospec.orchestrator.pipeline import Pipeline
from autospec.storage import workspace_dir


# =========================================================================
# Module layer — fake subprocess/Popen inside docker_deploy
# =========================================================================


def _fake_docker(monkeypatch, script):
    """Route ``docker_deploy._docker`` through a scripted callable.

    ``script`` is ``(args) -> (returncode, output)``; it receives the docker
    argv (without the ``docker`` binary itself)."""
    def _fake(args, *, timeout, cwd=None):
        return script(list(args))

    monkeypatch.setattr(docker_deploy, "_docker", _fake)


# ------------------------------------------------------------ docker_available

def test_docker_available_false_on_file_not_found(monkeypatch):
    """docker binary absent (FileNotFoundError at launch) → not available."""
    def _boom(cmd, **kwargs):
        raise FileNotFoundError("docker introuvable")

    monkeypatch.setattr(subprocess, "run", _boom)
    ok, out = docker_deploy.docker_available()
    assert ok is False
    # The launch error string is surfaced (the pipeline classifies it as infra).
    assert "docker" in out.lower()


def test_docker_available_false_on_named_pipe_daemon_down(monkeypatch):
    """Docker Desktop OFF on Windows: named-pipe connect error → down + infra."""
    pipe_err = (
        "error during connect: this error may indicate that the docker daemon is "
        "not running: open //./pipe/docker_engine: The system cannot find the file "
        "specified."
    )

    def _fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout=pipe_err)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    ok, out = docker_deploy.docker_available()
    assert ok is False
    assert docker_deploy.looks_like_daemon_down(out) is True


def test_looks_like_daemon_down_negative_on_ordinary_error():
    assert docker_deploy.looks_like_daemon_down("some build layer failed") is False
    assert docker_deploy.looks_like_daemon_down("") is False


# ------------------------------------------------------------- ensure_network

def test_ensure_network_idempotent_when_inspect_ok(monkeypatch):
    """Network already present (inspect rc 0) → create is never called."""
    calls = []

    def _script(args):
        calls.append(args)
        if args[:2] == ["network", "inspect"]:
            return 0, '[{"Name":"autospec-net"}]'
        raise AssertionError(f"unexpected docker call {args}")

    _fake_docker(monkeypatch, _script)
    ok, detail = docker_deploy.ensure_network("autospec-net")
    assert ok is True
    assert detail == ""
    assert all(a[:2] != ["network", "create"] for a in calls)


def test_ensure_network_creates_when_missing(monkeypatch):
    def _script(args):
        if args[:2] == ["network", "inspect"]:
            return 1, "Error: No such network: autospec-net"
        if args[:2] == ["network", "create"]:
            return 0, "abc123"
        raise AssertionError(args)

    _fake_docker(monkeypatch, _script)
    ok, _ = docker_deploy.ensure_network("autospec-net")
    assert ok is True


def test_ensure_network_tolerates_already_exists_race(monkeypatch):
    """A concurrent pipeline created it between our inspect and create."""
    def _script(args):
        if args[:2] == ["network", "inspect"]:
            return 1, "No such network"
        if args[:2] == ["network", "create"]:
            return 1, 'Error response from daemon: network with name autospec-net already exists'
        raise AssertionError(args)

    _fake_docker(monkeypatch, _script)
    ok, _ = docker_deploy.ensure_network("autospec-net")
    assert ok is True


def test_ensure_network_daemon_down_is_reported(monkeypatch):
    def _script(args):
        return 1, "error during connect: open //./pipe/docker_engine"

    _fake_docker(monkeypatch, _script)
    ok, detail = docker_deploy.ensure_network("autospec-net")
    assert ok is False
    assert docker_deploy.looks_like_daemon_down(detail) is True


# --------------------------------------------------------------- wait_healthy

def test_wait_healthy_fails_fast_when_container_exited(monkeypatch):
    """State ``exited`` → fail fast (no HTTP polling) WITH the container logs."""
    def _script(args):
        if args[:2] == ["inspect", "-f"]:
            return 0, "exited"
        if args[0] == "logs":
            return 0, "Traceback: bind 127.0.0.1 refused"
        raise AssertionError(args)

    _fake_docker(monkeypatch, _script)
    # urlopen must never be reached for an exited container.
    monkeypatch.setattr(
        docker_deploy.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not poll HTTP")),
    )
    ok, detail = docker_deploy.wait_healthy("autospec-app", 18000, timeout=5.0)
    assert ok is False
    assert "exited" in detail
    assert "Traceback" in detail  # logs embedded for the repair prompt


def test_wait_healthy_404_is_healthy(monkeypatch):
    """Any HTTP status (incl. 404) proves the port is open = healthy."""
    def _script(args):
        if args[:2] == ["inspect", "-f"]:
            return 0, "running"
        raise AssertionError(args)

    _fake_docker(monkeypatch, _script)

    import urllib.error

    def _urlopen(url, timeout=5):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(docker_deploy.urllib.request, "urlopen", _urlopen)
    ok, detail = docker_deploy.wait_healthy("autospec-app", 18000, timeout=5.0)
    assert ok is True
    assert detail == ""


def test_wait_healthy_timeout_with_logs(monkeypatch):
    """Never listening → timeout, failure carries the last error + logs."""
    def _script(args):
        if args[:2] == ["inspect", "-f"]:
            return 0, "running"
        if args[0] == "logs":
            return 0, "still booting…"
        raise AssertionError(args)

    _fake_docker(monkeypatch, _script)

    def _urlopen(url, timeout=5):
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(docker_deploy.urllib.request, "urlopen", _urlopen)
    # Keep the test instant: no real 1s polling sleeps (wait_healthy does a local
    # ``import time`` → patch the stdlib module it resolves to).
    import time as _time
    monkeypatch.setattr(_time, "sleep", lambda *_a, **_k: None)
    ok, detail = docker_deploy.wait_healthy("autospec-app", 18000, timeout=0.01)
    assert ok is False
    assert "timeout" in detail.lower()
    assert "still booting" in detail  # logs embedded


# ------------------------------------------------- check_cross_reachability

def test_cross_reachability_own_pair_failure_blocks(monkeypatch):
    """A failing pair INVOLVING the current container fails this project's gate —
    after ONE retry (a slow cold-start must not instantly burn a repair attempt)."""
    deployed = [
        {"name": "autospec-a", "project": "a", "port": 8000},
        {"name": "autospec-b", "project": "b", "port": 8000},
    ]
    calls: list[tuple[str, str]] = []

    def _probe(src, dst, dst_port):
        calls.append((src, dst))
        # a → b is broken (persistently); the reverse works.
        if src == "autospec-a" and dst == "autospec-b":
            return False, "connection refused"
        return True, ""

    monkeypatch.setattr(docker_deploy, "probe", _probe)
    monkeypatch.setattr(docker_deploy, "_PROBE_RETRY_DELAY_S", 0.0)
    ok, detail = docker_deploy.check_cross_reachability("autospec-a", deployed)
    assert ok is False
    assert "FAIL autospec-a -> autospec-b" in detail
    # The failing own pair was probed twice (one retry), the healthy one once.
    assert calls.count(("autospec-a", "autospec-b")) == 2
    assert calls.count(("autospec-b", "autospec-a")) == 1


def test_cross_reachability_own_pair_recovers_on_retry(monkeypatch):
    """A transient failure (peer still booting) passes on the retry — the gate
    stays green and no repair attempt is burned."""
    deployed = [
        {"name": "autospec-a", "project": "a", "port": 8000},
        {"name": "autospec-b", "project": "b", "port": 8000},
    ]
    failures = {"n": 0}

    def _probe(src, dst, dst_port):
        if src == "autospec-a" and dst == "autospec-b" and failures["n"] == 0:
            failures["n"] += 1
            return False, "connection refused (booting)"
        return True, ""

    monkeypatch.setattr(docker_deploy, "probe", _probe)
    monkeypatch.setattr(docker_deploy, "_PROBE_RETRY_DELAY_S", 0.0)
    ok, detail = docker_deploy.check_cross_reachability("autospec-a", deployed)
    assert ok is True
    assert "FAIL" not in detail


def test_cross_reachability_foreign_probe_budget(monkeypatch):
    """Foreign pairs stop after the probe budget so a big fleet cannot block the
    gate for minutes; the truncation is stated, never silent."""
    deployed = [{"name": f"autospec-{i}", "project": str(i), "port": 8000} for i in range(7)]
    calls = {"n": 0}

    def _probe(src, dst, dst_port):
        calls["n"] += 1
        return True, ""

    monkeypatch.setattr(docker_deploy, "probe", _probe)
    monkeypatch.setattr(docker_deploy, "_MAX_FOREIGN_PROBES", 5)
    ok, detail = docker_deploy.check_cross_reachability("autospec-0", deployed)
    assert ok is True
    # 12 own pairs (0↔each of 6 others, both directions) + 5 foreign (budget).
    assert calls["n"] == 12 + 5
    assert "non sondée" in detail


def test_cross_reachability_foreign_pair_is_warning_only(monkeypatch):
    """A failing pair between two FOREIGN containers never fails our gate — it is
    surfaced as a warning so we don't burn our attempts on another project's bug."""
    deployed = [
        {"name": "autospec-me", "project": "me", "port": 8000},
        {"name": "autospec-b", "project": "b", "port": 8000},
        {"name": "autospec-c", "project": "c", "port": 8000},
    ]

    def _probe(src, dst, dst_port):
        # Only the b↔c foreign pair is broken; everything touching "me" is fine.
        if src == "autospec-b" and dst == "autospec-c":
            return False, "no route"
        return True, ""

    monkeypatch.setattr(docker_deploy, "probe", _probe)
    ok, detail = docker_deploy.check_cross_reachability("autospec-me", deployed)
    assert ok is True  # own pairs all green → gate passes
    assert "avertissements (paires tierces)" in detail
    assert "FAIL autospec-b -> autospec-c" in detail


# ------------------------------------------------------- allocate_host_port

def test_allocate_host_port_reuses_persisted(monkeypatch):
    """A state that already owns a port keeps it (stable across redeploys)."""
    state = ProjectState(id="alloc-reuse", name="a", goal="g")
    state.deploy_host_port = 18042
    # No docker / storage scan should be needed on the reuse path.
    monkeypatch.setattr(docker_deploy, "list_deployed", lambda: (_ for _ in ()).throw(AssertionError("no scan on reuse")))
    assert docker_deploy.allocate_host_port(state) == 18042


def test_allocate_host_port_returns_base_when_free(monkeypatch):
    monkeypatch.setattr(settings, "docker_host_port_base", 18000)
    monkeypatch.setattr(docker_deploy, "list_deployed", lambda: [])
    monkeypatch.setattr(docker_deploy, "host_port_is_free", lambda port: True)
    from autospec import storage
    monkeypatch.setattr(storage, "list_states", lambda: [])
    state = ProjectState(id="alloc-base", name="a", goal="g")
    assert docker_deploy.allocate_host_port(state) == 18000


def test_allocate_host_port_skips_collisions(monkeypatch):
    """Base + next are claimed (by a running container's PUBLISHED host port and
    by a persisted state); the third is host-busy → we land on base+3."""
    monkeypatch.setattr(settings, "docker_host_port_base", 18000)
    monkeypatch.setattr(
        docker_deploy,
        "list_deployed",
        lambda: [{"name": "x", "project": "x", "port": 8000, "host_ports": [18000]}],
    )
    other = ProjectState(id="other", name="o", goal="g")
    other.deploy_host_port = 18001
    from autospec import storage
    monkeypatch.setattr(storage, "list_states", lambda: [other])
    monkeypatch.setattr(docker_deploy, "host_port_is_free", lambda port: port != 18002)
    state = ProjectState(id="alloc-collide", name="a", goal="g")
    assert docker_deploy.allocate_host_port(state) == 18003


def test_allocate_claims_published_ports_even_without_state_file(monkeypatch):
    """The docker-published HOST port is authoritative: a container whose project
    state file is gone (deleted project, wiped workspace) still claims its port."""
    monkeypatch.setattr(settings, "docker_host_port_base", 18000)
    monkeypatch.setattr(
        docker_deploy,
        "list_deployed",
        # Orphan container: publishes 18000; container-internal port label 8000.
        lambda: [{"name": "orphan", "project": "gone", "port": 8000, "host_ports": [18000]}],
    )
    from autospec import storage
    monkeypatch.setattr(storage, "list_states", lambda: [])  # no state files at all
    monkeypatch.setattr(docker_deploy, "host_port_is_free", lambda port: True)
    state = ProjectState(id="alloc-orphan", name="a", goal="g")
    assert docker_deploy.allocate_host_port(state) == 18001


def test_allocate_ignores_container_internal_port_label(monkeypatch):
    """The autospec.port label (container-INTERNAL port) must NOT be treated as a
    host claim: a container labelled 18005 internally but publishing nothing on
    that host port leaves 18005 available."""
    monkeypatch.setattr(settings, "docker_host_port_base", 18005)
    monkeypatch.setattr(
        docker_deploy,
        "list_deployed",
        lambda: [{"name": "x", "project": "x", "port": 18005, "host_ports": [19000]}],
    )
    from autospec import storage
    monkeypatch.setattr(storage, "list_states", lambda: [])
    monkeypatch.setattr(docker_deploy, "host_port_is_free", lambda port: True)
    state = ProjectState(id="alloc-label", name="a", goal="g")
    assert docker_deploy.allocate_host_port(state) == 18005


# ------------------------------------------------------ published-port parsing

def test_parse_host_ports_ipv4_and_ipv6():
    ports = docker_deploy._parse_host_ports(
        "0.0.0.0:18000->8000/tcp, [::]:18000->8000/tcp, 0.0.0.0:18001->9000/tcp"
    )
    assert ports == [18000, 18001]


def test_parse_host_ports_empty_and_unpublished():
    assert docker_deploy._parse_host_ports("") == []
    assert docker_deploy._parse_host_ports("8000/tcp") == []  # exposed, not published


def test_list_deployed_parses_ports_column(monkeypatch):
    """docker ps now yields a 4th {{.Ports}} column parsed into host_ports."""
    out = (
        "autospec-a\ta\t8000\t0.0.0.0:18000->8000/tcp, [::]:18000->8000/tcp\n"
        "autospec-b\tb\t80\t0.0.0.0:18001->80/tcp\n"
        "autospec-old\told\t8000\n"  # pre-upgrade 3-column line stays parseable
    )

    def _script(args):
        assert args[0] == "ps"
        return 0, out

    _fake_docker(monkeypatch, _script)
    deployed = docker_deploy.list_deployed()
    assert deployed[0] == {
        "name": "autospec-a", "project": "a", "port": 8000, "host_ports": [18000]
    }
    assert deployed[1]["host_ports"] == [18001]
    assert deployed[2]["host_ports"] == []


# ------------------------------------------------------ name sanitisation

def test_slug_image_and_container_name_sanitisation():
    assert docker_deploy.slug("My_Project 42!") == "my-project-42"
    assert docker_deploy.slug("---weird__ID---") == "weird-id"
    assert docker_deploy.slug("") == "app"
    assert docker_deploy.image_name("My_Project 42!") == "autospec/my-project-42:latest"
    assert docker_deploy.container_name("My_Project 42!") == "autospec-my-project-42"


# ----------------------------------------------------- should_run kind resolution

def _done_state(pid, *, streams=None, language=BackendLanguage.PYTHON):
    st = ProjectState(id=pid, name="app", goal="g", backend_language=language)
    st.stories = [UserStory(id="US-1", epic_id="E", title="t", status=StoryStatus.DONE)]
    if streams is not None:
        st.streams = streams
    return st


def _write_backend_main(ws):
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("import uvicorn\napp = 'fastapi'\n", encoding="utf-8")
    (ws / "pyproject.toml").write_text("[project]\nname='x'\ndependencies=['fastapi']\n", encoding="utf-8")


def test_should_run_backend_only(monkeypatch):
    monkeypatch.setattr(settings, "fake_agents", False)
    state = _done_state("sr-backend")
    ws = workspace_dir(state.id)
    _write_backend_main(ws)
    run, reason, kind = docker_deploy.should_run(state, ws, enabled=True)
    assert run is True
    assert kind == "backend"


def test_should_run_fullstack_when_frontend_present(monkeypatch):
    monkeypatch.setattr(settings, "fake_agents", False)
    state = _done_state(
        "sr-fullstack",
        streams=[
            Stream(id="backend", kind=StreamKind.BACKEND, primary=True),
            Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend"),
        ],
    )
    ws = workspace_dir(state.id)
    _write_backend_main(ws)
    fe = ws / "frontend"
    fe.mkdir(parents=True, exist_ok=True)
    (fe / "package.json").write_text('{"name":"fe"}', encoding="utf-8")
    run, reason, kind = docker_deploy.should_run(state, ws, enabled=True)
    assert run is True
    assert kind == "fullstack"


def test_should_run_frontend_only_is_nginx_port80(monkeypatch):
    """A frontend-only SPA (no python web backend) → nginx image, kind 'frontend'."""
    monkeypatch.setattr(settings, "fake_agents", False)
    state = _done_state(
        "sr-frontend",
        streams=[Stream(id="frontend", kind=StreamKind.FRONTEND, language="react", file_root="frontend")],
    )
    ws = workspace_dir(state.id)
    fe = ws / "frontend"
    fe.mkdir(parents=True, exist_ok=True)
    (fe / "package.json").write_text('{"name":"fe"}', encoding="utf-8")
    run, reason, kind = docker_deploy.should_run(state, ws, enabled=True)
    assert run is True
    assert kind == "frontend"


def test_should_run_skips_non_web(monkeypatch):
    """CLI/library (no web backend, no frontend) → skip with an explicit reason."""
    monkeypatch.setattr(settings, "fake_agents", False)
    state = _done_state("sr-cli")
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("print('hello cli')\n", encoding="utf-8")
    run, reason, kind = docker_deploy.should_run(state, ws, enabled=True)
    assert run is False
    assert kind == ""
    assert "non applicable" in reason


def test_should_run_skips_when_disabled_or_demo(monkeypatch):
    state = _done_state("sr-off")
    ws = workspace_dir(state.id)
    _write_backend_main(ws)
    monkeypatch.setattr(settings, "fake_agents", False)
    assert docker_deploy.should_run(state, ws, enabled=False)[0] is False
    monkeypatch.setattr(settings, "fake_agents", True)
    run, reason, _ = docker_deploy.should_run(state, ws, enabled=True)
    assert run is False
    assert "démo" in reason


def test_should_run_non_python_backend_skips(monkeypatch):
    monkeypatch.setattr(settings, "fake_agents", False)
    state = _done_state("sr-go", language=BackendLanguage.GO)
    ws = workspace_dir(state.id)
    _write_backend_main(ws)
    run, reason, kind = docker_deploy.should_run(state, ws, enabled=True)
    assert run is False
    assert kind == ""
    assert "non-python" in reason


# ------------------------------------------------------------ probe fallback

def test_probe_wget_fallback_for_nginx_source(monkeypatch):
    """nginx:alpine source containers ship busybox wget but no python: probe
    tries ``python -c`` first, then falls back to ``wget`` when python is absent."""
    seen = []

    def _script(args):
        seen.append(args)
        if args[0] == "exec" and "python" in args:
            # nginx image: python is not present.
            return 127, "OCI runtime exec failed: executable file not found in $PATH: python"
        if args[0] == "exec" and "wget" in args:
            return 0, "<html>…</html>"
        raise AssertionError(args)

    _fake_docker(monkeypatch, _script)
    ok, detail = docker_deploy.probe("autospec-fe", "autospec-api", 8000)
    assert ok is True
    # Both attempts were made: python first, wget fallback.
    assert any("python" in a for a in seen)
    assert any("wget" in a for a in seen)


def test_probe_python_success_no_fallback(monkeypatch):
    def _script(args):
        if args[0] == "exec" and "python" in args:
            return 0, ""
        raise AssertionError("wget must not be tried when python succeeds")

    _fake_docker(monkeypatch, _script)
    ok, _ = docker_deploy.probe("autospec-a", "autospec-b", 8000)
    assert ok is True


# =========================================================================
# Phase layer — Pipeline._adocker_delivery_phase
# =========================================================================


def _phase_state(pid: str) -> ProjectState:
    st = ProjectState(id=pid, name="app", goal="g")
    st.stories = [UserStory(id="US-1", epic_id="E", title="t", status=StoryStatus.DONE)]
    return st


@pytest.fixture
def deploy_env(monkeypatch):
    """Gate on, demo off, git faked, pytest green — plus a python web backend in
    the workspace so ``should_run`` classifies the project as ``backend``. Mirrors
    ``test_integration_repair.repair_env``. Returns the recorded git calls."""
    monkeypatch.setattr(settings, "fake_agents", False)
    monkeypatch.setattr(settings, "docker_delivery", True)
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
    monkeypatch.setattr(Pipeline, "astop_app", _stop)
    # docker_available is stubbed green by default; a test wanting daemon-down
    # overrides it. Never touch a real docker binary.
    monkeypatch.setattr(docker_deploy, "docker_available", lambda: (True, "24.0.0"))
    monkeypatch.setattr(docker_deploy, "allocate_host_port", lambda state: 18000)
    return git_calls


def _write_web_backend(state):
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("import uvicorn\napp = 'fastapi'\nport = 8000\n", encoding="utf-8")
    (ws / "pyproject.toml").write_text("[project]\nname='x'\ndependencies=['fastapi']\n", encoding="utf-8")
    return ws


def _fake_deploy(monkeypatch, results):
    """Queue ``deploy_and_verify`` results (last one repeats) à la ``_fake_gate``.

    Also stubs ``write_deploy_artifacts`` so no Dockerfile is really rendered on
    disk beyond a marker text (the repair-report test writes its own)."""
    queue = list(results)
    calls = {"n": 0}

    def _fake(state, ws, **kwargs):
        calls["n"] += 1
        return queue.pop(0) if len(queue) > 1 else queue[0]

    monkeypatch.setattr(docker_deploy, "deploy_and_verify", _fake)
    return calls


# --------------------------------------------------------------- skip paths

async def test_phase_skips_when_gate_off(monkeypatch, deploy_env):
    monkeypatch.setattr(settings, "docker_delivery", False)
    calls = _fake_deploy(monkeypatch, [DockerDeployResult(ok=True, detail="x")])
    state = _phase_state("dk-off")
    _write_web_backend(state)
    runner = FakeRunner([])
    pipeline = Pipeline(state, runner)

    assert await pipeline._adocker_delivery_phase() is True
    assert pipeline._delivery_blocked is False
    assert calls["n"] == 0  # zero docker work
    assert runner.calls == []


async def test_phase_skips_in_fake_agents_demo(monkeypatch, deploy_env):
    monkeypatch.setattr(settings, "fake_agents", True)
    calls = _fake_deploy(monkeypatch, [DockerDeployResult(ok=True, detail="x")])
    state = _phase_state("dk-demo")
    _write_web_backend(state)
    pipeline = Pipeline(state, FakeRunner([]))

    assert await pipeline._adocker_delivery_phase() is True
    assert calls["n"] == 0


async def test_phase_skips_cli_project_with_warning(monkeypatch, deploy_env):
    """Enabled-but-non-web: skipped, zero docker work, an explicit warning chat +
    ``deploy_status == 'skipped'``."""
    calls = _fake_deploy(monkeypatch, [DockerDeployResult(ok=True, detail="x")])
    chats: list[str] = []
    monkeypatch.setattr(Pipeline, "_chat", lambda self, role, content: chats.append(content))
    state = _phase_state("dk-cli")
    ws = workspace_dir(state.id)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "main.py").write_text("print('cli only')\n", encoding="utf-8")
    pipeline = Pipeline(state, FakeRunner([]))

    assert await pipeline._adocker_delivery_phase() is True
    assert calls["n"] == 0
    assert state.deploy_status == "skipped"
    assert any("non applicable" in c and "PAS empaquetée" in c for c in chats)


# ------------------------------------------------------------- daemon down

async def test_phase_daemon_down_parks_infra(monkeypatch, deploy_env):
    """Docker Desktop off → ``_apark_infra`` + ``_delivery_blocked``, zero agent
    calls, and the issue mentions infra (attempts never burned)."""
    monkeypatch.setattr(
        docker_deploy, "docker_available",
        lambda: (False, "error during connect: open //./pipe/docker_engine"),
    )
    calls = _fake_deploy(monkeypatch, [DockerDeployResult(ok=True, detail="x")])
    state = _phase_state("dk-daemon-down")
    _write_web_backend(state)
    runner = FakeRunner([])
    pipeline = Pipeline(state, runner)

    assert await pipeline._adocker_delivery_phase() is False
    assert pipeline._delivery_blocked is True
    assert calls["n"] == 0  # deploy_and_verify never reached
    assert runner.calls == []  # no repair agent dispatched for an infra fault
    assert any("infra" in issue.lower() for issue in state.delivery_issues)


# --------------------------------------------- build failure → repair → green

async def test_phase_build_failure_repairs_until_green(monkeypatch, deploy_env):
    """Build fails → Dev agent repairs → redeploy VERT. The repair prompt carries
    the Dockerfile section and the ``dev_fix_deploy`` wording; ``deploy_status``
    ends ``deployed``."""
    state = _phase_state("dk-build-fix")
    ws = _write_web_backend(state)
    # A managed Dockerfile is present so the repair report embeds it.
    (ws / "Dockerfile").write_text("# autospec:managed\nFROM python:3.12\nEXPOSE 8000\n", encoding="utf-8")

    _fake_deploy(monkeypatch, [
        DockerDeployResult(
            ok=False,
            detail="=== docker build (tail) ===\nERROR: uv sync failed (missing dep)",
            image="autospec/dk-build-fix:latest",
            container="autospec-dk-build-fix",
        ),
        DockerDeployResult(
            ok=True,
            detail="déployé autospec-dk-build-fix sur http://localhost:18000",
            image="autospec/dk-build-fix:latest",
            container="autospec-dk-build-fix",
            host_port=18000,
        ),
    ])
    runner = FakeRunner(['{"status": "fixed", "summary": "dep ajoutée à pyproject", "files": []}'])
    pipeline = Pipeline(state, runner)

    assert await pipeline._adocker_delivery_phase() is True
    assert pipeline._delivery_blocked is False
    assert state.deploy_status == "deployed"
    assert len(runner.calls) == 1
    prompt = runner.calls[0]["prompt"]
    assert "=== Dockerfile ===" in prompt  # report embeds the Dockerfile
    assert "autospec:managed" in prompt
    assert "GATE DE LIVRAISON DOCKER" in prompt  # dev_fix_deploy prompt, not dev_fix_integration
    assert runner.calls[0]["cwd"] is not None


# ------------------------------------------- exhausted attempts → blocked

async def test_phase_blocks_after_exhausted_attempts(monkeypatch, deploy_env):
    monkeypatch.setattr(settings, "integration_fix_attempts", 2)
    _fake_deploy(monkeypatch, [
        DockerDeployResult(
            ok=False,
            detail="health-wait timeout — le conteneur n'écoute pas",
            image="autospec/dk-ko:latest",
            container="autospec-dk-ko",
        ),
    ])
    runner = FakeRunner([
        '{"status": "fixed", "summary": "essai 1", "files": []}',
        '{"status": "fixed", "summary": "essai 2", "files": []}',
    ])
    state = _phase_state("dk-ko")
    _write_web_backend(state)
    pipeline = Pipeline(state, runner)

    assert await pipeline._adocker_delivery_phase() is False
    assert pipeline._delivery_blocked is True
    assert state.deploy_status == "failed"
    assert len(runner.calls) == 2  # every attempt consumed
    assert any("Livraison Docker échouée" in issue for issue in state.delivery_issues)


# ------------------------------------------ repair breaks pytest → rollback

async def test_phase_repair_rolls_back_when_fix_breaks_suite(monkeypatch, deploy_env):
    """A repair that turns the suite red must be rolled back (``git reset --hard``)
    — never trade a red suite for a green deploy."""
    git_calls = deploy_env
    monkeypatch.setattr(settings, "integration_fix_attempts", 1)

    async def _red_pytest(self, ws=None):
        return False, "1 failed", {}

    monkeypatch.setattr(Pipeline, "_arun_pytest", _red_pytest)
    _fake_deploy(monkeypatch, [
        DockerDeployResult(
            ok=False,
            detail="health-wait timeout",
            image="autospec/dk-rollback:latest",
            container="autospec-dk-rollback",
        ),
    ])
    runner = FakeRunner(['{"status": "fixed", "summary": "s", "files": []}'])
    state = _phase_state("dk-rollback")
    _write_web_backend(state)
    pipeline = Pipeline(state, runner)

    assert await pipeline._adocker_delivery_phase() is False
    assert pipeline._delivery_blocked is True
    assert ("reset", "--hard", "HEAD") in git_calls
    assert ("clean", "-fd") in git_calls
