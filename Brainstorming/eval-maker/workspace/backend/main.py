"""FastAPI application entry point with all routers, CORS, and lifespan."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.database import ainit_db

# Import all models so Base.metadata knows about them
import backend.models  # noqa: F401

from backend.routers import (
    extract,
    rules,
    cluster,
    judges,
    dataset,
    langfuse,
    evals,
    heatmap,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle: create DB tables on boot."""
    # Ensure data directory exists
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(exist_ok=True)

    logger.info("Initializing database...")
    await ainit_db()
    logger.info("Database initialized.")

    yield

    logger.info("Shutting down.")


app = FastAPI(
    title="Eval Suite Generator",
    description="Generates evaluation suites for the SkillForge tutoring prompt",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers under /api/v1 prefix
API_PREFIX = "/api/v1"

app.include_router(extract.router, prefix=API_PREFIX, tags=["extract"])
app.include_router(rules.router, prefix=API_PREFIX, tags=["rules"])
app.include_router(cluster.router, prefix=API_PREFIX, tags=["cluster"])
app.include_router(judges.router, prefix=API_PREFIX, tags=["judges"])
app.include_router(dataset.router, prefix=API_PREFIX, tags=["dataset"])
app.include_router(langfuse.router, prefix=API_PREFIX, tags=["langfuse"])
app.include_router(evals.router, prefix=API_PREFIX, tags=["evals"])
app.include_router(heatmap.router, prefix=API_PREFIX, tags=["heatmap"])


@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}


# Serve frontend static files (MUST come after all API router includes)
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
