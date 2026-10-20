import os
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.database import create_target, get_targets
from app.models import JobTarget
from app.sqlalchemy_db import create_database_engine
from tests.db_support import initialize_test_database


PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_TABLES = {
    "job_targets",
    "jobs",
    "knowledge_items",
    "resumes",
    "resume_sources",
    "resume_image_sources",
    "agent_runs",
}


class AlembicSetupTests(unittest.TestCase):
    def _database_path(self, name: str) -> Path:
        directory = Path(__file__).resolve().parent / "tmp_alembic"
        directory.mkdir(exist_ok=True)
        path = directory / f"{name}.db"
        path.unlink(missing_ok=True)
        return path

    def test_upgrade_creates_current_schema_in_empty_database(self) -> None:
        database_path = self._database_path("fresh")
        try:
            with patch.dict(os.environ, {"DATABASE_PATH": str(database_path)}):
                command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
                command.check(Config(str(PROJECT_ROOT / "alembic.ini")))

            engine = create_database_engine(database_path)
            try:
                inspector = inspect(engine)
                self.assertEqual(set(inspector.get_table_names()) - {"alembic_version"}, EXPECTED_TABLES)
                self.assertEqual(
                    [(foreign_key["referred_table"], foreign_key["options"].get("ondelete"))
                     for foreign_key in inspector.get_foreign_keys("jobs")],
                    [("job_targets", "SET NULL")],
                )
                resume_columns = {column["name"] for column in inspector.get_columns("resumes")}
                self.assertTrue({"target_id", "is_current"}.issubset(resume_columns))
                self.assertEqual(
                    [(foreign_key["referred_table"], foreign_key["options"].get("ondelete"))
                     for foreign_key in inspector.get_foreign_keys("resumes")],
                    [("job_targets", "SET NULL")],
                )
            finally:
                engine.dispose()
        finally:
            try:
                database_path.unlink(missing_ok=True)
            except PermissionError:
                pass

    def test_stamp_preserves_existing_data_and_enables_orm_reads(self) -> None:
        database_path = self._database_path("legacy")
        try:
            initialize_test_database(database_path)
            # 模拟应用历史版本创建的库：基本表完整，但还没有后续新增的 AI 任务表。
            with sqlite3.connect(database_path) as connection:
                connection.execute("DROP TABLE agent_runs")
            saved_target = create_target(
                title="Python 工程师",
                keywords="FastAPI",
                cities=["北京"],
                database_path=database_path,
            )

            with patch.dict(os.environ, {"DATABASE_PATH": str(database_path)}):
                command.stamp(Config(str(PROJECT_ROOT / "alembic.ini")), "20261013_0001")
                command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")

            engine = create_database_engine(database_path)
            try:
                with Session(engine) as session:
                    target = session.scalar(
                        select(JobTarget).where(JobTarget.id == saved_target["id"])
                    )
                    self.assertIsNotNone(target)
                    self.assertEqual(target.title, "Python 工程师")
                    self.assertEqual(target.cities, '["北京"]')
                    session.add(JobTarget(title="AI 应用开发", cities='["天津"]'))
                    session.commit()
                self.assertTrue(EXPECTED_TABLES.issubset(set(inspect(engine).get_table_names())))
                self.assertEqual(
                    {target["title"] for target in get_targets(database_path)},
                    {"Python 工程师", "AI 应用开发"},
                )
            finally:
                engine.dispose()
        finally:
            try:
                database_path.unlink(missing_ok=True)
            except PermissionError:
                pass


if __name__ == "__main__":
    unittest.main()
