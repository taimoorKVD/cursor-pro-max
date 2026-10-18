"""SQLite access and schema initialization."""
from __future__ import annotations

import sqlite3
import threading
import time

from orchestrator import config

DB_LOCK = threading.RLock()


def connect() -> sqlite3.Connection:
    config.DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DATABASE_FILE), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def initialize() -> None:
    config.WORK_ROOT.mkdir(parents=True, exist_ok=True)
    with DB_LOCK, connect() as c:
        c.execute(
            """CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            sender TEXT NOT NULL,
            project TEXT NOT NULL,
            instruction TEXT NOT NULL,
            status TEXT NOT NULL,
            workspace TEXT,
            branch TEXT,
            summary TEXT,
            content_digest TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
            )"""
        )
        _ensure_column(c, "tasks", "content_digest", "TEXT")
        _ensure_column(c, "tasks", "execution_stage", "TEXT")
        _ensure_column(c, "tasks", "started_at", "INTEGER")
        _ensure_column(c, "tasks", "ended_at", "INTEGER")
        _ensure_column(c, "tasks", "last_activity_at", "INTEGER")
        _ensure_column(c, "tasks", "agent_pid", "INTEGER")
        _ensure_column(c, "tasks", "exit_code", "INTEGER")
        _ensure_column(c, "tasks", "modified_files", "TEXT")
        _ensure_column(c, "tasks", "blocker", "TEXT")
        _ensure_column(c, "tasks", "revision", "INTEGER")
        _ensure_column(c, "tasks", "approved_sha", "TEXT")
        _ensure_column(c, "tasks", "agent_chat_id", "TEXT")
        _ensure_column(c, "tasks", "attachments", "TEXT")
        c.execute("CREATE TABLE IF NOT EXISTS incoming (message_id TEXT PRIMARY KEY)")
        c.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            available_at INTEGER NOT NULL,
            leased_until INTEGER,
            last_error TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            fence TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
            )"""
        )
        _ensure_column(c, "jobs", "fence", "TEXT")
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_claim ON jobs(status, available_at, id)"
        )
        from orchestrator.attachments import ensure_schema as ensure_attachments_schema
        from orchestrator.audit import ensure_schema
        from orchestrator.converse import ensure_schema as ensure_converse_schema
        from orchestrator.history import ensure_schema as ensure_history_schema
        from orchestrator.learning import ensure_schema as ensure_learning_schema
        from orchestrator.session import ensure_schema as ensure_session_schema
        from orchestrator.task_events import ensure_schema as ensure_events_schema
        from orchestrator.token_spend import ensure_schema as ensure_token_spend_schema
        from orchestrator.webchat import ensure_schema as ensure_webchat_schema

        ensure_schema(c)
        ensure_webchat_schema(c)
        ensure_session_schema(c)
        ensure_events_schema(c)
        ensure_history_schema(c)
        ensure_attachments_schema(c)
        ensure_converse_schema(c)
        ensure_learning_schema(c)
        ensure_token_spend_schema(c)


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl_type: str) -> None:
    cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


def now() -> int:
    return int(time.time())
