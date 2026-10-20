"""把历史数据库中保存的简历材料迁移到配置的本地文件目录。"""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import DATABASE_PATH
from app.models import ResumeImageSource, ResumeSource
from app.sqlalchemy_db import create_database_engine
from app.storage import delete_private_file, save_private_file


def migrate_legacy_private_files(database_path: Path = DATABASE_PATH) -> int:
    """只复制尚无 storage_path 的旧记录；重复运行不会重复写入。"""
    engine = create_database_engine(database_path)
    created_paths: list[str] = []
    try:
        with Session(engine) as session:
            images = session.scalars(
                select(ResumeImageSource).where(ResumeImageSource.storage_path.is_(None))
            ).all()
            sources = session.scalars(
                select(ResumeSource).where(ResumeSource.storage_path.is_(None))
            ).all()
            for image in images:
                if not image.content:
                    continue
                path = save_private_file(image.content, Path(image.filename).suffix)
                created_paths.append(path)
                image.storage_path = path
            for source in sources:
                if not source.content:
                    continue
                # 历史记录只保存了解析出的文字，原始二进制文件无法从数据库恢复。
                path = save_private_file(source.content, ".txt")
                created_paths.append(path)
                source.storage_path = path
            session.commit()
            return len(created_paths)
    except Exception:
        for path in created_paths:
            delete_private_file(path)
        raise
    finally:
        engine.dispose()
