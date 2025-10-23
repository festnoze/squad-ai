from uuid import UUID, uuid4
from sqlalchemy.orm import Mapped, mapped_column, declared_attr


class BaseEntity:
    """Base mixin that provides only an ID field for simple entities.

    Use this for lookup tables or simple entities that don't need timestamps.

    Attributes:
        id: Primary key UUID
    """

    @declared_attr
    def id(cls) -> Mapped[UUID]:
        return mapped_column(primary_key=True, default=uuid4)
