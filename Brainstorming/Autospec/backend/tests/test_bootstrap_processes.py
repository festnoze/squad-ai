"""Real preflight process-tree cleanup, without generated projects or models."""

import asyncio
import ctypes
import os
import socket
import sys
import time
from pathlib import Path

import pytest

from autospec.orchestrator import bootstrap


def _alive(pid):
    if os.name == "nt":
        from ctypes import wintypes

        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x100000, False, pid)
        if not handle:
            return False
        try:
            return api.WaitForSingleObject(handle, 0) == 258
        finally:
            api.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    status = Path(f"/proc/{pid}/stat")
    try:
        return status.read_text().split(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return not sys.platform.startswith("linux")


async def _wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        await asyncio.sleep(0.01)
    assert predicate()


def _child_source(marker, *, server=False):
    setup = "import os,pathlib,time"
    value = "str(os.getpid())"
    if server:
        setup += ",socket; sock=socket.socket(); sock.bind(('127.0.0.1',0)); sock.listen()"
        value = "str(os.getpid())+':'+str(sock.getsockname()[1])"
    return f"{setup}; pathlib.Path({str(marker)!r}).write_text({value}); time.sleep(60)"


def _parent_source(child, marker, *, wait=False):
    return (f"import subprocess,sys,pathlib,time; subprocess.Popen([sys.executable,'-u','-c',{child!r}], "
            f"stdout=sys.stdout,stderr=sys.stderr); p=pathlib.Path({str(marker)!r})\n"
            "while not p.exists(): time.sleep(.01)\n"
            + ("time.sleep(60)" if wait else "print('parent complete',flush=True)"))


async def test_command_parent_exit_reaps_descendant_and_closes_inherited_stdout(tmp_path):
    marker = tmp_path / "owned.pid"
    parent = _parent_source(_child_source(marker), marker)
    started = time.monotonic()
    output = await bootstrap._command([sys.executable, "-u", "-c", parent], tmp_path, dict(os.environ), time.monotonic() + 10, None)
    assert "parent complete" in output
    assert time.monotonic() - started < 5
    await _wait_for(lambda: not _alive(int(marker.read_text())))


async def test_command_timeout_reaps_child_and_grandchild(tmp_path):
    marker = tmp_path / "grandchild.pid"
    child = _parent_source(_child_source(marker), marker, wait=True)
    parent = _parent_source(child, marker, wait=True)
    with pytest.raises(bootstrap.BootstrapFailure, match="délai"):
        await bootstrap._command([sys.executable, "-u", "-c", parent], tmp_path, dict(os.environ), time.monotonic() + 1, None)
    assert marker.exists()
    await _wait_for(lambda: not _alive(int(marker.read_text())))


async def test_cancelling_command_reaps_real_descendant(tmp_path):
    marker = tmp_path / "cancelled-child.pid"
    parent = _parent_source(_child_source(marker), marker, wait=True)
    task = asyncio.create_task(bootstrap._command([sys.executable, "-u", "-c", parent], tmp_path, dict(os.environ), time.monotonic() + 60, None))
    try:
        await _wait_for(marker.exists)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 8)
        await _wait_for(lambda: not _alive(int(marker.read_text())))
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def test_exited_server_launcher_does_not_leave_listener_running(tmp_path):
    marker = tmp_path / "server.pid-port"
    parent = _parent_source(_child_source(marker, server=True), marker)
    process = await bootstrap._spawn([sys.executable, "-u", "-c", parent], tmp_path, dict(os.environ))
    tail = []
    reader = asyncio.create_task(bootstrap._drain(process, tail))
    try:
        await _wait_for(marker.exists)
        await _wait_for(lambda: process.returncode is not None)
        pid, port = map(int, marker.read_text().split(":"))
        assert _alive(pid)
        await bootstrap._close_process(process, reader)
        await _wait_for(lambda: not _alive(pid))
        with socket.socket() as check:
            check.settimeout(0.5)
            assert check.connect_ex(("127.0.0.1", port)) != 0
        assert reader.done()
    finally:
        await bootstrap._close_process(process, reader)


async def test_repeated_cancellation_waits_for_tree_cleanup(tmp_path, monkeypatch):
    marker = tmp_path / "twice.pid"
    parent = _parent_source(_child_source(marker), marker, wait=True)
    entered, release = asyncio.Event(), asyncio.Event()
    original_stop = bootstrap._stop_impl

    async def delayed_stop(process):
        entered.set()
        await release.wait()
        await original_stop(process)

    monkeypatch.setattr(bootstrap, "_stop_impl", delayed_stop)
    task = asyncio.create_task(bootstrap._command([sys.executable, "-u", "-c", parent], tmp_path, dict(os.environ), time.monotonic() + 60, None))
    try:
        await _wait_for(marker.exists)
        task.cancel()
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        await asyncio.sleep(0.03)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 8)
        await _wait_for(lambda: not _alive(int(marker.read_text())))
    finally:
        release.set()
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def test_cancel_during_spawn_keeps_and_reaps_late_process_handle(tmp_path, monkeypatch):
    created, release = asyncio.Event(), asyncio.Event()
    processes = []
    original_spawn = asyncio.create_subprocess_exec

    async def delayed_spawn(*args, **kwargs):
        proc = await original_spawn(*args, **kwargs)
        processes.append(proc)
        created.set()
        await release.wait()
        return proc

    monkeypatch.setattr(bootstrap.asyncio, "create_subprocess_exec", delayed_spawn)
    task = asyncio.create_task(bootstrap._spawn([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path, dict(os.environ)))
    try:
        await asyncio.wait_for(created.wait(), 3)
        task.cancel()
        await asyncio.sleep(0.03)
        assert not task.done()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 8)
        assert processes and all(proc.returncode is not None for proc in processes)
    finally:
        release.set()
        for proc in processes:
            await bootstrap._stop(proc)
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


async def test_cancelled_preflight_cannot_launch_another_command(tmp_path, monkeypatch):
    cancel = asyncio.Event()
    cancel.set()

    async def forbidden_spawn(*args, **kwargs):
        pytest.fail("cancelled preflight must not launch another process")

    monkeypatch.setattr(bootstrap, "_spawn", forbidden_spawn)
    with pytest.raises(asyncio.CancelledError):
        await bootstrap._command([sys.executable, "-c", "print('no')"], tmp_path, dict(os.environ), time.monotonic() + 5, cancel)
