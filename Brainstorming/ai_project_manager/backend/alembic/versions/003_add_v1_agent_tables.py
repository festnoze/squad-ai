"""add v1 agent tables

Revision ID: 003
Revises: 002
Create Date: 2026-04-11 00:00:00.000000

V1 introduces three new persisted concepts:

1. ``item_dependencies`` — directed graph of "task A depends on task B"
   edges produced by the scoping LLM. Used by the orchestrator to pick
   the next executable batch.
2. ``project_runs`` — one row per "Lancer l'implémentation" invocation,
   with status counters kept live by the orchestrator.
3. ``project_run_steps`` — append-only log of observable agent steps
   (orchestrator decisions, dev/qa invocations).

It also extends the existing ``items`` table with V1-specific fields:
``deliverable_paths`` (JSON list of generated files), ``deliverable_notes``
(free-form markdown accumulated by the agents), and ``blocked_reason``
(set when the item ends up in the terminal ``blocked`` state).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- items: new columns ------------------------------------------------
    with op.batch_alter_table("items") as batch_op:
        batch_op.add_column(
            sa.Column("deliverable_paths", sa.JSON(), nullable=True),
        )
        batch_op.add_column(
            sa.Column("deliverable_notes", sa.Text(), nullable=True),
        )
        batch_op.add_column(
            sa.Column("blocked_reason", sa.Text(), nullable=True),
        )

    # ---- item_dependencies -------------------------------------------------
    op.create_table(
        "item_dependencies",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("item_id", sa.CHAR(length=36), nullable=False),
        sa.Column("depends_on_item_id", sa.CHAR(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name="fk_item_dependencies_item_id_items",
        ),
        sa.ForeignKeyConstraint(
            ["depends_on_item_id"],
            ["items.id"],
            name="fk_item_dependencies_depends_on_item_id_items",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_item_dependencies_item_id",
        "item_dependencies",
        ["item_id"],
        unique=False,
    )
    op.create_index(
        "ix_item_dependencies_depends_on_item_id",
        "item_dependencies",
        ["depends_on_item_id"],
        unique=False,
    )

    # ---- project_runs ------------------------------------------------------
    op.create_table(
        "project_runs",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("project_id", sa.CHAR(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("total_tasks", sa.Integer(), nullable=False),
        sa.Column("done_tasks", sa.Integer(), nullable=False),
        sa.Column("blocked_tasks", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_runs_project_id_projects",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_runs_project_id",
        "project_runs",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_runs_deleted_at",
        "project_runs",
        ["deleted_at"],
        unique=False,
    )

    # ---- project_run_steps -------------------------------------------------
    op.create_table(
        "project_run_steps",
        sa.Column("id", sa.CHAR(length=36), nullable=False),
        sa.Column("run_id", sa.CHAR(length=36), nullable=False),
        sa.Column("item_id", sa.CHAR(length=36), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["project_runs.id"],
            name="fk_project_run_steps_run_id_project_runs",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name="fk_project_run_steps_item_id_items",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_run_steps_run_id",
        "project_run_steps",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_project_run_steps_deleted_at",
        "project_run_steps",
        ["deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_run_steps_deleted_at", table_name="project_run_steps")
    op.drop_index("ix_project_run_steps_run_id", table_name="project_run_steps")
    op.drop_table("project_run_steps")

    op.drop_index("ix_project_runs_deleted_at", table_name="project_runs")
    op.drop_index("ix_project_runs_project_id", table_name="project_runs")
    op.drop_table("project_runs")

    op.drop_index(
        "ix_item_dependencies_depends_on_item_id",
        table_name="item_dependencies",
    )
    op.drop_index("ix_item_dependencies_item_id", table_name="item_dependencies")
    op.drop_table("item_dependencies")

    with op.batch_alter_table("items") as batch_op:
        batch_op.drop_column("blocked_reason")
        batch_op.drop_column("deliverable_notes")
        batch_op.drop_column("deliverable_paths")
