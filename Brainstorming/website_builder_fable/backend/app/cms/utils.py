"""Shared CMS helpers: timestamps, slugs, project existence check.

OWNED BY: backend-cms agent.

The projects table itself is owned by the backend-core agent (models_core.py).
To keep this module independently testable we check project existence with a
raw SQL query instead of importing a core model; a missing table simply means
"no such project".
"""

import re
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession


def now_iso() -> str:
    """ISO 8601 UTC timestamp with a trailing Z (second precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(value: str) -> str:
    """Lowercase [a-z0-9-]+ slug derived from an arbitrary string."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


async def aensure_project(session: AsyncSession, project_id: int) -> None:
    """Raise 404 unless the project exists."""
    try:
        result = await session.execute(
            text("SELECT 1 FROM projects WHERE id = :pid"), {"pid": project_id}
        )
        found = result.first() is not None
    except OperationalError:
        # projects table not created yet (core module absent): no project exists
        await session.rollback()
        found = False
    if not found:
        raise HTTPException(status_code=404, detail="Project not found")
