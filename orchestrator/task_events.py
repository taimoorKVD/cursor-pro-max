"""Durable execution events and stage helpers for coding tasks.

Stages must reflect evidence. While the Cursor subprocess is alive without
structured mid-run signals, the stage is ``agent_running`` — never inferred
``investigating`` / ``implementing``.
"""
from __future__ import annotations

import json
from typing import Any

from orchestrator import db

# Evidence-backed stages only. investigating/implementing are reserved for
# future structured agent events — not set merely because a process is alive.
STAGES = (
    "queued",
    "preparing_workspace",
    "agent_running",
    "testing",
    "ready_for_review",
    "blocked",
    "failed",
    "canceled",
    "timeout",
    # Optional future evidence-only stages (not used without events):
    "investigating",
    "implementing",
)

# Happy-path pipeline for remaining/completed checklists
PIPELINE = (
    "queued",
    "preparing_workspace",
    "agent_running",
    "testing",
    "ready_for_review",
)

STAGE_LABELS = {
    "queued": "Queued",
    "preparing_workspace": "Preparing isolated workspace",
    "agent_running": "Agent running — awaiting tool activity",
    "investigating": "Investigating codebase",
    "implementing": "Implementing changes",
    "testing": "Running configured tests",
    "ready_for_review": "Ready for review",
    "blocked": "Blocked",
    "failed": "Failed",
    "canceled": "Canceled",
    "timeout": "Timed out",
}

# Shown only while stage is agent_running and no read/write stream evidence yet.
AGENT_UNAVAILABLE_DETAIL = "Agent running"
# Before the Cursor subprocess exists (auth / AppContainer ACL prep can take a while).
AGENT_STARTING_DETAIL = "Starting Cursor agent — preparing isolation (process not started yet)."


def ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            ts INTEGER NOT NULL,
            stage TEXT,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            detail_json TEXT,
            FOREIGN KEY(task_id) REFERENCES tasks(id)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id, id)"
    )


def record(
    task_id: str,
    event_type: str,
    message: str,
    *,
    stage: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Append an execution event. Does not invent progress — callers pass evidence."""
    now = db.now()
    payload = json.dumps(detail, ensure_ascii=False) if detail else None
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        c.execute(
            """INSERT INTO task_events (task_id, ts, stage, event_type, message, detail_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_id, now, stage, event_type, message[:2000], payload),
        )


def clear_for_task(task_id: str) -> int:
    """Delete all events for a task (used when chat is cleared)."""
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        cur = c.execute("DELETE FROM task_events WHERE task_id=?", (task_id,))
        return int(cur.rowcount or 0)


def list_events(task_id: str, *, after_id: int = 0, limit: int = 100) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        if after_id > 0:
            rows = c.execute(
                """SELECT id, task_id, ts, stage, event_type, message, detail_json
                   FROM task_events WHERE task_id=? AND id > ? ORDER BY id LIMIT ?""",
                (task_id, after_id, limit),
            ).fetchall()
        else:
            # Most recent events (progress UI shows the tail).
            rows = list(
                reversed(
                    c.execute(
                        """SELECT id, task_id, ts, stage, event_type, message, detail_json
                           FROM task_events WHERE task_id=? ORDER BY id DESC LIMIT ?""",
                        (task_id, limit),
                    ).fetchall()
                )
            )
    out = []
    for row in rows:
        item = dict(row)
        raw = item.pop("detail_json", None)
        if raw:
            try:
                item["detail"] = json.loads(raw)
            except json.JSONDecodeError:
                item["detail"] = None
        else:
            item["detail"] = None
        out.append(item)
    return out


def latest_event(task_id: str) -> dict[str, Any] | None:
    rows = list_events(task_id, limit=500)
    return rows[-1] if rows else None


def completed_and_remaining(stage: str | None, status: str) -> tuple[list[str], list[str], str]:
    """Return (completed labels, remaining labels, current label) from recorded stage."""
    if status == "failed":
        return ([], [], STAGE_LABELS.get(stage or "failed", "Failed"))
    if status == "published":
        done = [STAGE_LABELS[s] for s in PIPELINE]
        return (done, [], "Published — applied to your project")
    if status == "publish_failed":
        done = [STAGE_LABELS[s] for s in PIPELINE]
        return (done, [], "Publish failed — needs attention")
    if status == "rejected":
        done = [STAGE_LABELS[s] for s in PIPELINE]
        return (done, [], "Rejected")
    if status in {"review", "publishing"}:
        done = [STAGE_LABELS[s] for s in PIPELINE]
        return (done, [], STAGE_LABELS["ready_for_review"])

    current = stage or ("queued" if status == "queued" else "agent_running")
    # investigating / implementing are evidence refinements of the agent_running
    # pipeline slot — keep their labels, but index the checklist on agent_running.
    pipeline_stage = (
        "agent_running" if current in {"investigating", "implementing"} else current
    )

    if pipeline_stage not in PIPELINE:
        return ([], [], STAGE_LABELS.get(current, current))

    idx = PIPELINE.index(pipeline_stage)
    completed = [STAGE_LABELS[s] for s in PIPELINE[:idx]]
    remaining = [STAGE_LABELS[s] for s in PIPELINE[idx + 1 :]]
    if current in {"investigating", "implementing"}:
        current_label = STAGE_LABELS[current]
    elif current == "agent_running":
        current_label = AGENT_UNAVAILABLE_DETAIL
    else:
        current_label = STAGE_LABELS.get(current, current)
    return (completed, remaining, current_label)
