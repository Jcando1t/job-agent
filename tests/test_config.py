import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import PROJECT_ROOT, get_settings


class SettingsTests(unittest.TestCase):
    def test_defaults_keep_local_data_inside_project(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = get_settings()

        self.assertEqual(settings.app_env, "local")
        self.assertEqual(settings.database_path, PROJECT_ROOT / "data" / "job_agent.db")
        self.assertEqual(settings.file_storage_dir, PROJECT_ROOT / "data" / "files")
        self.assertEqual(settings.deepseek_api_key, "")
        self.assertEqual(settings.llm_timeout_seconds, 30)

    def test_environment_can_override_paths_and_model_settings(self) -> None:
        values = {
            "APP_ENV": "test",
            "DATABASE_PATH": "tmp/test.db",
            "FILE_STORAGE_DIR": "D:/resume-files",
            "DEEPSEEK_API_KEY": "test-only-key",
            "DEEPSEEK_BASE_URL": "https://example.test/v1",
            "DEEPSEEK_MODEL": "test-model",
            "LLM_TIMEOUT_SECONDS": "12.5",
        }
        with patch.dict(os.environ, values, clear=True):
            settings = get_settings()

        self.assertEqual(settings.app_env, "test")
        self.assertEqual(settings.database_path, PROJECT_ROOT / "tmp" / "test.db")
        self.assertEqual(settings.file_storage_dir, Path("D:/resume-files"))
        self.assertEqual(settings.deepseek_api_key, "test-only-key")
        self.assertEqual(settings.deepseek_base_url, "https://example.test/v1")
        self.assertEqual(settings.deepseek_model, "test-model")
        self.assertEqual(settings.llm_timeout_seconds, 12.5)

    def test_environment_accepts_underscored_deepseek_api_key_name(self) -> None:
        with patch.dict(os.environ, {"DEEP_SEEK_API_KEY": "test-alias-key"}, clear=True):
            settings = get_settings()

        self.assertEqual(settings.deepseek_api_key, "test-alias-key")

    def test_canonical_deepseek_api_key_takes_precedence(self) -> None:
        values = {
            "DEEPSEEK_API_KEY": "canonical-key",
            "DEEP_SEEK_API_KEY": "alias-key",
        }
        with patch.dict(os.environ, values, clear=True):
            settings = get_settings()

        self.assertEqual(settings.deepseek_api_key, "canonical-key")

    def test_timeout_must_be_positive_number(self) -> None:
        with patch.dict(os.environ, {"LLM_TIMEOUT_SECONDS": "0"}, clear=True):
            with self.assertRaisesRegex(ValueError, "大于 0"):
                get_settings()


if __name__ == "__main__":
    unittest.main()
