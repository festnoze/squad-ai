"""HTTP + WebSocket API exposing the Autospec pipeline to the React frontend."""

from __future__ import annotations

import asyncio
import re

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..agents.runner import AgentRunner, ClaudeCliRunner
from ..config import PROJECT_DIR
from ..models import ChatMessage, ChatRole, PipelinePhase, ProjectState, new_id
from ..orchestrator.events import bus
from ..orchestrator.pipeline import Pipeline
from ..storage import delete_workspace, list_states, load_state

app = FastAPI(title="Autospec", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

pipelines: dict[str, Pipeline] = {}
_runner: AgentRunner = ClaudeCliRunner()


def set_runner(runner: AgentRunner) -> None:
    """Swap the agent backend (tests inject a FakeRunner here)."""
    global _runner
    _runner = runner


class CreateProjectRequest(BaseModel):
    goal: str
    name: str = ""
    auto_spec: bool = False


class MessageRequest(BaseModel):
    message: str


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip())[:32].strip("-").lower()
    return slug or "projet"


def _pipeline(project_id: str) -> Pipeline:
    pipeline = pipelines.get(project_id)
    if not pipeline:
        raise HTTPException(404, f"Projet inconnu : {project_id}")
    return pipeline


@app.post("/api/projects")
async def acreate_project(req: CreateProjectRequest) -> dict:
    if not req.goal.strip():
        raise HTTPException(422, "L'objectif du projet est vide.")
    name = req.name.strip() or _slug(req.goal)
    state = ProjectState(id=new_id(_slug(name)), name=name, goal=req.goal, auto_spec=req.auto_spec)
    state.chat.append(ChatMessage(role=ChatRole.USER, content=req.goal))
    pipeline = Pipeline(state, _runner)
    pipelines[state.id] = pipeline
    pipeline.start()
    return {"id": state.id, "state": state.model_dump(mode="json")}


@app.get("/api/projects")
async def alist_projects() -> list[dict]:
    live = {p.state.id: p.state for p in pipelines.values()}
    stored = {s.id: s for s in list_states()}
    stored.update(live)
    return [s.model_dump(mode="json") for s in stored.values()]


@app.get("/api/projects/{project_id}")
async def aget_project(project_id: str) -> dict:
    pipeline = pipelines.get(project_id)
    if pipeline:
        return pipeline.state.model_dump(mode="json")
    stored = load_state(project_id)
    if stored:
        return stored.model_dump(mode="json")
    raise HTTPException(404, f"Projet inconnu : {project_id}")


@app.delete("/api/projects/{project_id}")
async def adelete_project(project_id: str) -> dict:
    pipeline = pipelines.pop(project_id, None)
    if pipeline:
        await pipeline.adispose()
    existed = delete_workspace(project_id)
    if not pipeline and not existed:
        raise HTTPException(404, f"Projet inconnu : {project_id}")
    bus.publish({"type": "deleted", "project_id": project_id})
    return {"ok": True}


@app.post("/api/projects/{project_id}/chat")
async def achat(project_id: str, req: MessageRequest) -> dict:
    pipeline = _pipeline(project_id)
    await pipeline.asend_user_message(req.message)
    return {"ok": True, "phase": pipeline.state.phase}


@app.post("/api/projects/{project_id}/stop")
async def astop(project_id: str) -> dict:
    await _pipeline(project_id).astop()
    return {"ok": True}


@app.post("/api/projects/{project_id}/run")
async def arun_app(project_id: str) -> dict:
    pipeline = _pipeline(project_id)
    if pipeline.state.phase in (PipelinePhase.SPEC, PipelinePhase.PLAN):
        raise HTTPException(409, "Le projet n'a pas encore de code à lancer.")
    await pipeline.arun_app()
    return {"ok": True}


@app.websocket("/ws")
async def aws_events(ws: WebSocket) -> None:
    await ws.accept()
    queue = bus.subscribe()
    try:
        while True:
            event = await queue.get()
            await ws.send_json(event)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        bus.unsubscribe(queue)


# Serve the built frontend when available (production mode).
_dist = PROJECT_DIR / "frontend" / "dist"
if _dist.exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/")
    async def aindex() -> FileResponse:
        return FileResponse(_dist / "index.html")


def main() -> None:
    import uvicorn

    uvicorn.run("autospec.api.server:app", host="127.0.0.1", port=8100, reload=False)


if __name__ == "__main__":
    main()
