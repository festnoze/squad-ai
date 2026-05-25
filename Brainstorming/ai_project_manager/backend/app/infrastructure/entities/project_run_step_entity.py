"""SQLAlchemy entity for the `project_run_steps` table.

Every step represents an observable agent action taken during a run:
* an orchestrator decision (``role="orchestrator"``)
* a DevAgent invocation on a specific task (``role="dev"``)
* a QaAgent invocation on a specific task (``role="qa"``)

Steps are append-only: once written, they are never mutated. The
``status`` field captures the terminal state of the step itself
(``running``, ``succeeded``, ``failed``, ``rejected``). The orchestrator
writes steps as they start and patches them at the end via a short
transaction, which is fine because we only ever write them from the
single background task that drives the run.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.entities.base import GUID, StatefulBase


class ProjectRunStepEntity(StatefulBase):
    """A single observable agent action inside a `ProjectRun`."""

    __tablename__ = "project_run_steps"

    run_id: Mapped[UUID] = mapped_column(
        GUID(),
        ForeignKey("project_runs.id"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[UUID | None] = mapped_column(
        GUID(),
        ForeignKey("items.id"),
        nullable=True,
    )
    # One of: orchestrator, dev, qa
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # One of: running, succeeded, failed, rejected
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # QA iteration number (1 for the first dev/QA round, 2 for the
    # second if QA rejected). 0 for orchestrator steps.
    iteration: Mapped[int] = mapped_column(nullable=False, default=0)
    # Short human-readable message shown in the UI log.
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional detailed payload (prompt, response, files touched, etc.).
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
