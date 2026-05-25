"""`ProjectRun` domain model (Pydantic).

Represents a single "Lancer l'implémentation" invocation over a project.
One row per run; counters are updated live by the orchestrator so the
frontend can render a progress bar without scanning step rows.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from app.models.base_model import IdStatefulBaseModel


class ProjectRunStatus(str, Enum):
    """Workflow status of a run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProjectRun(IdStatefulBaseModel):
    """A single orchestration run."""

    project_id: UUID
    status: ProjectRunStatus = ProjectRunStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    total_tasks: int = 0
    done_tasks: int = 0
    blocked_tasks: int = 0
