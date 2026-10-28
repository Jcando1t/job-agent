"""为已保存简历版本增加可选头像图片。"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261023_0008"
down_revision: Union[str, None] = "20261020_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("resumes")}
    if "photo_image_id" not in columns:
        with op.batch_alter_table("resumes") as batch_op:
            batch_op.add_column(sa.Column("photo_image_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("resumes")}
    if "photo_image_id" in columns:
        with op.batch_alter_table("resumes") as batch_op:
            batch_op.drop_column("photo_image_id")
