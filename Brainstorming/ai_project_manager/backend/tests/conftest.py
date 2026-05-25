"""Shared pytest fixtures for the AI Project Manager backend.

- `db_session` spins up a throwaway SQLite in-memory database, creates every
  table from `Base.metadata`, and yields an `AsyncSession`.
- `client` returns an `httpx.AsyncClient` bound to a FastAPI app whose
  `get_db` dependency has been overridden to reuse the test session.
"""

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import get_db
from app.infrastructure.entities import Base  # noqa: F401  # registers metadata
from app.main import create_app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a clean in-memory SQLite session per test."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        future=True,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
        class_=AsyncSession,
    )

    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Yield an httpx client wired to a FastAPI app using the test session.

    The underlying FastAPI `app` is attached to the client as `client.app`
    so individual tests can register extra `dependency_overrides` (for
    example to swap the Epic-4 `_get_agent_executor` dependency for a
    no-op fake executor). It's a `setattr` hack because `AsyncClient`
    does not natively expose the transport's app.
    """
    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        ac.app = app  # type: ignore[attr-defined]
        yield ac

    app.dependency_overrides.clear()
