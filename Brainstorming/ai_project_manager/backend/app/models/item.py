"""Item domain model (Pydantic).

`Item` is the unified representation of the three node types that make up a
project tree: Epic, User Story and Task. Keeping a single model (rather than
three separate ones) lets the chatbot reason about the whole hierarchy with
one vocabulary and makes the adaptive Epic/US/Task structure described in
the PRD trivial to persist.

Hierarchy rules (enforced at the service layer, not by DB constraints):
    * An Epic is always a root (``parent_id`` is ``None``).
    * A User Story can either be the child of an Epic or a root itself.
    * A Task can either be the child of a User Story or a root itself.

The ``acceptance_criteria`` field is primarily meant for ``user_story``
items (and optionally for complex ``task`` items).

V1 additions:

- ``deliverable_paths`` / ``deliverable_notes``: outputs produced by the
  DevAgent + QaAgent during a ``ProjectRun``. Paths are relative to the
  backend ``generated/`` workspace.
- ``blocked_reason``: explains why an item ended up in the terminal
  ``blocked`` status (QA rejection loop, dependency failure, ...).
- ``BLOCKED`` status: added to the enum to represent definitively failed
  items so they no longer block the rest of the graph.
"""

from enum import Enum
from uuid import UUID

from app.models.base_model import IdStatefulBaseModel


class ItemType(str, Enum):
    """Type discriminator for an `Item`."""

    EPIC = "epic"
    USER_STORY = "user_story"
    TASK = "task"


class ItemComplexity(str, Enum):
    """Estimated complexity of an `Item`."""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class ItemStatus(str, Enum):
    """Workflow status of an `Item`.

    `PROPOSED` is the intermediate state used when the assistant suggests a
    new item but the PM has not yet validated it.
    `BLOCKED` (V1) is the terminal state used when an orchestration run
    cannot complete the item (e.g. QA rejected twice).
    """

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_TEST = "in_test"
    DONE = "done"
    PROPOSED = "proposed"
    BLOCKED = "blocked"


class Item(IdStatefulBaseModel):
    """A node of the project tree (Epic, User Story or Task).

    Attributes:
        project_id: Project the item belongs to.
        parent_id: Parent item id, or ``None`` if the item is a root.
        type: Whether this node is an epic, a user story or a task.
        title: Short human-readable title.
        description: Optional long-form description.
        complexity: Optional complexity estimate.
        status: Workflow status; defaults to ``TODO``.
        acceptance_criteria: Optional list of acceptance criteria
            (typically set on user stories).
        order: Sort order inside the parent (smaller is earlier).
        deliverable_paths: Paths (relative to the backend generated workspace)
            of files produced by the DevAgent. None until a run writes them.
        deliverable_notes: Free-form markdown notes accumulated by the
            DevAgent and the QaAgent across iterations.
        blocked_reason: Human-readable explanation populated when
            ``status == BLOCKED``.
    """

    project_id: UUID
    parent_id: UUID | None = None
    type: ItemType
    title: str
    description: str | None = None
    complexity: ItemComplexity | None = None
    status: ItemStatus = ItemStatus.TODO
    acceptance_criteria: list[str] | None = None
    order: int = 0
    deliverable_paths: list[str] | None = None
    deliverable_notes: str | None = None
    blocked_reason: str | None = None
