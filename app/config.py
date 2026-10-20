"""应用配置。

配置优先从项目根目录的 .env 和系统环境变量读取，敏感值不写入代码。
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _project_path(value: str, default: Path) -> Path:
    path = Path(value).expanduser() if value else default
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_path: Path
    file_storage_dir: Path
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    llm_timeout_seconds: float
    llm_use_env_proxy: bool = False


def get_settings() -> Settings:
    """每次读取当前环境，便于测试和本地修改配置后重新启动应用。"""
    timeout_text = os.getenv("LLM_TIMEOUT_SECONDS", "30")
    try:
        timeout = float(timeout_text)
    except ValueError as error:
        raise ValueError("LLM_TIMEOUT_SECONDS 必须是数字") from error
    if timeout <= 0:
        raise ValueError("LLM_TIMEOUT_SECONDS 必须大于 0")

    return Settings(
        app_env=os.getenv("APP_ENV", "local"),
        database_path=_project_path(
            os.getenv("DATABASE_PATH", ""), PROJECT_ROOT / "data" / "job_agent.db"
        ),
        file_storage_dir=_project_path(
            os.getenv("FILE_STORAGE_DIR", ""), PROJECT_ROOT / "data" / "files"
        ),
        # Accept the compact canonical name and the underscored variant used
        # by some local environment configurations.
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEP_SEEK_API_KEY", ""),
        deepseek_base_url=os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        ),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        llm_timeout_seconds=timeout,
        llm_use_env_proxy=os.getenv("LLM_USE_ENV_PROXY", "0").strip().lower() in {"1", "true", "yes"},
    )
