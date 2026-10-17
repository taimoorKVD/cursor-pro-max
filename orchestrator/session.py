"""Durable per-sender conversation context (active project / active task)."""
from __future__ import annotations

from typing import Any

from orchestrator import db


def ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS chat_sessions (
            sender TEXT PRIMARY KEY,
            active_project TEXT,
            active_task_id TEXT,
            updated_at INTEGER NOT NULL
        )"""
    )


def get(sender: str) -> dict[str, Any]:
    if not sender:
        return {"sender": "", "active_project": None, "active_task_id": None}
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        row = c.execute(
            "SELECT sender, active_project, active_task_id, updated_at FROM chat_sessions WHERE sender=?",
            (sender,),
        ).fetchone()
    if not row:
        return {
            "sender": sender,
            "active_project": None,
            "active_task_id": None,
            "updated_at": None,
        }
    return dict(row)


def set_active_project(sender: str, project: str | None) -> None:
    switch_project(sender, project)


def set_active_task(sender: str, task_id: str | None, *, project: str | None = None) -> None:
    fields: dict[str, Any] = {"active_task_id": task_id}
    if project is not None:
        fields["active_project"] = project
    _upsert(sender, **fields)


def switch_project(sender: str, project: str | None) -> dict[str, Any]:
    """Set active project and restore that project's in-flight task pointer.

    Switching chats does **not** cancel work on the previous project — other
    project tasks keep running. The session's ``active_task_id`` is rebound to
    the destination project's queued/running/review task (if any) so progress
    UI stays scoped to the chat you are viewing.

    Returns ``{changed, previous, project}``.
    """
    current = get(sender)
    previous = (current.get("active_project") or None) or None
    new = (project or None) or None
    if previous:
        previous = str(previous).strip() or None
    if new:
        new = str(new).strip() or None
    changed = previous != new
    if changed:
        task_id = None
        if new:
            try:
                from orchestrator import tasks

                inflight = tasks.active_task_for_sender(sender, project=new)
                if inflight:
                    task_id = inflight.get("id")
            except Exception:  # noqa: BLE001
                task_id = None
        _upsert(sender, active_project=new, active_task_id=task_id)
        try:
            from orchestrator import converse

            converse.clear_pending(sender)
        except Exception:  # noqa: BLE001
            pass
    elif new is not None:
        _upsert(sender, active_project=new)
    return {"changed": changed, "previous": previous, "project": new}


def clear(sender: str) -> None:
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        c.execute("DELETE FROM chat_sessions WHERE sender=?", (sender,))


def _upsert(sender: str, **fields: Any) -> None:
    if not sender:
        return
    now = db.now()
    current = get(sender)
    project = current.get("active_project")
    task_id = current.get("active_task_id")
    if "active_project" in fields:
        project = fields["active_project"]
    if "active_task_id" in fields:
        task_id = fields["active_task_id"]
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        c.execute(
            """INSERT INTO chat_sessions (sender, active_project, active_task_id, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(sender) DO UPDATE SET
                 active_project=excluded.active_project,
                 active_task_id=excluded.active_task_id,
                 updated_at=excluded.updated_at""",
            (sender, project, task_id, now),
        )
