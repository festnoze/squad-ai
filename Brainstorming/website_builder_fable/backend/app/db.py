"""Database setup: async SQLite engine, session factory, declarative Base.

OWNED BY: scaffold (infrastructure). Module agents READ this file, never edit it.

Exposes:
- DB_PATH, UPLOADS_DIR (Path constants, env-var overridable for tests)
- engine, async_session, Base
- aget_session (FastAPI dependency)
- ainit_db (create data dirs + create_all; called from the app lifespan)
"""

import os
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

_BACKEND_DIR = Path(__file__).resolve().parent.parent

DB_PATH = Path(os.environ.get("WBF_DB_PATH") or (_BACKEND_DIR / "data" / "app.db"))
UPLOADS_DIR = Path(os.environ.get("WBF_UPLOADS_DIR") or (_BACKEND_DIR / "data" / "uploads"))

DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"

engine = create_async_engine(DATABASE_URL, echo=False)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def aget_session():
    """FastAPI dependency yielding an AsyncSession."""
    async with async_session() as session:
        yield session


async def ainit_db():
    """Create data directories and all tables. Idempotent."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    # Import model modules so their tables register on Base.metadata.
    from app import models_cms, models_core  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
