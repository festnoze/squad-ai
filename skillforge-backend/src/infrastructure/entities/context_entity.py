from typing import TYPE_CHECKING
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from infrastructure.entities import Base

if TYPE_CHECKING:
    from infrastructure.entities.thread_entity import ThreadEntity


class ContextEntity(Base):
    __tablename__ = "contexts"

    # id, created_at, updated_at, deleted_at inherited from Base (StatefulBase)
    context_filter: Mapped[dict] = mapped_column(JSONB, nullable=False)
    context_full: Mapped[dict] = mapped_column(JSONB, nullable=False)

    threads: Mapped[list["ThreadEntity"]] = relationship("ThreadEntity", back_populates="context", cascade="all, delete-orphan", lazy="joined")
