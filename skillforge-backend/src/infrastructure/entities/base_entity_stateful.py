from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column, declared_attr


class BaseEntityStateful:
    """Mixin that provides common fields for all entities.

    These fields are included directly in each entity's table,
    not in a separate table.

    Attributes:
        id: Primary key UUID
        created_at: Timestamp when entity was created (stored as UTC without timezone)
        updated_at: Timestamp when entity was last updated (stored as UTC without timezone)
        deleted_at: Soft delete timestamp (None = not deleted, stored as UTC without timezone)

    Note:
        All timestamps are stored as timezone-naive UTC datetimes in the database
        to be compatible with PostgreSQL's TIMESTAMP WITHOUT TIME ZONE.
        Converters should add timezone info when creating DTOs.
    """

    @declared_attr
    def id(cls) -> Mapped[UUID]:
        return mapped_column(primary_key=True, default=uuid4)

    @declared_attr
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    @declared_attr
    def updated_at(cls) -> Mapped[Optional[datetime]]:
        return mapped_column(DateTime, default=None, onupdate=datetime.utcnow, nullable=True)

    @declared_attr
    def deleted_at(cls) -> Mapped[Optional[datetime]]:
        """Soft delete timestamp. If set, entity is considered deleted."""
        return mapped_column(DateTime, default=None, nullable=True)
