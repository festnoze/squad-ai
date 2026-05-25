"""add item and chat_message tables

Revision ID: 002
Revises: 001
Create Date: 2026-04-10 00:00:01.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("project_id", sa.CHAR(length=36), nullable=False),
        sa.Column("parent_id", sa.CHAR(length=36), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("complexity", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_items_project_id_projects",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["items.id"],
            name="fk_items_parent_id_items",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_items_project_id",
        "items",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_items_deleted_at",
        "items",
        ["deleted_at"],
        unique=False,
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("project_id", sa.CHAR(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("meta_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_chat_messages_project_id_projects",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_chat_messages_project_id",
        "chat_messages",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_chat_messages_deleted_at",
        "chat_messages",
        ["deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_deleted_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_project_id", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index("ix_items_deleted_at", table_name="items")
    op.drop_index("ix_items_project_id", table_name="items")
    op.drop_table("items")
