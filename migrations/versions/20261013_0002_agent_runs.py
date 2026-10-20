"""增加 AI 简历改进任务和审核状态记录。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261013_0002"
down_revision: Union[str, None] = "20261013_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # initialize_database() may have added these nullable columns before an
    # existing database was stamped at the initial baseline.
    inspector = sa.inspect(op.get_bind())
    if "storage_path" not in {column["name"] for column in inspector.get_columns("resume_sources")}:
        op.add_column("resume_sources", sa.Column("storage_path", sa.String(), nullable=True))
    if "storage_path" not in {
        column["name"] for column in inspector.get_columns("resume_image_sources")
    }:
        op.add_column("resume_image_sources", sa.Column("storage_path", sa.String(), nullable=True))
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.String(), server_default="local", nullable=False),
        sa.Column("source_resume_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), server_default="draft", nullable=False),
        sa.Column("input_snapshot", sa.Text(), nullable=False),
        sa.Column("result_content", sa.Text(), server_default="", nullable=False),
        sa.Column("greeting", sa.Text(), server_default="", nullable=False),
        sa.Column("evidence_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("missing_info_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column("error_message", sa.Text(), server_default="", nullable=False),
        sa.Column("created_at", sa.String(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.String(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["source_resume_id"], ["resume_sources.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("agent_runs")
    op.drop_column("resume_image_sources", "storage_path")
    op.drop_column("resume_sources", "storage_path")
