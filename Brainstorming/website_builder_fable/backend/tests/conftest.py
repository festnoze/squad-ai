"""Shared test fixtures.

OWNED BY: scaffold (infrastructure). Module agents READ this file, never edit it.
Provides an async httpx client bound to the app with a temporary SQLite db
and a temporary uploads dir (fresh per test function).

IMPORTANT: env vars are set BEFORE importing app modules, because app.db
reads WBF_DB_PATH / WBF_UPLOADS_DIR at import time.
"""

import os
import tempfile
from pathlib import Path

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="wbf_tests_"))
os.environ["WBF_DB_PATH"] = str(_TMP_ROOT / "test.db")
os.environ["WBF_UPLOADS_DIR"] = str(_TMP_ROOT / "uploads")

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.db import Base, ainit_db, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
async def client():
    """Async client against the app, with a fresh (empty) schema per test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await ainit_db()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
