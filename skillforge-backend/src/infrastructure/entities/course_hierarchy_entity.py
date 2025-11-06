from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from infrastructure.entities import Base


class CourseHierarchyEntity(Base):
    __tablename__ = "course_hierarchies"

    # id, created_at, updated_at, deleted_at inherited from Base (StatefulBase)
    # Use JSON.with_variant to handle both PostgreSQL (JSONB) and SQLite (JSON)
    course_filter: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    course_hierarchy: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
