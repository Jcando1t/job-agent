"""为岗位记录增加求职跟进状态。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261014_0005"
down_revision: Union[str, None] = "20261014_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("jobs")}
    if "status" not in columns:
        op.add_column("jobs", sa.Column("status", sa.String(), server_default="未处理", nullable=False))


def downgrade() -> None:
    op.drop_column("jobs", "status")
