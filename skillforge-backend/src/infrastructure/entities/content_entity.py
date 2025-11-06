from sqlalchemy import Text, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from infrastructure.entities import Base


class ContentEntity(Base):
    __tablename__ = "contents"

    # id, created_at, updated_at, deleted_at inherited from Base (StatefulBase)
    # Use JSON.with_variant to handle both PostgreSQL (JSONB) and SQLite (JSON)
    filter: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    context_metadata: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    content_full: Mapped[str] = mapped_column(Text, nullable=False)
    content_html: Mapped[str] = mapped_column(Text, nullable=False)
    content_media: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    content_summary_full: Mapped[str] = mapped_column(Text, nullable=False)
    content_summary_light: Mapped[str] = mapped_column(Text, nullable=False)
    content_summary_compact: Mapped[str] = mapped_column(Text, nullable=False)

    # Along with this must be created a tree of the parcours hierarchy in DB, allowing both: existance of upper levels (theme, module and matiere) and navigability to neighbors leafs.
    # The idea is that each node of the tree has its own content record associated. Here is GPT5 idea to do it:
