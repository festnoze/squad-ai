"""Actual Windows lifecycle sentinels; Docker adversaries run only in Docker."""
import json
import os
import subprocess
import sys
import time

import pytest

from autospec.agents import runner
from autospec.agents.owned_resources import OwnedResource, OwnedResourceRegistry
from autospec.orchestrator import sandbox


def _wait(predicate, seconds=5):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        time.sleep(.01)
    assert predicate()


def _windows_alive(pid):
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(0x00100000, False, pid)
    if not handle:
        return False
    try:
        return api.WaitForSingleObject(handle, 0) == 0x102
    finally:
        api.CloseHandle(handle)


def _sleeper():
    return runner.spawn_owned_process([sys.executable, "-I", "-S", "-c", "import time; time.sleep(60)"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_stop_a_preserves_b_and_unowned_sentinel_with_reused_pid_guard():
    a, b, sentinel = _sleeper(), _sleeper(), _sleeper()
    registry_a, registry_b = runner.ProcessRegistry("run-a"), runner.ProcessRegistry("run-b")
    try:
        registry_a.add(a)
        registry_b.add(b)
        record = registry_a.resources()[0]
        assert record["owner"] == "run-a" and record["identifier"] == str(a.pid)
        assert not registry_a.terminate(a.pid, "stale-creation-identity")
        assert not registry_a.terminate(b.pid, record["creation_identity"])
        assert a.poll() is None and b.poll() is None and sentinel.poll() is None
        assert registry_a.terminate(a.pid, record["creation_identity"])
        a.wait(timeout=3)
        assert b.poll() is None and sentinel.poll() is None
        assert registry_a.terminate_all() == 0
        assert registry_b.resources()[0]["owner"] == "run-b"
    finally:
        for proc in (a, b, sentinel):
            runner.close_owned_process(proc)
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                pipe.close()


@pytest.mark.skipif(os.name != "nt", reason="Real Windows Job detached descendants")
def test_owned_windows_job_includes_detached_child(tmp_path):
    marker = tmp_path / "detached.pid"
    child = f"import os,time; open({str(marker)!r},'w').write(str(os.getpid())); time.sleep(60)"
    parent = ("import subprocess,sys,time; "
              f"subprocess.Popen([sys.executable,'-I','-S','-c',{child!r}], creationflags=0x8, "
              "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); time.sleep(60)")
    proc = runner.spawn_owned_process([sys.executable, "-I", "-S", "-c", parent])
    try:
        _wait(marker.exists)
        pid = int(marker.read_text())
        assert _windows_alive(pid)
        runner.close_owned_process(proc)
        _wait(lambda: not _windows_alive(pid))
        runner.close_owned_process(proc)  # idempotent
    finally:
        runner.close_owned_process(proc)


def test_nonprocess_resource_identity_guards_and_volume_preservation():
    registry = OwnedResourceRegistry("a")
    cleaned = []
    current = {"container": "creation-a", "volume": "volume-a"}
    container = OwnedResource("container", "named-a", "creation-a", "a")
    registry.register(container, identity=lambda: current["container"], cleanup=lambda deadline: cleaned.append("a"))
    registry.register(OwnedResource("volume", "data-a", "volume-a", "a"),
                      identity=lambda: current["volume"], cleanup=lambda deadline: cleaned.append("volume"))
    with pytest.raises(ValueError):
        registry.register(OwnedResource("container", "b", "b", "b"), identity=lambda: "b")
    with pytest.raises(ValueError):
        registry.register(OwnedResource("port", "8126", "listener-b", "a"),
                          identity=lambda: "listener-b", cleanup=lambda deadline: None)
    current["container"] = "reused-name-b"
    outcomes = registry.cleanup()
    assert outcomes == {"container:named-a": "identity_mismatch", "volume:data-a": "preserved"}
    assert not cleaned
    current["container"] = "creation-a"
    assert registry.cleanup()["container:named-a"] == "cleaned"
    assert cleaned == ["a"]
    registry.cleanup()
    assert cleaned == ["a"]


def test_sandbox_builder_is_hardened_and_rejects_host_network():
    cmd = sandbox.docker_run_cmd(["python", "main.py"], "C:\\Product With Space", "sha256:" + "a" * 64, run_id="a")
    assert cmd[cmd.index("--network") + 1] == "none"
    assert cmd[cmd.index("--user") + 1] == "65532:65532"
    assert cmd[cmd.index("--cap-drop") + 1] == "ALL"
    assert "no-new-privileges=true" in cmd and "--read-only" in cmd
    assert "C:/Product With Space:/app:rw" in cmd
    assert "--privileged" not in cmd and "--env-file" not in cmd
    assert not any("docker.sock" in part or ".claude" in part for part in cmd)
    with pytest.raises(runner.AgentError, match="ISOLATION_UNAVAILABLE"):
        sandbox.docker_run_cmd(["python"], "C:/product", "img", network="host")


def test_unavailable_sandbox_never_executes_generated_code(monkeypatch, tmp_path):
    def failed(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, "", "docker unavailable")
    monkeypatch.setattr(sandbox.subprocess, "run", failed)
    monkeypatch.setattr(sandbox, "_run_tracked", lambda *a, **kw: pytest.fail("No fallback execution allowed"))
    with pytest.raises(runner.AgentError, match="ISOLATION_UNAVAILABLE"):
        sandbox.run_isolated(["python", "hostile.py"], tmp_path, "img")


def test_raw_factory_workspace_cannot_be_mounted(tmp_path):
    (tmp_path / "autospec-state.json").write_text("factory state")
    with pytest.raises(runner.AgentError, match="ISOLATION_UNAVAILABLE"):
        sandbox.require_sandbox(tmp_path, "img")


_IMAGE = os.getenv("AUTOSPEC_REAL_DOCKER_IMAGE")
@pytest.mark.skipif(not _IMAGE, reason="Explicit disposable Docker bench")
def test_real_docker_nominal_and_adversarial_operations_preserve_host(tmp_path):
    product = tmp_path / "product"
    product.mkdir()
    host_file = tmp_path / "outside-sentinel.txt"
    host_file.write_text("intact")
    sentinel = _sleeper()
    try:
        script = "import pathlib,os,json; pathlib.Path('/app/result.txt').write_text('nominal'); print(json.dumps({'uid':os.getuid()}))"
        rc, out, err = sandbox.run_isolated(["python", "-I", "-S", "-c", script], product, _IMAGE, run_id="real-nominal", timeout=15)
        assert rc == 0, err
        assert json.loads(out)["uid"] == 65532 and (product / "result.txt").read_text() == "nominal"
        assert sentinel.poll() is None
        # This adversary is executed ONLY in the disposable Linux container.
        # Broad signalling has its own PID namespace; host path is unmounted.
        hostile = f"""
import os,signal,pathlib,json,subprocess,sys,time
assert not pathlib.Path({str(host_file)!r}).exists()
assert not pathlib.Path('/var/run/docker.sock').exists()
try: assert not pathlib.Path('/root/.claude').exists()
except PermissionError: pass
assert not any(k in os.environ for k in ['ANTHROPIC_API_KEY','OPENAI_API_KEY'])
try: pathlib.Path('/outside-must-fail').write_text('escape')
except OSError: pass
else: raise AssertionError('rootfs writable')
try: os.kill({sentinel.pid}, signal.SIGTERM)
except ProcessLookupError: pass
child = subprocess.Popen([sys.executable,'-I','-S','-c','import time; time.sleep(60)'])
os.kill(-1, signal.SIGTERM)
assert child.wait(timeout=3) == -signal.SIGTERM
print('confined')
"""
        rc, out, err = sandbox.run_isolated(["python", "-I", "-S", "-c", hostile], product, _IMAGE, run_id="real-hostile", timeout=15)
        assert rc == 0 and "confined" in out, err
        assert sentinel.poll() is None and host_file.read_text() == "intact"
    finally:
        runner.close_owned_process(sentinel)
        for pipe in (sentinel.stdin, sentinel.stdout, sentinel.stderr):
            pipe.close()


@pytest.mark.skipif(not _IMAGE, reason="Explicit disposable Docker timeout bench")
def test_real_docker_timeout_cleans_only_its_owned_container(tmp_path):
    with pytest.raises(subprocess.TimeoutExpired):
        sandbox.run_isolated(["python", "-I", "-S", "-c", "import time; time.sleep(60)"],
                             tmp_path, _IMAGE, run_id="real-timeout", timeout=.5)
    result = subprocess.run(["docker", "ps", "--all", "--filter", "label=autospec.run_id=real-timeout", "--format", "{{.ID}}"],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0 and not result.stdout.strip()
