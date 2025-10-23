from typing import TYPE_CHECKING
from uuid import UUID
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from infrastructure.entities import Base

if TYPE_CHECKING:
    from infrastructure.entities.thread_entity import ThreadEntity
    from infrastructure.entities.school_entity import SchoolEntity
    from infrastructure.entities.user_preference_entity import UserPreferenceEntity


class UserEntity(Base):
    __tablename__ = "users"

    # id, created_at, updated_at, deleted_at inherited from BaseEntityMixin
    lms_user_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    school_id: Mapped[UUID | None] = mapped_column(ForeignKey("schools.id"), nullable=True)
    civility: Mapped[str] = mapped_column(String(50), nullable=False)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)

    school: Mapped["SchoolEntity | None"] = relationship("SchoolEntity", back_populates="users", lazy="joined")
    preference: Mapped["UserPreferenceEntity | None"] = relationship("UserPreferenceEntity", back_populates="user", uselist=False, lazy="joined")
    threads: Mapped[list["ThreadEntity"]] = relationship("ThreadEntity", back_populates="user", cascade="all, delete-orphan", lazy="joined")
