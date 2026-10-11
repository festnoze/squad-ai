"""Docker lifecycle tests: no Docker daemon or user container is touched."""

import json
import socket
import sys
import threading
import time
import io
import urllib.error
from concurrent.futures import ThreadPoolExecutor

import pytest

from autospec import storage
from autospec.config import settings
from autospec.models import ProjectState
from autospec.orchestrator import docker_deploy as docker


@pytest.fixture(autouse=True)
def cleanup_reservations():
    yield
    docker._operation.cancel_event = None
    for project_id in list(docker._port_reservations):
        docker.release_host_port(project_id)


def test_timeout_interrupts_a_process_that_never_closes_stdout():
    started = time.monotonic()
    rc, output = docker._run_process(
        [sys.executable, "-u", "-c", "import time; print('started',flush=True); time.sleep(30)"],
        timeout=0.2,
    )
    assert rc == -1
    assert "timeout" in output
    assert time.monotonic() - started < 8


def test_cancellation_interrupts_streaming_process():
    cancel = threading.Event()
    docker._operation.cancel_event = cancel
    timer = threading.Timer(0.15, cancel.set)
    timer.start()
    try:
        rc, output = docker._run_process([sys.executable, "-c", "import time; time.sleep(30)"], timeout=30)
    finally:
        timer.cancel()
    assert rc == -2
    assert "cancelled" in output


def test_registry_error_does_not_look_like_empty_registry(monkeypatch):
    monkeypatch.setattr(docker, "_docker", lambda *a, **k: (1, "cannot connect to the Docker daemon"))
    with pytest.raises(docker.DockerRuntimeError, match="cannot connect"):
        docker.list_deployed()


def test_missing_copy_source_is_an_application_build_failure():
    assert not docker.looks_like_infra("COPY failed: main.py: no such file or directory")
    assert docker.looks_like_infra("Docker CLI unavailable: executable not found")


@pytest.mark.parametrize("failure", ["500", "database"])
def test_managed_health_rejects_http_errors_and_wrong_database(monkeypatch, failure):
    monkeypatch.setattr(docker, "_docker", lambda *a, **k: (0, "running"))
    monkeypatch.setattr(docker, "_container_logs", lambda *a: "")
    def response(url, **kwargs):
        if failure == "500":
            raise urllib.error.HTTPError(url, 500, "db unavailable", {}, None)
        result = io.BytesIO(json.dumps({"status": "ok", "service": "autospec-bootstrap", "database": "none"}).encode())
        result.status = 200
        return result
    monkeypatch.setattr(docker.urllib.request, "urlopen", response)
    ok, detail = docker.wait_healthy("app", 12345, timeout=0.01, health_path="/api/health",
        expected={"status": "ok", "service": "autospec-bootstrap", "database": "ok"})
    assert not ok
    assert ("HTTP 500" if failure == "500" else "database") in detail


def test_frontend_health_rejects_http500(monkeypatch):
    monkeypatch.setattr(docker, "_docker", lambda *a, **k: (0, "running"))
    monkeypatch.setattr(docker, "_container_logs", lambda *a: "")
    def response(url, **kwargs):
        raise urllib.error.HTTPError(url, 500, "failed", {}, None)
    monkeypatch.setattr(docker.urllib.request, "urlopen", response)
    assert not docker.wait_healthy("frontend", 12345, timeout=0.01, strict_http=True)[0]


def test_volume_ownership_is_checked_before_reuse(monkeypatch):
    monkeypatch.setattr(docker, "_docker", lambda *a, **k: (0, json.dumps([{"Labels": {docker.LABEL_PROJECT: "someone-else"}}])))
    with pytest.raises(docker.DockerRuntimeError, match="autre projet"):
        docker.ensure_data_volume("app")


def test_undeploy_never_removes_a_foreign_container(engine):
    engine.containers["autospec-app"]["Config"]["Labels"][docker.LABEL_PROJECT] = "another-project"
    result = docker.undeploy("app")
    assert not result.ok
    assert not any(args[0] == "rm" for args in engine.calls)


def test_packaged_image_reconciliation_distinguishes_missing_from_daemon_failure(monkeypatch):
    monkeypatch.setattr(docker, "_docker", lambda *a, **k: (1, "No such image"))
    missing = docker.inspect_packaged_image("app")
    assert missing.skipped and not missing.infra
    monkeypatch.setattr(docker, "_docker", lambda *a, **k: (1, "daemon unavailable"))
    unavailable = docker.inspect_packaged_image("app")
    assert unavailable.infra and not unavailable.skipped


@pytest.mark.parametrize("status", [404, 500])
def test_wget_http_error_proves_connectivity(monkeypatch, status):
    def run(args, **kwargs):
        if "python" in args:
            return 127, "executable file not found"
        return 1, f"wget: server returned error: HTTP/1.1 {status} Error"
    monkeypatch.setattr(docker, "_docker", run)
    assert docker.probe("src", "dst", 8080)[0]


def test_undeploy_reports_daemon_failure_and_keeps_image(monkeypatch):
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        return 1, "cannot connect to the Docker daemon"
    monkeypatch.setattr(docker, "_docker", run)
    result = docker.undeploy("app")
    assert not result.ok and result.infra
    assert not any(args[0] == "rmi" for args in calls)


def test_port_allocation_reserves_unique_sockets_under_concurrency(monkeypatch):
    monkeypatch.setattr(settings, "docker_host_port_base", 25000)
    monkeypatch.setattr(docker, "list_deployed", lambda: [])
    monkeypatch.setattr(storage, "list_states", lambda: [])
    states = [ProjectState(id=f"parallel-{i}", name="p", goal="g") for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        ports = list(pool.map(docker.allocate_host_port, states))
    assert len(set(ports)) == 8
    assert all(not docker.host_port_is_free(port) for port in ports)
    for state, port in zip(states, ports):
        docker.release_host_port(state.id)
        assert docker.host_port_is_free(port)


def test_stale_persisted_port_is_not_reused_when_another_process_owns_it(monkeypatch):
    monkeypatch.setattr(docker, "list_deployed", lambda: [])
    monkeypatch.setattr(storage, "list_states", lambda: [])
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]
        state = ProjectState(id="stale", name="p", goal="g", deploy_host_port=port)
        assert docker.allocate_host_port(state) != port


class FakeEngine:
    def __init__(self):
        self.calls = []
        self.containers = {"autospec-app": self.info("old", 18000)}

    @staticmethod
    def info(image, host_port):
        return {"State": {"Running": True},
                "Config": {"Image": image, "Labels": {docker.LABEL_PROJECT: "app", docker.LABEL_PORT: "8000"}},
                "NetworkSettings": {"Ports": {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(host_port)}]}}}

    def run(self, args, **kwargs):
        self.calls.append(list(args))
        if args[0] == "inspect":
            info = self.containers.get(args[1])
            return (0, json.dumps([info])) if info else (1, "No such container")
        if args[0] == "run":
            name = args[args.index("--name") + 1]
            self.containers[name] = self.info(args[-1], 25000 if "candidate" in name else 18000)
            return 0, name
        if args[0] == "stop":
            self.containers[args[-1]]["State"]["Running"] = False
        if args[0] == "start":
            self.containers[args[-1]]["State"]["Running"] = True
        if args[0] == "rename":
            self.containers[args[2]] = self.containers.pop(args[1])
        if args[0] == "rm":
            self.containers.pop(args[-1], None)
        return 0, ""


@pytest.fixture
def engine(monkeypatch):
    engine = FakeEngine()
    monkeypatch.setattr(docker, "_docker", engine.run)
    monkeypatch.setattr(docker, "docker_available", lambda: (True, ""))
    monkeypatch.setattr(docker, "ensure_network", lambda network: (True, ""))
    monkeypatch.setattr(docker, "build_image", lambda *a, **k: (True, "built"))
    monkeypatch.setattr(docker, "resolve_web_port", lambda ws: 8000)
    monkeypatch.setattr(docker, "list_deployed", lambda **kwargs: [{"name": "autospec-app", "project": "app", "port": 8000}])
    monkeypatch.setattr(docker, "wait_healthy", lambda *a, **k: (True, ""))
    return engine


def deploy(tmp_path, **kwargs):
    return docker.deploy_and_verify(ProjectState(id="app", name="p", goal="g"), tmp_path,
                                    network="test", host_port=18000, build_timeout=5,
                                    deploy_timeout=5, kind="backend", **kwargs)


def test_candidate_failure_never_stops_last_working_container(engine, monkeypatch, tmp_path):
    monkeypatch.setattr(docker, "wait_healthy", lambda *a, **k: (False, "boot crashed"))
    result = deploy(tmp_path)
    assert not result.ok
    assert not any(args[0] == "stop" for args in engine.calls)
    assert list(engine.containers) == ["autospec-app"]
    assert engine.containers["autospec-app"]["Config"]["Image"] == "old"


def test_fast_candidate_crash_retains_application_logs(engine, monkeypatch, tmp_path):
    original_inspect = docker._inspect_container
    def inspect(name):
        info = original_inspect(name)
        if info and "candidate" in name:
            info["NetworkSettings"]["Ports"] = {}
        return info
    monkeypatch.setattr(docker, "_inspect_container", inspect)
    monkeypatch.setattr(docker, "_container_logs", lambda name: "RuntimeError: missing configuration")
    result = deploy(tmp_path)
    assert not result.ok and "missing configuration" in result.detail
    assert engine.containers["autospec-app"]["Config"]["Image"] == "old"


def test_final_failure_restores_old_container(engine, monkeypatch, tmp_path):
    monkeypatch.setattr(docker, "wait_healthy", lambda name, *a, **k: ("candidate" in name, "final crashed"))
    result = deploy(tmp_path)
    assert not result.ok
    assert list(engine.containers) == ["autospec-app"]
    assert engine.containers["autospec-app"]["Config"]["Image"] == "old"
    assert engine.containers["autospec-app"]["State"]["Running"]


def test_success_replaces_old_only_after_candidate_validation(engine, monkeypatch, tmp_path):
    events = []
    original = engine.run
    def run(args, **kwargs):
        events.append(args[0])
        return original(args, **kwargs)
    monkeypatch.setattr(docker, "_docker", run)
    def health(name, *a, **k):
        events.append("healthy")
        return True, ""
    monkeypatch.setattr(docker, "wait_healthy", health)
    result = deploy(tmp_path)
    assert result.ok
    assert events.index("healthy") < events.index("stop")
    assert list(engine.containers) == ["autospec-app"]
    runs = [args for args in engine.calls if args[0] == "run"]
    assert runs[-1][runs[-1].index("-p") + 1] == "127.0.0.1:18000:8000"
    for args in runs:
        assert args[args.index("--cap-drop") + 1] == "ALL"
        assert "no-new-privileges" in args
        assert "--memory" in args and "--cpus" in args and "--pids-limit" in args


def test_sqlite_candidate_is_isolated_and_live_volume_survives_undeploy(engine, monkeypatch, tmp_path):
    monkeypatch.setattr(docker, "ensure_data_volume", lambda project, name=None: name or docker.data_volume_name(project))
    health = []
    monkeypatch.setattr(docker, "wait_healthy", lambda *a, **k: (health.append(k) or True, ""))
    state = ProjectState(id="app", name="p", goal="g", technical_stack={"kind": "api", "backend": "python", "database": "sqlite"})
    result = docker.deploy_and_verify(state, tmp_path, network="test", host_port=18000,
        build_timeout=5, deploy_timeout=5, kind="backend")
    assert result.ok
    runs = [args for args in engine.calls if args[0] == "run"]
    assert "candidate" in runs[0][runs[0].index("--mount") + 1]
    assert runs[1][runs[1].index("--mount") + 1] == "type=volume,source=autospec-app-data,target=/app/data"
    assert all(options["expected"]["database"] == "ok" for options in health)
    docker.undeploy("app")
    removed_volumes = [args[-1] for args in engine.calls if args[:2] == ["volume", "rm"]]
    assert removed_volumes and all("candidate" in volume for volume in removed_volumes)


def test_rejected_foreign_candidate_volume_is_never_removed(engine, monkeypatch, tmp_path):
    original_run = engine.run
    def run(args, **kwargs):
        if args[:2] == ["volume", "inspect"]:
            return 0, json.dumps([{"Labels": {docker.LABEL_PROJECT: "foreign"}}])
        return original_run(args, **kwargs)
    monkeypatch.setattr(docker, "_docker", run)
    def volume(project, name=None):
        if name:
            raise docker.DockerRuntimeError("Le volume appartient à un autre projet")
        return docker.data_volume_name(project)
    monkeypatch.setattr(docker, "ensure_data_volume", volume)
    state = ProjectState(id="app", name="p", goal="g", technical_stack={"kind": "api", "database": "sqlite"})
    result = docker.deploy_and_verify(state, tmp_path, network="test", host_port=18000,
        build_timeout=5, deploy_timeout=5, kind="backend")
    assert not result.ok and result.infra
    assert not any(args[:2] == ["volume", "rm"] for args in engine.calls)


def test_cancellation_after_build_cannot_start_a_container(engine, monkeypatch, tmp_path):
    event = threading.Event()
    def build(*a, **k):
        event.set()
        return True, "built"
    monkeypatch.setattr(docker, "build_image", build)
    # _docker mocks have no cancellation semantics, so lifecycle must check too.
    result = deploy(tmp_path, cancel_event=event)
    assert not result.ok and result.cancelled
    assert not any(args[0] == "run" for args in engine.calls)


def test_registry_failure_during_verify_is_infra_and_rolls_back(engine, monkeypatch, tmp_path):
    def fail_registry(**kwargs):
        raise docker.DockerRuntimeError("cannot connect to the Docker daemon")
    monkeypatch.setattr(docker, "list_deployed", fail_registry)
    result = deploy(tmp_path)
    assert not result.ok and result.infra
    assert engine.containers["autospec-app"]["Config"]["Image"] == "old"


def test_reconciliation_reports_stopped_and_absent(engine):
    engine.containers["autospec-app"]["State"]["Running"] = False
    result = docker.inspect_deployment("app")
    assert not result.ok and not result.skipped
    engine.containers.clear()
    assert docker.inspect_deployment("app").skipped


def test_image_packaging_never_publishes_a_server(engine, tmp_path):
    result = docker.deploy_and_verify(ProjectState(id="library", name="p", goal="g"), tmp_path,
                                      network="test", host_port=0, build_timeout=5,
                                      deploy_timeout=5, kind="library")
    assert result.ok and result.packaged and result.host_port == 0
    assert not result.container
    runs = [args for args in engine.calls if args[0] == "run"]
    assert all("-p" not in args and "none" in args for args in runs)
