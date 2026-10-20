"""兼容 OpenAI API 的模型客户端，业务代码不直接依赖具体模型供应商。"""

import json
import re
import time
from typing import Any

from app.config import Settings, get_settings


class LLMError(RuntimeError):
    """模型调用、返回格式或配置错误。"""


class LLMConfigurationError(LLMError):
    pass


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.deepseek_api_key:
            raise LLMConfigurationError(
                "尚未配置 DEEPSEEK_API_KEY。请在本地 .env 中填写密钥后重启应用。"
            )

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        try:
            import httpx
            from openai import APIConnectionError, APITimeoutError, OpenAI
        except ImportError as error:
            raise LLMConfigurationError(
                "模型客户端依赖未安装，请运行 pip install -r requirements.txt。"
            ) from error

        request = {
            "model": self.settings.deepseek_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        # 本地开发环境可能预置一个失效代理（例如 127.0.0.1:9）。默认直连，
        # 需要代理时设置 LLM_USE_ENV_PROXY=1。
        with httpx.Client(trust_env=self.settings.llm_use_env_proxy) as http_client:
            client = OpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
                timeout=self.settings.llm_timeout_seconds,
                http_client=http_client,
            )
            for attempt in range(3):
                try:
                    response = client.chat.completions.create(**request)
                    content = response.choices[0].message.content or ""
                    break
                except (APIConnectionError, APITimeoutError) as error:
                    if attempt == 2:
                        cause = getattr(error, "__cause__", None)
                        cause_text = f"原因：{cause}" if cause else ""
                        raise LLMError(
                            f"模型服务暂时无法连接，已自动重试 3 次。请检查网络后再重试。{cause_text}"
                        ) from error
                    time.sleep(1.5 * (attempt + 1))
                except Exception as error:
                    raise LLMError(f"模型调用失败：{error}") from error

        try:
            return self._parse_json(content)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise LLMError("模型返回的内容不是有效 JSON，请重试。") from error

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        text = content.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.S | re.I)
        if fenced:
            text = fenced.group(1).strip()
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("模型 JSON 顶层必须是对象")
        return value
