"""保存岗位定制简历附带的打招呼语。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261014_0003"
down_revision: Union[str, None] = "20261013_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    # Initial revisions contain these fields for new databases. Keep the
    # conditional add for databases already at revision 0002.
    if "greeting" not in {column["name"] for column in inspector.get_columns("resumes")}:
        op.add_column(
            "resumes", sa.Column("greeting", sa.Text(), server_default="", nullable=False)
        )
    if "greeting" not in {column["name"] for column in inspector.get_columns("agent_runs")}:
        op.add_column("agent_runs", sa.Column("greeting", sa.Text(), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("agent_runs", "greeting")
    op.drop_column("resumes", "greeting")
