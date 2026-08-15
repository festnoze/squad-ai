"""Core models: Project, Page.

OWNED BY: backend-core agent.
SQLAlchemy 2.0 declarative (Mapped / mapped_column, sqlalchemy.JSON columns).
All models inherit from app.db.Base so ainit_db picks them up.

Shapes follow docs/CONTRACTS.md (which wins over the decision docs):
- Project.theme JSON: {"primary_color", "font", "base_spacing"}
- Page.content JSON: the canonical block tree (root {"id": "root", "type": "page", ...})

The Asset model lives in app/models_cms.py (owned by the backend-cms agent,
which also owns the assets router); the renderer imports it lazily.

Also exposes small shared helpers (slugify, utcnow_iso, defaults) used by the
core routers; backend-cms may import them too.
"""

import re
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

DEFAULT_THEME = {"primary_color": "#2563eb", "font": "system-ui", "base_spacing": 16}


def empty_tree() -> dict:
    """A new page's block tree root (canonical schema, CONTRACTS.md section 2)."""
    return {"id": "root", "type": "page", "props": {}, "style": {}, "children": []}


def utcnow_iso() -> str:
    """ISO 8601 UTC timestamp with trailing Z (e.g. 2026-08-01T14:03:22Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(value: str) -> str:
    """Lowercase [a-z0-9-]+ slug derived from a name."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    theme: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("project_id", "slug", name="uq_pages_project_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False)
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=empty_tree)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
    updated_at: Mapped[str] = mapped_column(String, nullable=False, default=utcnow_iso)
