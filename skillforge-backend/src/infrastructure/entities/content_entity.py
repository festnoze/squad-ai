from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from infrastructure.entities import Base


class ContentEntity(Base):
    __tablename__ = "contents"

    # id, created_at, updated_at, deleted_at inherited from Base (StatefulBase)
    filter: Mapped[dict] = mapped_column(JSONB, nullable=False)
    context_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_full: Mapped[str] = mapped_column(Text, nullable=False)
    content_html: Mapped[str] = mapped_column(Text, nullable=False)
    content_media: Mapped[dict] = mapped_column(JSONB, nullable=False)
