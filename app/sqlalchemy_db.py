"""SQLAlchemy 连接工厂，供迁移和渐进式数据库改造使用。"""

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL

from app.config import get_settings


def create_database_engine(database_path: Path | None = None) -> Engine:
    path = (database_path or get_settings().database_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    url = URL.create("sqlite", database=str(path))
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine
