from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from infrastructure.entities import Base

if TYPE_CHECKING:
    from infrastructure.entities.thread_entity import ThreadEntity
    from infrastructure.entities.role_entity import RoleEntity


class MessageEntity(Base):
    __tablename__ = "messages"

    # id, created_at, updated_at, deleted_at inherited from BaseEntityMixin
    thread_id: Mapped[UUID] = mapped_column(ForeignKey("threads.id"), nullable=False)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    elapsed_seconds: Mapped[int] = mapped_column(Integer, default=0)

    thread: Mapped["ThreadEntity"] = relationship("ThreadEntity", back_populates="messages")
    role: Mapped["RoleEntity"] = relationship("RoleEntity", back_populates="messages", lazy="joined")
