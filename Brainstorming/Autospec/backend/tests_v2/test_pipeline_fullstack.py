"""Fullstack pipeline end to end: real uv, npm, vite, vitest and git, scripted agents."""

import json
import textwrap

from autospec.core.fake import FakeRunner, write
from autospec.core.models import Phase, ProjectState, Profile, StoryStatus
from autospec.core.pipeline import Pipeline
from autospec.core.settings import Settings
from autospec.core.store import Store

PKG = "counter"
UI_NODEID = "frontend/src/acceptance/us_1.test.tsx::counter > shows the value from the api"

PLAN = json.dumps({
    "profile": "fullstack",
    "epics": [{"id": "EPIC-1", "title": "Counter", "description": ""}],
    "stories": [{"id": "US-1", "epic_id": "EPIC-1", "title": "Show the counter", "priority": 1,
                 "depends_on": [], "gherkin": "Feature: counter",
                 "criteria": ['GET /api/counter returns {"value": 0}',
                              "the page shows 'Value: 0' read from /api/counter"]}],
})

API_TEST = textwrap.dedent(f"""
    def test_ac1_counter_starts_at_zero():
        from fastapi.testclient import TestClient
        from {PKG}.app import create_app

        assert TestClient(create_app()).get("/api/counter").json() == {{"value": 0}}
    """)

UI_TEST = textwrap.dedent("""
    import { render, screen } from "@testing-library/react";
    import { describe, expect, it, vi } from "vitest";
    import App from "../App";

    describe("counter", () => {
      it("shows the value from the api", async () => {
        globalThis.fetch = vi.fn(async () => new Response(JSON.stringify({ value: 0 }))) as typeof fetch;
        render(<App />);
        expect(await screen.findByText("Value: 0")).toBeTruthy();
      });
    });
    """)

APP_TSX = textwrap.dedent("""
    import { useEffect, useState } from "react";

    export default function App() {
      const [value, setValue] = useState<number | null>(null);
      useEffect(() => {
        fetch("/api/counter")
          .then((response) => response.json())
          .then((data) => setValue(data.value))
          .catch(() => setValue(null));
      }, []);
      return (
        <main>
          <h1>{"Counter"}</h1>
          <p>{value === null ? "..." : `Value: ${value}`}</p>
        </main>
      );
    }
    """)

ROUTE = textwrap.dedent("""\
    @app.get("/api/counter")
        def counter() -> dict[str, int]:
            return {"value": 0}

        # API routes go under /api/...""")


def qa(call):
    write(call, {"tests/acceptance/test_us_1.py": API_TEST, "frontend/src/acceptance/us_1.test.tsx": UI_TEST})
    return json.dumps({"tests": [
        {"ac_id": "US-1.AC-1", "nodeids": ["tests/acceptance/test_us_1.py::test_ac1_counter_starts_at_zero"]},
        {"ac_id": "US-1.AC-2", "nodeids": [UI_NODEID]},
    ]})


def dev(call):
    app_py = call.cwd / PKG / "app.py"
    text = app_py.read_text(encoding="utf-8")
    write(call, {f"{PKG}/app.py": text.replace("# API routes go under /api/...", ROUTE.strip(), 1),
                 "frontend/src/App.tsx": APP_TSX})
    return json.dumps({"summary": "route and page"})


async def test_fullstack_story_is_verified_across_python_and_vitest(tmp_path):
    ws = tmp_path / "counter"
    ws.mkdir()
    state = ProjectState(id="counter-1", name="Counter", package=PKG, profile=Profile.FULLSTACK,
                         brief="# Counter\nA web counter.")
    settings = Settings(workspace_root=tmp_path, suite_timeout_s=900, smoke_timeout_s=180)
    runner = FakeRunner({"po": PLAN, "qa": qa, "dev": dev})

    state = await Pipeline(state, ws, runner, settings).arun()

    assert state.phase == Phase.DONE, state.error
    story = state.story("US-1")
    assert story.status == StoryStatus.DONE and story.attempts == 1
    assert "frontend/src/acceptance/us_1.test.tsx" in story.test_fingerprint
    events = Store(ws).events()
    assert not [e for e in events if e["type"] in ("qa_rejected", "verify_failed")], events
    smoke = [e for e in events if e["type"] == "smoke"]
    assert smoke and smoke[0]["ok"], smoke


async def test_fullstack_dev_editing_the_vite_config_is_rejected(tmp_path):
    ws = tmp_path / "counter"
    ws.mkdir()
    state = ProjectState(id="counter-2", name="Counter", package=PKG, profile=Profile.FULLSTACK,
                         brief="# Counter\nA web counter.")
    settings = Settings(workspace_root=tmp_path, suite_timeout_s=900, smoke_timeout_s=180,
                        dev_max_attempts=2)

    def cheat(call):
        config = call.cwd / "frontend" / "vite.config.ts"
        config.write_text(config.read_text(encoding="utf-8").replace(
            'environment: "jsdom"', 'environment: "jsdom", exclude: ["src/acceptance/**"]'), encoding="utf-8")
        return dev(call)

    runner = FakeRunner({"po": PLAN, "qa": qa, "dev": [cheat, dev]})
    state = await Pipeline(state, ws, runner, settings).arun()

    assert state.phase == Phase.DONE, state.error
    assert state.story("US-1").attempts == 2
    retry = [c for c in runner.calls if c.role == "dev"][1].prompt
    assert "frontend/vite.config.ts" in retry
