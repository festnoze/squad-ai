from typing import TYPE_CHECKING
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from infrastructure.entities import Base

if TYPE_CHECKING:
    from infrastructure.entities.user_entity import UserEntity


class SchoolEntity(Base):
    __tablename__ = "schools"

    # id, created_at, updated_at, deleted_at inherited from BaseEntityStateful
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    users: Mapped[list["UserEntity"]] = relationship("UserEntity", back_populates="school", lazy="select")
