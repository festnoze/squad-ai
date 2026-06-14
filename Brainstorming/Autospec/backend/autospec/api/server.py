"""HTTP + WebSocket API exposing the Autospec pipeline to the React frontend."""

from __future__ import annotations

import asyncio
import io
import os
import re
import shutil
import stat
import zipfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..agents.providers import PROVIDERS, make_runner, provider_model
from ..agents.runner import AgentRunner
from ..agents.scripted import ScriptedRunner
from ..config import PROJECT_DIR, settings
from ..models import ChatMessage, ChatRole, PipelinePhase, ProjectState, StoryStatus, new_id
from ..orchestrator.events import bus
from ..orchestrator.pipeline import Pipeline
from ..forecast import forecast_iteration_cost
from ..spec_import import parse_spec_import
from ..metrics import compute_metrics
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


def recover_projects(states: list[ProjectState] | None = None) -> list[str]:
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
    for state in (list_states() if states is None else states):
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
        if state.awaiting_approval:
            state.awaiting_approval = ""
            changed = True
        pipeline = Pipeline(state, _runner)
        pipelines[state.id] = pipeline
        if changed:
            pipeline._sync()
        if state.resume_at:
            # Re-arm the M2 auto-resume timer lost with the previous process
            # (a past resume_at fires immediately: the window already reset).
            try:
                pipeline.schedule_resume(state.resume_at)
            except RuntimeError:
                pass  # no running event loop (sync context)
        recovered.append(state.id)
    return recovered


async def _arecover_projects() -> None:
    """Background recovery (BUG2): offload the heavy state-file I/O so a blocked
    startup never leaves the freshly-launched front's WS proxy connect ETIMEDOUT.
    Uvicorn binds the listening socket BEFORE the lifespan completes, so a
    synchronous recovery (read every state file + re-persist) starves accept().
    The list_states() read runs in a thread; the registration runs back on the
    event loop, so M2 resume timers are armed and `pipelines` is mutated
    race-free (recover_projects is synchronous — atomic w.r.t. other loop tasks)."""
    states = await asyncio.to_thread(list_states)
    recover_projects(states)


@asynccontextmanager
async def _lifespan(app):
    """Recover persisted projects on startup so they stay controllable — without
    blocking startup (the file I/O is offloaded; see _arecover_projects)."""
    app.state.recover_task = asyncio.create_task(_arecover_projects())
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
_runner: AgentRunner = (
    ScriptedRunner() if settings.fake_agents else make_runner(settings.agent_provider)
)


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
    brief: str = ""  # I3: optional imported spec — seeds the brief, skips the interview
    brownfield_path: str = ""  # B1: existing repo to extend


class MessageRequest(BaseModel):
    message: str


class SpecModeRequest(BaseModel):
    mode: str


class RollbackRequest(BaseModel):
    iteration: int


class BudgetRequest(BaseModel):
    budget_usd: float | None = None
    budget_tokens: int | None = None


class ProviderRequest(BaseModel):
    provider: str
    model: str | None = None


class ComponentInput(BaseModel):
    id: str | None = None
    kind: str = "other"
    name: str | None = None
    technology: str | None = None
    rationale: str | None = None
    optional: bool = False
    status: str = "proposed"


class ComponentsRequest(BaseModel):
    components: list[ComponentInput]


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


@app.get("/api/provider")
async def aget_provider() -> dict:
    """Current agent provider/model. In demo mode the scripted backend rules."""
    if settings.fake_agents:
        return {"provider": "fake", "model": "scripted", "available": list(PROVIDERS)}
    return {
        "provider": settings.agent_provider,
        "model": provider_model(settings.agent_provider),
        "available": list(PROVIDERS),
    }


@app.post("/api/provider")
async def aset_provider(req: ProviderRequest) -> dict:
    """Switch the agent backend (claude / openai / ollama) and optionally the
    model, live: new and existing pipelines use it from their next agent call."""
    if settings.fake_agents:
        raise HTTPException(409, "Mode démo (AUTOSPEC_FAKE_AGENTS) : provider verrouillé.")
    provider = req.provider.strip().lower() or "claude"
    if req.model is not None:
        model = req.model.strip()
        if provider == "openai":
            settings.openai_model = model or settings.openai_model
        elif provider == "ollama":
            settings.ollama_model = model or settings.ollama_model
        else:
            settings.claude_model = model or None
    try:
        runner = make_runner(provider)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    settings.agent_provider = provider
    set_runner(runner)
    for pipeline in pipelines.values():
        pipeline.runner = runner
    return {
        "ok": True,
        "provider": settings.agent_provider,
        "model": provider_model(settings.agent_provider),
    }


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
        brief=parse_spec_import(req.brief),
        brownfield_path=(req.brownfield_path or "").strip(),
    )
    state.chat.append(ChatMessage(role=ChatRole.USER, content=req.goal))
    pipeline = Pipeline(state, _runner)
    pipelines[state.id] = pipeline
    pipeline.start()
    return {"id": state.id, "state": state.model_dump(mode="json")}


@app.get("/api/projects")
async def alist_projects() -> list[dict]:
    live = {p.state.id: p.state for p in pipelines.values()}
    stored = {s.id: s for s in await asyncio.to_thread(list_states)}
    stored.update(live)
    return [s.model_dump(mode="json") for s in stored.values()]


@app.get("/api/metrics")
async def ametrics() -> dict:
    """Factory-wide aggregated metrics across all projects (U2)."""
    live = {p.state.id: p.state for p in pipelines.values()}
    stored = {s.id: s for s in await asyncio.to_thread(list_states)}
    stored.update(live)
    return compute_metrics(list(stored.values()))


@app.get("/api/projects/{project_id}/forecast")
async def aforecast(project_id: str) -> dict:
    """Estimate the cost of the project's pending stories (O2), using the
    cross-project average cost/story as a fallback for fresh projects."""
    pipeline = _pipeline(project_id)
    live = {p.state.id: p.state for p in pipelines.values()}
    stored = {s.id: s for s in await asyncio.to_thread(list_states)}
    stored.update(live)
    fallback = compute_metrics(list(stored.values()))["cost_per_story"]
    return forecast_iteration_cost(pipeline.state, fallback)


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


@app.post("/api/projects/{project_id}/approve")
async def aapprove(project_id: str) -> dict:
    """Approve a pending approval gate so the build proceeds (U4)."""
    await _pipeline(project_id).aapprove()
    return {"ok": True}


@app.post("/api/projects/{project_id}/reject")
async def areject(project_id: str) -> dict:
    """Reject a pending approval gate: stop the pipeline (U4)."""
    await _pipeline(project_id).areject()
    return {"ok": True}


@app.get("/api/projects/{project_id}/iterations")
async def aiterations(project_id: str) -> dict:
    """List iteration snapshots available for rollback (R2)."""
    return {"iterations": await _pipeline(project_id).aiterations()}


@app.post("/api/projects/{project_id}/rollback")
async def arollback(project_id: str, req: RollbackRequest) -> dict:
    """Roll the workspace back to an iteration snapshot (R2)."""
    try:
        await _pipeline(project_id).arollback(req.iteration)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"ok": True}


@app.post("/api/projects/{project_id}/cancel-resume")
async def acancel_resume(project_id: str) -> dict:
    """Cancel the M2 scheduled auto-resume of a project."""
    await _pipeline(project_id).acancel_resume()
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


@app.put("/api/projects/{project_id}/components")
async def aset_components(project_id: str, req: ComponentsRequest) -> dict:
    """Replace the project's components (user validation/edition)."""
    pipeline = _pipeline(project_id)
    try:
        await pipeline.aset_components([c.model_dump() for c in req.components])
    except ValueError as exc:  # unknown status value
        raise HTTPException(422, str(exc))
    return {"ok": True, "state": pipeline.state.model_dump(mode="json")}


@app.post("/api/projects/{project_id}/components/setup")
async def asetup_components(project_id: str) -> dict:
    """Materialize the approved components in the workspace (background)."""
    pipeline = _pipeline(project_id)
    await _acall_pipeline(
        pipeline.asetup_components(), f"Projet inconnu : {project_id}"
    )
    return {"ok": True}


@app.post("/api/projects/{project_id}/document")
async def adocument_project(project_id: str) -> dict:
    """Run the tech-writer over the generated project (background README pass)."""
    pipeline = _pipeline(project_id)
    await _acall_pipeline(pipeline.adocument(), f"Projet inconnu : {project_id}")
    return {"ok": True}


@app.post("/api/projects/{project_id}/deploy")
async def adeploy_project(project_id: str) -> dict:
    """Generate deployment artifacts (Dockerfile, CI) for the generated product (D1)."""
    pipeline = _pipeline(project_id)
    try:
        return await pipeline.adeploy()
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/projects/{project_id}/evaluate")
async def aevaluate_project(project_id: str) -> dict:
    """Exercise the generated product and feed findings into the impact pipeline (E6)."""
    pipeline = _pipeline(project_id)
    await _acall_pipeline(pipeline.aevaluate(), f"Projet inconnu : {project_id}")
    return {"ok": True}


@app.post("/api/projects/{project_id}/security-review")
async def asecurity_review_project(project_id: str) -> dict:
    """Audit the generated code + dependencies and feed findings into the impact pipeline (S1)."""
    pipeline = _pipeline(project_id)
    await _acall_pipeline(pipeline.asecurity_review(), f"Projet inconnu : {project_id}")
    return {"ok": True}


@app.post("/api/projects/{project_id}/retro")
async def aretro_project(project_id: str) -> dict:
    """Run the factory retrospective: distil build signals into lessons (E7)."""
    pipeline = _pipeline(project_id)
    await _acall_pipeline(pipeline.aretrospect(), f"Projet inconnu : {project_id}")
    return {"ok": True}


@app.get("/api/projects/{project_id}/export")
async def aexport_zip(project_id: str) -> Response:
    """Download the generated workspace as a zip (VCS/venv/state noise excluded)."""
    pipeline = _pipeline(project_id)
    ws = workspace_dir(project_id)
    if not ws.exists():
        raise HTTPException(404, "Le workspace n'existe pas encore.")

    def _zip() -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in ws.rglob("*"):
                if not path.is_file():
                    continue
                rel = path.relative_to(ws)
                if any(part in _EXCLUDED_DIRS for part in rel.parts[:-1]):
                    continue
                if _is_excluded_file(path.name):
                    continue
                zf.write(path, rel.as_posix())
        return buf.getvalue()

    data = await asyncio.to_thread(_zip)
    filename = re.sub(r"[^a-zA-Z0-9._-]+", "-", pipeline.state.name) or project_id
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}.zip"'},
    )


@app.post("/api/projects/{project_id}/git-export")
async def agit_export(project_id: str) -> dict:
    """Clean git commit of the generated workspace (delivery snapshot)."""
    pipeline = _pipeline(project_id)
    result = await _acall_pipeline(
        pipeline.aexport_git(), f"Projet inconnu : {project_id}"
    )
    return {"ok": True, **result}


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
