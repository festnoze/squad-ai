from typing import TYPE_CHECKING
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from infrastructure.entities import SimpleBase

if TYPE_CHECKING:
    from infrastructure.entities.message_entity import MessageEntity


class RoleEntity(SimpleBase):
    __tablename__ = "roles"

    # id inherited from BaseEntity via SimpleBase
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

    messages: Mapped[list["MessageEntity"]] = relationship("MessageEntity", back_populates="role", lazy="select")
