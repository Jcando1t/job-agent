import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.database import (
    create_resume_image_source,
    create_resume_source,
    get_resume_image_source,
    get_resume_sources,
)
from tests.db_support import initialize_test_database
from app.services.private_file_migration import migrate_legacy_private_files


class PrivateFileMigrationTests(unittest.TestCase):
    def test_old_resume_materials_are_copied_once_to_local_files(self) -> None:
        root = Path(__file__).resolve().parent / "tmp_private_file_migration"
        root.mkdir(exist_ok=True)
        try:
            database_path = root / "legacy.db"
            database_path.unlink(missing_ok=True)
            storage_dir = root / "private-files"
            storage_dir.mkdir(exist_ok=True)
            initialize_test_database(database_path)
            image_bytes = b"\x89PNG\r\n\x1a\nlegacy-image"
            image = create_resume_image_source(
                "resume.png", "image/png", image_bytes, database_path=database_path
            )
            source = create_resume_source(
                "resume.txt", "姓名：张三", database_path=database_path
            )
            settings = Settings(
                app_env="test",
                database_path=database_path,
                file_storage_dir=storage_dir,
                deepseek_api_key="",
                deepseek_base_url="https://api.deepseek.com",
                deepseek_model="deepseek-chat",
                llm_timeout_seconds=30,
            )
            with patch("app.storage.get_settings", return_value=settings):
                self.assertEqual(migrate_legacy_private_files(database_path), 2)
                self.assertEqual(migrate_legacy_private_files(database_path), 0)
                migrated_image = get_resume_image_source(image["id"], database_path)
                migrated_source = get_resume_sources(database_path)[0]
            self.assertEqual(migrated_image["content"], image_bytes)
            self.assertEqual(migrated_source["content"], source["content"])
            self.assertEqual(len(list(storage_dir.iterdir())), 2)
        finally:
            for path in storage_dir.iterdir() if storage_dir.exists() else []:
                path.unlink(missing_ok=True)
            if storage_dir.exists():
                storage_dir.rmdir()
            database_path = root / "legacy.db"
            database_path.unlink(missing_ok=True)
            if root.exists():
                root.rmdir()


if __name__ == "__main__":
    unittest.main()
