"""Local MVP HTTP application and production frontend host."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from pmx.agents.registry import agent_summaries
from pmx.analysis.signals import PROTOCOL
from pmx.api.analyses import AnalysisService
from pmx.api.campaigns import CampaignService
from pmx.api.catalogue import Catalogue
from pmx.api.models import AnalysisSettingsRequest, CampaignRequest, RunRequest, SignalRequest
from pmx.api.service import RunService
from pmx.api.signals import SignalService
from pmx.errors import PmxError


def create_app(
    *,
    dataset_root: Path = Path("data/datasets"),
    runs_dir: Path = Path("runs/mvp"),
    web_dist: Path = Path("web/dist"),
) -> FastAPI:
    """Create an isolated app; explicit directories make integration tests and local launches repeatable."""
    catalogue = Catalogue(dataset_root)
    service = RunService(catalogue, runs_dir)
    analyses = AnalysisService(dataset_root, runs_dir)
    campaigns = CampaignService(service, on_completed=analyses.enqueue_auto)
    signals = SignalService(catalogue, runs_dir)
    dist = web_dist.resolve()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        analyses.recover()
        yield
        service.close()
        analyses.close()
        signals.close()

    app = FastAPI(
        title="pmx MVP",
        version="1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.catalogue = catalogue
    app.state.run_service = service
    app.state.campaign_service = campaigns
    app.state.analysis_service = analyses
    app.state.signal_service = signals

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        details = "; ".join(
            f"{'.'.join(str(part) for part in row['loc'][1:])}: {row['msg']}" for row in error.errors()
        )
        return JSONResponse(status_code=422, content={"detail": details})

    @app.exception_handler(KeyError)
    async def missing(request: Request, error: KeyError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(error.args[0])})

    @app.exception_handler(ValueError)
    @app.exception_handler(PmxError)
    async def invalid_data(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @app.exception_handler(RuntimeError)
    async def busy(request: Request, error: RuntimeError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "dataset_available": bool(catalogue.names())}

    @app.get("/api/datasets")
    def datasets() -> dict[str, Any]:
        return {"datasets": [catalogue.summary(name) for name in catalogue.names()]}

    @app.get("/api/datasets/{name}")
    def dataset(name: str) -> dict[str, Any]:
        return catalogue.summary(name)

    @app.get("/api/datasets/{name}/markets")
    def markets(
        name: str,
        provider: Literal["kalshi", "manifold", "polymarket"] | None = None,
        fold: Literal["train", "validation"] | None = None,
        category: Annotated[str, Query(max_length=100)] = "",
        q: Annotated[str, Query(max_length=300)] = "",
        page: Annotated[int, Query(ge=1, le=100_000)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> dict[str, Any]:
        query = q.casefold().strip()
        rows = [
            row
            for row in catalogue.markets(name)
            if (not provider or row["provider"] == provider)
            and (not fold or row["fold"] == fold)
            and (not category or row["category"] == category)
            and (not query or query in f"{row['id']} {row['question']}".casefold())
        ]
        offset = (page - 1) * page_size
        return {"items": rows[offset : offset + page_size], "total": len(rows), "page": page, "page_size": page_size}

    @app.get("/api/datasets/{name}/markets/{market_id}")
    def market(name: str, market_id: str) -> dict[str, Any]:
        return catalogue.detail(name, market_id)

    @app.get("/api/agents")
    def agents() -> dict[str, Any]:
        return {"agents": agent_summaries()}

    @app.get("/api/signal-studies/protocol")
    def signal_protocol() -> dict[str, Any]:
        return PROTOCOL

    @app.get("/api/signal-studies")
    def signal_history() -> dict[str, Any]:
        return {"studies": signals.history()}

    @app.post("/api/signal-studies", status_code=202)
    def submit_signals(request: SignalRequest) -> dict[str, Any]:
        return signals.submit(request.dataset)

    @app.get("/api/signal-studies/{study_id}")
    def signal_detail(study_id: str) -> dict[str, Any]:
        return signals.detail(study_id)

    @app.get("/api/signal-studies/{study_id}/export")
    def signal_export(study_id: str) -> FileResponse:
        return FileResponse(signals.export(study_id), filename=f"pmx-{study_id}.json")

    @app.get("/api/signal-studies/{study_id}/observations")
    def signal_observations(study_id: str) -> FileResponse:
        return FileResponse(signals.export(study_id, observations=True), filename=f"pmx-{study_id}-observations.json")

    @app.post("/api/runs", status_code=202)
    def submit(request: RunRequest) -> dict[str, Any]:
        return service.submit(request)

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str) -> dict[str, Any]:
        return service.get_job(job_id)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str) -> dict[str, Any]:
        return campaigns.cancel(job_id)

    @app.post("/api/campaigns", status_code=202)
    def submit_campaign(request: CampaignRequest) -> dict[str, Any]:
        return campaigns.submit(request)

    @app.get("/api/campaigns")
    def campaign_history() -> dict[str, Any]:
        return {"campaigns": campaigns.history()}

    @app.get("/api/campaigns/{campaign_id}")
    def campaign_detail(campaign_id: str) -> dict[str, Any]:
        return campaigns.detail(campaign_id)

    @app.get("/api/campaigns/{campaign_id}/export")
    def export_campaign(campaign_id: str) -> JSONResponse:
        return JSONResponse(campaigns.detail(campaign_id), headers={
            "Content-Disposition": f'attachment; filename="pmx-{campaign_id}.json"',
        })

    @app.get("/api/analysis/settings")
    def analysis_settings() -> dict[str, Any]:
        return analyses.settings()

    @app.post("/api/analysis/settings")
    def configure_analysis(request: AnalysisSettingsRequest) -> dict[str, Any]:
        return analyses.configure(enabled=request.enabled)

    @app.get("/api/campaigns/{campaign_id}/analysis")
    def analysis(campaign_id: str) -> dict[str, Any]:
        campaigns.detail(campaign_id)
        return analyses.detail(campaign_id)

    @app.post("/api/campaigns/{campaign_id}/analysis", status_code=202)
    def request_analysis(campaign_id: str) -> dict[str, Any]:
        return analyses.submit(campaign_id, retry=True)

    @app.get("/api/campaigns/{campaign_id}/analysis/export")
    def export_analysis(campaign_id: str) -> FileResponse:
        return FileResponse(analyses.export(campaign_id), filename=f"pmx-{campaign_id}-analysis.md")

    @app.get("/api/campaigns/{campaign_id}/analysis/evidence")
    def export_analysis_evidence(campaign_id: str) -> FileResponse:
        return FileResponse(analyses.export(campaign_id, evidence=True), filename=f"pmx-{campaign_id}-evidence.json")

    @app.get("/api/runs")
    def runs() -> dict[str, Any]:
        return {"runs": service.history()}

    @app.get("/api/runs/{run_id}")
    def run(run_id: str) -> dict[str, Any]:
        return service.detail(run_id)

    @app.get("/api/runs/{run_id}/export")
    def export_run(run_id: str) -> JSONResponse:
        detail = service.detail(run_id)
        return JSONResponse(
            detail, headers={"Content-Disposition": f'attachment; filename="pmx-{run_id}.json"'}
        )

    @app.get("/api/runs/{run_id}/markets/{market_id}")
    def replay_market(run_id: str, market_id: str) -> dict[str, Any]:
        return service.market_replay(run_id, market_id)

    @app.get("/api/runs/{run_id}/markets/{market_id}/export")
    def export_replay(run_id: str, market_id: str) -> JSONResponse:
        payload = service.market_replay(run_id, market_id)
        return JSONResponse(
            payload, headers={"Content-Disposition": f'attachment; filename="pmx-{run_id}-replay.json"'}
        )

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Endpoint API introuvable.")
        candidate = (dist / path).resolve()
        if not candidate.is_relative_to(dist):
            raise HTTPException(status_code=404, detail="Fichier introuvable.")
        if candidate.is_file():
            return FileResponse(candidate)
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Interface non construite. Exécutez npm run build dans web.")

    return app
