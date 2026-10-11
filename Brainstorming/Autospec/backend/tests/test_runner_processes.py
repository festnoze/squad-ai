"""Real, local subprocess regressions. No harness/model/network is contacted."""

import asyncio
import ctypes
import json
import os
import shutil
import subprocess
import sys
import threading
import time

import pytest

from autospec.agents import runner


def _alive(pid: int) -> bool:
    if os.name == "nt":
        from ctypes import wintypes

        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return api.WaitForSingleObject(handle, 0) == 0x00000102  # WAIT_TIMEOUT
        finally:
            api.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A killed orphan may briefly be a zombie until init/subreaper reaps it.
    from pathlib import Path

    status = Path(f"/proc/{pid}/stat")
    return not status.exists() or status.read_text().split(")", 1)[1].split()[0] != "Z"


def _assert_dead(pid: int) -> None:
    deadline = time.monotonic() + 3
    while _alive(pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _alive(pid), f"local test subprocess {pid} survived cleanup"


async def _wait_for(predicate, timeout=5) -> None:
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert predicate(), "local subprocess failed to reach its synchronization point"


def _python(script):
    return [sys.executable, "-u", "-c", script]


def test_tracked_reads_both_streams_and_complete_unicode_prompt():
    prompt = "l'été — 日本語\n" * 12000
    rc, out, err = runner._run_tracked(
        _python("import sys; data=sys.stdin.buffer.read(); "
                "sys.stdout.buffer.write(data); sys.stderr.buffer.write('diagnostic é'.encode())"),
        prompt, None, 10,
    )
    assert rc == 0
    assert out == prompt
    assert err == "diagnostic é"


@pytest.mark.parametrize("input_size", [0, 2 * 1024 * 1024], ids=["empty", "blocked-large-stdin"])
def test_silent_timeout_also_bounds_stdin_that_is_never_consumed(tmp_path, input_size):
    marker = tmp_path / "silent.pid"
    script = f"import os,time,pathlib; pathlib.Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(60)"
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        runner._run_tracked(_python(script), "x" * input_size, None, 0.5)
    assert time.monotonic() - started < 8
    assert marker.exists()
    _assert_dead(int(marker.read_text()))
    assert not any(t.name == "autospec-agent-io" for t in threading.enumerate())


@pytest.mark.parametrize("fd", [1, 2])
def test_flooded_stream_is_bounded_and_fails_explicitly(monkeypatch, tmp_path, fd):
    monkeypatch.setattr(runner, "_MAX_OUTPUT_BYTES", 4096)
    marker = tmp_path / "flood.pid"
    script = (f"import os,time,pathlib; pathlib.Path({str(marker)!r}).write_text(str(os.getpid())); "
              f"os.write({fd}, b'x'*1000000); time.sleep(60)")
    started = time.monotonic()
    with pytest.raises(runner.AgentError, match="output exceeded 4096 bytes"):
        runner._run_tracked(_python(script), "", None, 10)
    assert time.monotonic() - started < 8
    _assert_dead(int(marker.read_text()))
    assert not any(t.name == "autospec-agent-io" for t in threading.enumerate())


@pytest.mark.parametrize("cli_type", [runner.ClaudeCliRunner, runner.CodexCliRunner])
async def test_cli_task_cancellation_awaits_real_process_tree_cleanup(monkeypatch, tmp_path, cli_type):
    marker = tmp_path / "child.pid"
    parent_marker = tmp_path / "parent.pid"
    child = f"import os,time,pathlib; pathlib.Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(60)"
    parent = (f"import subprocess,sys,time,pathlib,os; "
              f"pathlib.Path({str(parent_marker)!r}).write_text(str(os.getpid())); "
              f"subprocess.Popen([sys.executable,'-u','-c',{child!r}]); time.sleep(60)")
    real_run = runner._run_tracked
    monkeypatch.setattr(runner, "_run_tracked", lambda args, prompt, cwd, timeout:
                        real_run(_python(parent), "", cwd, timeout))
    registry = runner.ProcessRegistry()
    token = runner.active_processes.set(registry)
    task = asyncio.create_task(cli_type().arun("local test only", ""))
    try:
        await _wait_for(marker.exists)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=8)
        _assert_dead(int(marker.read_text()))
        _assert_dead(int(parent_marker.read_text()))
        assert len(registry) == 0
        assert not registry._calls
        assert not any(t.name == "autospec-agent-io" for t in threading.enumerate())
    finally:
        registry.terminate_all()
        task.cancel()
        runner.active_processes.reset(token)


async def test_registry_stop_reaches_worker_queued_before_popen(tmp_path):
    registry = runner.ProcessRegistry()
    token = runner.active_processes.set(registry)
    entered, release = threading.Event(), threading.Event()
    marker = tmp_path / "should-not-launch"

    def delayed_run():
        entered.set()
        assert release.wait(timeout=5)
        return runner._run_tracked(_python(f"from pathlib import Path; Path({str(marker)!r}).touch()"), "", None, 10)

    task = asyncio.create_task(runner._await_tracked(delayed_run))
    try:
        await _wait_for(entered.is_set)
        assert registry.terminate_all() == 0  # no Popen yet, but call is cancelled
        release.set()
        rc, _, err = await asyncio.wait_for(task, timeout=5)
        assert rc != 0 and "cancelled" in err
        assert not marker.exists()
        assert not registry._calls
        # Stops cancel current operations, not future resumed calls.
        rc, out, _ = await runner._await_tracked(
            lambda: runner._run_tracked(_python("print('resumed')"), "", None, 5)
        )
        assert rc == 0 and out.strip() == "resumed"
    finally:
        release.set()
        registry.terminate_all()
        task.cancel()
        runner.active_processes.reset(token)


@pytest.mark.parametrize("cancel_task", [False, True])
async def test_stop_during_popen_cannot_orphan_late_spawn(monkeypatch, cancel_task):
    registry = runner.ProcessRegistry()
    token = runner.active_processes.set(registry)
    created, release = threading.Event(), threading.Event()
    processes = []
    real_popen = runner.subprocess.Popen

    def delayed_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        processes.append(proc)
        created.set()
        assert release.wait(timeout=5)
        return proc

    monkeypatch.setattr(runner.subprocess, "Popen", delayed_popen)
    task = asyncio.create_task(runner._await_tracked(
        lambda: runner._run_tracked(_python("import time; time.sleep(60)"), "", None, 30)
    ))
    try:
        await _wait_for(created.is_set)
        assert registry.terminate_all() == 0  # Popen has not registered yet
        if cancel_task:
            task.cancel()
            await asyncio.sleep(0.03)
            assert not task.done(), "cancellation must await the spawning worker"
            task.cancel()  # repeated shutdown does not abandon cleanup either
        release.set()
        if cancel_task:
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=8)
        else:
            assert (await asyncio.wait_for(task, timeout=8))[0] != 0
        assert len(processes) == 1
        assert processes[0].poll() is not None
        assert len(registry) == 0 and not registry._calls
    finally:
        release.set()
        registry.terminate_all()
        for proc in processes:
            runner._terminate_tree(proc)
        task.cancel()
        runner.active_processes.reset(token)


def test_successful_parent_exit_does_not_leave_child_holding_pipes(tmp_path):
    marker = tmp_path / "orphan.pid"
    child = f"import os,time,pathlib; pathlib.Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(60)"
    parent = (f"import subprocess,sys,time,pathlib; subprocess.Popen([sys.executable,'-u','-c',{child!r}]); "
              f"p=pathlib.Path({str(marker)!r})\n"
              "while not p.exists(): time.sleep(.01)\n"
              "print('complete')")
    started = time.monotonic()
    rc, out, _ = runner._run_tracked(_python(parent), "", None, 10)
    assert rc == 0 and out.strip() == "complete"
    assert time.monotonic() - started < 8
    _assert_dead(int(marker.read_text()))


def test_timeout_kills_child_and_grandchild(tmp_path):
    marker = tmp_path / "grandchild.pid"
    grandchild = f"import os,time,pathlib; pathlib.Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(60)"
    child = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-u','-c',{grandchild!r}]); time.sleep(60)"
    parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-u','-c',{child!r}]); time.sleep(60)"
    with pytest.raises(subprocess.TimeoutExpired):
        runner._run_tracked(_python(parent), "", None, 1)
    assert marker.exists()
    _assert_dead(int(marker.read_text()))


@pytest.mark.skipif(os.name != "nt", reason="Windows job containment")
def test_failed_job_assignment_reaps_suspended_child(monkeypatch):
    processes = []
    real_popen = runner.subprocess.Popen

    def record_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        processes.append(proc)
        return proc

    def fail_assignment(self, proc):
        raise OSError("test denied assignment")

    monkeypatch.setattr(runner.subprocess, "Popen", record_popen)
    monkeypatch.setattr(runner._WindowsJob, "assign_and_resume", fail_assignment)
    with pytest.raises(OSError, match="test denied assignment"):
        runner._run_tracked(_python("import time; time.sleep(60)"), "", None, 5)
    assert len(processes) == 1
    assert processes[0].poll() is not None


@pytest.mark.skipif(os.name != "nt", reason="Windows taskkill fallback")
def test_taskkill_fallback_has_timeout_and_kills_direct_child(monkeypatch):
    class Proc:
        pid = 123456
        returncode = None

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -1

    def fail_taskkill(args, **kwargs):
        assert args == ["taskkill", "/F", "/T", "/PID", "123456"]
        assert 0 < kwargs["timeout"] <= 3
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])

    monkeypatch.setattr(runner.subprocess, "run", fail_taskkill)
    proc = Proc()
    runner._terminate_tree(proc)
    assert proc.poll() == -1


@pytest.mark.skipif(os.name != "nt", reason="Windows shell wrapper rejection")
def test_windows_arbitrary_batch_launcher_is_rejected_before_execution(tmp_path):
    launcher = tmp_path / "local harness with spaces.cmd"
    sentinel = tmp_path / "must-not-execute"
    launcher.write_text(
        f'@echo unsafe > "{sentinel}"\r\n',
        encoding="utf-8",
    )
    with pytest.raises(runner.AgentError, match="Unsafe Windows agent wrapper"):
        runner._run_tracked([str(launcher)], "local smoke", None, 5)
    assert not sentinel.exists()


def _npm_fixture(tmp_path, harness, entry="cli.js", package_name=None):
    npm = tmp_path / "npm directory with spaces & symbols"
    npm.mkdir(exist_ok=True)
    names = {"claude": "@anthropic-ai/claude-code", "codex": "@openai/codex"}
    package = npm / "node_modules" / names[harness]
    package.mkdir(parents=True, exist_ok=True)
    (package / "package.json").write_text(json.dumps({
        "name": package_name or names[harness], "bin": {harness: entry},
    }), encoding="utf-8")
    target = package / entry
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_relative_to(package):
        target.write_text("process.stdout.write(JSON.stringify(process.argv.slice(2)));", encoding="utf-8")
    shim = npm / f"{harness}.cmd"
    sentinel = npm / "wrapper-must-not-execute"
    shim.write_text(f'@echo unsafe > "{sentinel}"\r\n@exit /b 17\r\n', encoding="utf-8")
    return shim, target, sentinel


@pytest.mark.skipif(os.name != "nt" or not shutil.which("node.exe"), reason="Windows + local Node")
@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_npm_shim_is_bypassed_and_special_arguments_are_literal(tmp_path, monkeypatch, harness):
    shim, target, wrapper_sentinel = _npm_fixture(tmp_path, harness)
    injected_sentinel = tmp_path / "injected-must-not-execute"
    monkeypatch.setenv("AUTOSPEC_TEST_LITERAL", "must-not-expand")
    payload = f'quoted " & echo injected > "{injected_sentinel}" & " %AUTOSPEC_TEST_LITERAL% ^ ! | < >'
    arguments = ["--append-system-prompt", payload, "Unicode été 日本語", "", "trailing\\"]
    rc, out, err = runner._run_tracked([str(shim), *arguments], "", None, 5)
    assert rc == 0, err
    assert json.loads(out) == arguments
    assert not wrapper_sentinel.exists()
    assert not injected_sentinel.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows npm launcher resolution")
def test_npm_native_claude_entrypoint_bypasses_batch(tmp_path):
    shim, target, sentinel = _npm_fixture(tmp_path, "claude", "bin/claude.exe")
    assert runner._resolve_agent_command([str(shim), "--version"]) == [str(target.resolve()), "--version"]
    assert not sentinel.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows npm launcher resolution")
@pytest.mark.parametrize("failure", ["wrong-name", "missing-bin", "escape", "batch-target", "invalid-json"])
def test_unrecognized_or_unsafe_npm_metadata_fails_closed(tmp_path, failure):
    shim, target, sentinel = _npm_fixture(tmp_path, "claude")
    manifest = target.parent / "package.json"
    if failure == "wrong-name":
        manifest.write_text(json.dumps({"name": "other-package", "bin": {"claude": "cli.js"}}), encoding="utf-8")
    elif failure == "missing-bin":
        target.unlink()
    elif failure == "escape":
        manifest.write_text(json.dumps({"name": "@anthropic-ai/claude-code", "bin": {"claude": "../../outside.js"}}), encoding="utf-8")
    elif failure == "batch-target":
        target.rename(target.with_suffix(".cmd"))
        manifest.write_text(json.dumps({"name": "@anthropic-ai/claude-code", "bin": {"claude": "cli.cmd"}}), encoding="utf-8")
    else:
        manifest.write_text("not json", encoding="utf-8")
    with pytest.raises(runner.AgentError, match="Cannot safely resolve claude npm launcher"):
        runner._run_tracked([str(shim), '" & echo unsafe'], "", None, 5)
    assert not sentinel.exists()


def test_custom_native_executable_retains_literal_arguments():
    payload = 'literal " & %HOME% ! ^ | < >'
    rc, out, err = runner._run_tracked(
        [sys.executable, "-c", "import sys,json; print(json.dumps(sys.argv[1:]))", payload], "", None, 5,
    )
    assert rc == 0, err
    assert json.loads(out) == [payload]


def test_failed_spawn_releases_call_registration(tmp_path):
    registry = runner.ProcessRegistry()
    token = runner.active_processes.set(registry)
    try:
        with pytest.raises(OSError):
            runner._run_tracked([str(tmp_path / "no-such-local-executable")], "", None, 3)
        assert len(registry) == 0 and not registry._calls
    finally:
        runner.active_processes.reset(token)


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_timeout_cannot_launch_unbounded_agent(monkeypatch, timeout):
    def must_not_launch(*args, **kwargs):
        pytest.fail("an invalid timeout must fail before spawning")

    monkeypatch.setattr(runner.subprocess, "Popen", must_not_launch)
    with pytest.raises(runner.AgentError, match="timeout must be finite"):
        runner._run_tracked(_python("print('no')"), "", None, timeout)


def test_agent_start_and_cancel_do_not_wait_for_saturated_default_executor(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    marker = tmp_path / "independent.pid"
    script = f"import os,time,pathlib; pathlib.Path({str(marker)!r}).write_text(str(os.getpid())); time.sleep(60)"
    release, entered = threading.Event(), threading.Event()

    def occupy_default_executor():
        entered.set()
        release.wait(timeout=10)

    async def exercise():
        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=1) as pool:
            loop.set_default_executor(pool)
            blocked = pool.submit(occupy_default_executor)
            task = None
            try:
                await _wait_for(entered.is_set)
                task = asyncio.create_task(runner._await_tracked(
                    lambda: runner._run_tracked(_python(script), "", None, 30)
                ))
                await _wait_for(marker.exists, timeout=2)
                assert not blocked.done()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=5)
                _assert_dead(int(marker.read_text()))
                assert not blocked.done(), "cleanup must not depend on shared executor capacity"
            finally:
                release.set()
                if task is not None and not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

    asyncio.run(exercise())
