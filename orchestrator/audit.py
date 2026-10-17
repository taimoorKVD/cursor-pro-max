"""Structured audit trail (no secret bodies)."""
from __future__ import annotations

import json
import logging
from typing import Any

from orchestrator import db
from orchestrator.scrub import scrub

log = logging.getLogger("orchestrator.audit")


def ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            actor TEXT,
            task_id TEXT,
            action TEXT NOT NULL,
            detail TEXT,
            ok INTEGER NOT NULL DEFAULT 1
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_events(task_id, id)")


def record(
    action: str,
    *,
    actor: str | None = None,
    task_id: str | None = None,
    detail: dict[str, Any] | None = None,
    ok: bool = True,
) -> None:
    payload = scrub(json.dumps(detail or {}, separators=(",", ":"), ensure_ascii=True))[:2000]
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        c.execute(
            """INSERT INTO audit_events (ts, actor, task_id, action, detail, ok)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (db.now(), actor, task_id, action, payload, 1 if ok else 0),
        )
    log.info(
        "audit action=%s ok=%s task_id=%s actor=%s detail=%s",
        action,
        ok,
        task_id,
        actor,
        payload,
    )
