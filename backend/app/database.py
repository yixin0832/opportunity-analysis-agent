from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import get_settings


def database_path_from_url(database_url: str | None = None) -> Path:
    url = database_url or get_settings().database_url
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise ValueError("M4 当前仅支持 sqlite:/// 数据库地址。")
    raw_path = url[len(prefix):]
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def connect(database_url: str | None = None) -> sqlite3.Connection:
    db_path = database_path_from_url(database_url)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(connection: sqlite3.Connection | None = None) -> None:
    owns_connection = connection is None
    conn = connection or connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS analysis_sessions (
                analysis_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                original_input TEXT NOT NULL,
                current_status TEXT NOT NULL,
                current_stage TEXT,
                current_revision INTEGER NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                app_version TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS analysis_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                input_text TEXT NOT NULL,
                clarification_answers_json TEXT NOT NULL,
                raw_extraction_json TEXT NOT NULL,
                validated_opportunity_json TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                pipeline_version TEXT NOT NULL,
                latency_ms INTEGER,
                UNIQUE(analysis_id, revision),
                FOREIGN KEY (analysis_id) REFERENCES analysis_sessions(analysis_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_analysis_revisions_analysis_revision
                ON analysis_revisions(analysis_id, revision);
            CREATE INDEX IF NOT EXISTS idx_analysis_sessions_updated_at
                ON analysis_sessions(updated_at);
            """
        )
        conn.commit()
    finally:
        if owns_connection:
            conn.close()


def check_db() -> bool:
    try:
        with connect() as conn:
            init_db(conn)
            conn.execute("SELECT 1").fetchone()
        return True
    except Exception:
        return False
