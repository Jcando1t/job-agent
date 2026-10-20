"""数据库写入失败时，确认本地新简历文件会被清理。"""

import base64
from pathlib import Path
import unittest
from unittest.mock import patch

import main
from app.config import Settings
from app.schemas import ResumeFileInput, ResumeImageInput, ResumeSourceInput


class PrivateUploadCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = Path(__file__).resolve().parent / "tmp_upload_cleanup"
        self.directory.mkdir(exist_ok=True)
        self.storage_dir = self.directory / "files"
        self.storage_dir.mkdir(exist_ok=True)
        self.settings = Settings(
            app_env="test",
            database_path=self.directory / "test.db",
            file_storage_dir=self.storage_dir,
            deepseek_api_key="",
            deepseek_base_url="https://api.deepseek.com",
            deepseek_model="deepseek-chat",
            llm_timeout_seconds=30,
        )
        self.settings_patch = patch("app.storage.get_settings", return_value=self.settings)
        self.settings_patch.start()

    def tearDown(self) -> None:
        self.settings_patch.stop()
        for path in self.storage_dir.iterdir():
            path.unlink(missing_ok=True)
        self.storage_dir.rmdir()
        self.directory.rmdir()

    def _assert_failed_database_write_leaves_no_file(self, action) -> None:
        with self.assertRaisesRegex(RuntimeError, "simulated database failure"):
            action()
        self.assertEqual(list(self.storage_dir.iterdir()), [])

    def test_pasted_resume_is_removed_when_database_write_fails(self) -> None:
        payload = ResumeSourceInput(filename="resume.txt", content="测试简历正文")
        with patch("main.create_resume_source", side_effect=RuntimeError("simulated database failure")):
            self._assert_failed_database_write_leaves_no_file(
                lambda: main.add_resume_source(payload)
            )

    def test_uploaded_resume_is_removed_when_database_write_fails(self) -> None:
        payload = ResumeFileInput(
            filename="resume.txt",
            content_base64=base64.b64encode(b"test resume").decode("ascii"),
        )
        with patch("main.create_resume_source", side_effect=RuntimeError("simulated database failure")):
            self._assert_failed_database_write_leaves_no_file(
                lambda: main.upload_resume_source(payload)
            )

    def test_uploaded_image_is_removed_when_database_write_fails(self) -> None:
        png = b"\x89PNG\r\n\x1a\ntest image"
        payload = ResumeImageInput(
            filename="resume.png",
            content_type="image/png",
            content_base64=base64.b64encode(png).decode("ascii"),
        )
        with patch(
            "main.create_resume_image_source",
            side_effect=RuntimeError("simulated database failure"),
        ):
            self._assert_failed_database_write_leaves_no_file(
                lambda: main.add_resume_image(payload)
            )


if __name__ == "__main__":
    unittest.main()
