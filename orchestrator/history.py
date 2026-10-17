"""Shared conversational turn history for every messaging channel.

Identity isolation: rows are keyed by sender id
(`web:owner`, `tg:<id>`, WhatsApp digits).

Project isolation: turns are also tagged with the active project so switching
from LifeOS to another project does not leak the previous thread into LLM
context or the chat UI.
"""
from __future__ import annotations

from typing import Any

from orchestrator import db

MAX_TEXT = 4000
DEFAULT_LIMIT = 16


def ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS conversation_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            ts INTEGER NOT NULL,
            direction TEXT NOT NULL,
            text TEXT NOT NULL,
            level TEXT NOT NULL DEFAULT 'info',
            channel TEXT,
            project TEXT
        )"""
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(conversation_turns)")}
    if "project" not in cols:
        conn.execute("ALTER TABLE conversation_turns ADD COLUMN project TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_sender_id "
        "ON conversation_turns(sender, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversation_sender_project "
        "ON conversation_turns(sender, project, id)"
    )


def channel_of(sender: str) -> str:
    if sender.startswith("web:"):
        return "web"
    if sender.startswith("tg:"):
        return "telegram"
    return "whatsapp"


def _active_project(sender: str) -> str | None:
    try:
        from orchestrator import session

        proj = (session.get(sender).get("active_project") or "").strip()
        return proj or None
    except Exception:  # noqa: BLE001
        return None


def append(
    sender: str,
    direction: str,
    text: str,
    *,
    level: str = "info",
    project: str | None = None,
) -> None:
    """Persist one turn. Safe to call from any channel adapter."""
    if not sender:
        return
    body = (text or "")[:MAX_TEXT]
    if not body:
        return
    direction = "in" if direction == "in" else "out"
    if project is None:
        project = _active_project(sender)
    now = db.now()
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        c.execute(
            """INSERT INTO conversation_turns
               (sender, ts, direction, text, level, channel, project)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (sender, now, direction, body, level or "info", channel_of(sender), project),
        )


def recent(
    sender: str,
    limit: int = DEFAULT_LIMIT,
    *,
    project: str | None = None,
) -> list[dict[str, Any]]:
    """Latest turns for sender (and optional project), oldest→newest."""
    if not sender:
        return []
    limit = max(1, min(int(limit), 80))
    if project is None:
        project = _active_project(sender)
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        if project:
            rows = c.execute(
                """SELECT id, sender, ts, direction, text, level, channel, project
                   FROM conversation_turns
                   WHERE sender=? AND project=?
                   ORDER BY id DESC LIMIT ?""",
                (sender, project, limit),
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT id, sender, ts, direction, text, level, channel, project
                   FROM conversation_turns
                   WHERE sender=?
                   ORDER BY id DESC LIMIT ?""",
                (sender, limit),
            ).fetchall()
    return [dict(r) for r in reversed(list(rows))]


def clear_sender(sender: str, *, project: str | None = None) -> None:
    if not sender:
        return
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        if project:
            c.execute(
                "DELETE FROM conversation_turns WHERE sender=? AND project=?",
                (sender, project),
            )
        else:
            c.execute("DELETE FROM conversation_turns WHERE sender=?", (sender,))
