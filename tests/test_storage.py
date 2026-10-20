import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.storage import delete_private_file, get_private_file, save_private_file


class PrivateStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(__file__).resolve().parent / "tmp_private_storage"
        self.directory.mkdir(exist_ok=True)
        self.settings = Settings(
            app_env="test",
            database_path=self.directory / "test.db",
            file_storage_dir=self.directory / "files",
            deepseek_api_key="",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-chat",
            llm_timeout_seconds=30,
        )
        self.settings.file_storage_dir.mkdir(exist_ok=True)
        self.settings_context = patch("app.storage.get_settings", return_value=self.settings)
        self.settings_context.start()

    def tearDown(self) -> None:
        self.settings_context.stop()
        for path in self.settings.file_storage_dir.iterdir():
            path.unlink(missing_ok=True)
        self.settings.file_storage_dir.rmdir()
        if (self.directory / "test.db").exists():
            (self.directory / "test.db").unlink()
        self.directory.rmdir()

    def test_save_read_and_delete_private_file(self) -> None:
        stored_name = save_private_file("个人资料", ".txt")
        path = get_private_file(stored_name)
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_text(encoding="utf-8"), "个人资料")
        delete_private_file(stored_name)
        self.assertFalse(path.exists())

    def test_rejects_paths_outside_storage_root(self) -> None:
        for name in ("../secret.txt", "nested/secret.txt", str(self.directory / "secret.txt")):
            with self.subTest(name=name), self.assertRaises(ValueError):
                get_private_file(name)


if __name__ == "__main__":
    unittest.main()
