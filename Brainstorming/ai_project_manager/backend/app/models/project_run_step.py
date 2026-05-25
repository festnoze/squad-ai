"""`ProjectRunStep` domain model (Pydantic).

Append-only log entry for an observable agent action inside a run.
Steps are inserted at start time and patched at finish time by the
single background task that drives the run, so there is no concurrent
writer risk on a given row.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from app.models.base_model import IdStatefulBaseModel


class ProjectRunStepRole(str, Enum):
    """Which agent produced the step."""

    ORCHESTRATOR = "orchestrator"
    DEV = "dev"
    QA = "qa"


class ProjectRunStepStatus(str, Enum):
    """Terminal state of a step."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"  # QA step that returned a rejection verdict


class ProjectRunStep(IdStatefulBaseModel):
    """A single agent step inside a run."""

    run_id: UUID
    item_id: UUID | None = None
    role: ProjectRunStepRole
    status: ProjectRunStepStatus
    iteration: int = 0
    summary: str
    detail: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
