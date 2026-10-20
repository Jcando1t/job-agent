"""测试专用数据库准备工具；生产数据库表结构由 Alembic 管理。"""

from pathlib import Path

from app.models import Base
from app.sqlalchemy_db import create_database_engine


def initialize_test_database(database_path: Path) -> None:
    engine = create_database_engine(database_path)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
