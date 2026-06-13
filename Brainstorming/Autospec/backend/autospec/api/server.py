"""HTTP + WebSocket API exposing the Autospec pipeline to the React frontend."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import stat
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..agents.runner import AgentRunner, ClaudeCliRunner
from ..agents.scripted import ScriptedRunner
from ..config import PROJECT_DIR, settings
from ..models import ChatMessage, ChatRole, PipelinePhase, ProjectState, StoryStatus, new_id
from ..orchestrator.events import bus
from ..orchestrator.pipeline import Pipeline
from ..storage import list_states, load_state, workspace_dir

# Directories and files hidden from the workspace file explorer: VCS/build/cache
# noise plus Autospec's own persisted state and report artifacts.
_EXCLUDED_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache"}
_MAX_FILE_CHARS = 200_000


def _is_excluded_file(name: str) -> bool:
    """Whether a file is an Autospec artifact that the explorer should hide."""
    if name == "autospec-state.json" or name.endswith(".pyc"):
        return True
    if name == ".report.json":
        return True
    return name.startswith("autospec-report-") and name.endswith(".json")

# Phases whose work is interrupted by a backend restart: a project caught in one
# of them was actively running a background task that no longer exists.
_INTERRUPTED_PHASES = {
    PipelinePhase.SPEC,
    PipelinePhase.ANALYZE,
    PipelinePhase.ARCHITECT,
    PipelinePhase.PLAN,
    PipelinePhase.BUILD,
}


def recover_projects() -> list[str]:
    """Re-register persisted projects as dormant pipelines after a restart.

    Pipelines live in memory, so a backend restart leaves persisted projects
    unreachable for any controlling action (chat, stop, force-done, ...). For
    each persisted state not already live, this rebuilds a dormant ``Pipeline``
    (no background task is started) and recovers an interrupted run: an active
    phase becomes ``STOPPED``, in-progress stories revert to ``TODO`` and the
    ``running``/``paused`` flags are reset (the app subprocess was killed). The
    recovered state is persisted and broadcast. Returns the re-registered ids.
    """
    recovered: list[str] = []
    for state in list_states():
        if state.id in pipelines:
            continue
        changed = False
        if state.phase in _INTERRUPTED_PHASES:
            state.phase = PipelinePhase.STOPPED
            changed = True
        for story in state.stories:
            if story.status in (StoryStatus.IN_PROGRESS, StoryStatus.GREEN):
                story.status = StoryStatus.TODO
                changed = True
        if state.running:
            state.running = False
            changed = True
        if state.paused:
            state.paused = False
            changed = True
        pipeline = Pipeline(state, _runner)
        pipelines[state.id] = pipeline
        if changed:
            pipeline._sync()
        recovered.append(state.id)
    return recovered


@asynccontextmanager
async def _lifespan(app):
    """Recover persisted projects on startup so they stay controllable."""
    recover_projects()
    yield


app = FastAPI(title="Autospec", version="0.1.0", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5183",
        "http://127.0.0.1:5183",
        "http://localhost:8100",
        "http://127.0.0.1:8100",
        "http://localhost:8123",
        "http://127.0.0.1:8123",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

pipelines: dict[str, Pipeline] = {}
_runner: AgentRunner = ScriptedRunner() if settings.fake_agents else ClaudeCliRunner()


def set_runner(runner: AgentRunner) -> None:
    """Swap the agent backend (tests inject a FakeRunner here)."""
    global _runner
    _runner = runner


class CreateProjectRequest(BaseModel):
    goal: str
    name: str = ""
    auto_spec: bool = False
    budget_usd: float = 0.0
    budget_tokens: int = 0


class MessageRequest(BaseModel):
    message: str


class SpecModeRequest(BaseModel):
    mode: str


class BudgetRequest(BaseModel):
    budget_usd: float | None = None
    budget_tokens: int | None = None


class AcceptanceCriterionInput(BaseModel):
    id: str | None = None
    text: str


class EditStoryRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    gherkin: str | None = None
    priority: int | None = None
    acceptance_criteria: list[AcceptanceCriterionInput] | None = None


class AddStoryRequest(BaseModel):
    epic_id: str
    title: str
    description: str | None = None
    gherkin: str | None = None
    priority: int = 3
    acceptance_criteria: list[str] | None = None
    depends_on: list[str] | None = None


class StoryPriority(BaseModel):
    id: str
    priority: int


class ReorderRequest(BaseModel):
    priorities: list[StoryPriority]


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip())[:32].strip("-").lower()
    return slug or "projet"


def _pipeline(project_id: str) -> Pipeline:
    pipeline = pipelines.get(project_id)
    if not pipeline:
        raise HTTPException(404, f"Projet inconnu : {project_id}")
    return pipeline


async def _acall_pipeline(coro, not_found: str):
    """Await a pipeline call, mapping domain errors to HTTP errors.

    ``KeyError`` (unknown story/epic) -> 404 with ``not_found`` as detail;
    ``ValueError`` (invalid state transition, e.g. story being developed or
    pipeline already active) -> 409 with the pipeline's own (French) message.
    """
    try:
        return await coro
    except KeyError:
        raise HTTPException(404, not_found)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/projects")
async def acreate_project(req: CreateProjectRequest) -> dict:
    if not req.goal.strip():
        raise HTTPException(422, "L'objectif du projet est vide.")
    name = req.name.strip() or _slug(req.goal)
    state = ProjectState(
        id=new_id(_slug(name)),
        name=name,
        goal=req.goal,
        auto_spec=req.auto_spec,
        budget_usd=max(0.0, req.budget_usd),
        budget_tokens=max(0, req.budget_tokens),
    )
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


def _force_delete_workspace(project_id: str) -> bool:
    """Delete a project workspace, defeating read-only files.

    Each finished story is committed to a per-workspace git repo, and git marks
    its pack/object files read-only — on Windows ``shutil.rmtree`` then fails to
    remove the ``.git`` directory (leaving the workspace behind). We retry with
    an ``onerror`` handler that clears the read-only bit before re-deleting.
    """
    ws = workspace_dir(project_id)
    if not ws.exists():
        return False

    def _on_error(func, path, _exc) -> None:
        # Best-effort: clear the read-only bit and retry; a still-locked file
        # (e.g. held by a running app/pytest) is reported by the caller below.
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            pass

    shutil.rmtree(ws, onerror=_on_error)
    if ws.exists():
        raise OSError(f"workspace {project_id} partiellement verrouillé")
    return True


@app.delete("/api/projects/{project_id}")
async def adelete_project(project_id: str) -> dict:
    pipeline = pipelines.pop(project_id, None)
    if pipeline:
        await pipeline.adispose()
    try:
        existed = _force_delete_workspace(project_id)
    except OSError:
        # The state file survived: re-register the (now dormant) pipeline so
        # the project stays listed/controllable and the delete can be retried.
        if pipeline:
            pipelines[project_id] = pipeline
        raise HTTPException(
            409, "Le workspace est verrouillé (un processus l'utilise) — réessaie dans un instant."
        )
    if not pipeline and not existed:
        raise HTTPException(404, f"Projet inconnu : {project_id}")
    bus.publish({"type": "deleted", "project_id": project_id})
    return {"ok": True}


@app.post("/api/projects/{project_id}/chat")
async def achat(project_id: str, req: MessageRequest) -> dict:
    pipeline = _pipeline(project_id)
    # An empty message would unblock the PM interview queue (the same sentinel
    # astop uses) and waste an agent turn: reject it upfront.
    if not req.message.strip():
        raise HTTPException(422, "Le message est vide.")
    await pipeline.asend_user_message(req.message)
    return {"ok": True, "phase": pipeline.state.phase}


@app.post("/api/projects/{project_id}/spec-mode")
async def aset_spec_mode(project_id: str, req: SpecModeRequest) -> dict:
    pipeline = _pipeline(project_id)
    try:
        await pipeline.aset_spec_mode(req.mode)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return {"ok": True, "spec_mode": pipeline.state.spec_mode}


@app.post("/api/projects/{project_id}/budget")
async def aset_budget(project_id: str, req: BudgetRequest) -> dict:
    pipeline = _pipeline(project_id)
    if req.budget_usd is not None:
        pipeline.state.budget_usd = max(0.0, req.budget_usd)
    if req.budget_tokens is not None:
        pipeline.state.budget_tokens = max(0, req.budget_tokens)
    pipeline._enforce_budget()  # stop immediately if the new cap is already exceeded
    pipeline._sync()
    return {"ok": True, "budget_usd": pipeline.state.budget_usd, "budget_tokens": pipeline.state.budget_tokens}


@app.post("/api/projects/{project_id}/stop")
async def astop(project_id: str) -> dict:
    await _pipeline(project_id).astop()
    return {"ok": True}


@app.post("/api/projects/{project_id}/pause")
async def apause(project_id: str) -> dict:
    await _pipeline(project_id).apause()
    return {"ok": True}


@app.post("/api/projects/{project_id}/resume")
async def aresume(project_id: str) -> dict:
    await _pipeline(project_id).aresume()
    return {"ok": True}


@app.post("/api/projects/{project_id}/resume-build")
async def aresume_build(project_id: str) -> dict:
    pipeline = _pipeline(project_id)
    await _acall_pipeline(pipeline.aresume_build(), f"Projet inconnu : {project_id}")
    return {"ok": True}


@app.post("/api/projects/{project_id}/run")
async def arun_app(project_id: str) -> dict:
    pipeline = _pipeline(project_id)
    if pipeline.state.phase in (
        PipelinePhase.SPEC,
        PipelinePhase.PLAN,
        PipelinePhase.ARCHITECT,
        PipelinePhase.BUILD,
    ):
        raise HTTPException(409, "Le projet n'a pas encore de code à lancer.")
    await pipeline.arun_app()
    return {"ok": True}


@app.post("/api/projects/{project_id}/stop-app")
async def astop_app(project_id: str) -> dict:
    await _pipeline(project_id).astop_app()
    return {"ok": True}


@app.post("/api/projects/{project_id}/archive")
async def aarchive_project(project_id: str) -> dict:
    pipeline = _pipeline(project_id)
    # Archiving hides the project: refuse while agents are actively working on
    # it (they would keep running — and spending budget — out of sight).
    if pipeline.state.phase in _INTERRUPTED_PHASES:
        raise HTTPException(409, "La pipeline est active : arrête-la avant d'archiver le projet.")
    await pipeline.aset_archived(True)
    return {"ok": True}


@app.post("/api/projects/{project_id}/unarchive")
async def aunarchive_project(project_id: str) -> dict:
    await _pipeline(project_id).aset_archived(False)
    return {"ok": True}


@app.patch("/api/projects/{project_id}/stories/{story_id}")
async def aedit_story(project_id: str, story_id: str, req: EditStoryRequest) -> dict:
    pipeline = _pipeline(project_id)
    fields = req.model_dump(exclude_unset=True)
    if fields.get("title") is not None and not fields["title"].strip():
        raise HTTPException(422, "Le titre de la story est vide.")
    await _acall_pipeline(
        pipeline.aedit_story(story_id, **fields), f"Story inconnue : {story_id}"
    )
    return {"ok": True, "state": pipeline.state.model_dump(mode="json")}


@app.post("/api/projects/{project_id}/stories")
async def aadd_story(project_id: str, req: AddStoryRequest) -> dict:
    pipeline = _pipeline(project_id)
    if not req.title.strip():
        raise HTTPException(422, "Le titre de la story est vide.")
    await _acall_pipeline(
        pipeline.aadd_story(
            epic_id=req.epic_id,
            title=req.title,
            description=req.description or "",
            gherkin=req.gherkin or "",
            priority=req.priority,
            acceptance_criteria=req.acceptance_criteria,
            depends_on=req.depends_on,
        ),
        f"Epic inconnu : {req.epic_id}",
    )
    return {"ok": True, "state": pipeline.state.model_dump(mode="json")}


@app.delete("/api/projects/{project_id}/stories/{story_id}")
async def adelete_story(project_id: str, story_id: str) -> dict:
    pipeline = _pipeline(project_id)
    await _acall_pipeline(pipeline.adelete_story(story_id), f"Story inconnue : {story_id}")
    return {"ok": True}


@app.post("/api/projects/{project_id}/stories/{story_id}/rebuild")
async def arebuild_story(project_id: str, story_id: str) -> dict:
    pipeline = _pipeline(project_id)
    await _acall_pipeline(pipeline.arebuild_story(story_id), f"Story inconnue : {story_id}")
    return {"ok": True}


@app.post("/api/projects/{project_id}/stories/{story_id}/force-done")
async def aforce_done(project_id: str, story_id: str) -> dict:
    pipeline = _pipeline(project_id)
    await _acall_pipeline(pipeline.aforce_done(story_id), f"Story inconnue : {story_id}")
    return {"ok": True, "state": pipeline.state.model_dump(mode="json")}


@app.get("/api/projects/{project_id}/stories/{story_id}/diff")
async def astory_diff(project_id: str, story_id: str) -> dict:
    pipeline = _pipeline(project_id)
    result = await _acall_pipeline(
        pipeline.astory_diff(story_id), f"Story inconnue : {story_id}"
    )
    return {"ok": True, **result}


@app.post("/api/projects/{project_id}/stories/reorder")
async def areorder_stories(project_id: str, req: ReorderRequest) -> dict:
    pipeline = _pipeline(project_id)
    await pipeline.areorder_stories([p.model_dump() for p in req.priorities])
    return {"ok": True, "state": pipeline.state.model_dump(mode="json")}


@app.get("/api/projects/{project_id}/files")
async def alist_files(project_id: str) -> dict:
    """List the workspace file tree (POSIX relative paths) for a project.

    Hides VCS/build/cache directories and Autospec's own state/report artifacts.
    Returns ``{"files": []}`` when the workspace has not been scaffolded yet.
    """
    _pipeline(project_id)
    ws = workspace_dir(project_id)
    if not ws.exists():
        return {"files": []}
    files: list[str] = []
    for path in ws.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ws)
        if any(part in _EXCLUDED_DIRS for part in rel.parts[:-1]):
            continue
        if _is_excluded_file(path.name):
            continue
        files.append(rel.as_posix())
    return {"files": sorted(files)}


@app.get("/api/projects/{project_id}/files/raw")
async def aread_file(project_id: str, path: str) -> dict:
    """Return the text content of a workspace file, guarded against traversal."""
    _pipeline(project_id)
    ws = workspace_dir(project_id)
    ws_root = ws.resolve()
    target = (ws / path).resolve()
    if not target.is_relative_to(ws_root):
        raise HTTPException(400, "chemin invalide")
    if not target.is_file():
        raise HTTPException(404, "fichier introuvable")
    content = target.read_text(encoding="utf-8", errors="replace")
    truncated = len(content) > _MAX_FILE_CHARS
    if truncated:
        content = content[:_MAX_FILE_CHARS]
    return {"path": path, "content": content, "truncated": truncated}


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


# Serve the built frontend when available (production mode). Both index.html
# and assets/ must exist: a partial build must not crash the API at startup
# (StaticFiles raises on a missing directory).
_dist = PROJECT_DIR / "frontend" / "dist"
if (_dist / "index.html").exists() and (_dist / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/")
    async def aindex() -> FileResponse:
        return FileResponse(_dist / "index.html")


def main() -> None:
    import uvicorn

    uvicorn.run("autospec.api.server:app", host="127.0.0.1", port=8100, reload=False)


if __name__ == "__main__":
    main()
