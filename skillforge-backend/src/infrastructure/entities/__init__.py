from sqlalchemy.orm import DeclarativeBase
from infrastructure.entities.base_entity_stateful import BaseEntityStateful
from infrastructure.entities.base_entity import BaseEntity


# Single DeclarativeBase for all entities
class DeclarativeBaseClass(DeclarativeBase):
    pass


# StatefulBase: includes id, created_at, updated_at, deleted_at
class StatefulBase(DeclarativeBaseClass, BaseEntityStateful):
    """Base class for entities with full audit fields (id, created_at, updated_at, deleted_at)"""

    __abstract__ = True  # Don't create a table for this base class


# SimpleBase: includes only id field
class SimpleBase(DeclarativeBaseClass, BaseEntity):
    """Base class for simple entities with only id field (no timestamps)"""

    __abstract__ = True  # Don't create a table for this base class


# Keep "Base" as alias for backward compatibility
Base = StatefulBase

# Import all entity classes to register them with SQLAlchemy metadata
# This ensures all tables are known when create_all() is called
from infrastructure.entities.role_entity import RoleEntity  # noqa: E402
from infrastructure.entities.school_entity import SchoolEntity  # noqa: E402
from infrastructure.entities.user_preference_entity import UserPreferenceEntity  # noqa: E402
from infrastructure.entities.user_entity import UserEntity  # noqa: E402
from infrastructure.entities.context_entity import ContextEntity  # noqa: E402
from infrastructure.entities.thread_entity import ThreadEntity  # noqa: E402
from infrastructure.entities.message_entity import MessageEntity  # noqa: E402


# Export entities for easy importing
__all__ = [
    "Base",
    "StatefulBase",
    "SimpleBase",
    "BaseEntity",
    "BaseEntityStateful",
    "DeclarativeBaseClass",
    "RoleEntity",
    "SchoolEntity",
    "UserPreferenceEntity",
    "UserEntity",
    "ContextEntity",
    "ThreadEntity",
    "MessageEntity",
]
