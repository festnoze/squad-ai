"""HTTP API v2 (docs/v2/CONTRACTS.md 9.1): real uv, git and clean suites, scripted agents."""

from __future__ import annotations

import asyncio
import json
import shutil
import socket
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from starlette.requests import Request

from autospec.core import api, profiles
from autospec.core.__main__ import main
from autospec.core.api import aevent_stream, create_app, read_events, stream_start
from autospec.core.fake import FakeRunner, demo_dev, demo_plan, demo_qa
from autospec.core.models import Phase, ProjectState, Profile
from autospec.core.pipeline import LIMIT_WAIT_S, MIN_WAIT_S, NETWORK_WAIT_S, Pipeline, resume_time
from autospec.core.ports import AgentError
from autospec.core.settings import Settings
from autospec.core.store import Store

BRIEF = "# Greeter\nA library that greets people."
SUMMARY_KEYS = {"id", "name", "profile", "phase", "running", "stories_done", "stories_total",
                "cost_usd", "updated_at", "error", "resume_at"}
NOW = 1_800_000_000.0
module_loop = pytest.mark.asyncio(loop_scope="module")  # tests sharing the `done` project


def _one_story_plan(package: str) -> str:
    plan = json.loads(demo_plan(package))
    plan["stories"] = plan["stories"][:1]
    return json.dumps(plan)


def _handlers(package: str = "greeter") -> dict:
    return {"pm": json.dumps({"brief": BRIEF}), "po": _one_story_plan(package),
            "qa": demo_qa(package), "dev": demo_dev(package)}


class GatedRunner(FakeRunner):
    """Scripted agents whose ``nth`` call of ``role`` hangs until the run is cancelled."""

    def __init__(self, handlers: dict, role: str, nth: int = 1):
        super().__init__(handlers)
        self.role, self.nth, self.seen = role, nth, 0
        self.entered = asyncio.Event()

    async def arun(self, call):
        if call.role == self.role:
            self.seen += 1
            if self.seen == self.nth:
                self.entered.set()
                await asyncio.Event().wait()  # never set: only a stop gets past it
        return await super().arun(call)


def _settings(root: Path) -> Settings:
    return Settings(workspace_root=root, qa_max_attempts=2, dev_max_attempts=2, suite_timeout_s=300,
                    smoke_timeout_s=60, project_budget_usd=100, call_budget_usd=5)


@asynccontextmanager
async def _serve(root: Path, runner_factory, *, frontend_dist: Path | None = None, **kwargs):
    """The app with its lifespan (discovery, timers, shutdown) and an in-process client."""
    app = create_app(_settings(root), runner_factory, frontend_dist=frontend_dist, **kwargs)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://127.0.0.1:8400") as client:
            yield SimpleNamespace(app=app, client=client, runs=app.state.runs)


async def _create(client: httpx.AsyncClient, **body) -> str:
    response = await client.post("/api/v2/projects", json={"name": "Greeter", **body})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _await_end(client: httpx.AsyncClient, pid: str, timeout_s: float = 300.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        project = (await client.get(f"/api/v2/projects/{pid}")).json()
        if not project["running"]:
            return project
        await asyncio.sleep(0.2)
    raise AssertionError(f"{pid} still running after {timeout_s} s")


def _seed(root: Path, pid: str, **fields) -> None:
    """A project on disk, as a previous server (or the CLI) left it."""
    base = {"id": pid, "name": "Greeter", "package": "greeter", "profile": Profile.LIB}
    Store(root / pid).save(ProjectState(**{**base, **fields}))


async def _sse(app, pid: str, *, last_event_id: str | None = None, after: int = 0, count: int = 1) -> list[str]:
    """The first ``count`` messages of the stream endpoint, read from its body iterator
    (an in-process client would wait for the end of an endless stream)."""
    route = next(r for r in app.routes if getattr(r, "path", "") == "/api/v2/projects/{pid}/stream")
    headers = [(b"last-event-id", last_event_id.encode())] if last_event_id is not None else []
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "query_string": b""})
    response = await route.endpoint(pid=pid, request=request, after=after)
    assert response.media_type == "text/event-stream"
    stream = response.body_iterator
    try:
        return [await asyncio.wait_for(anext(stream), 10) for _ in range(count)]
    finally:
        await stream.aclose()


def _data(message: str) -> dict:
    return json.loads(message.split("data: ", 1)[1])


# -- one project built to the end through the API --------------------------------

@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def done(tmp_path_factory):
    root = tmp_path_factory.mktemp("api-done")
    async with _serve(root, lambda state: FakeRunner(_handlers(state.package))) as server:
        created = await server.client.post("/api/v2/projects",
                                           json={"name": "Greeter", "profile": "lib", "brief": BRIEF})
        assert created.status_code == 201, created.text
        pid = created.json()["id"]
        first = (await server.client.get(f"/api/v2/projects/{pid}")).json()
        final = await _await_end(server.client, pid)
        yield SimpleNamespace(app=server.app, client=server.client, pid=pid, ws=root / pid,
                              created=created.json(), first=first, final=final)


@module_loop
async def test_a_created_project_starts_at_once_and_runs_to_done(done):
    assert set(done.created) == SUMMARY_KEYS
    assert (done.created["running"], done.created["phase"], done.created["profile"]) == (True, "created", "lib")
    assert done.first["running"] is True
    assert done.final["phase"] == "done", done.final["error"]
    assert done.final["running"] is False and done.final["resume_at"] is None
    assert [(s["id"], s["status"], s["attempts"]) for s in done.final["stories"]] == [("US-1", "done", 1)]


@module_loop
async def test_the_list_summarises_every_project(done):
    listed = (await done.client.get("/api/v2/projects")).json()

    assert [item["id"] for item in listed] == [done.pid]
    item = listed[0]
    assert set(item) == SUMMARY_KEYS
    assert (item["phase"], item["running"], item["stories_done"], item["stories_total"]) == ("done", False, 1, 1)
    assert item["cost_usd"] > 0 and item["error"] == ""


@module_loop
async def test_get_returns_the_full_state_or_404(done):
    project = (await done.client.get(f"/api/v2/projects/{done.pid}")).json()

    assert project["id"] == done.pid and project["brief"] == BRIEF and project["package"] == "greeter"
    assert project["usage"]["calls"] == 3, "po, qa, dev"
    assert project["stories"][0]["acceptance_tests"][0]["nodeids"]
    assert (await done.client.get("/api/v2/projects/nope-1")).status_code == 404


@module_loop
async def test_events_are_polled_by_index(done):
    url = f"/api/v2/projects/{done.pid}/events"
    everything = (await done.client.get(url)).json()
    total = everything["next"]

    assert total == len(everything["events"]) == len(Store(done.ws).events())
    types = [event["type"] for event in everything["events"]]
    assert types[-1] == "end" and {"phase", "agent_start", "suite", "smoke"} <= set(types)
    assert (await done.client.get(url, params={"after": total - 2})).json() == {
        "events": everything["events"][-2:], "next": total}
    assert (await done.client.get(url, params={"after": total + 5})).json() == {"events": [], "next": total}


@module_loop
async def test_the_stream_replays_the_journal_after_last_event_id(done):
    total = len(Store(done.ws).events())

    replay = await _sse(done.app, done.pid, last_event_id=str(total - 3), count=2)
    assert [message.split("\n", 1)[0] for message in replay] == [f"id: {total - 2}", f"id: {total - 1}"]
    assert _data(replay[-1])["type"] == "end"
    assert replay[0].endswith("\n\n")

    from_start = await _sse(done.app, done.pid)
    assert from_start[0].startswith("id: 0\ndata: ") and _data(from_start[0])["type"] == "phase"
    from_after = await _sse(done.app, done.pid, after=total - 1)
    assert from_after[0].startswith(f"id: {total - 1}\n")


@module_loop
async def test_files_and_raw_contents(done):
    files = (await done.client.get(f"/api/v2/projects/{done.pid}/files")).json()["files"]
    assert {"pyproject.toml", "uv.lock", "greeter/greet.py", "tests/acceptance/test_us_1.py"} <= set(files)
    assert not [f for f in files if f.startswith((".autospec/", ".git/", ".venv/"))]

    url = f"/api/v2/projects/{done.pid}/files/raw"
    raw = (await done.client.get(url, params={"path": "greeter/greet.py"})).json()
    expected = (done.ws / "greeter" / "greet.py").read_bytes().decode("utf-8")
    assert raw == {"path": "greeter/greet.py", "content": expected, "truncated": False}

    for outside in ("../outside.txt", "greeter/../../outside.txt", str(Path(sys.executable).resolve()), ".",
                    "//autospec.invalid/share/x", "\\\\autospec.invalid\\share\\x", "C:greeter/greet.py",
                    "/greeter/greet.py", "\\greeter\\greet.py"):
        assert (await done.client.get(url, params={"path": outside})).status_code == 400, outside
    for missing in ("missing.py", "greeter"):
        assert (await done.client.get(url, params={"path": missing})).status_code == 404, missing

    big = done.ws / ".autospec" / "big.log"
    big.write_bytes(b"x" * (api.RAW_MAX_BYTES + 10))
    truncated = (await done.client.get(url, params={"path": ".autospec/big.log"})).json()
    assert truncated["truncated"] is True and len(truncated["content"]) == api.RAW_MAX_BYTES


def test_an_anchored_path_is_refused_before_touching_the_disk(tmp_path, monkeypatch):
    def no_resolve(self, strict=False):
        raise AssertionError(f"resolved {self}: a UNC path would open an SMB connection")

    monkeypatch.setattr(Path, "resolve", no_resolve)
    for anchored in ("//10.255.255.1/share/x", "\\\\10.255.255.1\\share\\x", "C:/Windows/win.ini", "/etc/passwd"):
        with pytest.raises(api.HTTPException) as refused:
            api._read_file(tmp_path, anchored)
        assert refused.value.status_code == 400, anchored


@module_loop
async def test_the_diff_of_a_done_story_is_its_done_commit(done):
    diff = (await done.client.get(f"/api/v2/projects/{done.pid}/stories/US-1/diff")).json()

    assert diff["available"] is True
    assert "greeter/greet.py" in diff["diff"] and "+def greet" in diff["diff"]
    assert "tests/acceptance" not in diff["diff"], "the tests belong to the acceptance commit"
    assert (await done.client.get(f"/api/v2/projects/{done.pid}/stories/US-9/diff")).status_code == 404


@module_loop
async def test_a_done_project_can_be_neither_resumed_nor_stopped(done):
    assert (await done.client.post(f"/api/v2/projects/{done.pid}/resume")).status_code == 409
    assert (await done.client.post(f"/api/v2/projects/{done.pid}/stop")).status_code == 409


# -- stop, resume, delete ---------------------------------------------------------

async def test_stop_a_blocked_run_then_resume_it_to_done_then_delete_it(tmp_path):
    runner = GatedRunner(_handlers(), role="dev")
    async with _serve(tmp_path, lambda state: runner) as server:
        client = server.client
        pid = await _create(client, profile="lib", brief=BRIEF)
        url = f"/api/v2/projects/{pid}"
        await asyncio.wait_for(runner.entered.wait(), 300)

        assert (await client.get(url)).json()["running"] is True
        assert (await client.post(f"{url}/resume")).status_code == 409
        assert (await client.delete(url)).status_code == 409

        stop = await client.post(f"{url}/stop")
        assert (stop.status_code, stop.json()) == (202, {"ok": True})
        stopped = (await client.get(url)).json()
        assert (stopped["phase"], stopped["running"], stopped["error"]) == ("stopped", False, "interrupted")
        assert stopped["stories"][0]["attempts"] == 0, "a human stop is not a failed attempt"
        assert Store(tmp_path / pid).load().phase == Phase.STOPPED
        assert (await client.post(f"{url}/stop")).status_code == 409
        assert (await client.get(f"{url}/stories/US-1/diff")).json() == {"available": False, "diff": ""}

        assert (await client.post(f"{url}/resume")).status_code == 202
        final = await _await_end(client, pid)
        assert final["phase"] == "done", final["error"]
        assert final["stories"][0]["attempts"] == 1
        assert runner.roles() == ["po", "qa", "dev"], "the committed acceptance tests are kept"

        assert (await client.delete(url)).status_code == 204
        assert not (tmp_path / pid).exists()
        assert (await client.get(url)).status_code == 404


async def test_a_stop_during_the_scaffold_waits_for_it_so_a_resume_finds_it_whole(tmp_path, monkeypatch):
    in_lock, release = threading.Event(), threading.Event()
    real_uv_env = profiles.uv_env

    def slow_uv_env(ws):  # the scaffold asks for it after writing its layout, before `uv lock`
        if not in_lock.is_set():
            in_lock.set()
            release.wait(60)
        return real_uv_env(ws)

    monkeypatch.setattr(profiles, "uv_env", slow_uv_env)
    try:
        async with _serve(tmp_path, lambda state: FakeRunner(_handlers())) as server:
            client = server.client
            pid = await _create(client, profile="lib", brief=BRIEF)
            url, ws = f"/api/v2/projects/{pid}", tmp_path / pid
            assert await asyncio.to_thread(in_lock.wait, 60)
            assert (ws / "pyproject.toml").exists() and not (ws / ".git").exists(), "half built"

            stops = [asyncio.create_task(client.post(f"{url}/stop")) for _ in range(2)]
            await asyncio.sleep(0.5)
            assert not [stop for stop in stops if stop.done()], "both stops wait for the scaffold thread"
            assert (await client.get(url)).json()["running"] is True
            assert (await client.post(f"{url}/resume")).status_code == 409
            assert (await client.delete(url)).status_code == 409

            release.set()
            assert [(await stop).status_code for stop in stops] == [202, 202]
            stopped = (await client.get(url)).json()
            assert (stopped["phase"], stopped["running"]) == ("stopped", False)
            assert (ws / ".git").is_dir() and (ws / "uv.lock").is_file(), "the scaffold ran to its end"

            assert (await client.post(f"{url}/resume")).status_code == 202
            final = await _await_end(client, pid)
            assert final["phase"] == "done", final["error"]
    finally:
        release.set()


async def test_only_the_exact_directory_name_names_a_project(tmp_path):
    runner = GatedRunner(_handlers(), role="po")
    async with _serve(tmp_path, lambda state: runner) as server:
        client = server.client
        pid = await _create(client, profile="lib", brief=BRIEF)
        await asyncio.wait_for(runner.entered.wait(), 30)

        # NTFS opens these as the same directory: they must not bypass the running check.
        for alias in (pid.upper(), f"{pid}.", f"{pid}.."):
            url = f"/api/v2/projects/{alias}"
            assert (await client.get(url)).status_code == 404, alias
            assert (await client.delete(url)).status_code == 404, alias
            assert (await client.post(f"{url}/resume")).status_code == 404, alias
        assert (tmp_path / pid).is_dir() and server.runs.running(pid)
        assert (await client.post(f"/api/v2/projects/{pid}/stop")).status_code == 202


async def test_only_local_pages_reach_the_api(tmp_path):
    async with _serve(tmp_path, lambda state: FakeRunner({})) as server:
        client = server.client
        health = "/api/v2/health"
        for host in ("127.0.0.1:8400", "localhost:8400", "[::1]:8400", "LOCALHOST", "localhost:5400"):
            assert (await client.get(health, headers={"host": host})).status_code == 200, host
        for host in ("evil.example", "evil.example:8400", "127.0.0.1.evil.example", "autospec", "localhost:x"):
            assert (await client.get(health, headers={"host": host})).status_code == 403, host

        create = {"name": "Greeter", "goal": "greet people"}
        for origin in ("http://evil.example", "null", "http://localhost:3000", "http://127.0.0.1:8401"):
            refused = await client.post("/api/v2/projects", json=create, headers={"origin": origin})
            assert refused.status_code == 403, origin
        assert not list(tmp_path.iterdir()), "a refused request creates nothing"

        stop = "/api/v2/projects/nope-1/stop"  # 404: the request got through to the route
        for origin in ("http://127.0.0.1:8400", "http://localhost:8400", "http://localhost:5400"):
            assert (await client.post(stop, headers={"origin": origin})).status_code == 404, origin
        proxied = {"host": "localhost:5400", "origin": "http://localhost:5400"}  # the Vite dev proxy
        assert (await client.post(stop, headers=proxied)).status_code == 404


async def test_projects_are_discovered_from_the_workspace_root(tmp_path):
    _seed(tmp_path, "old-1", created_at="2026-01-01T00:00:00+00:00", phase=Phase.BUILD)
    _seed(tmp_path, "new-1", created_at="2026-06-01T00:00:00+00:00", phase=Phase.DONE)
    legacy = tmp_path / "legacy-1" / ".autospec"  # written before resume_at and model existed
    legacy.mkdir(parents=True)
    (legacy / "state.json").write_text(json.dumps({
        "id": "legacy-1", "name": "Legacy", "package": "legacy", "phase": "stopped",
        "created_at": "2025-01-01T00:00:00+00:00", "a_field_from_elsewhere": 1}), encoding="utf-8")
    broken = tmp_path / "broken-1" / ".autospec"
    broken.mkdir(parents=True)
    (broken / "state.json").write_text("{", encoding="utf-8")
    (tmp_path / "not-a-project").mkdir()

    async with _serve(tmp_path, lambda state: FakeRunner({})) as server:
        client = server.client
        assert (await client.get("/api/v2/health")).json() == {"status": "ok"}
        listed = (await client.get("/api/v2/projects")).json()
        assert [(p["id"], p["phase"], p["running"]) for p in listed] == [
            ("new-1", "done", False), ("old-1", "build", False), ("legacy-1", "stopped", False)]
        assert (listed[-1]["resume_at"], listed[-1]["profile"]) == (None, None)
        assert (await client.get("/")).status_code == 404, "no built frontend"

        for body in ({"name": "Greeter"}, {"name": "  ", "goal": "greet"},
                     {"name": "Greeter", "goal": "greet", "profile": "desktop"}):
            assert (await client.post("/api/v2/projects", json=body)).status_code == 422, body

        pid = await _create(client, name="Data", package="json", goal="parse data")
        assert pid.startswith("json-app-"), "the package is normalised like a name"
        failed = await _await_end(client, pid)
        assert failed["package"] == "json_app"
        assert failed["phase"] == "error" and "KeyError" in failed["error"], "no scripted pm"


async def test_the_built_frontend_is_served_at_the_root(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")

    async with _serve(tmp_path / "root", lambda state: FakeRunner({}), frontend_dist=dist) as server:
        client = server.client
        assert '<div id="root">' in (await client.get("/")).text
        assert (await client.get("/assets/app.js")).text == "console.log(1)"
        assert '<div id="root">' in (await client.get("/projects/greeter-1")).text, "client-side route"
        assert (await client.get("/assets/missing.js")).status_code == 404
        assert (await client.get("/api/v2/nope")).status_code == 404
        assert (await client.get("/api/v2/health")).json() == {"status": "ok"}


# -- automatic resume ---------------------------------------------------------------

@pytest.mark.parametrize(("kind", "message", "expected"), [
    ("limit", "Claude AI usage limit reached|1900000000", 1_900_000_000.0),
    ("limit", "claude session failed (success): Claude AI usage limit reached|1900000000123", 1_900_000_000.123),
    ("limit", "usage limit reached|1000000000", NOW + MIN_WAIT_S),  # a reset already past
    ("limit", "usage limit reached, try again later", NOW + LIMIT_WAIT_S),
    ("network", "Can't reach the API server (ENOTFOUND)", NOW + NETWORK_WAIT_S),
    ("budget", "max budget reached|1900000000", None),
    ("unavailable", "claude not found", None),
    ("cli", "boom", None),
])
def test_resume_time_of_a_provider_error(kind, message, expected):
    assert resume_time(kind, message, NOW) == (pytest.approx(expected) if expected else None)


async def test_a_limit_park_arms_a_timer_that_resumes_the_run(tmp_path):
    reset = int(time.time()) + 3600
    handlers = {**_handlers(), "pm": [AgentError(f"Claude AI usage limit reached|{reset}", "limit"),
                                      json.dumps({"brief": BRIEF})]}
    runner = GatedRunner(handlers, role="pm", nth=2)
    # The server's clock runs two hours ahead: the reset is already due when the run parks.
    async with _serve(tmp_path, lambda state: runner, clock=lambda: time.time() + 7200) as server:
        pid = await _create(server.client, goal="greet people")
        await asyncio.wait_for(runner.entered.wait(), 30)

        events = Store(tmp_path / pid).events()
        parked = next(event for event in events if event["type"] == "end")
        assert (parked["phase"], parked["resume_at"]) == ("needs_attention", reset)
        assert [event["resume_at"] for event in events if event["type"] == "auto_resume"] == [reset]
        project = (await server.client.get(f"/api/v2/projects/{pid}")).json()
        assert (project["running"], project["phase"], project["resume_at"]) == (True, "brief", None)
        assert (await server.client.post(f"/api/v2/projects/{pid}/stop")).status_code == 202


async def test_a_network_park_waits_five_minutes_and_stop_cancels_it(tmp_path, monkeypatch):
    monkeypatch.setattr(Pipeline, "network_retry_delays_s", ())
    handlers = {**_handlers(), "pm": AgentError("Can't reach the API server (ENOTFOUND)", "network")}
    async with _serve(tmp_path, lambda state: FakeRunner(handlers)) as server:
        client = server.client
        before = time.time()
        pid = await _create(client, goal="greet people")
        parked = await _await_end(client, pid)

        assert parked["phase"] == "needs_attention" and "ENOTFOUND" in parked["error"]
        assert before + NETWORK_WAIT_S <= parked["resume_at"] <= time.time() + NETWORK_WAIT_S
        assert pid in server.runs.timers
        assert (await client.get("/api/v2/projects")).json()[0]["resume_at"] == parked["resume_at"]

        assert (await client.post(f"/api/v2/projects/{pid}/stop")).status_code == 202
        stopped = (await client.get(f"/api/v2/projects/{pid}")).json()
        assert (stopped["phase"], stopped["resume_at"], stopped["running"]) == ("stopped", None, False)
        assert pid not in server.runs.timers
        assert Store(tmp_path / pid).load().resume_at is None
        assert (await client.post(f"/api/v2/projects/{pid}/stop")).status_code == 409


async def test_a_project_parked_in_the_past_resumes_at_startup(tmp_path):
    _seed(tmp_path, "greeter-parked", goal="greet people", phase=Phase.NEEDS_ATTENTION,
          error="pm agent: usage limit reached", resume_at=time.time() - 10)
    runner = GatedRunner(_handlers(), role="pm")
    async with _serve(tmp_path, lambda state: runner) as server:
        await asyncio.wait_for(runner.entered.wait(), 30)

        project = (await server.client.get("/api/v2/projects/greeter-parked")).json()
        assert (project["running"], project["phase"], project["resume_at"]) == (True, "brief", None)
        assert "auto_resume" in [event["type"] for event in Store(tmp_path / "greeter-parked").events()]
        assert (await server.client.post("/api/v2/projects/greeter-parked/stop")).status_code == 202
        assert Store(tmp_path / "greeter-parked").load().phase == Phase.STOPPED


async def test_a_manual_resume_replaces_the_pending_automatic_one(tmp_path):
    _seed(tmp_path, "greeter-parked", goal="greet people", phase=Phase.NEEDS_ATTENTION,
          resume_at=time.time() + 3600)
    runner = GatedRunner(_handlers(), role="pm")
    async with _serve(tmp_path, lambda state: runner) as server:
        assert "greeter-parked" in server.runs.timers, "re-armed at startup"

        assert (await server.client.post("/api/v2/projects/greeter-parked/resume")).status_code == 202
        assert "greeter-parked" not in server.runs.timers
        await asyncio.wait_for(runner.entered.wait(), 30)
        project = (await server.client.get("/api/v2/projects/greeter-parked")).json()
        assert (project["running"], project["resume_at"]) == (True, None)
        assert Store(tmp_path / "greeter-parked").load().resume_at is None
    assert Store(tmp_path / "greeter-parked").load().phase == Phase.STOPPED, "shutdown stops the run"


# -- event journal and stream helpers -------------------------------------------------

def test_read_events_leaves_a_line_being_written_for_the_next_read(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_bytes(b'{"type": "a"}\n\n{"type": "b"}\n{"type": "c"')

    records, offset = read_events(path)
    assert records == [{"type": "a"}, {"type": "b"}]
    with path.open("ab") as handle:
        handle.write(b', "x": 1}\n')
    assert read_events(path, offset) == ([{"type": "c", "x": 1}], path.stat().st_size)
    assert read_events(tmp_path / "missing.jsonl") == ([], 0)


def test_stream_start_prefers_last_event_id():
    assert stream_start("4", 0) == 5
    assert stream_start(None, 3) == 3
    assert stream_start(" junk ", 2) == 2


async def test_the_stream_follows_new_records_beats_and_ends_with_the_workspace(tmp_path):
    store = Store(tmp_path / "greeter-1")
    store.append_event({"type": "phase", "phase": "brief"})
    stream = aevent_stream(store.events_path, 0, heartbeat_s=0.05, poll_s=0.01)

    async def next_message() -> str:
        return await asyncio.wait_for(anext(stream), 5)

    messages = [await next_message()]
    assert messages[0].startswith("id: 0\n")
    store.append_event({"type": "phase", "phase": "plan"})
    while not any(m.startswith("id: 1\n") for m in messages) or ": heartbeat\n\n" not in messages:
        messages.append(await next_message())
    assert _data(next(m for m in messages if m.startswith("id: 1\n")))["phase"] == "plan"

    shutil.rmtree(store.ws)

    async def drain() -> list[str]:
        return [message async for message in stream]

    assert all(m == ": heartbeat\n\n" for m in await asyncio.wait_for(drain(), 5))


async def test_shutdown_cuts_open_streams_then_stops_the_runs(tmp_path):
    import uvicorn

    _seed(tmp_path, "greeter-1", phase=Phase.DONE)
    Store(tmp_path / "greeter-1").append_event({"type": "phase", "phase": "done"})
    app = create_app(_settings(tmp_path), lambda state: FakeRunner({}), frontend_dist=None)
    server = uvicorn.Server(uvicorn.Config(app, log_config=None, timeout_graceful_shutdown=api.SHUTDOWN_GRACE_S))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        base = f"http://127.0.0.1:{sock.getsockname()[1]}"
        async with httpx.AsyncClient(base_url=base, trust_env=False, timeout=10) as client:
            async with client.stream("GET", "/api/v2/projects/greeter-1/stream") as stream:
                assert await anext(stream.aiter_lines()) == "id: 0"
                server.should_exit = True  # what Ctrl+C does
                started = time.monotonic()
                await asyncio.wait_for(asyncio.shield(serving), api.SHUTDOWN_GRACE_S + 10)
        assert time.monotonic() - started < api.SHUTDOWN_GRACE_S + 5
        assert app.state.runs.closing, "the lifespan shutdown ran"
    finally:
        server.force_exit = True
        await asyncio.wait({serving}, timeout=10)
        sock.close()


def test_serve_bounds_the_graceful_shutdown(tmp_path, monkeypatch):
    import uvicorn

    seen = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: seen.update(options, app=app))
    assert api.serve(_settings(tmp_path), port=8412, runner_factory=lambda state: FakeRunner({})) == 0
    assert seen.pop("app").state.runs.root == tmp_path
    assert seen == {"host": "127.0.0.1", "port": 8412, "timeout_graceful_shutdown": api.SHUTDOWN_GRACE_S}


# -- command line -----------------------------------------------------------------------

def test_the_serve_command_wires_the_workspace_root_and_the_runner(tmp_path, monkeypatch):
    seen = {}

    def fake_serve(settings, *, port, runner_factory):
        seen.update(root=settings.workspace_root, port=port,
                    runner=runner_factory(ProjectState(id="x-1", name="X", package="x")))
        return 0

    monkeypatch.setattr(api, "serve", fake_serve)
    assert main(["serve", "--port", "8411", "--fake", "--workspace-root", str(tmp_path)]) == 0
    assert (seen["root"], seen["port"]) == (tmp_path.resolve(), 8411)
    assert isinstance(seen["runner"], FakeRunner)
    assert main(["serve", "--fake"]) == 0 and seen["port"] == 8400
