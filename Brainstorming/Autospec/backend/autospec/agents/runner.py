"""Agent execution backends.

ClaudeCliRunner drives the locally installed Claude Code CLI in headless mode
(`claude -p --output-format json`), which is how the BMAD personas get executed.
Tests use FakeRunner instead.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import tempfile
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from ..config import settings
from .file_broker import FILE_PROTOCOL, FileBroker, IsolationViolation, context_for, active_dependency_handler, active_claim_handler


class ProcessRegistry:
    """Thread-safe set of live agent child processes, so an in-flight CLI call can
    be interrupted (project switch / API shutdown). Populated from the worker
    thread that spawns the process; killed from the event-loop thread."""

    def __init__(self, run_id: str | None = None) -> None:
        self.run_id = run_id or uuid.uuid4().hex
        self._procs: set[subprocess.Popen] = set()
        self._identities: dict[subprocess.Popen, str] = {}
        self._calls: set[threading.Event] = set()
        self._lock = threading.Lock()

    def register_call(self, cancel: threading.Event) -> None:
        # Register BEFORE scheduling/spawning: a stop must also reach calls whose
        # worker has not started or whose Popen has not returned yet.
        with self._lock:
            self._calls.add(cancel)

    def discard_call(self, cancel: threading.Event) -> None:
        with self._lock:
            self._calls.discard(cancel)

    def add(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._identities[proc] = _process_identity(proc)
            self._procs.add(proc)

    def discard(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.discard(proc)
            self._identities.pop(proc, None)

    def resources(self) -> list[dict]:
        with self._lock:
            return [{"version": 1, "kind": "process", "identifier": str(p.pid),
                     "creation_identity": identity, "owner": self.run_id,
                     "descendants": ("windows_job" if getattr(p, "_autospec_job", None) is not None
                                     else "retained_handle" if os.name == "nt" else "process_group")}
                    for p, identity in self._identities.items()]

    def terminate(self, pid: int, creation_identity: str) -> bool:
        """No PID-only stop: a stale/reused PID is not owned by this call."""
        with self._lock:
            selected = next((p for p, identity in self._identities.items()
                             if p.pid == pid and identity == creation_identity), None)
        if selected is None or _process_identity(selected) != creation_identity:
            return False
        close_owned_process(selected)
        return True

    def terminate_all(self) -> int:
        """Hard-kill every still-running tracked process (whole tree). Returns the
        number killed. Safe to call repeatedly and from any thread."""
        with self._lock:
            for cancel in self._calls:
                cancel.set()
            procs = [(p, self._identities[p]) for p in self._procs
                     if p.poll() is None or getattr(p, "_autospec_job", None) is not None]
        for proc, identity in procs:
            if _process_identity(proc) == identity:
                close_owned_process(proc)
        return len(procs)

    def __len__(self) -> int:
        with self._lock:
            return len(self._procs)


def _process_identity(proc: subprocess.Popen) -> str:
    """Creation identity from the retained handle, never an opened PID."""
    if os.name == "nt" and hasattr(proc, "_handle"):
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        api.GetProcessTimes.restype = wintypes.BOOL
        values = [wintypes.FILETIME() for _ in range(4)]
        if not api.GetProcessTimes(int(proc._handle), *(ctypes.byref(v) for v in values)):
            raise ctypes.WinError(ctypes.get_last_error())
        return f"windows:{values[0].dwHighDateTime:08x}{values[0].dwLowDateTime:08x}"
    identity = getattr(proc, "_autospec_creation_identity", None)
    if identity is None:
        identity = f"handle:{uuid.uuid4().hex}"
        proc._autospec_creation_identity = identity
    return identity


# The registry an agent call should register its child process into, set by the
# pipeline per call (via _UsageTracker). The async wrapper explicitly copies the
# context into its worker, so event-loop values remain visible where the process
# is spawned. None = no project-wide tracking (tests / FakeRunner).
active_processes: contextvars.ContextVar[ProcessRegistry | None] = contextvars.ContextVar(
    "autospec_active_processes", default=None
)

# Per-agent-call override set by Pipeline so product profiles can enable skills
# for one project without mutating the process-wide settings singleton.
active_skills_enabled: contextvars.ContextVar[bool | None] = contextvars.ContextVar(
    "autospec_active_skills_enabled", default=None
)

# Estimated remaining project budget, never a billing-account limit. The
# orchestrator serializes budgeted calls so parallel agents cannot each spend it.
active_budget_usd: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "autospec_active_budget_usd", default=None
)

# Logical agent sessions include file mediation and dependency waits. Only a
# model turn occupies the provider; the supervisor owns this observer.
active_provider_observer: contextvars.ContextVar[Callable[[bool], Awaitable[None]] | None] = contextvars.ContextVar(
    "autospec_provider_observer", default=None
)


async def observe_provider(active: bool) -> None:
    observer = active_provider_observer.get()
    if observer is not None:
        await observer(active)


_active_call_cancel: contextvars.ContextVar[threading.Event | None] = contextvars.ContextVar(
    "autospec_agent_call_cancel", default=None
)
_agent_environment: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "autospec_agent_environment", default=None,
)
_MAX_OUTPUT_BYTES = 16 * 1024 * 1024  # per stream; never silently truncate JSON
_PROCESS_CLEANUP_TIMEOUT = 3.0


def _resolve_agent_command(args: list[str]) -> list[str]:
    """Bypass npm batch/PowerShell shims: Windows can parse them as shell code.

    Never interpret wrapper source. Only known harness names with matching npm
    metadata may resolve to their package's native binary or Node entrypoint.
    Custom native executables remain supported; arbitrary shell wrappers must
    be replaced by an executable path in CLAUDE_CMD/CODEX_CMD.
    """
    if os.name != "nt" or not args:
        return args
    resolved = shutil.which(args[0]) or args[0]
    shim = Path(resolved)
    if shim.suffix.lower() not in {".cmd", ".bat", ".ps1"}:
        return [resolved, *args[1:]]
    packages = {"claude": "@anthropic-ai/claude-code", "codex": "@openai/codex"}
    harness = shim.stem.lower()
    package_name = packages.get(harness)
    if package_name is None:
        raise AgentError(
            "Unsafe Windows agent wrapper: configure CLAUDE_CMD/CODEX_CMD with a native "
            "executable, or install the standard Claude/Codex npm package"
        )
    package_dir = (shim.parent / "node_modules" / package_name).resolve()
    manifest = package_dir / "package.json"
    try:
        if not shim.is_file():
            raise ValueError("npm launcher was not found")
        with manifest.open(encoding="utf-8") as handle:
            raw = handle.read(131073)
        if len(raw) > 131072:
            raise ValueError("npm manifest too large")
        metadata = json.loads(raw)
        if not isinstance(metadata, dict) or metadata.get("name") != package_name:
            raise ValueError("npm package name does not match the harness")
        bins = metadata.get("bin")
        entry = bins.get(harness) if isinstance(bins, dict) else bins
        if not isinstance(entry, str) or not entry:
            raise ValueError("npm package has no harness entrypoint")
        target = (package_dir / entry).resolve()
        if not target.is_relative_to(package_dir) or not target.is_file():
            raise ValueError("npm entrypoint is missing or outside its package")
        suffix = target.suffix.lower()
        if suffix in {".exe", ".com"}:
            return [str(target), *args[1:]]
        if suffix not in {".js", ".cjs", ".mjs"}:
            raise ValueError("npm entrypoint is not a native executable or Node script")
        adjacent_node = shim.parent / "node.exe"
        node = str(adjacent_node) if adjacent_node.is_file() else shutil.which("node.exe")
        if not node:
            raise ValueError("node.exe was not found")
        return [node, str(target), *args[1:]]
    except (OSError, ValueError) as exc:
        raise AgentError(
            f"Cannot safely resolve {harness} npm launcher ({exc}); install its standard "
            "npm package or configure CLAUDE_CMD/CODEX_CMD with a native executable"
        ) from exc


class _WindowsJob:
    """An owned, kill-on-close Windows job, including grandchildren.

    Assign the child while suspended, then resume its primary thread. Unlike
    taskkill's snapshot, the job still owns descendants after the CLI exits and
    cannot miss a child spawned between creation and registration. Fail closed
    if containment cannot be established; no third-party Windows dependency.
    """

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t),
                ("max_ws", ctypes.c_size_t), ("active", wintypes.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                ("scheduling", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("basic", BasicLimits), ("io", ctypes.c_ulonglong * 6),
                ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t),
            ]

        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
            "CreateToolhelp32Snapshot": ([wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
            "Thread32First": ([wintypes.HANDLE, ctypes.c_void_p], wintypes.BOOL),
            "Thread32Next": ([wintypes.HANDLE, ctypes.c_void_p], wintypes.BOOL),
            "OpenThread": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "ResumeThread": ([wintypes.HANDLE], wintypes.DWORD),
        }
        for name, (argtypes, restype) in signatures.items():
            function = getattr(self.api, name)
            function.argtypes, function.restype = argtypes, restype
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign_and_resume(self, proc: subprocess.Popen) -> None:
        import ctypes
        from ctypes import wintypes

        # Popen retains the original process handle; opening a PID here would
        # unnecessarily reintroduce an identity/reuse race.
        if not self.api.AssignProcessToJobObject(self.handle, int(proc._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

        class ThreadEntry(ctypes.Structure):
            _fields_ = [
                ("size", wintypes.DWORD), ("usage", wintypes.DWORD),
                ("tid", wintypes.DWORD), ("pid", wintypes.DWORD),
                ("priority", wintypes.LONG), ("delta", wintypes.LONG),
                ("flags", wintypes.DWORD),
            ]

        snapshot = self.api.CreateToolhelp32Snapshot(0x00000004, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            entry = ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            found = self.api.Thread32First(snapshot, ctypes.byref(entry))
            while found:
                if entry.pid == proc.pid:
                    thread = self.api.OpenThread(0x0002, False, entry.tid)  # THREAD_SUSPEND_RESUME
                    if not thread:
                        raise ctypes.WinError(ctypes.get_last_error())
                    try:
                        if self.api.ResumeThread(thread) == 0xFFFFFFFF:
                            raise ctypes.WinError(ctypes.get_last_error())
                    finally:
                        self.api.CloseHandle(thread)
                    return
                found = self.api.Thread32Next(snapshot, ctypes.byref(entry))
            raise OSError("Cannot find the suspended agent's primary thread")
        finally:
            self.api.CloseHandle(snapshot)

    def terminate(self) -> None:
        import ctypes

        if self.handle and not self.api.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def _terminate_tree(proc: subprocess.Popen, *, grace_period: float = 0) -> None:
    """Bounded, idempotent tree cleanup, even after the direct child exits."""
    lock = getattr(proc, "_autospec_cleanup_lock", None) or threading.Lock()
    with lock:
        try:
            if proc.poll() is None and grace_period > 0:
                # EOF is the cooperative shutdown mechanism for headless CLI
                # processes. A server may expose its own graceful callback;
                # never signal arbitrary processes by executable name/PID.
                if getattr(proc, "stdin", None) is not None:
                    try:
                        proc.stdin.close()
                    except (OSError, ValueError):
                        pass
                try:
                    proc.wait(timeout=min(grace_period, _PROCESS_CLEANUP_TIMEOUT))
                except subprocess.TimeoutExpired:
                    pass
            job = getattr(proc, "_autospec_job", None)
            if job is not None:
                job.terminate()
            elif os.name == "nt":
                if proc.poll() is None:
                    # Assignment failure: only the suspended direct child is
                    # safe to stop via its retained handle. No taskkill fallback.
                    proc.kill()
            else:
                import signal

                # Tracked POSIX children start new sessions. getpgid(pid) no
                # longer works after parent exit, but its owned group may live.
                os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, ValueError, subprocess.SubprocessError):
            try:
                proc.kill()
            except OSError:
                pass
        # Assignment itself may have failed, leaving a suspended child outside
        # the job. Always clean the direct child as well as the container/group.
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass


def spawn_owned_process(args: list[str], *, cancel: threading.Event | None = None, **kwargs) -> subprocess.Popen:
    """Spawn trusted supervisor commands in an owned Job/session.

    This is lifecycle ownership, NOT a sandbox for generated code. Generated
    code must additionally use orchestrator.sandbox or fail closed.
    """
    job = None
    proc = None
    try:
        if os.name == "nt":
            flags = kwargs.get("creationflags", 0)
            if flags & 0x01000000:  # CREATE_BREAKAWAY_FROM_JOB
                raise AgentError("Owned processes cannot break away from their Windows job")
            job = _WindowsJob()
            kwargs["creationflags"] = flags | 0x00000004  # CREATE_SUSPENDED
        else:
            kwargs["start_new_session"] = True
        proc = subprocess.Popen(_resolve_agent_command(args), **kwargs)
        proc._autospec_cleanup_lock = threading.Lock()
        proc._autospec_job = job
        proc._autospec_creation_identity = _process_identity(proc)
        if cancel is not None and cancel.is_set():
            _terminate_tree(proc)
            return proc
        if job is not None:
            job.assign_and_resume(proc)
        return proc
    except BaseException:
        if proc is not None:
            _terminate_tree(proc)
            try:
                proc.wait(timeout=_PROCESS_CLEANUP_TIMEOUT)
            except (subprocess.TimeoutExpired, OSError):
                pass
        if job is not None:
            job.close()
        raise


def close_owned_process(proc: subprocess.Popen, *, grace_period: float = 0.15) -> None:
    """Idempotent bounded cleanup of this exact handle and all owned descendants."""
    _terminate_tree(proc, grace_period=grace_period)
    try:
        proc.wait(timeout=_PROCESS_CLEANUP_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):
        pass
    with proc._autospec_cleanup_lock:
        job = proc._autospec_job
        proc._autospec_job = None
        if job is not None:
            job.close()


def _run_tracked(
    args: list[str], input_text: str, cwd: str | None, timeout: float
) -> tuple[int, str, str]:
    """Run a child process to completion, tracking it in the context's
    ProcessRegistry so it can be interrupted, and tree-killing it on timeout.
    Returns (returncode, stdout, stderr). Runs on a worker thread (blocking)."""
    if not math.isfinite(timeout):
        raise AgentError("Agent timeout must be finite")
    registry = active_processes.get()
    cancel = _active_call_cancel.get()
    own_call = cancel is None
    cancel = cancel if cancel is not None else threading.Event()
    if registry is not None and own_call:
        registry.register_call(cancel)
    proc = None
    job = None
    io_threads: list[threading.Thread] = []
    output = [bytearray(), bytearray()]
    overflow = threading.Event()
    deadline = time.monotonic() + timeout

    def read_output(pipe, destination: bytearray) -> None:
        try:
            while chunk := pipe.read(65536):
                remaining = _MAX_OUTPUT_BYTES - len(destination)
                destination.extend(chunk[:max(0, remaining)])
                if len(chunk) > remaining:
                    overflow.set()
                    return
        except (OSError, ValueError):
            pass  # pipe closed by cancellation/timeout cleanup
        finally:
            pipe.close()

    def write_input(pipe) -> None:
        try:
            data = memoryview(input_text.encode("utf-8"))
            while data and not cancel.is_set():
                count = pipe.write(data[:65536])
                if not count:
                    break
                data = data[count:]
        except (BrokenPipeError, OSError, ValueError):
            pass
        finally:
            pipe.close()

    try:
        if cancel.is_set():
            return -1, "", "Agent execution cancelled before launch"
        if timeout <= 0:
            raise subprocess.TimeoutExpired(args, timeout)
        kwargs: dict = dict(
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=cwd, bufsize=0,
        )
        if _agent_environment.get() is not None:
            kwargs["env"] = _agent_environment.get()
        proc = spawn_owned_process(args, cancel=cancel, **kwargs)
        job = proc._autospec_job
        if cancel.is_set():
            return -1, "", "Agent execution cancelled during launch"
        if registry is not None:
            registry.add(proc)
        for target, args_ in (
            (read_output, (proc.stdout, output[0])),
            (read_output, (proc.stderr, output[1])),
            (write_input, (proc.stdin,)),
        ):
            thread = threading.Thread(target=target, args=args_, daemon=True, name="autospec-agent-io")
            io_threads.append(thread)
            thread.start()
        exited_cleanup = False
        while True:
            if cancel.is_set():
                _terminate_tree(proc)
                return -1, "", "Agent execution cancelled"
            if overflow.is_set():
                raise AgentError(f"Agent output exceeded {_MAX_OUTPUT_BYTES} bytes per stream")
            if proc.poll() is not None:
                if not exited_cleanup:
                    # CLI turns cannot leave background commands behind, even
                    # when those commands inherited stdout and keep pipes open.
                    _terminate_tree(proc)
                    exited_cleanup = True
                if all(not thread.is_alive() for thread in io_threads):
                    break
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(args, timeout)
            cancel.wait(min(0.025, max(0, deadline - time.monotonic())))
        if overflow.is_set():
            raise AgentError(f"Agent output exceeded {_MAX_OUTPUT_BYTES} bytes per stream")
        return proc.returncode, *(buffer.decode("utf-8", errors="replace") for buffer in output)
    finally:
        if proc is not None:
            _terminate_tree(proc)
            try:
                proc.wait(timeout=_PROCESS_CLEANUP_TIMEOUT)
            except (subprocess.TimeoutExpired, OSError):
                pass
            cleanup_deadline = time.monotonic() + _PROCESS_CLEANUP_TIMEOUT
            for thread in io_threads:
                thread.join(timeout=max(0, cleanup_deadline - time.monotonic()))
            for pipe in (proc.stdin, proc.stdout, proc.stderr):
                if pipe is not None:
                    pipe.close()
            if registry is not None:
                registry.discard(proc)
            with proc._autospec_cleanup_lock:
                proc._autospec_job = None
                if job is not None:
                    job.close()
        elif job is not None:
            job.close()
        if registry is not None and own_call:
            registry.discard_call(cancel)


async def _await_tracked(run: Callable[[], tuple[int, str, str]]) -> tuple[int, str, str]:
    """Signal AND await cleanup; don't queue behind unrelated to_thread jobs."""
    cancel = threading.Event()
    registry = active_processes.get()
    if registry is not None:
        registry.register_call(cancel)
    token = _active_call_cancel.set(cancel)
    context = contextvars.copy_context()
    loop = asyncio.get_running_loop()
    worker = loop.create_future()

    def deliver(result, error) -> None:
        if not worker.done():
            if error is None:
                worker.set_result(result)
            else:
                worker.set_exception(error)

    def invoke() -> None:
        try:
            result = context.run(run)
        except BaseException as exc:
            loop.call_soon_threadsafe(deliver, None, exc)
        else:
            loop.call_soon_threadsafe(deliver, result, None)

    # The shared executor can be saturated by other long calls, including one
    # from another project. A dedicated supervised worker makes cancellation
    # independent of that queue; all contextvars still propagate explicitly.
    thread = threading.Thread(target=invoke, daemon=True, name="autospec-agent-worker")
    try:
        thread.start()
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancel.set()
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue  # repeated stop/dispose still waits for tree cleanup
            except Exception:
                break
        if not worker.cancelled():
            # Retrieve any worker exception to avoid "never retrieved" warnings;
            # the original caller cancellation is the outcome to propagate.
            worker.exception()
        raise
    finally:
        _active_call_cancel.reset(token)
        if registry is not None:
            registry.discard_call(cancel)


@dataclass
class AgentResult:
    text: str
    session_id: str | None = None
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0
    usage_reported: bool = True


@dataclass(frozen=True)
class RunnerCapabilities:
    """What the orchestrator can safely expect from an agent backend."""

    can_edit_files: bool
    can_run_shell: bool
    supports_native_skills: bool
    reliable_for_build: bool
    execution_model: str
    notes: str = ""


class AgentError(RuntimeError):
    def __init__(self, message: str = "", *, usage: AgentResult | None = None, budget_exhausted: bool = False, code: str | None = None):
        super().__init__(message)
        self.usage = usage
        self.budget_exhausted = budget_exhausted
        self.code = code


def _usage_number(value, *, integer: bool = False):
    """Untrusted provider telemetry must not poison totals with NaN/negatives."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    if not math.isfinite(number) or number < 0:
        return 0
    return int(number) if integer else number


def _claude_result(payload: dict) -> AgentResult:
    usage = payload.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    reported = [usage[key] for key in (
        "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
    ) if key in usage]
    if "total_cost_usd" in payload:
        reported.append(payload["total_cost_usd"])
    try:
        complete = (
            "total_cost_usd" in payload
            and "input_tokens" in usage and "output_tokens" in usage
            and all(math.isfinite(float(value)) and float(value) >= 0 for value in reported)
        )
    except (TypeError, ValueError, OverflowError):
        complete = False
    return AgentResult(
        text=str(payload.get("result") or ""),
        session_id=payload.get("session_id"),
        cost_usd=_usage_number(payload.get("total_cost_usd")),
        # Anthropic reports uncached, cache-write and cache-read input separately.
        input_tokens=sum(_usage_number(usage.get(key), integer=True) for key in (
            "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
        )),
        output_tokens=_usage_number(usage.get("output_tokens"), integer=True),
        duration_ms=_usage_number(payload.get("duration_ms"), integer=True),
        usage_reported=complete,
    )


class AgentRunner(Protocol):
    async def arun(
        self,
        prompt: str,
        system_prompt: str,
        cwd: Path | None = None,
        session_id: str | None = None,
        model: str | None = None,
    ) -> AgentResult: ...


_CLAUDE_ISOLATION_FLAGS = (
    "--restricted", "--safe-mode", "--tools", "--strict-mcp-config",
    "--disable-slash-commands", "--no-chrome", "--no-session-persistence", "--permission-prompts",
)


def _subscription_environment() -> dict[str, str]:
    """Keep OS/auth locations; do not inherit keys, provider switches or preload code.

    Existing OAuth is read by the trusted CLI in its normal user profile. It is
    never serialized or copied into a product directory/container/prompt.
    """
    names = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP",
             "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
             "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "LANG", "LC_ALL",
             "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "SSL_CERT_FILE",
             "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS"}
    environment = {key: value for key, value in os.environ.items() if key.upper() in names}
    environment.update({"CLAUDE_CODE_SAFE_MODE": "1", "ENABLE_CLAUDEAI_MCP_SERVERS": "false",
                        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"})
    return environment


@lru_cache(maxsize=8)
def _probe_claude_isolation(command: tuple[str, ...], stamps: tuple[int, ...]) -> None:
    """Offline capability probe. No prompt/API/model call is made."""
    try:
        result = subprocess.run([*command, "--help"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=10, check=False,
                                encoding="utf-8", errors="replace", env=_subscription_environment())
    except (OSError, subprocess.SubprocessError) as exc:
        raise AgentError(f"ISOLATION_UNAVAILABLE: Claude CLI capability probe failed: {exc}",
                         code="ISOLATION_UNAVAILABLE") from exc
    missing = [flag for flag in _CLAUDE_ISOLATION_FLAGS if flag not in result.stdout]
    if result.returncode or missing:
        raise AgentError(f"ISOLATION_UNAVAILABLE: Claude CLI lacks mandatory flags: {missing}",
                         code="ISOLATION_UNAVAILABLE")


def _ensure_claude_isolation() -> None:
    command = tuple(_resolve_agent_command([settings.claude_cmd]))
    # A replaced launcher/binary must not reuse old feature attestation.
    stamps = tuple(Path(p).stat().st_mtime_ns if Path(p).is_file() else 0 for p in command)
    _probe_claude_isolation(command, stamps)


class ClaudeCliRunner:
    """Subscription-authenticated inference, with no native execution tools.

    Turns and filesystem requests are mediated by Autospec. Native --resume is
    deliberately forbidden: a legacy transcript may contain previously granted
    tools/settings and is not an isolation attestation.
    """

    reports_provider_turns = True

    def __init__(self) -> None:
        self._sessions: dict[str, tuple[str | None, list[str]]] = {}

    async def arun(self, prompt: str, system_prompt: str, cwd: Path | None = None,
                   session_id: str | None = None, model: str | None = None) -> AgentResult:
        remaining = active_budget_usd.get()
        if remaining is not None and (not math.isfinite(remaining) or remaining <= 0):
            raise AgentError("Budget estimatif disponible nul ou invalide.", budget_exhausted=True)
        root = str(Path(cwd).absolute()) if cwd is not None else None
        if session_id and session_id not in self._sessions:
            raise AgentError("ISOLATION_UNAVAILABLE: legacy/unknown native session cannot be resumed; start a new mediated session",
                             code="ISOLATION_UNAVAILABLE")
        sid = session_id or f"restricted-{uuid.uuid4().hex}"
        saved_root, previous = self._sessions.get(sid, (root, []))
        if saved_root != root:
            raise AgentError("Mediated session cannot move to another execution root", code="ISOLATION_VIOLATION")
        history = [*previous, f"USER:\n{prompt}"]
        try:
            broker = FileBroker(context_for(cwd, sid)) if cwd is not None else None
        except IsolationViolation as exc:
            raise AgentError(str(exc), code=exc.code) from exc
        total = AgentResult(text="", session_id=sid)
        for _ in range(max(1, settings.provider_tool_rounds)):
            transcript = "\n\n".join(history)
            if len(transcript.encode("utf-8")) > 4_000_000:
                raise AgentError("Mediated conversation size limit exceeded", usage=total)
            try:
                await observe_provider(True)
                try:
                    result = await self._turn(transcript, system_prompt + (FILE_PROTOCOL if broker else ""),
                                              cwd, model, remaining)
                finally:
                    await observe_provider(False)
            except AgentError as exc:
                if exc.usage:
                    self._accumulate(total, exc.usage)
                    exc.usage = total
                raise
            self._accumulate(total, result)
            total.text = result.text
            history.append(f"ASSISTANT:\n{result.text}")
            try:
                call = extract_json(result.text)
            except (AgentError, TypeError):
                call = None
            if not isinstance(call, dict) or "tool" not in call:
                self._sessions[sid] = (root, history)
                return total
            if broker is None:
                raise AgentError("No filesystem capability for this call", usage=total, code="ISOLATION_VIOLATION")
            if remaining is not None:
                if not result.usage_reported:
                    raise AgentError("Cannot continue mediated turns with unreported budget usage", usage=total)
                remaining -= result.cost_usd
                if remaining <= 0:
                    raise AgentError("Mediated-turn budget exhausted", usage=total, budget_exhausted=True)
            try:
                if call["tool"] in {"dependency_request", "claim_expand"}:
                    handler = (active_dependency_handler.get() if call["tool"] == "dependency_request"
                               else active_claim_handler.get())
                    if handler is None:
                        raise AgentError("DEPENDENCY_COORDINATOR_UNAVAILABLE: no trusted dependency handler",
                                         code="DEPENDENCY_COORDINATOR_UNAVAILABLE", usage=total)
                    request = {key: value for key, value in call.items() if key not in {"tool", "task_id"}}
                    if broker.context.task_id:
                        request["task_id"] = broker.context.task_id
                    response = json.dumps(await asyncio.to_thread(handler, broker.root, request), ensure_ascii=False)
                    if len(response.encode("utf-8")) > 256_000:
                        raise AgentError("Dependency coordinator response size exceeded", usage=total)
                else:
                    response = await asyncio.to_thread(broker.apply, call)
            except IsolationViolation as exc:
                raise AgentError(str(exc), usage=total, code=exc.code) from exc
            history.append(f"TOOL RESULT:\n{response}")
        raise AgentError(f"Agent did not conclude within {settings.provider_tool_rounds} mediated turns", usage=total)

    @staticmethod
    def _accumulate(total: AgentResult, result: AgentResult) -> None:
        total.cost_usd += result.cost_usd
        total.input_tokens += result.input_tokens
        total.output_tokens += result.output_tokens
        total.duration_ms += result.duration_ms
        total.usage_reported = total.usage_reported and result.usage_reported

    async def _turn(
        self,
        prompt: str,
        system_prompt: str,
        cwd: Path | None = None,
        model: str | None = None,
        remaining: float | None = None,
    ) -> AgentResult:
        args = [
            settings.claude_cmd,
            "-p",
            "--output-format", "json",
            "--restricted", "--safe-mode",
            "--tools", "",
            "--strict-mcp-config", "--disallowedTools", "*",
            "--disable-slash-commands", "--no-chrome", "--no-session-persistence",
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--settings", '{"disableAllHooks":true,"syncClaudeAiSkills":false,"syncClaudeAiPlugins":false}',
            "--system-prompt", system_prompt or "Reply to the user's request. No tools are available.",
        ]
        chosen_model = model or settings.claude_model
        if chosen_model:
            args += ["--model", chosen_model]
        if remaining is not None:
            if not math.isfinite(remaining) or remaining <= 0:
                raise AgentError("Budget estimatif disponible nul ou invalide.", budget_exhausted=True)
            args += ["--max-budget-usd", str(remaining)]

        # Run the child process in a worker thread via the blocking subprocess
        # API: asyncio's subprocess support is unavailable on Windows'
        # SelectorEventLoop (the loop uvicorn runs), where
        # create_subprocess_exec raises NotImplementedError. Staying off the
        # event loop for child processes keeps this working on every platform.
        def _run() -> tuple[int, str, str]:
            _ensure_claude_isolation()
            token = _agent_environment.set(_subscription_environment())
            try:
                # CLI startup/managed policy runs in a trusted EMPTY directory,
                # never in generated source. OAuth stays in its original user
                # profile. Product data reaches the model only via mediation.
                with tempfile.TemporaryDirectory(prefix="autospec-inference-") as inference_root:
                    return _run_tracked(args, prompt, inference_root, settings.agent_timeout_s)
            finally:
                _agent_environment.reset(token)

        try:
            returncode, out_raw, err_raw = await _await_tracked(_run)
        except subprocess.TimeoutExpired:
            raise AgentError(f"Agent timed out after {settings.agent_timeout_s}s")
        except OSError as exc:
            # e.g. claude CLI not installed / not on PATH
            raise AgentError(f"Could not run claude CLI ({settings.claude_cmd}): {exc}")

        out = (out_raw or "").strip()
        try:
            payload = json.loads(out)
        except json.JSONDecodeError:
            # --output-format json should always give JSON, but degrade gracefully
            payload = None
        result = _claude_result(payload) if isinstance(payload, dict) else None
        exhausted = isinstance(payload, dict) and payload.get("subtype") == "error_max_budget_usd"
        if returncode != 0:
            err = (err_raw or "").strip()
            raise AgentError(f"claude CLI exited with {returncode}: {err or out}", usage=result, budget_exhausted=exhausted)
        if not isinstance(payload, dict):
            return AgentResult(text=out, usage_reported=False)
        if payload.get("is_error") or exhausted:
            # Some failures (e.g. error_during_execution) exit 0 but flag the payload.
            detail = payload.get("result") or payload.get("subtype") or out[:500]
            raise AgentError(f"claude CLI reported an error: {detail}", usage=result, budget_exhausted=exhausted)
        return result


def _extract_codex_text(out: str) -> tuple[str, int, int]:
    """Parse ``codex exec --json`` output into (final_text, in_tokens, out_tokens).

    Codex emits JSONL (one event per line). We don't hard-code the exact event
    schema (it evolves across versions): we scan every line that parses as a JSON
    object and keep the LAST human-readable assistant message found under any of
    the common keys, plus any token-usage counters seen. If nothing parses as
    JSON (e.g. plain-text mode), the whole output is returned as the text."""
    last_text = ""
    in_tok = out_tok = 0
    saw_json = False

    def _dig_text(obj: dict) -> str:
        # Common shapes across codex versions: {"msg":{"type":"agent_message","message":...}},
        # {"item":{"type":"agent_message","text":...}}, {"type":"agent_message","text":...}.
        for container in (obj, obj.get("msg"), obj.get("item"), obj.get("message")):
            if not isinstance(container, dict):
                continue
            kind = str(container.get("type") or "")
            if kind and "agent_message" not in kind and "message" not in kind and "assistant" not in kind:
                continue
            for key in ("text", "message", "content", "last_agent_message"):
                val = container.get(key)
                if isinstance(val, str) and val.strip():
                    return val
        return ""

    for line in out.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        saw_json = True
        text = _dig_text(obj)
        if text:
            last_text = text
        usage = obj.get("usage") or obj.get("token_usage") or {}
        if isinstance(usage, dict):
            in_tok = int(usage.get("input_tokens", usage.get("prompt_tokens", in_tok)) or in_tok)
            out_tok = int(usage.get("output_tokens", usage.get("completion_tokens", out_tok)) or out_tok)

    if not saw_json:
        return out, 0, 0
    return (last_text or out), in_tok, out_tok


class CodexCliRunner:
    """Compatibility selector for a backend whose isolation is unavailable."""

    async def arun(
        self,
        prompt: str,
        system_prompt: str,
        cwd: Path | None = None,
        session_id: str | None = None,
        model: str | None = None,
    ) -> AgentResult:
        # The old backend disabled both approvals AND sandbox. Until a backend
        # has an attested host boundary, fail before spawning or spending.
        raise AgentError("ISOLATION_UNAVAILABLE: Codex host-shell backend is disabled; use restricted Claude file tools",
                         code="ISOLATION_UNAVAILABLE")


class FakeRunner:
    """Deterministic runner for tests: pops queued replies in order."""

    def __init__(self, replies: list[str] | None = None):
        self.replies = list(replies or [])
        self.calls: list[dict] = []

    def queue(self, *replies: str) -> None:
        self.replies.extend(replies)

    async def arun(
        self,
        prompt: str,
        system_prompt: str,
        cwd: Path | None = None,
        session_id: str | None = None,
        model: str | None = None,
    ) -> AgentResult:
        self.calls.append(
            {"prompt": prompt, "system_prompt": system_prompt, "cwd": cwd,
             "session_id": session_id, "model": model}
        )
        if not self.replies:
            raise AgentError("FakeRunner has no queued reply")
        return AgentResult(text=self.replies.pop(0), session_id="fake-session")


_FENCED_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _balanced_end(text: str, start: int) -> int:
    """Index of the '}' closing the object opened at `start`, or -1 (string-aware)."""
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _first_object(text: str) -> dict | None:
    """Return the first parseable top-level JSON object found in `text`, or None.

    Brace-balanced candidates that fail to parse (e.g. braces inside a code
    sample) are skipped instead of aborting the whole extraction.
    """
    pos = text.find("{")
    while pos != -1:
        end = _balanced_end(text, pos)
        if end != -1:
            try:
                obj = json.loads(text[pos : end + 1])
            except json.JSONDecodeError:
                obj = None
            if isinstance(obj, dict):
                return obj
        pos = text.find("{", pos + 1)
    return None


def extract_json(text: str) -> dict:
    """Extract the first JSON object from an agent reply, tolerating fences/prose.

    Fenced ```json blocks are tried first; if none yields a valid object the
    whole reply is scanned, so JSON preceded by brace-laden prose still parses.
    Raises AgentError (never JSONDecodeError) when no object can be extracted.
    """
    for match in _FENCED_RE.finditer(text):
        obj = _first_object(match.group(1))
        if obj is not None:
            return obj
    obj = _first_object(text)
    if obj is not None:
        return obj
    if "{" not in text:
        raise AgentError(f"No JSON object in agent reply: {text[:200]!r}")
    raise AgentError(f"No parseable JSON object in agent reply: {text[:200]!r}")
