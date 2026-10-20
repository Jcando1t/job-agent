"""为岗位记录增加备注和下一步行动。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261014_0006"
down_revision: Union[str, None] = "20261014_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("jobs")}
    if "notes" not in columns:
        op.add_column("jobs", sa.Column("notes", sa.Text(), server_default="", nullable=False))
    if "next_action" not in columns:
        op.add_column("jobs", sa.Column("next_action", sa.String(), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("jobs", "next_action")
    op.drop_column("jobs", "notes")
