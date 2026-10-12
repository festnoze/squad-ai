"""REM-03: owned factory death inside effective operations, not stage labels."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from autospec.agents.runner import close_owned_process, spawn_owned_process
from autospec.orchestrator import sandbox

BACKEND = Path(__file__).resolve().parents[1]
WORKER = Path(__file__).with_name("rem03_operation_worker.py")


def read(path):
    return json.loads(path.read_bytes())


def wait_for(path, worker, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return read(path)
        if worker.poll() is not None:
            output, errors = worker.communicate(timeout=5)
            raise AssertionError(f"Effective operation never reached its barrier: {output!r} {errors!r}")
        time.sleep(.025)
    raise AssertionError(f"Barrier was not reached: {path.name}")


def worker(root, operation, action):
    # Only constant trusted factory code is launched on the host. -I prevents
    # ambient PYTHONPATH/user site or a product workdir from shadowing imports.
    return spawn_owned_process([sys.executable, "-I", str(WORKER), str(BACKEND), str(root), operation, action],
        cwd=str(BACKEND), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class OwnedJobMember:
    """Keep an OS handle to the actual interpreter, not just a reusable PID.

    A Windows venv python.exe may be a redirector with a descendant interpreter.
    Membership must be proven against the retained launcher's exact owned Job.
    """
    def __init__(self, process, pid):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        self.api.IsProcessInJob.restype = wintypes.BOOL
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.WaitForSingleObject.restype = wintypes.DWORD
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = self.api.OpenProcess(0x00100000 | 0x1000, False, pid)
        assert self.handle
        member = wintypes.BOOL()
        assert self.api.IsProcessInJob(self.handle, process._autospec_job.handle, ctypes.byref(member))
        assert member.value, "Reported interpreter is not in this exact owned Job"
        assert self.api.WaitForSingleObject(self.handle, 0) == 0x102

    def assert_exited(self):
        assert self.api.WaitForSingleObject(self.handle, 5000) == 0

    def close(self):
        self.api.CloseHandle(self.handle)


def collect_receipt(root, operation, extra):
    value = {"operation": operation, "platform": sys.platform, "python": sys.version,
        "trusted_worker_sha256": hashlib.sha256(WORKER.read_bytes()).hexdigest(),
        "source_sha256": {name: hashlib.sha256((BACKEND / name).read_bytes()).hexdigest() for name in (
            "autospec/orchestrator/pipeline.py", "autospec/api/server.py", "autospec/agents/runner.py",
            "autospec/orchestrator/sandbox.py", "autospec/orchestrator/isolated_validation.py")},
        "recovered": read(root / "recovered.json"), "resumed": read(root / "resumed.json"), **extra}
    evidence = os.environ.get("AUTOSPEC_REM03_EVIDENCE")
    if evidence:
        target = Path(evidence)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{operation}-receipt.json").write_text(json.dumps(value, sort_keys=True, indent=2), encoding="utf-8")
    return value


def recover(root, operation):
    resumed = worker(root, operation, "recover")
    try:
        output, errors = resumed.communicate(timeout=180 if operation == "smoke" else 45)
        assert resumed.returncode == 0, (output, errors)
        assert not (root / "forbidden-call.json").exists()
        return {"restart_exit_code": resumed.returncode, "restart_stdout": output.decode("utf-8", "replace"),
                "restart_stderr": errors.decode("utf-8", "replace")}
    finally:
        close_owned_process(resumed)


@pytest.mark.parametrize("operation", ["provider", "merge"])
@pytest.mark.skipif(os.name != "nt", reason="native exact Windows Job membership/crash proof")
def test_actual_cli_or_git_transaction_death_and_explicit_recovery(tmp_path, operation):
    root = tmp_path / operation
    root.mkdir()
    active = worker(root, operation, "interrupt")
    members = []
    try:
        barrier = wait_for(root / "barrier.json", active)
        assert barrier["operation"] == operation
        members.append(OwnedJobMember(active, barrier["factory_pid"]))
        pre = read(root / "workspace/operation/autospec-state.json")
        assert pre["generation_checkpoint"]["status"] == "active"
        assert pre["usage"]["agent_calls"] == 0 and not pre["delivery_ready"]
        if operation == "provider":
            assert barrier["cli_pid"] != active.pid
            members.append(OwnedJobMember(active, barrier["cli_pid"]))
            assert barrier["prompt_sha256"] == hashlib.sha256(b"REM03_LOCAL_ONLY_PROMPT").hexdigest()
            activity = next(iter(pre["agent_activity"].values()))
            assert activity["phase"] == "provider" and activity["active_provider_calls"] == 1
        else:
            assert len(barrier["parents"]) == 2 and barrier["lock_owner"] == "T1"
            assert pre["stories"][0]["tasks"][0]["current_stage"] == "merging"
        close_owned_process(active)
        assert active.poll() is not None
        for member in members:
            member.assert_exited()
        output, errors = active.communicate(timeout=5)
        assert not (root / "completed.json").exists()
        restart = recover(root, operation)
        post = read(root / "recovered.json")["state"]
        assert post["generation_checkpoint"]["run_id"] == pre["generation_checkpoint"]["run_id"]
        assert post["stories"][0]["tasks"][0]["status"] == "todo"
        assert post["stories"][0]["tasks"][0]["current_stage"] == "queued"
        assert post["stories"][0]["tasks"][0]["attempts"] == 1
        if operation == "merge":
            assert read(root / "resumed.json")["merge_commit"] == barrier["merge_commit"]
            assert (root / "workspace/operation/payload.txt").read_bytes() == b"real branch contribution\n"
        collect_receipt(root, operation, {"barrier": barrier, "pre_crash_state": pre,
            "exact_owned_job_membership_verified": True, "member_handles_signaled_after_crash": True,
            "factory_exit_code": active.returncode, "factory_stdout": output.decode("utf-8", "replace"),
            "factory_stderr": errors.decode("utf-8", "replace"), **restart})
    finally:
        close_owned_process(active)
        for member in members:
            member.close()


def test_local_cli_positive_receipt_is_accounted_normally(tmp_path):
    (tmp_path / "release").touch()
    active = worker(tmp_path, "provider", "nominal")
    try:
        output, errors = active.communicate(timeout=45)
        assert active.returncode == 0, (output, errors)
        completed = read(tmp_path / "completed.json")
        assert completed["usage"]["agent_calls"] == 1
        assert completed["usage"]["unreported_calls"] == 0
        assert completed["usage"]["cost_usd"] == 0
    finally:
        close_owned_process(active)


@pytest.mark.skipif(os.environ.get("AUTOSPEC_REM03_DOCKER") != "1", reason="explicit real Docker NETNONE operation interruption opt-in")
def test_actual_smoke_container_death_and_same_source_explicit_recovery(tmp_path):
    from autospec.orchestrator.isolated_validation import IsolatedValidator
    from autospec.orchestrator.environments import source_hash

    root = tmp_path / "smoke"
    product = root / "workspace/operation"
    product.mkdir(parents=True)
    (product / "pyproject.toml").write_bytes(b'[project]\nname="rem03-smoke-fixture"\nversion="1.0.0"\nrequires-python=">=3.12"\ndependencies=[]\n')
    (product / "main.py").write_bytes(b'import json,os,time\nprint(json.dumps({"marker":"REM03_REAL_NETNONE_SMOKE","uid":os.getuid(),"pid":os.getpid()}),flush=True)\ntime.sleep(15)\nprint("REM03_REAL_NETNONE_COMPLETED",flush=True)\n')
    # Manifest-only resolver is trusted; actual source is not run during lock preparation.
    IsolatedValidator(root / "preparation").manager.ensure_lock(product, "python")
    before = source_hash(product)
    active = worker(root, "smoke", "interrupt")
    dispatch = None
    identifier = None
    member = None
    try:
        dispatch = wait_for(root / "docker-dispatch.json", active, 180)
        if os.name == "nt":
            member = OwnedJobMember(active, dispatch["factory_pid"])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            identifier = sandbox._container_identity("docker", dispatch["name"], dispatch["owner"])
            if identifier:
                logs = sandbox._docker_call(["docker", "logs", identifier], capture_output=True, text=True, timeout=5)
                if "REM03_REAL_NETNONE_SMOKE" in logs.stdout:
                    break
            assert active.poll() is None
            time.sleep(.05)
        else:
            raise AssertionError("No marker from the effective NETNONE product execution")
        observed = sandbox._docker_call(["docker", "inspect", identifier], capture_output=True, text=True, timeout=10)
        container = json.loads(observed.stdout)[0]
        assert observed.returncode == 0 and container["State"]["Running"]
        assert container["HostConfig"]["NetworkMode"] == "none"
        assert container["Config"]["User"] == "65532:65532"
        assert container["HostConfig"]["ReadonlyRootfs"] is True
        assert container["HostConfig"]["CapDrop"] == ["ALL"]
        assert container["Config"]["Labels"]["autospec.run_id"] == dispatch["owner"]
        marker = next(json.loads(row) for row in logs.stdout.splitlines() if "REM03_REAL_NETNONE_SMOKE" in row)
        assert marker["uid"] == 65532
        pre = read(product / "autospec-state.json")
        assert pre["phase"] == "govern" and pre["generation_checkpoint"]["status"] == "active"
        close_owned_process(active)
        if member:
            member.assert_exited()
        output, errors = active.communicate(timeout=5)
        assert active.returncode != 0 and not (root / "completed.json").exists()
        # The daemon container can outlive the killed factory. Cleanup is only
        # our recorded immutable CID + UUID ownership; never prune/name sweeping.
        sandbox._cleanup_container("docker", identifier, dispatch["owner"])
        assert sandbox._container_identity("docker", identifier, dispatch["owner"]) is None
        restart = recover(root, "smoke")
        assert source_hash(product) == before
        assert read(root / "recovered.json")["state"]["stories"][0]["tasks"][0]["status"] == "done"
        assert read(root / "resumed.json")["delivery_ready"] is False
        collect_receipt(root, "smoke", {"dispatch": dispatch, "container": container,
            "factory_job_membership_and_signaled_handle": bool(member),
            "product_marker": marker, "container_stdout_before_crash": logs.stdout,
            "source_before_after_sha256": before, "owned_container_absent_after_cleanup": True,
            "factory_exit_code": active.returncode, "factory_stdout": output.decode("utf-8", "replace"),
            "factory_stderr": errors.decode("utf-8", "replace"), **restart})
    finally:
        close_owned_process(active)
        if member:
            member.close()
        if dispatch:
            sandbox._cleanup_container("docker", identifier or dispatch["name"], dispatch["owner"])
