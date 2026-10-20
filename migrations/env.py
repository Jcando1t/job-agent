from logging.config import fileConfig

from alembic import context
from alembic.operations import ops
from sqlalchemy import Integer, String, Text, engine_from_config, pool

from app.config import get_settings
from app.models import Base


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
database_path = settings.database_path.resolve()
database_path.parent.mkdir(parents=True, exist_ok=True)
config.set_main_option(
    "sqlalchemy.url", f"sqlite:///{database_path.as_posix()}"
)
target_metadata = Base.metadata


def compare_type(_context, _inspected_column, _metadata_column, inspected_type, metadata_type):
    """SQLite 将 String/Text 与 INTEGER PK 的声明反射为类型差异；用显式迁移维护结构。"""
    if isinstance(inspected_type, String) and isinstance(metadata_type, (String, Text)):
        return False
    return None


def process_revision_directives(_context, _revision, directives):
    """SQLite 反射把 INTEGER 主键的 nullable 差异报告为迁移，过滤无效变更。"""
    script = directives[0]
    def remove_noise(operations):
        filtered = []
        for operation in operations:
            if (
                isinstance(operation, ops.AlterColumnOp)
                and operation.column_name == "id"
                and isinstance(operation.existing_type, Integer)
                and operation.modify_nullable is False
            ):
                continue
            if isinstance(operation, ops.ModifyTableOps):
                operation.ops = remove_noise(operation.ops)
                if not operation.ops:
                    continue
            filtered.append(operation)
        return filtered

    script.upgrade_ops.ops = remove_noise(script.upgrade_ops.ops)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        compare_type=compare_type,
        compare_server_default=False,
        process_revision_directives=process_revision_directives,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=compare_type,
            compare_server_default=False,
            process_revision_directives=process_revision_directives,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
