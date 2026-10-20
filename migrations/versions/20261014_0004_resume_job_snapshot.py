"""将每版简历关联到生成时使用的岗位 JD。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261014_0004"
down_revision: Union[str, None] = "20261014_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("resumes")}
    if "job_snapshot" not in columns:
        op.add_column(
            "resumes",
            sa.Column("job_snapshot", sa.Text(), server_default="{}", nullable=False),
        )


def downgrade() -> None:
    op.drop_column("resumes", "job_snapshot")
