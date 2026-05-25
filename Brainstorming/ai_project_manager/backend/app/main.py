"""FastAPI application entry point.

Creates the FastAPI app, configures CORS, registers routers and exposes
a `lifespan` hook for startup/shutdown logging.

V1 addition: the lifespan hook also calls
`ProjectRunService.arecover_orphan_runs()` so any run left in a non-terminal
state by a previous process is flipped to ``failed`` with reason
``server_restart``. This prevents the frontend from showing a stuck
progress bar after a backend restart.
"""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.application.project_run_service import ProjectRunService
from app.config import get_settings
from app.routers.chat_router import router as chat_router
from app.routers.health_router import router as health_router
from app.routers.items_router import router as items_router
from app.routers.project_router import router as project_router
from app.routers.project_run_router import router as project_run_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
    """App lifecycle hook: log startup/shutdown + recover orphan runs."""
    settings = get_settings()
    logger.info("Starting %s", settings.app_name)
    logger.info("Database URL: %s", settings.database_url)
    if not settings.openai_api_key:
        logger.warning(
            "OPENAI_API_KEY is not set — LLM-backed chat features will 503",
        )
    logger.info(
        "LLM_INFO: type=%s model=%s",
        settings.llm_info.get("type"),
        settings.llm_info.get("model"),
    )

    # V1: flip any "running" run left over from a previous process to
    # "failed" with reason "server_restart". Best-effort: if the DB is
    # not yet migrated (cold-start with no tables), swallow the error.
    try:
        await ProjectRunService().arecover_orphan_runs()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Orphan-run recovery skipped: %s", exc)

    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    """Application factory — useful for tests that need a fresh app."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(project_router)
    app.include_router(chat_router)
    app.include_router(items_router)
    app.include_router(project_run_router)

    return app


app = create_app()
