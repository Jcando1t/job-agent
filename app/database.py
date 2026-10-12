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
    connection.execute("PRAGMA foreign_keys = ON")
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL DEFAULT 'local',
                target_id INTEGER,
                title TEXT NOT NULL,
                company TEXT NOT NULL DEFAULT '',
                city TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '手动录入',
                original_url TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (target_id) REFERENCES job_targets(id) ON DELETE SET NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL DEFAULT 'local',
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                organization TEXT NOT NULL DEFAULT '',
                period TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                source_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS resumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL DEFAULT 'local',
                version INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source_item_ids TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS resume_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL DEFAULT 'local',
                filename TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        resume_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(resumes)")
        }
        if "source_resume_id" not in resume_columns:
            connection.execute("ALTER TABLE resumes ADD COLUMN source_resume_id INTEGER")


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


def _to_job_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "target_id": row["target_id"],
        "target_title": row["target_title"],
        "title": row["title"],
        "company": row["company"],
        "city": row["city"],
        "source": row["source"],
        "original_url": row["original_url"],
        "description": row["description"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _get_job(connection: sqlite3.Connection, job_id: int) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT jobs.*, job_targets.title AS target_title
        FROM jobs
        LEFT JOIN job_targets ON job_targets.id = jobs.target_id
        WHERE jobs.id = ? AND jobs.owner_id = 'local'
        """,
        (job_id,),
    ).fetchone()


def get_jobs(database_path: Path = DATABASE_PATH) -> list[dict]:
    with _connection(database_path) as connection:
        rows = connection.execute(
            """
            SELECT jobs.*, job_targets.title AS target_title
            FROM jobs
            LEFT JOIN job_targets ON job_targets.id = jobs.target_id
            WHERE jobs.owner_id = 'local'
            ORDER BY jobs.id DESC
            """
        ).fetchall()
    return [_to_job_dict(row) for row in rows]


def create_job(
    title: str,
    company: str = "",
    city: str = "",
    source: str = "手动录入",
    original_url: str = "",
    description: str = "",
    target_id: int | None = None,
    database_path: Path = DATABASE_PATH,
) -> dict | None:
    with _connection(database_path) as connection:
        if target_id is not None:
            target = connection.execute(
                "SELECT id FROM job_targets WHERE id = ? AND owner_id = 'local'",
                (target_id,),
            ).fetchone()
            if target is None:
                return None
        cursor = connection.execute(
            """
            INSERT INTO jobs (target_id, title, company, city, source, original_url, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (target_id, title, company, city, source, original_url, description),
        )
        row = _get_job(connection, cursor.lastrowid)
    return _to_job_dict(row)


def update_job(
    job_id: int,
    title: str,
    company: str = "",
    city: str = "",
    source: str = "手动录入",
    original_url: str = "",
    description: str = "",
    target_id: int | None = None,
    database_path: Path = DATABASE_PATH,
) -> dict | None:
    with _connection(database_path) as connection:
        if target_id is not None:
            target = connection.execute(
                "SELECT id FROM job_targets WHERE id = ? AND owner_id = 'local'",
                (target_id,),
            ).fetchone()
            if target is None:
                return None
        cursor = connection.execute(
            """
            UPDATE jobs
            SET target_id = ?, title = ?, company = ?, city = ?, source = ?,
                original_url = ?, description = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND owner_id = 'local'
            """,
            (target_id, title, company, city, source, original_url, description, job_id),
        )
        if cursor.rowcount == 0:
            return None
        row = _get_job(connection, job_id)
    return _to_job_dict(row)


def delete_job(job_id: int, database_path: Path = DATABASE_PATH) -> bool:
    with _connection(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM jobs WHERE id = ? AND owner_id = 'local'",
            (job_id,),
        )
    return cursor.rowcount > 0


def _to_knowledge_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "category": row["category"],
        "title": row["title"],
        "organization": row["organization"],
        "period": row["period"],
        "content": row["content"],
        "source_note": row["source_note"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_knowledge_items(database_path: Path = DATABASE_PATH) -> list[dict]:
    with _connection(database_path) as connection:
        rows = connection.execute(
            "SELECT * FROM knowledge_items WHERE owner_id = 'local' ORDER BY id DESC"
        ).fetchall()
    return [_to_knowledge_dict(row) for row in rows]


def create_knowledge_item(
    category: str,
    title: str,
    organization: str = "",
    period: str = "",
    content: str = "",
    source_note: str = "",
    database_path: Path = DATABASE_PATH,
) -> dict:
    with _connection(database_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO knowledge_items (category, title, organization, period, content, source_note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (category, title, organization, period, content, source_note),
        )
        row = connection.execute(
            "SELECT * FROM knowledge_items WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return _to_knowledge_dict(row)


def update_knowledge_item(
    item_id: int,
    category: str,
    title: str,
    organization: str = "",
    period: str = "",
    content: str = "",
    source_note: str = "",
    database_path: Path = DATABASE_PATH,
) -> dict | None:
    with _connection(database_path) as connection:
        cursor = connection.execute(
            """
            UPDATE knowledge_items
            SET category = ?, title = ?, organization = ?, period = ?, content = ?,
                source_note = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND owner_id = 'local'
            """,
            (category, title, organization, period, content, source_note, item_id),
        )
        if cursor.rowcount == 0:
            return None
        row = connection.execute(
            "SELECT * FROM knowledge_items WHERE id = ?",
            (item_id,),
        ).fetchone()
    return _to_knowledge_dict(row)


def delete_knowledge_item(item_id: int, database_path: Path = DATABASE_PATH) -> bool:
    with _connection(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM knowledge_items WHERE id = ? AND owner_id = 'local'",
            (item_id,),
        )
    return cursor.rowcount > 0


def _to_resume_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "version": row["version"],
        "title": row["title"],
        "content": row["content"],
        "source_item_ids": json.loads(row["source_item_ids"]),
        "source_resume_id": row["source_resume_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_resumes(database_path: Path = DATABASE_PATH) -> list[dict]:
    with _connection(database_path) as connection:
        rows = connection.execute(
            "SELECT * FROM resumes WHERE owner_id = 'local' ORDER BY version DESC, id DESC"
        ).fetchall()
    return [_to_resume_dict(row) for row in rows]


def _to_resume_source_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "filename": row["filename"],
        "content": row["content"],
        "created_at": row["created_at"],
    }


def get_resume_sources(database_path: Path = DATABASE_PATH) -> list[dict]:
    with _connection(database_path) as connection:
        rows = connection.execute(
            "SELECT * FROM resume_sources WHERE owner_id = 'local' ORDER BY id DESC"
        ).fetchall()
    return [_to_resume_source_dict(row) for row in rows]


def create_resume_source(
    filename: str,
    content: str,
    database_path: Path = DATABASE_PATH,
) -> dict:
    with _connection(database_path) as connection:
        cursor = connection.execute(
            "INSERT INTO resume_sources (filename, content) VALUES (?, ?)",
            (filename, content),
        )
        row = connection.execute(
            "SELECT * FROM resume_sources WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return _to_resume_source_dict(row)


def delete_resume_source(source_id: int, database_path: Path = DATABASE_PATH) -> bool:
    with _connection(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM resume_sources WHERE id = ? AND owner_id = 'local'",
            (source_id,),
        )
    return cursor.rowcount > 0


def create_resume(
    title: str,
    content: str,
    source_item_ids: list[int],
    source_resume_id: int | None = None,
    database_path: Path = DATABASE_PATH,
) -> dict:
    source_item_ids = list(dict.fromkeys(item_id for item_id in source_item_ids if item_id > 0))
    with _connection(database_path) as connection:
        next_version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM resumes WHERE owner_id = 'local'"
        ).fetchone()[0]
        cursor = connection.execute(
            """
            INSERT INTO resumes (version, title, content, source_item_ids, source_resume_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (next_version, title, content, json.dumps(source_item_ids), source_resume_id),
        )
        row = connection.execute(
            "SELECT * FROM resumes WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return _to_resume_dict(row)


def delete_resume(resume_id: int, database_path: Path = DATABASE_PATH) -> bool:
    with _connection(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM resumes WHERE id = ? AND owner_id = 'local'",
            (resume_id,),
        )
    return cursor.rowcount > 0
