"""匹配当前个人求职工作台 SQLite 表结构。

Revision ID: 20261013_0001
Revises:
Create Date: 2026-10-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261013_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_targets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.String(), server_default="local", nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("keywords", sa.String(), server_default="", nullable=False),
        sa.Column("cities", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.String(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.String(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.String(), server_default="local", nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("company", sa.String(), server_default="", nullable=False),
        sa.Column("city", sa.String(), server_default="", nullable=False),
        sa.Column("source", sa.String(), server_default="手动录入", nullable=False),
        sa.Column("original_url", sa.String(), server_default="", nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.String(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.String(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["target_id"], ["job_targets.id"], ondelete="SET NULL"),
    )
    op.create_table(
        "knowledge_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.String(), server_default="local", nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("organization", sa.String(), server_default="", nullable=False),
        sa.Column("period", sa.String(), server_default="", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_note", sa.String(), server_default="", nullable=False),
        sa.Column("created_at", sa.String(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.String(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_table(
        "resumes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.String(), server_default="local", nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_item_ids", sa.Text(), server_default="[]", nullable=False),
        sa.Column("greeting", sa.Text(), server_default="", nullable=False),
        sa.Column("job_snapshot", sa.Text(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.String(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.String(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("source_resume_id", sa.Integer(), nullable=True),
    )
    op.create_table(
        "resume_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.String(), server_default="local", nullable=False),
        sa.Column("filename", sa.String(), server_default="", nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("source_image_ids", sa.Text(), server_default="[]", nullable=False),
    )
    op.create_table(
        "resume_image_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.String(), server_default="local", nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.String(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("resume_image_sources")
    op.drop_table("resume_sources")
    op.drop_table("resumes")
    op.drop_table("knowledge_items")
    op.drop_table("jobs")
    op.drop_table("job_targets")
