"""验证兼容 OpenAI 格式的模型客户端，不发送真实网络请求。"""

from types import SimpleNamespace
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from app.config import Settings
from app.services.llm_client import LLMClient, LLMConfigurationError, LLMError


class LLMClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            app_env="test",
            database_path=Path("test.db"),
            file_storage_dir=Path("test-files"),
            deepseek_api_key="test-only-key",
            deepseek_base_url="https://api.example.test",
            deepseek_model="test-model",
            llm_timeout_seconds=12.5,
        )

    def test_sends_compatible_json_request_and_parses_fenced_response(self) -> None:
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='```json\n{"resume_markdown":"经历"}\n```')
                )
            ]
        )
        with patch("httpx.Client") as http_client, patch("openai.OpenAI") as openai_client:
            openai_client.return_value.chat.completions.create.return_value = response

            result = LLMClient(self.settings).complete_json("系统规则", "简历资料")

        self.assertEqual(result, {"resume_markdown": "经历"})
        http_client.assert_called_once_with(trust_env=False)
        openai_client.assert_called_once_with(
            api_key="test-only-key",
            base_url="https://api.example.test",
            timeout=12.5,
            http_client=http_client.return_value.__enter__.return_value,
        )
        request = openai_client.return_value.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "test-model")
        self.assertEqual(
            request["messages"],
            [
                {"role": "system", "content": "系统规则"},
                {"role": "user", "content": "简历资料"},
            ],
        )
        self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertEqual(request["temperature"], 0.2)

    def test_environment_proxy_can_be_enabled_explicitly(self) -> None:
        settings = replace(self.settings, llm_use_env_proxy=True)
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])
        with patch("httpx.Client") as http_client, patch("openai.OpenAI") as openai_client:
            openai_client.return_value.chat.completions.create.return_value = response
            LLMClient(settings).complete_json("系统", "用户")
        http_client.assert_called_once_with(trust_env=True)

    def test_missing_api_key_has_actionable_configuration_error(self) -> None:
        settings = replace(self.settings, deepseek_api_key="")
        with self.assertRaisesRegex(LLMConfigurationError, "DEEPSEEK_API_KEY"):
            LLMClient(settings)

    def test_provider_error_is_wrapped_in_readable_llm_error(self) -> None:
        with patch("openai.OpenAI") as openai_client:
            openai_client.return_value.chat.completions.create.side_effect = TimeoutError(
                "request timed out"
            )

            with self.assertRaisesRegex(LLMError, "模型调用失败：request timed out"):
                LLMClient(self.settings).complete_json("系统", "用户内容")

    def test_invalid_json_response_has_readable_error(self) -> None:
        with patch("openai.OpenAI") as openai_client:
            openai_client.return_value.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="不是 JSON"))]
            )

            with self.assertRaisesRegex(LLMError, "不是有效 JSON"):
                LLMClient(self.settings).complete_json("系统", "用户内容")

    def test_json_array_is_rejected_when_object_is_required(self) -> None:
        with patch("openai.OpenAI") as openai_client:
            openai_client.return_value.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="[1, 2]"))]
            )

            with self.assertRaisesRegex(LLMError, "不是有效 JSON"):
                LLMClient(self.settings).complete_json("系统", "用户内容")


if __name__ == "__main__":
    unittest.main()
