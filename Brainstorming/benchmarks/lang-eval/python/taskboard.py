"""TaskBoard domain library — identical spec across Python / Go / Rust."""

from dataclasses import dataclass
from enum import Enum


class TaskStatus(Enum):
    TODO = "todo"
    DONE = "done"


class TaskError(Exception):
    """Base domain error. Note: not enforced by the type system — callers may
    forget to catch it (no compile-time signal)."""


class EmptyTitle(TaskError):
    pass


class BadPriority(TaskError):
    def __init__(self, value: int):
        super().__init__(f"priority must be 1..5, got {value}")
        self.value = value


class NotFound(TaskError):
    def __init__(self, task_id: int):
        super().__init__(f"task {task_id} not found")
        self.task_id = task_id


class AlreadyDone(TaskError):
    def __init__(self, task_id: int):
        super().__init__(f"task {task_id} already done")
        self.task_id = task_id


@dataclass
class Task:
    id: int
    title: str
    priority: int
    status: TaskStatus


class TaskBoard:
    def __init__(self) -> None:
        self._tasks: dict[int, Task] = {}
        self._next_id = 1

    def add(self, title: str, priority: int) -> int:
        if not title.strip():
            raise EmptyTitle("title must not be empty")
        if priority < 1 or priority > 5:
            raise BadPriority(priority)
        task = Task(self._next_id, title.strip(), priority, TaskStatus.TODO)
        self._tasks[task.id] = task
        self._next_id += 1
        return task.id

    def complete(self, task_id: int) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            raise NotFound(task_id)
        if task.status is TaskStatus.DONE:
            raise AlreadyDone(task_id)
        task.status = TaskStatus.DONE

    def pending(self) -> list[Task]:
        todo = [t for t in self._tasks.values() if t.status is TaskStatus.TODO]
        # highest priority first, then by id ascending
        return sorted(todo, key=lambda t: (-t.priority, t.id))

    def stats(self) -> tuple[int, int, int]:
        total = len(self._tasks)
        done = sum(1 for t in self._tasks.values() if t.status is TaskStatus.DONE)
        return total, done, total - done
