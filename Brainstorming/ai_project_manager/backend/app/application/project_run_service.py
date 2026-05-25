"""V1 orchestration service: run the whole project's task graph.

This is the module the `/api/projects/{id}/runs` endpoint delegates to.
It encapsulates every piece of business logic that V1 introduces:

1. **Start a run** (``astart_project_run``)
   - Refuse if one is already running for the project.
   - Insert a ``project_runs`` row in status ``running``.
   - Count TODO tasks and persist it as ``total_tasks``.
   - Spawn a detached asyncio task that drives the orchestration.

2. **Drive the graph** (``_aexecute_run``, background task)
   - Load the current tasks + dependency graph.
   - While work remains:
     * Compute the set of executable tasks (all deps terminal).
     * Ask the `OrchestratorAgent` to pick the next batch.
     * Launch each task in parallel inside a semaphore.
     * Wait for the batch to finish, update the counters, continue.
   - Mark the run ``succeeded`` when every task is in a terminal
     status, or ``failed`` if an unrecoverable error bubbles up.

3. **Run a single task** (``_arun_single_task``)
   - Flip the item to ``in_progress``.
   - Call the `DevAgent` to produce real code.
   - Flip the item to ``in_test`` and call the `QaAgent`.
   - If approved: flip to ``done``, persist deliverable paths.
   - If rejected and iterations remain: loop with QA feedback.
   - If rejected twice: flip to ``blocked`` with the last feedback.

4. **Cleanup orphan runs** (``arecover_orphan_runs``)
   - Called at app startup. Every run still marked ``running`` from a
     previous process is flipped to ``failed`` with a clear error.

The service is careful to use **short-lived database sessions**
everywhere inside the background task, because the HTTP request that
triggered the run is long gone. `AsyncSessionLocal` is imported lazily
inside helper methods so tests can monkeypatch it.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from app.agents.dev_agent import DevAgent, DevAgentFailure, DevAgentResult
from app.agents.orchestrator_agent import OrchestratorAgent
from app.agents.qa_agent import QaAgent, QaVerdict
from app.infrastructure.common import get_utc_now
from app.infrastructure.item_dependency_repository import (
    ItemDependencyRepository,
)
from app.infrastructure.item_repository import ItemRepository
from app.infrastructure.project_run_repository import ProjectRunRepository
from app.models.item import Item, ItemStatus, ItemType
from app.models.project_run import ProjectRun, ProjectRunStatus
from app.models.project_run_step import (
    ProjectRunStep,
    ProjectRunStepRole,
    ProjectRunStepStatus,
)


logger = logging.getLogger(__name__)


# Maximum number of tasks the orchestrator runs in parallel. Kept as a
# module-level constant (not a setting) because the orchestration is
# already I/O-bound and the user never asked for tuning knobs.
MAX_PARALLEL_TASKS = 3

# How many dev/QA iterations we tolerate on a single task before
# marking it ``blocked``. 2 means: first pass, second pass after
# feedback, then give up.
MAX_TASK_ITERATIONS = 2


class ProjectRunConflict(Exception):
    """Raised when a run is requested while another is already running."""


@dataclass
class _TaskContext:
    """Small bag of per-task state used by ``_arun_single_task``."""

    task: Item
    run_id: UUID


# ---------------------------------------------------------------------------
# Public service
# ---------------------------------------------------------------------------


class ProjectRunService:
    """Top-level facade used by the router and the startup hook."""

    def __init__(
        self,
        *,
        # Injectable factories so tests can plug in fakes. None means
        # "build a fresh instance with the default singletons".
        dev_agent_factory: Callable[[], DevAgent] | None = None,
        qa_agent_factory: Callable[[], QaAgent] | None = None,
        orchestrator_factory: Callable[[], OrchestratorAgent] | None = None,
        session_factory: Any | None = None,
        max_parallel: int = MAX_PARALLEL_TASKS,
        max_iterations: int = MAX_TASK_ITERATIONS,
    ) -> None:
        self._dev_agent_factory = dev_agent_factory or (lambda: DevAgent())
        self._qa_agent_factory = qa_agent_factory or (lambda: QaAgent())
        self._orchestrator_factory = (
            orchestrator_factory or (lambda: OrchestratorAgent())
        )
        self._session_factory = session_factory
        self._max_parallel = max(1, max_parallel)
        self._max_iterations = max(1, max_iterations)

    # ------------------------------------------------------------------
    # Startup hook: mark orphan runs as failed
    # ------------------------------------------------------------------

    async def arecover_orphan_runs(self) -> int:
        """Mark every running/pending run as failed (server_restart).

        Called once on app startup. Returns the number of rows patched.
        """
        session_factory = self._resolve_session_factory()
        async with session_factory() as session:
            repo = ProjectRunRepository(session)
            orphans = await repo.aget_orphan_running_runs()
            for run in orphans:
                if run.id is None:
                    continue
                now = get_utc_now()
                await repo.aupdate_run_fields(
                    run.id,
                    status=ProjectRunStatus.FAILED,
                    finished_at=now,
                    error="server_restart",
                )
            await session.commit()
        if orphans:
            logger.warning(
                "Recovered %d orphan run(s) from a previous process",
                len(orphans),
            )
        return len(orphans)

    # ------------------------------------------------------------------
    # Start a new run
    # ------------------------------------------------------------------

    async def astart_project_run(
        self,
        *,
        session: Any,
        project_id: UUID,
    ) -> ProjectRun:
        """Create a run + spawn the background task that drives it.

        Reuses the caller's session (the HTTP request's) to perform
        the initial insert, then spawns a detached asyncio task that
        opens its own short-lived sessions for the rest of the work.
        """
        run_repo = ProjectRunRepository(session)

        # Refuse if a run is already in flight.
        existing = await run_repo.aget_active_run_for_project(project_id)
        if existing is not None:
            raise ProjectRunConflict(
                f"Project {project_id} already has an active run "
                f"({existing.id}).",
            )

        # Count executable TODO tasks so the progress bar has a denominator.
        item_repo = ItemRepository(session)
        all_items = await item_repo.aget_items_by_project(project_id)
        task_items = [
            it for it in all_items if it.type == ItemType.TASK
        ]
        total_tasks = sum(
            1 for it in task_items if it.status == ItemStatus.TODO
        )

        now = get_utc_now()
        run = await run_repo.acreate_run(
            ProjectRun(
                project_id=project_id,
                status=ProjectRunStatus.RUNNING,
                started_at=now,
                total_tasks=total_tasks,
            ),
        )
        if run.id is None:
            raise RuntimeError("Failed to persist the project run row.")

        # Log the initial orchestrator decision step synchronously so the
        # frontend sees something immediately after the POST.
        await run_repo.acreate_step(
            ProjectRunStep(
                run_id=run.id,
                role=ProjectRunStepRole.ORCHESTRATOR,
                status=ProjectRunStepStatus.SUCCEEDED,
                iteration=0,
                summary=(
                    f"Run démarré. {total_tasks} task(s) à exécuter."
                ),
                started_at=now,
                finished_at=now,
            ),
        )
        await session.commit()

        # Detach the worker: the HTTP request returns 202 while it runs.
        asyncio.create_task(self._aexecute_run_safely(run.id))
        return run

    # ------------------------------------------------------------------
    # Background driver
    # ------------------------------------------------------------------

    async def _aexecute_run_safely(self, run_id: UUID) -> None:
        """Top-level background task: catch-all so nothing leaks out."""
        try:
            await self._aexecute_run(run_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Run %s crashed: %s", run_id, exc)
            await self._amark_run_failed(run_id, exc)

    async def _aexecute_run(self, run_id: UUID) -> None:
        """Main orchestration loop for a single run."""
        orchestrator = self._orchestrator_factory()
        semaphore = asyncio.Semaphore(self._max_parallel)

        while True:
            # Re-load the graph on every iteration so we observe fresh
            # status transitions written by previous batches.
            snapshot = await self._aload_run_snapshot(run_id)
            if snapshot is None:
                logger.warning(
                    "Run %s vanished mid-execution, aborting.",
                    run_id,
                )
                return

            executable = self._compute_executable_tasks(
                tasks=snapshot.tasks,
                dependencies=snapshot.dependencies,
            )

            if not executable:
                # If no task is executable AND none are still running
                # (ie. none are in in_progress / in_test), we are done.
                in_flight = [
                    t for t in snapshot.tasks
                    if t.status
                    in (ItemStatus.IN_PROGRESS, ItemStatus.IN_TEST)
                ]
                if not in_flight:
                    await self._amark_run_succeeded(run_id, snapshot.tasks)
                    return
                # Otherwise wait a beat for the in-flight tasks to land.
                await asyncio.sleep(0.1)
                continue

            # Ask the orchestrator LLM for its picks (or fallback).
            decision = await orchestrator.apick_next_batch(
                executable_tasks=executable,
                max_parallel=self._max_parallel,
            )
            await self._arecord_orchestrator_decision(run_id, decision)

            # Index the tasks by id for easy lookup.
            by_id = {t.id: t for t in executable if t.id is not None}
            selected = [
                by_id[uid] for uid in decision.selected_task_ids if uid in by_id
            ]
            if not selected:
                # Orchestrator returned nothing usable — pick the first
                # executable task as a safety net.
                selected = executable[:1]

            # Kick them off in parallel, bounded by the semaphore.
            await asyncio.gather(
                *(
                    self._arun_single_task_with_semaphore(
                        semaphore=semaphore,
                        task=task,
                        run_id=run_id,
                    )
                    for task in selected
                ),
            )

            # Loop: the next iteration will reload the graph and pick again.

    # ------------------------------------------------------------------
    # Single task driver
    # ------------------------------------------------------------------

    async def _arun_single_task_with_semaphore(
        self,
        *,
        semaphore: asyncio.Semaphore,
        task: Item,
        run_id: UUID,
    ) -> None:
        async with semaphore:
            await self._arun_single_task(_TaskContext(task=task, run_id=run_id))

    async def _arun_single_task(self, ctx: _TaskContext) -> None:
        """Dev/QA loop for a single task with bounded iterations."""
        task = ctx.task
        if task.id is None:
            return
        await self._aset_item_status(task.id, ItemStatus.IN_PROGRESS)

        dev_agent = self._dev_agent_factory()
        qa_agent = self._qa_agent_factory()
        last_feedback: str | None = None
        dev_result: DevAgentResult | None = None

        for iteration in range(1, self._max_iterations + 1):
            # --- Dev step -------------------------------------------------
            dev_step_id = await self._arecord_step(
                run_id=ctx.run_id,
                item_id=task.id,
                role=ProjectRunStepRole.DEV,
                status=ProjectRunStepStatus.RUNNING,
                iteration=iteration,
                summary=f"Dev itération {iteration}: génération du code",
            )
            try:
                dev_result = await dev_agent.aproduce_deliverable(
                    task,
                    qa_feedback=last_feedback,
                )
            except DevAgentFailure as exc:
                await self._aupdate_step(
                    step_id=dev_step_id,
                    status=ProjectRunStepStatus.FAILED,
                    summary=(
                        f"Dev itération {iteration} échouée: {exc}"
                    ),
                    detail=str(exc),
                )
                await self._amark_task_blocked(
                    task_id=task.id,
                    reason=f"DevAgent failure (iter {iteration}): {exc}",
                    run_id=ctx.run_id,
                )
                return

            relative_paths = [f.relative_path for f in dev_result.files]
            await self._aupdate_step(
                step_id=dev_step_id,
                status=ProjectRunStepStatus.SUCCEEDED,
                summary=(
                    f"Dev itération {iteration}: "
                    f"{len(relative_paths)} fichier(s) générés"
                ),
                detail=dev_result.summary,
            )
            # Persist the deliverable paths right now so the UI can show
            # them even if QA rejects later (the user can still inspect
            # what the dev agent produced).
            await self._apersist_task_deliverable(
                task_id=task.id,
                paths=relative_paths,
                notes=dev_result.summary,
            )
            await self._aset_item_status(task.id, ItemStatus.IN_TEST)

            # --- QA step --------------------------------------------------
            qa_step_id = await self._arecord_step(
                run_id=ctx.run_id,
                item_id=task.id,
                role=ProjectRunStepRole.QA,
                status=ProjectRunStepStatus.RUNNING,
                iteration=iteration,
                summary=f"QA itération {iteration}: relecture",
            )
            qa_result = await qa_agent.areview_deliverable(task, dev_result)
            if qa_result.verdict == QaVerdict.APPROVED:
                await self._aupdate_step(
                    step_id=qa_step_id,
                    status=ProjectRunStepStatus.SUCCEEDED,
                    summary=f"QA itération {iteration}: approuvée",
                    detail=qa_result.feedback,
                )
                await self._aappend_task_notes(
                    task_id=task.id,
                    note=(
                        f"\n\n## QA itération {iteration} (approuvée)\n"
                        f"{qa_result.feedback}"
                    ),
                )
                await self._aset_item_status(task.id, ItemStatus.DONE)
                await self._aincrement_run_counter(
                    run_id=ctx.run_id,
                    field="done_tasks",
                )
                return

            # Rejected: record and loop (or give up).
            await self._aupdate_step(
                step_id=qa_step_id,
                status=ProjectRunStepStatus.REJECTED,
                summary=f"QA itération {iteration}: rejet",
                detail=qa_result.feedback,
            )
            await self._aappend_task_notes(
                task_id=task.id,
                note=(
                    f"\n\n## QA itération {iteration} (rejet)\n"
                    f"{qa_result.feedback}"
                ),
            )
            last_feedback = qa_result.feedback
            if iteration >= self._max_iterations:
                await self._amark_task_blocked(
                    task_id=task.id,
                    reason=(
                        f"QA rejected {self._max_iterations} times. "
                        f"Last feedback: {qa_result.feedback}"
                    ),
                    run_id=ctx.run_id,
                )
                return
            # else: loop to a new dev iteration with the feedback injected.

    # ------------------------------------------------------------------
    # Snapshot loader
    # ------------------------------------------------------------------

    @dataclass
    class _RunSnapshot:
        """Cached view of a project's tasks + dependency graph."""

        tasks: list[Item]
        dependencies: list[tuple[UUID, UUID]]

    async def _aload_run_snapshot(
        self,
        run_id: UUID,
    ) -> "ProjectRunService._RunSnapshot | None":
        """Load the task list + dep graph for the run's project."""
        session_factory = self._resolve_session_factory()
        async with session_factory() as session:
            run_repo = ProjectRunRepository(session)
            run = await run_repo.aget_run_by_id(run_id)
            if run is None:
                return None
            item_repo = ItemRepository(session)
            dep_repo = ItemDependencyRepository(session)
            items = await item_repo.aget_items_by_project(run.project_id)
            deps_models = await dep_repo.aget_dependencies_for_project(
                run.project_id,
            )
        tasks = [it for it in items if it.type == ItemType.TASK]
        dependencies = [
            (d.item_id, d.depends_on_item_id) for d in deps_models
        ]
        return ProjectRunService._RunSnapshot(
            tasks=tasks,
            dependencies=dependencies,
        )

    # ------------------------------------------------------------------
    # Dependency resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_executable_tasks(
        tasks: list[Item],
        dependencies: list[tuple[UUID, UUID]],
    ) -> list[Item]:
        """Return every TODO task whose dependencies are terminal.

        A dep is terminal when its target is in status ``done`` or
        ``blocked``. Blocking a task still unblocks its downstream
        consumers — otherwise a single flaky LLM call would stall the
        whole run. This is a deliberate trade-off: V1 prioritises
        progress over strict correctness.
        """
        by_id = {t.id: t for t in tasks if t.id is not None}
        terminal = {
            tid
            for tid, task in by_id.items()
            if task.status in (ItemStatus.DONE, ItemStatus.BLOCKED)
        }
        incoming: dict[UUID, list[UUID]] = {}
        for item_id, depends_on in dependencies:
            if item_id not in by_id:
                continue
            incoming.setdefault(item_id, []).append(depends_on)

        executable: list[Item] = []
        for task in tasks:
            if task.id is None:
                continue
            if task.status != ItemStatus.TODO:
                continue
            deps = incoming.get(task.id, [])
            if all(dep in terminal or dep not in by_id for dep in deps):
                executable.append(task)
        return executable

    # ------------------------------------------------------------------
    # Low-level DB helpers (each one owns its session)
    # ------------------------------------------------------------------

    def _resolve_session_factory(self) -> Any:
        """Return the session factory, imported lazily to allow tests."""
        if self._session_factory is not None:
            return self._session_factory
        from app.database import AsyncSessionLocal
        return AsyncSessionLocal

    async def _aset_item_status(
        self,
        item_id: UUID,
        status: ItemStatus,
    ) -> None:
        session_factory = self._resolve_session_factory()
        async with session_factory() as session:
            repo = ItemRepository(session)
            await repo.aupdate_item(item_id, status=status)
            await session.commit()

    async def _apersist_task_deliverable(
        self,
        task_id: UUID,
        paths: list[str],
        notes: str,
    ) -> None:
        session_factory = self._resolve_session_factory()
        async with session_factory() as session:
            repo = ItemRepository(session)
            # Keep the notes additive so we don't clobber earlier iterations.
            current = await repo.aget_item_by_id(task_id)
            existing_notes = current.deliverable_notes if current else None
            merged_notes = (
                f"{existing_notes}\n\n{notes}".strip()
                if existing_notes and notes
                else (notes or existing_notes or None)
            )
            await repo.aupdate_item(
                task_id,
                deliverable_paths=paths,
                deliverable_notes=merged_notes,
            )
            await session.commit()

    async def _aappend_task_notes(
        self,
        task_id: UUID,
        note: str,
    ) -> None:
        if not note.strip():
            return
        session_factory = self._resolve_session_factory()
        async with session_factory() as session:
            repo = ItemRepository(session)
            current = await repo.aget_item_by_id(task_id)
            existing = current.deliverable_notes if current else None
            merged = f"{existing or ''}{note}".strip()
            await repo.aupdate_item(task_id, deliverable_notes=merged)
            await session.commit()

    async def _amark_task_blocked(
        self,
        task_id: UUID,
        reason: str,
        run_id: UUID,
    ) -> None:
        session_factory = self._resolve_session_factory()
        async with session_factory() as session:
            item_repo = ItemRepository(session)
            await item_repo.aupdate_item(
                task_id,
                status=ItemStatus.BLOCKED,
                blocked_reason=reason,
            )
            run_repo = ProjectRunRepository(session)
            run = await run_repo.aget_run_by_id(run_id)
            if run is not None and run.id is not None:
                await run_repo.aupdate_run_fields(
                    run.id,
                    blocked_tasks=run.blocked_tasks + 1,
                )
            await session.commit()

    async def _aincrement_run_counter(
        self,
        run_id: UUID,
        field: str,
    ) -> None:
        session_factory = self._resolve_session_factory()
        async with session_factory() as session:
            repo = ProjectRunRepository(session)
            run = await repo.aget_run_by_id(run_id)
            if run is None or run.id is None:
                return
            current = getattr(run, field, 0)
            await repo.aupdate_run_fields(run.id, **{field: current + 1})
            await session.commit()

    async def _arecord_step(
        self,
        *,
        run_id: UUID,
        item_id: UUID | None,
        role: ProjectRunStepRole,
        status: ProjectRunStepStatus,
        iteration: int,
        summary: str,
    ) -> UUID:
        session_factory = self._resolve_session_factory()
        async with session_factory() as session:
            repo = ProjectRunRepository(session)
            now = get_utc_now()
            step = await repo.acreate_step(
                ProjectRunStep(
                    run_id=run_id,
                    item_id=item_id,
                    role=role,
                    status=status,
                    iteration=iteration,
                    summary=summary,
                    started_at=now,
                ),
            )
            await session.commit()
        if step.id is None:
            raise RuntimeError("Failed to persist a project_run_step row.")
        return step.id

    async def _aupdate_step(
        self,
        *,
        step_id: UUID,
        status: ProjectRunStepStatus,
        summary: str | None = None,
        detail: str | None = None,
    ) -> None:
        session_factory = self._resolve_session_factory()
        async with session_factory() as session:
            repo = ProjectRunRepository(session)
            fields: dict[str, Any] = {
                "status": status,
                "finished_at": get_utc_now(),
            }
            if summary is not None:
                fields["summary"] = summary
            if detail is not None:
                fields["detail"] = detail
            await repo.aupdate_step_fields(step_id, **fields)
            await session.commit()

    async def _arecord_orchestrator_decision(
        self,
        run_id: UUID,
        decision: Any,
    ) -> None:
        summary = decision.rationale or "Orchestrator picked the next batch."
        ids = ", ".join(str(u) for u in decision.selected_task_ids) or "(none)"
        await self._arecord_step(
            run_id=run_id,
            item_id=None,
            role=ProjectRunStepRole.ORCHESTRATOR,
            status=ProjectRunStepStatus.SUCCEEDED,
            iteration=0,
            summary=f"Orchestrator → {summary} Picked: {ids}",
        )

    async def _amark_run_succeeded(
        self,
        run_id: UUID,
        tasks: list[Item],
    ) -> None:
        done = sum(1 for t in tasks if t.status == ItemStatus.DONE)
        blocked = sum(1 for t in tasks if t.status == ItemStatus.BLOCKED)
        session_factory = self._resolve_session_factory()
        async with session_factory() as session:
            repo = ProjectRunRepository(session)
            await repo.aupdate_run_fields(
                run_id,
                status=ProjectRunStatus.SUCCEEDED,
                finished_at=get_utc_now(),
                done_tasks=done,
                blocked_tasks=blocked,
            )
            await session.commit()

    async def _amark_run_failed(
        self,
        run_id: UUID,
        exc: Exception,
    ) -> None:
        session_factory = self._resolve_session_factory()
        async with session_factory() as session:
            repo = ProjectRunRepository(session)
            await repo.aupdate_run_fields(
                run_id,
                status=ProjectRunStatus.FAILED,
                finished_at=get_utc_now(),
                error=f"{exc}\n{traceback.format_exc(limit=3)}",
            )
            await session.commit()
