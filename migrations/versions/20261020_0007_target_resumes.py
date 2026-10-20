"""为简历版本关联求职方向并标记当前生效版本。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261020_0007"
down_revision: Union[str, None] = "20261014_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("resumes")}
    with op.batch_alter_table("resumes") as batch_op:
        if "target_id" not in columns:
            batch_op.add_column(sa.Column("target_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_resumes_target_id_job_targets", "job_targets", ["target_id"], ["id"], ondelete="SET NULL"
            )
        if "is_current" not in columns:
            batch_op.add_column(
                sa.Column("is_current", sa.Boolean(), server_default=sa.false(), nullable=False)
            )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("resumes")}
    with op.batch_alter_table("resumes") as batch_op:
        if "is_current" in columns:
            batch_op.drop_column("is_current")
        if "target_id" in columns:
            batch_op.drop_constraint("fk_resumes_target_id_job_targets", type_="foreignkey")
            batch_op.drop_column("target_id")
