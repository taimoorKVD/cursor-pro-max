"""Workspace retention cleanup."""
from __future__ import annotations

import logging

from orchestrator import config, db, projects, workspace

log = logging.getLogger("orchestrator.retention")

# Only remove workspaces for terminal / failed tasks older than retention.
_CLEANABLE = frozenset({"published", "rejected", "failed", "publish_failed"})


def cleanup_workspaces(now: int | None = None) -> int:
    """Delete expired task workspaces. Returns number of directories removed."""
    days = config.WORKSPACE_RETENTION_DAYS
    if days <= 0:
        return 0
    cutoff = (now if now is not None else db.now()) - days * 86400
    removed = 0
    with db.DB_LOCK, db.connect() as c:
        rows = c.execute(
            """SELECT id, project, workspace, branch, status, updated_at FROM tasks
               WHERE workspace IS NOT NULL AND workspace != ''
                 AND status IN ({placeholders})
                 AND updated_at < ?""".format(
                placeholders=",".join("?" for _ in _CLEANABLE)
            ),
            (*_CLEANABLE, cutoff),
        ).fetchall()
    registry = projects.projects()
    for row in rows:
        task = dict(row)
        proj_cfg = registry.get(str(task.get("project") or ""))
        if workspace.remove_for_task(task, project_config=proj_cfg):
            removed += 1
            log.info("Removed expired workspace for task %s", task["id"])
    return removed


def cleanup_sender_workspaces(
    sender: str,
    *,
    project: str | None = None,
    reason: str = "chat cleared",
) -> dict:
    """Cancel active work and delete isolated workspaces for a chat/activity clear.

    Returns ``{tasks, removed, canceled}``.
    """
    from orchestrator import task_events, tasks
    from orchestrator.process import cancel_tracked

    reason_label = (reason or "chat cleared").strip() or "chat cleared"
    rows = tasks.list_tasks_for_sender(sender, limit=200)
    if project:
        rows = [r for r in rows if (r.get("project") or "") == project]
    registry = projects.projects()
    removed = 0
    canceled = 0
    for task in rows:
        tid = task["id"]
        status = task.get("status") or ""
        # Include review: clear must dismiss "ready for review" work too,
        # otherwise the progress panel keeps showing that task as current.
        if status in {"queued", "running", "publishing", "review"}:
            if status in {"queued", "running", "publishing"}:
                cancel_tracked(tid)
                # Free the worker lease even when cancel hits before Popen
                # (stuck AppContainer ACL prep would otherwise hold the slot).
                try:
                    from orchestrator import queue

                    queue.fail_running_for_task(tid, f"Cancelled: {reason_label}")
                except Exception:  # noqa: BLE001
                    pass
            tasks.update_task(
                tid,
                status="failed",
                execution_stage="canceled",
                summary=f"Cancelled: {reason_label} — isolated workspace removed",
                blocker=reason_label[:80].title(),
                ended_at=db.now(),
                agent_pid=None,
            )
            task_events.record(
                tid,
                "canceled",
                f"Cancelled because {reason_label}",
                stage="canceled",
            )
            canceled += 1
            task = tasks.get_task(tid) or task
        else:
            # Finished / other tasks must leave the activity history too.
            # Do not change terminal statuses (illegal transitions); only hide them.
            try:
                tasks.update_task(
                    tid,
                    execution_stage="canceled",
                    blocker=reason_label[:80].title(),
                    summary=f"Cleared: {reason_label}",
                    agent_pid=None,
                )
            except Exception:  # noqa: BLE001
                pass
            task = tasks.get_task(tid) or task
        # Activity drawer history is wiped with chat/activity clear.
        try:
            task_events.clear_for_task(tid)
        except Exception:  # noqa: BLE001
            pass
        proj_cfg = registry.get(str(task.get("project") or ""))
        # Always try conventional path even if workspace column empty (collision leftovers).
        if workspace.remove_for_task(task, project_config=proj_cfg):
            # Also wipe WORK_ROOT/<id> if still present and column was empty originally.
            removed += 1
        leftover = config.WORK_ROOT / tid
        if leftover.exists():
            if workspace.remove(
                leftover,
                source=(proj_cfg or {}).get("path"),
                branch=task.get("branch") or f"wa/{tid}",
            ):
                removed += 1
    return {"tasks": len(rows), "removed": removed, "canceled": canceled}
