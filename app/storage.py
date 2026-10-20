"""本地敏感文件存储：文件名使用随机 UUID，避免把用户原文件名当作路径。"""

import re
import uuid
from pathlib import Path

from app.config import get_settings


def save_private_file(content: bytes | str, suffix: str) -> str:
    directory = get_settings().file_storage_dir
    directory.mkdir(parents=True, exist_ok=True)
    clean_suffix = suffix if re.fullmatch(r"\.[a-zA-Z0-9]{1,8}", suffix or "") else ".dat"
    relative_name = f"{uuid.uuid4().hex}{clean_suffix.lower()}"
    path = directory / relative_name
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return relative_name


def get_private_file(relative_name: str) -> Path:
    root = get_settings().file_storage_dir.resolve()
    path = (root / relative_name).resolve()
    if path.parent != root:
        raise ValueError("本地文件路径无效")
    return path


def delete_private_file(relative_name: str | None) -> None:
    if not relative_name:
        return
    get_private_file(relative_name).unlink(missing_ok=True)
