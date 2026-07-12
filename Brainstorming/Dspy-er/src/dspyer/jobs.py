from __future__ import annotations

import asyncio
import logging
import uuid

from .langfuse_service import LangfuseService
from .loop import arun_optimization
from .schemas import JobInfo, JobStatus, OptimizationRequest, utcnow

logger = logging.getLogger(__name__)

MAX_PROGRESS_LINES = 500


class JobManager:
    """In-memory registry of optimization jobs running as asyncio tasks."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobInfo] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def list_jobs(self) -> list[JobInfo]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def get_job(self, job_id: str) -> JobInfo | None:
        return self._jobs.get(job_id)

    def submit(self, request: OptimizationRequest, langfuse: LangfuseService) -> JobInfo:
        job_id = uuid.uuid4().hex[:12]
        now = utcnow()
        job = JobInfo(id=job_id, status=JobStatus.PENDING, created_at=now, updated_at=now, request=request)
        self._jobs[job_id] = job
        task = asyncio.create_task(self._arun_job(job, langfuse))
        self._tasks[job_id] = task
        return job

    def cancel(self, job_id: str) -> JobInfo | None:
        job = self._jobs.get(job_id)
        task = self._tasks.get(job_id)
        if job is None:
            return None
        if task is not None and not task.done():
            task.cancel()
        return job

    async def _arun_job(self, job: JobInfo, langfuse: LangfuseService) -> None:
        def progress(message: str) -> None:
            job.progress.append(message)
            del job.progress[:-MAX_PROGRESS_LINES]
            job.updated_at = utcnow()
            logger.info("[job %s] %s", job.id, message)

        job.status = JobStatus.RUNNING
        job.updated_at = utcnow()
        try:
            result = await arun_optimization(job.request, langfuse, progress=progress)
            job.result = result
            job.status = JobStatus.SUCCEEDED
        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
            job.error = "cancelled by user"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Job %s failed", job.id)
            job.status = JobStatus.FAILED
            job.error = str(exc)
        finally:
            job.updated_at = utcnow()
            self._tasks.pop(job.id, None)


job_manager = JobManager()
