"""SQLAlchemy declarative bases.

- `Base` is the root DeclarativeBase all entities (and Alembic) use.
- `StatefulBase` is an abstract mixin exposing `id`, `created_at`, `updated_at`
  and `deleted_at` — every business entity should inherit from it.

We store UUIDs as 36-char strings because SQLite has no native UUID type.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from sqlalchemy.types import CHAR, TypeDecorator

from app.infrastructure.common import get_utc_now


class GUID(TypeDecorator):
    """Portable UUID type stored as 36-char string on SQLite.

    SQLAlchemy's built-in Uuid works on most backends, but forcing a stable
    string representation makes debugging and Alembic migrations easier on
    a file-based SQLite MVP.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, _dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, UUID):
            return str(value)
        return str(UUID(str(value)))

    def process_result_value(self, value, _dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        return UUID(value)


class Base(DeclarativeBase):
    """Root declarative base for every SQLAlchemy entity."""


class StatefulBase(Base):
    """Abstract base with id + created_at / updated_at / deleted_at audit fields.

    All business entities inherit from this class. `__abstract__ = True`
    prevents SQLAlchemy from creating a table for it.
    """

    __abstract__ = True

    @declared_attr
    def id(cls) -> Mapped[UUID]:
        return mapped_column(GUID(), primary_key=True, default=uuid4)

    @declared_attr
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(
            DateTime(timezone=True),
            default=get_utc_now,
            nullable=False,
        )

    @declared_attr
    def updated_at(cls) -> Mapped[datetime | None]:
        return mapped_column(
            DateTime(timezone=True),
            default=get_utc_now,
            onupdate=get_utc_now,
            nullable=True,
        )

    @declared_attr
    def deleted_at(cls) -> Mapped[datetime | None]:
        return mapped_column(
            DateTime(timezone=True),
            default=None,
            nullable=True,
            index=True,
        )
