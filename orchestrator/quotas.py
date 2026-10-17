"""Per-sender task caps and daily Groq/Cursor call ceilings."""
from __future__ import annotations

from orchestrator import config, db


class QuotaExceeded(RuntimeError):
    pass


def ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS usage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            kind TEXT NOT NULL,
            sender TEXT
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_kind_ts ON usage_events(kind, ts)")


def enabled() -> bool:
    return bool(getattr(config, "QUOTAS_ENABLED", True))


def _day_start() -> int:
    now = db.now()
    return now - (now % 86400)


def _count_tasks(sender: str) -> int:
    with db.DB_LOCK, db.connect() as c:
        row = c.execute(
            "SELECT COUNT(*) FROM tasks WHERE sender=? AND created_at>=?",
            (sender, _day_start()),
        ).fetchone()
    return int(row[0]) if row else 0


def _count_usage(kind: str) -> int:
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        row = c.execute(
            "SELECT COUNT(*) FROM usage_events WHERE kind=? AND ts>=?",
            (kind, _day_start()),
        ).fetchone()
    return int(row[0]) if row else 0


def assert_task_allowed(sender: str) -> None:
    if not enabled():
        return
    limit = int(getattr(config, "MAX_TASKS_PER_SENDER_PER_DAY", 40))
    if limit <= 0:
        return
    if _count_tasks(sender) >= limit:
        raise QuotaExceeded(
            f"Daily task limit reached ({limit} for this sender). Try again tomorrow."
        )


def assert_agent_allowed() -> None:
    if not enabled():
        return
    limit = int(getattr(config, "MAX_AGENT_STARTS_PER_DAY", 40))
    if limit <= 0:
        return
    if _count_usage("cursor_agent") >= limit:
        raise QuotaExceeded(f"Daily Cursor agent limit reached ({limit}).")


def assert_groq_allowed() -> None:
    if not enabled():
        return
    limit = int(getattr(config, "MAX_GROQ_CALLS_PER_DAY", 300))
    if limit <= 0:
        return
    if _count_usage("groq") >= limit:
        raise QuotaExceeded(f"Daily Groq call limit reached ({limit}).")


def record(kind: str, sender: str | None = None) -> None:
    if not enabled():
        return
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        c.execute(
            "INSERT INTO usage_events (ts, kind, sender) VALUES (?, ?, ?)",
            (db.now(), kind, sender),
        )
