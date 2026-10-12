"""Trusted supervisor persistence tests, never generated product execution."""
from __future__ import annotations

import errno
import json
import os
import threading
from pathlib import Path

import pytest

from autospec.orchestrator import dependencies


def windows_error(code: int) -> OSError:
    error = PermissionError(errno.EACCES, "controlled Windows replacement refusal")
    error.winerror = code
    return error


def guard_target(monkeypatch, target: Path):
    """Forbid modifying permissions or deleting the committed destination."""
    original_unlink = os.unlink
    deleted = []

    def unlink(path, *args, **kwargs):
        assert Path(path) != target, "the committed target must never be deleted"
        deleted.append(Path(path))
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(dependencies.os, "unlink", unlink)
    monkeypatch.setattr(dependencies.os, "chmod", lambda *a, **k: pytest.fail("chmod weakens persistence permissions"))
    return deleted


@pytest.mark.parametrize("code", [5, 32, 33])
@pytest.mark.parametrize("failures", [1, 4])
def test_transient_windows_refusal_retries_same_fsynced_temp_atomically(tmp_path, monkeypatch, code, failures):
    target = tmp_path / "project.json"
    old = b'{"state":"committed"}\r\n'
    target.write_bytes(old)
    deleted = guard_target(monkeypatch, target)
    real_replace = os.replace
    real_fsync = os.fsync
    replacements, sleeps, fsyncs = [], [], []

    def fsync(fd):
        fsyncs.append(fd)
        return real_fsync(fd)

    def replace(source, destination):
        replacements.append((source, destination))
        assert destination == target
        assert target.read_bytes() == old
        assert json.loads(Path(source).read_text(encoding="utf-8")) == {"state": "next"}
        assert len(fsyncs) == 1, "one complete temp is durable before any swap attempt"
        if len(replacements) <= failures:
            raise windows_error(code)
        real_replace(source, destination)

    monkeypatch.setattr(dependencies.os, "fsync", fsync)
    monkeypatch.setattr(dependencies.os, "replace", replace)
    monkeypatch.setattr(dependencies.time, "sleep", sleeps.append)
    dependencies.atomic_json(target, {"state": "next"})
    assert json.loads(target.read_text()) == {"state": "next"}
    assert len(replacements) == failures + 1
    assert len({source for source, _ in replacements}) == 1
    assert Path(replacements[0][0]).parent == target.parent
    assert sleeps == [0.05 * index for index in range(1, failures + 1)]
    assert sum(sleeps) <= 0.5
    assert deleted == []  # replace consumes the temp; no unlink of any target
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("code", [5, 32, 33])
def test_permanent_windows_refusal_is_bounded_preserves_old_json_and_cleans_temp(tmp_path, monkeypatch, code):
    target = tmp_path / "project.json"
    old = b'{"state":"committed"}\r\n'
    target.write_bytes(old)
    deleted = guard_target(monkeypatch, target)
    calls, sleeps = [], []
    error = windows_error(code)

    def replace(source, destination):
        calls.append(source)
        assert destination == target and target.read_bytes() == old
        raise error

    monkeypatch.setattr(dependencies.os, "replace", replace)
    monkeypatch.setattr(dependencies.time, "sleep", sleeps.append)
    with pytest.raises(PermissionError) as caught:
        dependencies.atomic_json(target, {"state": "never committed"})
    assert caught.value is error
    assert len(calls) == 5 and len(set(calls)) == 1
    assert sleeps == [0.05, 0.1, 0.15000000000000002, 0.2]
    assert sum(sleeps) == pytest.approx(0.5)
    assert target.read_bytes() == old
    assert deleted == [Path(calls[0])]
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("error", [
    PermissionError(errno.EACCES, "POSIX or unclassified refusal"),
    windows_error(2),
    windows_error(112),
    OSError(errno.EXDEV, "cross-volume replacement forbidden"),
])
def test_unclassified_errors_fail_immediately_without_nonatomic_fallback(tmp_path, monkeypatch, error):
    target = tmp_path / "project.json"
    old = b'{"state":"committed"}\n'
    target.write_bytes(old)
    deleted = guard_target(monkeypatch, target)
    calls = []

    def replace(source, destination):
        calls.append(source)
        raise error

    monkeypatch.setattr(dependencies.os, "replace", replace)
    monkeypatch.setattr(dependencies.time, "sleep", lambda _: pytest.fail("unclassified errors cannot be retried"))
    with pytest.raises(OSError) as caught:
        dependencies.atomic_json(target, {"state": "not committed"})
    assert caught.value is error
    assert len(calls) == 1 and deleted == [Path(calls[0])]
    assert target.read_bytes() == old
    assert list(tmp_path.iterdir()) == [target]


def test_json_serialization_failure_never_dispatches_replace_and_cleans_temp(tmp_path, monkeypatch):
    target = tmp_path / "project.json"
    old = b'{"state":"committed"}\n'
    target.write_bytes(old)
    deleted = guard_target(monkeypatch, target)
    monkeypatch.setattr(dependencies.os, "replace", lambda *a: pytest.fail("invalid JSON reached replacement"))
    with pytest.raises(TypeError):
        dependencies.atomic_json(target, {"bad": object()})
    assert target.read_bytes() == old
    assert len(deleted) == 1 and list(tmp_path.iterdir()) == [target]


def test_fsync_failure_is_not_retried_and_never_replaces_old_json(tmp_path, monkeypatch):
    target = tmp_path / "project.json"
    old = b'{"state":"committed"}\n'
    target.write_bytes(old)
    deleted = guard_target(monkeypatch, target)
    error = windows_error(5)

    def fail_fsync(fd):
        raise error

    monkeypatch.setattr(dependencies.os, "fsync", fail_fsync)
    monkeypatch.setattr(dependencies.os, "replace", lambda *a: pytest.fail("non-durable temp reached replacement"))
    monkeypatch.setattr(dependencies.time, "sleep", lambda _: pytest.fail("only replacement may be retried"))
    with pytest.raises(OSError) as caught:
        dependencies.atomic_json(target, {"state": "not durable"})
    assert caught.value is error
    assert target.read_bytes() == old
    assert len(deleted) == 1 and list(tmp_path.iterdir()) == [target]


def test_permanent_first_write_failure_never_leaves_partial_json(tmp_path, monkeypatch):
    target = tmp_path / "new" / "project.json"
    error = windows_error(32)
    calls = []

    def replace(source, destination):
        calls.append(source)
        assert destination == target and not target.exists()
        raise error

    monkeypatch.setattr(dependencies.os, "replace", replace)
    monkeypatch.setattr(dependencies.time, "sleep", lambda _: None)
    with pytest.raises(OSError) as caught:
        dependencies.atomic_json(target, {"state": "never committed"})
    assert caught.value is error and len(calls) == 5
    assert not target.exists() and list(target.parent.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="real Windows kernel sharing semantics")
@pytest.mark.parametrize("release_during_retry", [True, False])
def test_real_windows_handle_sharing_refusal_release_or_fail_closed(tmp_path, release_during_retry):
    import ctypes
    from ctypes import wintypes

    target = tmp_path / "project.json"
    old = b'{"state":"committed"}\n'
    target.write_bytes(old)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # A genuine read handle allows readers/writers but denies DELETE sharing,
    # as an indexer or concurrent reader may do. No ACL or host config changes.
    handle = kernel.CreateFileW(str(target), 0x80000000, 0x3, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
    thread = None
    closed = threading.Event()

    def close():
        assert kernel.CloseHandle(handle)
        closed.set()

    try:
        try:
            os.replace(target, tmp_path / "must-not-be-replaced")
        except OSError as exc:
            assert exc.winerror in {5, 32, 33}
        else:
            pytest.fail("the kernel handle did not deny replacement")
        if release_during_retry:
            def delayed_close():
                dependencies.time.sleep(0.12)
                close()
            thread = threading.Thread(target=delayed_close)
            thread.start()
            dependencies.atomic_json(target, {"state": "next"})
            assert json.loads(target.read_text()) == {"state": "next"}
        else:
            with pytest.raises(OSError) as caught:
                dependencies.atomic_json(target, {"state": "next"})
            assert caught.value.winerror in {5, 32, 33}
            assert target.read_bytes() == old
        assert list(tmp_path.iterdir()) == [target]
    finally:
        if thread is not None:
            thread.join(timeout=1)
        if not closed.is_set():
            close()
