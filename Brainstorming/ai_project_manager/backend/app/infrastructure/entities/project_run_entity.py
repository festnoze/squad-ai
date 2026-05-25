"""SQLAlchemy entity for the `project_runs` table.

A `ProjectRun` represents a single invocation of "Lancer l'implémentation"
on a project: the orchestrator is spawned, walks the task graph, and
drives the work to completion (or to a terminal error / blocked state).

One project can accumulate many runs over its lifetime (retries,
re-launches after new tasks get added, ...). At most one run is ever
``running`` at a time — this is enforced by the application service,
not by a SQL constraint, because race conditions on the single-user
local MVP are handled in Python.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.entities.base import GUID, StatefulBase


class ProjectRunEntity(StatefulBase):
    """A single orchestration run over a project's task graph."""

    __tablename__ = "project_runs"

    project_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("projects.id"),
        nullable=False,
        index=True,
    )
    # One of: pending, running, succeeded, failed.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Counters maintained live by the orchestrator so the UI can show
    # progress without scanning `project_run_steps` on every poll.
    total_tasks: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )
    done_tasks: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )
    blocked_tasks: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
    )
