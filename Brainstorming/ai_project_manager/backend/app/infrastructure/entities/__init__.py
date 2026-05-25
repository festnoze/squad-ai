"""SQLAlchemy entities package.

Importing every entity module here ensures that Alembic `autogenerate` and
`Base.metadata.create_all()` see all tables.
"""

from app.infrastructure.entities.base import Base, StatefulBase  # noqa: F401
from app.infrastructure.entities.chat_message_entity import (  # noqa: F401
    ChatMessageEntity,
)
from app.infrastructure.entities.item_dependency_entity import (  # noqa: F401
    ItemDependencyEntity,
)
from app.infrastructure.entities.item_entity import ItemEntity  # noqa: F401
from app.infrastructure.entities.project_entity import ProjectEntity  # noqa: F401
from app.infrastructure.entities.project_run_entity import (  # noqa: F401
    ProjectRunEntity,
)
from app.infrastructure.entities.project_run_step_entity import (  # noqa: F401
    ProjectRunStepEntity,
)

__all__ = [
    "Base",
    "StatefulBase",
    "ProjectEntity",
    "ItemEntity",
    "ItemDependencyEntity",
    "ChatMessageEntity",
    "ProjectRunEntity",
    "ProjectRunStepEntity",
]
