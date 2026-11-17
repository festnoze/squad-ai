"""HTTP API v2 (docs/v2/CONTRACTS.md section 9.1): projects, runs, events, files and diffs.

The workspaces under ``settings.workspace_root`` are the only source of truth (projects
created by the CLI show up too); the server only keeps in memory one asyncio task per
running project and one timer per automatic resume.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import stat
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, model_validator
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import machine, verify
from .models import TERMINAL_PHASES, Phase, Profile, ProjectState, StoryStatus
from .pipeline import Pipeline
from .ports import AgentRunner
from .profiles import package_name, run_git
from .settings import Settings
from .store import STATE_FILE, Store

FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend_v2" / "dist"
HEARTBEAT_S = 15.0
POLL_S = 0.5  # how often the event stream looks for new journal lines
STOP_WAIT_S = 30.0
RAW_MAX_BYTES = 200_000
DIFF_MAX_CHARS = 500_000
SHUTDOWN_GRACE_S = 3  # event streams never end by themselves: uvicorn cuts them after this
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DEV_SERVER_PORT = 5400  # frontend_v2 dev server, which proxies /api here (CONTRACTS.md 9.2)
_PROJECT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")

log = logging.getLogger(__name__)

RunnerFactory = Callable[[ProjectState], AgentRunner]


# -- event journal -----------------------------------------------------------

def read_events(path: Path, offset: int = 0) -> tuple[list[dict], int]:
    """Complete JSONL records from byte ``offset`` on, and the offset after the last one.

    A line still being written (no newline yet) is left for the next read. Blank lines
    are skipped like ``Store.events`` does, so indexes match the journal records.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read()
    except FileNotFoundError:
        return [], offset
    end = data.rfind(b"\n") + 1
    records = []
    for line in data[:end].splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except ValueError:  # a line torn by a crash keeps its index
                records.append({"type": "unreadable"})
    return records, offset + end


async def aevent_stream(path: Path, start: int, *, heartbeat_s: float = HEARTBEAT_S,
                        poll_s: float = POLL_S) -> AsyncIterator[str]:
    """Server-sent events: the journal from index ``start`` on, then every new record.

    ``id`` is the record index, so a reconnecting client resumes after ``Last-Event-ID``.
    Ends when the workspace disappears (project deleted).
    """
    index, offset, beat = 0, 0, time.monotonic()
    while path.parent.parent.is_dir():
        records, offset = read_events(path, offset)
        for record in records:
            if index >= start:
                yield f"id: {index}\ndata: {json.dumps(record, ensure_ascii=False)}\n\n"
            index += 1
        if time.monotonic() - beat >= heartbeat_s:
            beat = time.monotonic()
            yield ": heartbeat\n\n"
        await asyncio.sleep(poll_s)


def stream_start(last_event_id: str | None, after: int) -> int:
    """The first index to send: the one after ``Last-Event-ID`` when given, else ``after``."""
    last = (last_event_id or "").strip()
    return int(last) + 1 if last.isdigit() else after


# -- workspace helpers --------------------------------------------------------

def _load(ws: Path) -> ProjectState:
    """The persisted state. On Windows a concurrent atomic replace can briefly deny the read."""
    for attempt in range(5):
        try:
            return Store(ws).load()
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05)
    raise AssertionError("unreachable")


def _rmtree(path: Path) -> None:
    def onexc(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)  # git marks its objects read-only
        func(target)

    shutil.rmtree(path, onexc=onexc)


def _list_files(ws: Path) -> list[str]:
    if not (ws / ".git").exists():
        return []  # not scaffolded yet
    # repo_tree already leaves out .autospec/, frontend/node_modules/ and frontend/dist/.
    files = verify.repo_tree(ws, limit=1_000_000).splitlines()
    return [p for p in files if p and "node_modules" not in p.split("/")]


def _read_file(ws: Path, rel: str) -> dict:
    # A drive or a root ("C:/x", "/x", "//host/share/x") would replace the workspace, and
    # resolving a UNC path opens an SMB connection: refuse them before touching the disk.
    if PureWindowsPath(rel).anchor or PurePosixPath(rel).is_absolute():
        raise HTTPException(400, "the path must be relative to the workspace")
    root = ws.resolve()
    target = (root / rel).resolve()
    if target == root or not target.is_relative_to(root):
        raise HTTPException(400, "the path must stay inside the workspace")
    if not target.is_file():
        raise HTTPException(404, f"no such file: {rel}")
    with target.open("rb") as handle:
        data = handle.read(RAW_MAX_BYTES + 1)
    return {"path": rel, "content": data[:RAW_MAX_BYTES].decode("utf-8", errors="replace"),
            "truncated": len(data) > RAW_MAX_BYTES}


def _story_diff(ws: Path, story_id: str) -> dict:
    """The patch of the ``"<story> done"`` commit, when the story got one."""
    if not (ws / ".git").exists():
        return {"available": False, "diff": ""}
    history = run_git(ws, "log", "--format=%H %s", check=False).stdout.splitlines()
    sha = next((line.split(" ", 1)[0] for line in history if line.partition(" ")[2] == f"{story_id} done"), "")
    if not sha:
        return {"available": False, "diff": ""}
    diff = run_git(ws, "show", "--format=", "--no-color", "--no-ext-diff", "--patch", sha, check=False).stdout
    if len(diff) > DIFF_MAX_CHARS:
        diff = diff[:DIFF_MAX_CHARS] + "\n[diff truncated]\n"
    return {"available": True, "diff": diff}


def summary(pid: str, state: ProjectState, running: bool) -> dict:
    return {
        "id": pid, "name": state.name, "profile": state.profile.value if state.profile else None,
        "phase": state.phase.value, "running": running,
        "stories_done": sum(s.status == StoryStatus.DONE for s in state.stories),
        "stories_total": len(state.stories), "cost_usd": state.usage.cost_usd,
        "updated_at": state.updated_at, "error": state.error, "resume_at": state.resume_at,
    }


# -- runs -----------------------------------------------------------------------

def _cancel_once(task: asyncio.Task) -> None:
    """A run being stopped may be waiting for work it must not leave halfway (the scaffold
    thread): a second stop waits with the first instead of cutting that wait short."""
    if not task.cancelling():
        task.cancel()


class Runs:
    """Running pipelines (one task per project) and the timers of automatic resumes.

    Projects are keyed by their workspace directory name, which is their id. ``clock``
    gives the epoch seconds the timers count from (tests move it forward).
    """

    def __init__(self, settings: Settings, runner_factory: RunnerFactory,
                 clock: Callable[[], float] = time.time):
        self.settings = settings
        self.runner_factory = runner_factory
        self.clock = clock
        self.root = Path(settings.workspace_root)
        self.tasks: dict[str, asyncio.Task] = {}
        self.states: dict[str, ProjectState] = {}  # live state of each running project
        self.timers: dict[str, asyncio.TimerHandle] = {}
        self.closing = False

    def ws(self, pid: str) -> Path:
        return self.root / pid

    def exists(self, pid: str) -> bool:
        # Only the exact directory name: NTFS also opens "GREETER-1" or "greeter-1." as greeter-1,
        # an alias the running check (keyed by name) would not recognise.
        return (bool(_PROJECT_ID.fullmatch(pid)) and Store(self.ws(pid)).exists()
                and pid in os.listdir(self.root))

    def running(self, pid: str) -> bool:
        return pid in self.tasks

    def state(self, pid: str) -> ProjectState:
        """The live state of a running project, else the persisted one."""
        return self.states.get(pid) or _load(self.ws(pid))

    def all(self) -> list[tuple[str, ProjectState]]:
        """Every project of the workspace root, newest first (unreadable ones are skipped)."""
        found = []
        for path in self.root.glob(f"*/.autospec/{STATE_FILE}"):
            pid = path.parent.parent.name
            try:
                found.append((pid, self.state(pid)))
            except (OSError, ValueError) as exc:
                log.warning("unreadable project %s: %s", pid, exc)
        return sorted(found, key=lambda item: (item[1].created_at, item[0]), reverse=True)

    def start(self, pid: str, state: ProjectState) -> None:
        self.disarm(pid)
        self.states[pid] = state
        task = asyncio.create_task(self._arun(pid, state), name=f"autospec:{pid}")
        self.tasks[pid] = task
        # A callback, not a finally: a task cancelled before its first step never runs its body.
        task.add_done_callback(lambda done: self._finished(pid, state, done))

    async def _arun(self, pid: str, state: ProjectState) -> None:
        settings = replace(self.settings, model=state.model) if state.model else self.settings
        try:
            await Pipeline(state, self.ws(pid), self.runner_factory(state), settings).arun()
        except Exception as exc:  # the pipeline lands its own errors: this is the runner factory
            log.exception("cannot run project %s", pid)
            state.error = f"cannot run: {type(exc).__name__}: {exc}"
            with suppress(OSError):
                Store(self.ws(pid)).save(state)

    def _finished(self, pid: str, state: ProjectState, task: asyncio.Task) -> None:
        if self.tasks.get(pid) is task:
            del self.tasks[pid]
            self.states.pop(pid, None)
        if state.phase not in TERMINAL_PHASES:  # cancelled before the pipeline started, or broken
            target = Phase.STOPPED if task.cancelled() else Phase.ERROR
            with suppress(OSError, machine.IllegalTransition):
                state.error = state.error or "interrupted"
                machine.set_phase(state, target)
                Store(self.ws(pid)).save(state)
                Store(self.ws(pid)).append_event({"type": "phase", "phase": target.value})
        if state.resume_at is not None and not task.cancelled():
            self.arm(pid, state.resume_at)  # parked by the provider: come back by itself

    async def astop(self, pid: str) -> None:
        """Cancel the run; the pipeline records the STOPPED phase."""
        task = self.tasks.get(pid)
        if task is not None:
            _cancel_once(task)
            await asyncio.wait({task}, timeout=STOP_WAIT_S)

    def cancel_resume(self, pid: str, state: ProjectState) -> None:
        """Stop a parked project whose automatic resume is pending: it becomes stopped."""
        self.disarm(pid)
        state.resume_at = None
        if Phase.STOPPED in machine.PHASE_TRANSITIONS[state.phase]:
            machine.set_phase(state, Phase.STOPPED)
        store = Store(self.ws(pid))
        store.save(state)
        store.append_event({"type": "phase", "phase": state.phase.value})

    def arm(self, pid: str, resume_at: float) -> None:
        if self.closing:
            return
        self.disarm(pid)
        delay = max(0.0, resume_at - self.clock())
        self.timers[pid] = asyncio.get_running_loop().call_later(delay, self._fire, pid)

    def disarm(self, pid: str) -> None:
        timer = self.timers.pop(pid, None)
        if timer is not None:
            timer.cancel()

    def _fire(self, pid: str) -> None:
        self.timers.pop(pid, None)
        if self.closing or self.running(pid) or not self.exists(pid):
            return
        try:
            state = _load(self.ws(pid))
            if state.resume_at is None or state.phase == Phase.DONE:
                return
            Store(self.ws(pid)).append_event({"type": "auto_resume", "resume_at": state.resume_at})
        except (OSError, ValueError) as exc:
            log.warning("automatic resume of %s skipped: %s", pid, exc)
            return
        self.start(pid, state)

    def arm_all(self) -> None:
        """Startup: re-arm the automatic resume of every parked project."""
        for pid, state in self.all():
            if state.resume_at is not None and state.phase != Phase.DONE:
                self.arm(pid, state.resume_at)

    async def aclose(self) -> None:
        self.closing = True
        for pid in list(self.timers):
            self.disarm(pid)
        tasks = list(self.tasks.values())
        for task in tasks:
            _cancel_once(task)
        if tasks:
            await asyncio.wait(tasks, timeout=STOP_WAIT_S)


# -- HTTP -----------------------------------------------------------------------

def _host_port(authority: str, default_port: int | None) -> tuple[str | None, int | None]:
    try:
        parts = urlsplit(authority if "//" in authority else f"//{authority}")
        return parts.hostname, parts.port or default_port
    except ValueError:  # a malformed port
        return None, None


def local_request(headers: Headers) -> bool:
    """Whether a request may reach the API, which starts agents with shell tools here: a
    loopback Host (a DNS-rebinding page names its own) and, when a browser names the page
    that sent it, a page of this server or of the dev server (no cross-site form or fetch)."""
    hosts, origins = headers.getlist("host"), headers.getlist("origin")
    if len(hosts) != 1 or len(origins) > 1:
        return False
    host, port = _host_port(hosts[0], 80)
    if host not in LOCAL_HOSTS:
        return False
    if not origins:
        return True  # curl, scripts, and same-origin GETs
    origin, origin_port = _host_port(origins[0], 80)  # "null" (sandboxed page, file://) has no host
    return origin in LOCAL_HOSTS and origin_port in (port, DEV_SERVER_PORT)


class _LocalOnly:
    """ASGI middleware refusing (403) every HTTP request ``local_request`` rejects."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and not local_request(Headers(scope=scope)):
            response = JSONResponse({"detail": "host or origin refused: the API only serves local pages"}, 403)
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)


class NewProject(BaseModel):
    name: str
    package: str | None = None  # normalised like a name ("json" -> "json_app")
    profile: Profile | None = None
    brief: str | None = None
    goal: str | None = None
    model: str | None = None

    @model_validator(mode="after")
    def _check(self) -> NewProject:
        if not self.name.strip():
            raise ValueError("name is required")
        if not (self.brief or "").strip() and not (self.goal or "").strip():
            raise ValueError("a brief or a goal is required")
        return self


class _Frontend(StaticFiles):
    """The built frontend_v2; an unknown page path falls back to index.html (client routes)."""

    async def get_response(self, path: str, scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            parts = Path(path).parts
            if exc.status_code != 404 or Path(path).suffix or parts[:1] == ("api",):
                raise
            return await super().get_response("index.html", scope)


def create_app(settings: Settings, runner_factory: RunnerFactory, *,
               frontend_dist: Path | None = FRONTEND_DIST, clock: Callable[[], float] = time.time) -> FastAPI:
    runs = Runs(settings, runner_factory, clock)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        runs.arm_all()
        yield
        await runs.aclose()

    app = FastAPI(title="Autospec v2", lifespan=lifespan)
    app.add_middleware(_LocalOnly)
    app.state.runs = runs

    def known(pid: str) -> Path:
        if not runs.exists(pid):
            raise HTTPException(404, f"unknown project {pid}")
        return runs.ws(pid)

    @app.get("/api/v2/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/v2/projects")
    async def list_projects() -> list[dict]:
        return [summary(pid, state, runs.running(pid)) for pid, state in runs.all()]

    @app.post("/api/v2/projects", status_code=201)
    async def create_project(body: NewProject) -> dict:
        package = package_name(body.package or body.name)
        pid = f"{package.replace('_', '-')}-{uuid.uuid4().hex[:8]}"
        runs.ws(pid).mkdir(parents=True)
        state = ProjectState(id=pid, name=body.name.strip(), package=package, profile=body.profile,
                             goal=body.goal or "", brief=body.brief or "", model=body.model or "")
        Store(runs.ws(pid)).save(state)
        runs.start(pid, state)
        return summary(pid, state, True)

    @app.get("/api/v2/projects/{pid}")
    async def get_project(pid: str) -> dict:
        known(pid)
        return {**runs.state(pid).model_dump(mode="json"), "running": runs.running(pid)}

    @app.post("/api/v2/projects/{pid}/resume", status_code=202)
    async def resume_project(pid: str) -> dict:
        known(pid)
        if runs.running(pid):
            raise HTTPException(409, "the project is already running")
        state = runs.state(pid)
        if state.phase == Phase.DONE:
            raise HTTPException(409, "the project is done")
        runs.start(pid, state)  # disarms the automatic resume; the run clears resume_at
        return {"ok": True}

    @app.post("/api/v2/projects/{pid}/stop", status_code=202)
    async def stop_project(pid: str) -> dict:
        """Cancel the run, or the pending automatic resume of a parked project."""
        known(pid)
        if runs.running(pid):
            await runs.astop(pid)
            return {"ok": True}
        state = runs.state(pid)
        if state.resume_at is None:
            raise HTTPException(409, "the project is not running")
        runs.cancel_resume(pid, state)
        return {"ok": True}

    @app.delete("/api/v2/projects/{pid}", status_code=204)
    async def delete_project(pid: str) -> Response:
        ws = known(pid)
        if runs.running(pid):
            raise HTTPException(409, "stop the project before deleting it")
        runs.disarm(pid)
        try:
            await asyncio.to_thread(_rmtree, ws)
        except OSError as exc:
            raise HTTPException(409, f"the workspace cannot be deleted: {exc}") from exc
        return Response(status_code=204)

    @app.get("/api/v2/projects/{pid}/events")
    async def get_events(pid: str, after: int = Query(0, ge=0)) -> dict:
        records, _ = read_events(Store(known(pid)).events_path)
        return {"events": records[after:], "next": len(records)}

    @app.get("/api/v2/projects/{pid}/stream")
    async def stream_events(pid: str, request: Request, after: int = Query(0, ge=0)) -> StreamingResponse:
        path = Store(known(pid)).events_path
        start = stream_start(request.headers.get("last-event-id"), after)
        return StreamingResponse(aevent_stream(path, start), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/v2/projects/{pid}/files")
    async def list_files(pid: str) -> dict:
        return {"files": await asyncio.to_thread(_list_files, known(pid))}

    @app.get("/api/v2/projects/{pid}/files/raw")
    async def read_file(pid: str, path: str = Query(..., min_length=1)) -> dict:
        return await asyncio.to_thread(_read_file, known(pid), path)

    @app.get("/api/v2/projects/{pid}/stories/{sid}/diff")
    async def story_diff(pid: str, sid: str) -> dict:
        ws = known(pid)
        if sid not in {story.id for story in runs.state(pid).stories}:
            raise HTTPException(404, f"unknown story {sid}")
        return await asyncio.to_thread(_story_diff, ws, sid)

    if frontend_dist is not None and (frontend_dist / "index.html").is_file():
        app.mount("/", _Frontend(directory=frontend_dist, html=True), name="frontend")
    return app


def serve(settings: Settings, *, port: int, runner_factory: RunnerFactory, host: str = "127.0.0.1") -> int:
    """Serve the API (and the built frontend) until interrupted.

    Without a graceful timeout, uvicorn would wait forever for the open event streams on
    Ctrl+C and never reach the lifespan shutdown that stops the runs cleanly.
    """
    import uvicorn

    uvicorn.run(create_app(settings, runner_factory), host=host, port=port,
                timeout_graceful_shutdown=SHUTDOWN_GRACE_S)
    return 0
