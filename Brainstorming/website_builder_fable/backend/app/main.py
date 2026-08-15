"""FastAPI application entry point.

OWNED BY: scaffold (infrastructure). Module agents READ this file, never edit it.
Run from the backend folder (venv active):
    uvicorn app.main:app --host 127.0.0.1 --port 8300 --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import assets, cms, pages, projects
from app.db import UPLOADS_DIR, ainit_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ainit_db()
    yield


app = FastAPI(title="Website Builder Fable", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5300", "http://127.0.0.1:5300"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api")
app.include_router(pages.router, prefix="/api")
app.include_router(cms.router, prefix="/api")
app.include_router(assets.router, prefix="/api")

# Serve uploaded files: an asset's public URL is /api/uploads/{project_id}/{filename}
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


@app.get("/api/health")
async def ahealth():
    return {"status": "ok"}
