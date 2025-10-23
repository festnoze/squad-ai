from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from infrastructure.entities import Base

if TYPE_CHECKING:
    from infrastructure.entities.user_entity import UserEntity


class UserPreferenceEntity(Base):
    __tablename__ = "user_preferences"

    # id, created_at, updated_at, deleted_at inherited from BaseEntityStateful
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    theme: Mapped[str | None] = mapped_column(String(20), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped["UserEntity"] = relationship("UserEntity", back_populates="preference")
