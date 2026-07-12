from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from . import __version__
from .jobs import job_manager
from .langfuse_service import LangfuseService
from .schemas import (
    EvaluatorType,
    JobInfo,
    JobStatus,
    OptimizationMethod,
    OptimizationRequest,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@lru_cache
def get_langfuse_service() -> LangfuseService:
    return LangfuseService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    yield
    try:
        get_langfuse_service().flush()
    except Exception:  # noqa: BLE001 - never fetched (e.g. tests without creds)
        pass


app = FastAPI(
    title="dspyer",
    version=__version__,
    description=(
        "Prompt & model optimization API. Give it a Langfuse prompt, dataset and "
        "evaluators; it runs improvement loops (DSPy, OPRO, Chain-of-Density, few-shot) "
        "and benchmarks candidate models to maximize eval scores."
    ),
    lifespan=lifespan,
)


@app.get("/health")
async def ahealth() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/methods")
async def alist_methods() -> dict:
    return {
        "methods": [m.value for m in OptimizationMethod],
        "evaluator_types": [e.value for e in EvaluatorType],
    }


@app.post("/optimizations", response_model=JobInfo, status_code=202)
async def astart_optimization(request: OptimizationRequest) -> JobInfo:
    try:
        langfuse = get_langfuse_service()
    except Exception as exc:  # noqa: BLE001 - missing/invalid credentials
        raise HTTPException(status_code=503, detail=f"Langfuse client init failed: {exc}") from exc
    return job_manager.submit(request, langfuse)


@app.get("/optimizations", response_model=list[JobInfo])
async def alist_optimizations() -> list[JobInfo]:
    return job_manager.list_jobs()


@app.get("/optimizations/{job_id}", response_model=JobInfo)
async def aget_optimization(job_id: str) -> JobInfo:
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.delete("/optimizations/{job_id}", response_model=JobInfo)
async def acancel_optimization(job_id: str) -> JobInfo:
    job = job_manager.cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/optimizations/{job_id}/best-prompt")
async def aget_best_prompt(job_id: str) -> dict:
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status != JobStatus.SUCCEEDED or job.result is None:
        raise HTTPException(status_code=409, detail=f"job is {job.status.value}, no result yet")
    return {
        "prompt": job.result.best_prompt,
        "model": job.result.best_model,
        "score": job.result.best_score,
        "baseline_score": job.result.baseline_score,
    }


def run() -> None:
    """Entry point: `uv run dspyer-serve`."""
    import uvicorn

    uvicorn.run("dspyer.main:app", host="127.0.0.1", port=8200, reload=False)


if __name__ == "__main__":
    run()
