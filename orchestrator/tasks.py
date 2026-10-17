"""Task persistence helpers."""
from __future__ import annotations

import json
from typing import Any

from orchestrator import db
from orchestrator.state import assert_recovery, assert_transition

_TASK_COLUMNS = frozenset(
    {
        "sender",
        "project",
        "instruction",
        "status",
        "workspace",
        "branch",
        "summary",
        "content_digest",
        "updated_at",
        "execution_stage",
        "started_at",
        "ended_at",
        "last_activity_at",
        "agent_pid",
        "exit_code",
        "modified_files",
        "blocker",
        "revision",
        "approved_sha",
        "agent_chat_id",
    }
)


def get_task(task_id: str) -> dict[str, Any] | None:
    with db.DB_LOCK, db.connect() as c:
        row = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None


def create_task(task_id: str, sender: str, project: str, instruction: str) -> None:
    now = db.now()
    with db.DB_LOCK, db.connect() as c:
        c.execute(
            """INSERT INTO tasks
            (id,sender,project,instruction,status,execution_stage,revision,
             created_at,updated_at,last_activity_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (task_id, sender, project, instruction, "queued", "queued", 1, now, now, now),
        )


def update_task(task_id: str, **fields: Any) -> None:
    if not fields:
        return
    unknown = set(fields) - _TASK_COLUMNS
    if unknown:
        raise ValueError(f"Unknown task fields: {sorted(unknown)}")
    if "status" in fields:
        current = get_task(task_id)
        if current:
            assert_transition(current["status"], fields["status"])
    fields = dict(fields)
    if "modified_files" in fields and not isinstance(fields["modified_files"], str):
        fields["modified_files"] = json.dumps(fields["modified_files"], ensure_ascii=False)
    fields["updated_at"] = db.now()
    if "last_activity_at" not in fields:
        fields["last_activity_at"] = fields["updated_at"]
    assignments = ", ".join(f"{k}=?" for k in fields)
    with db.DB_LOCK, db.connect() as c:
        c.execute(
            f"UPDATE tasks SET {assignments} WHERE id=?",
            (*fields.values(), task_id),
        )


def cas_update(task_id: str, expect_status: str, **fields: Any) -> bool:
    """Apply ``fields`` only if the row is still ``expect_status``. Returns whether it won."""
    if not fields:
        return False
    unknown = set(fields) - _TASK_COLUMNS
    if unknown:
        raise ValueError(f"Unknown task fields: {sorted(unknown)}")
    new_status = fields.get("status", expect_status)
    assert_transition(expect_status, new_status)
    fields = dict(fields)
    if "modified_files" in fields and not isinstance(fields["modified_files"], str):
        fields["modified_files"] = json.dumps(fields["modified_files"], ensure_ascii=False)
    fields["updated_at"] = db.now()
    if "last_activity_at" not in fields:
        fields["last_activity_at"] = fields["updated_at"]
    assignments = ", ".join(f"{k}=?" for k in fields)
    with db.DB_LOCK, db.connect() as c:
        cur = c.execute(
            f"UPDATE tasks SET {assignments} WHERE id=? AND status=?",
            (*fields.values(), task_id, expect_status),
        )
        return cur.rowcount == 1


def recover_task(task_id: str, status: str, summary: str) -> None:
    """Restart-only transition. Does not delete the workspace."""
    current = get_task(task_id)
    if not current:
        return
    assert_recovery(current["status"], status)
    now = db.now()
    with db.DB_LOCK, db.connect() as c:
        c.execute(
            """UPDATE tasks SET status=?, summary=?, updated_at=?, last_activity_at=?
               WHERE id=? AND status=?""",
            (status, summary[:1000], now, now, task_id, current["status"]),
        )


def claim_publishing(task_id: str) -> bool:
    """Single-flight review/publish_failed → publishing."""
    current = get_task(task_id)
    if not current or current["status"] not in {"review", "publish_failed"}:
        return False
    assert_transition(current["status"], "publishing")
    now = db.now()
    with db.DB_LOCK, db.connect() as c:
        cur = c.execute(
            """UPDATE tasks SET status='publishing', updated_at=?, last_activity_at=?
               WHERE id=? AND status=?""",
            (now, now, task_id, current["status"]),
        )
        return cur.rowcount == 1


def queue_for_resume(task_id: str, *, instruction: str | None = None) -> bool:
    """Re-queue a review/failed task to continue in the same workspace via --resume.

    Bumps ``revision``, keeps ``workspace`` / ``branch`` / ``agent_chat_id``, and
    clears review digest so a fresh approval is required.
    """
    current = get_task(task_id)
    if not current or current["status"] not in {"review", "failed"}:
        return False
    assert_transition(current["status"], "queued")
    now = db.now()
    rev = int(current.get("revision") or 1) + 1
    fields: dict[str, Any] = {
        "status": "queued",
        "execution_stage": "queued",
        "revision": rev,
        "summary": None,
        "content_digest": None,
        "approved_sha": None,
        "blocker": None,
        "exit_code": None,
        "ended_at": None,
        "agent_pid": None,
        "updated_at": now,
        "last_activity_at": now,
    }
    if instruction is not None and instruction.strip():
        fields["instruction"] = instruction.strip()
    assignments = ", ".join(f"{k}=?" for k in fields)
    with db.DB_LOCK, db.connect() as c:
        cur = c.execute(
            f"UPDATE tasks SET {assignments} WHERE id=? AND status=?",
            (*fields.values(), task_id, current["status"]),
        )
        return cur.rowcount == 1


def can_resume_agent(task: dict[str, Any] | None) -> bool:
    """True when the task has a durable Cursor session + existing workspace."""
    if not task:
        return False
    chat_id = (task.get("agent_chat_id") or "").strip()
    ws = (task.get("workspace") or "").strip()
    if not chat_id or not ws:
        return False
    from pathlib import Path

    return Path(ws).is_dir()


def touch(task_id: str) -> None:
    now = db.now()
    with db.DB_LOCK, db.connect() as c:
        c.execute(
            "UPDATE tasks SET last_activity_at=?, updated_at=? WHERE id=?",
            (now, now, task_id),
        )


def set_stage(task_id: str, stage: str, *, extra: dict[str, Any] | None = None) -> None:
    payload = {"execution_stage": stage, "last_activity_at": db.now()}
    if extra:
        payload.update(extra)
    update_task(task_id, **payload)


def seen_message(message_id: str) -> bool:
    """Return True if this is the first time we see message_id."""
    with db.DB_LOCK, db.connect() as c:
        inserted = c.execute(
            "INSERT OR IGNORE INTO incoming(message_id) VALUES (?)", (message_id,)
        ).rowcount
    return bool(inserted)


def list_tasks_for_sender(sender: str, *, limit: int = 15) -> list[dict[str, Any]]:
    with db.DB_LOCK, db.connect() as c:
        rows = c.execute(
            """SELECT id, project, status, instruction, summary, execution_stage,
                      created_at, updated_at, started_at, last_activity_at, ended_at,
                      modified_files, blocker, exit_code, workspace, branch,
                      revision, agent_chat_id, content_digest
               FROM tasks WHERE sender=? ORDER BY created_at DESC LIMIT ?""",
            (sender, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def active_task_for_sender(
    sender: str, *, project: str | None = None
) -> dict[str, Any] | None:
    """Prefer in-flight work, else newest review task.

    Terminal / cancelled tasks are never returned so clearing chat (which drops
    the session ``active_task_id``) does not keep the progress panel glued to
    the last finished run.

    When ``project`` is set, only tasks for that project are considered so
    parallel chats do not steal each other's active task pointer.
    """
    rows = list_tasks_for_sender(sender, limit=40)
    if project:
        rows = [r for r in rows if r.get("project") == project]
    for row in rows:
        if row.get("status") in {"queued", "running", "publishing"}:
            return row
    for row in rows:
        if row.get("status") == "review":
            return row
    return None


def inflight_tasks_for_sender(
    sender: str, *, project: str | None = None, limit: int = 40
) -> list[dict[str, Any]]:
    """Queued/running/publishing tasks for sender (newest first)."""
    rows = list_tasks_for_sender(sender, limit=limit)
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.get("status") not in {"queued", "running", "publishing"}:
            continue
        if project and row.get("project") != project:
            continue
        out.append(row)
    return out


def inflight_projects_for_sender(sender: str) -> list[str]:
    """Project ids with queued/running/publishing work (newest first, unique)."""
    seen: list[str] = []
    for row in inflight_tasks_for_sender(sender):
        name = str(row.get("project") or "").strip()
        if name and name not in seen:
            seen.append(name)
    return seen
