from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from infrastructure.entities import Base

if TYPE_CHECKING:
    from infrastructure.entities.message_entity import MessageEntity
    from infrastructure.entities.user_entity import UserEntity
    from infrastructure.entities.context_entity import ContextEntity


class ThreadEntity(Base):
    __tablename__ = "threads"

    # id, created_at, updated_at, deleted_at inherited from BaseEntityMixin
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    context_id: Mapped[UUID | None] = mapped_column(ForeignKey("contexts.id"), nullable=True)

    user: Mapped["UserEntity"] = relationship("UserEntity", back_populates="threads", lazy="joined")
    context: Mapped["ContextEntity | None"] = relationship("ContextEntity", back_populates="threads", lazy="joined")
    messages: Mapped[list["MessageEntity"]] = relationship("MessageEntity", back_populates="thread", cascade="all, delete-orphan", lazy="joined", order_by="MessageEntity.created_at.asc()")
