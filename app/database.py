import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "data" / "job_agent.db"


def _connect(database_path: Path = DATABASE_PATH) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def _connection(database_path: Path = DATABASE_PATH) -> Iterator[sqlite3.Connection]:
    connection = _connect(database_path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(database_path: Path = DATABASE_PATH) -> None:
    with _connection(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS job_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL DEFAULT 'local',
                title TEXT NOT NULL,
                keywords TEXT NOT NULL DEFAULT '',
                cities TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "keywords": row["keywords"],
        "cities": json.loads(row["cities"]),
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_targets(database_path: Path = DATABASE_PATH) -> list[dict]:
    with _connection(database_path) as connection:
        rows = connection.execute(
            "SELECT * FROM job_targets WHERE owner_id = 'local' ORDER BY id DESC"
        ).fetchall()
    return [_to_dict(row) for row in rows]


def create_target(
    title: str,
    keywords: str,
    cities: list[str],
    database_path: Path = DATABASE_PATH,
) -> dict:
    with _connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO job_targets (title, keywords, cities)
            VALUES (?, ?, ?)
            """,
            (title, keywords, json.dumps(cities, ensure_ascii=False)),
        )
        row = connection.execute(
            "SELECT * FROM job_targets WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return _to_dict(row)


def update_target(
    target_id: int,
    title: str,
    keywords: str,
    cities: list[str],
    database_path: Path = DATABASE_PATH,
) -> dict | None:
    with _connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE job_targets
            SET title = ?, keywords = ?, cities = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND owner_id = 'local'
            """,
            (title, keywords, json.dumps(cities, ensure_ascii=False), target_id),
        )
        if cursor.rowcount == 0:
            return None
        row = connection.execute(
            "SELECT * FROM job_targets WHERE id = ?",
            (target_id,),
        ).fetchone()
    return _to_dict(row)


def set_target_active(
    target_id: int,
    is_active: bool,
    database_path: Path = DATABASE_PATH,
) -> dict | None:
    with _connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE job_targets
            SET is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND owner_id = 'local'
            """,
            (int(is_active), target_id),
        )
        if cursor.rowcount == 0:
            return None
        row = connection.execute(
            "SELECT * FROM job_targets WHERE id = ?",
            (target_id,),
        ).fetchone()
    return _to_dict(row)


def delete_target(target_id: int, database_path: Path = DATABASE_PATH) -> bool:
    with _connection(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM job_targets WHERE id = ? AND owner_id = 'local'",
            (target_id,),
        )
    return cursor.rowcount > 0
