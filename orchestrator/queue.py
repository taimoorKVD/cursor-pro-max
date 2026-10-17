"""Durable SQLite-backed job queue with lease recovery."""
from __future__ import annotations

import secrets
from typing import Any

from orchestrator import config, db


def enqueue(task_id: str, kind: str = "execute") -> int:
    now = db.now()
    with db.DB_LOCK, db.connect() as c:
        cur = c.execute(
            """INSERT INTO jobs (task_id, kind, status, attempts, available_at, created_at, updated_at)
               VALUES (?, ?, 'pending', 0, ?, ?, ?)""",
            (task_id, kind, now, now, now),
        )
        return int(cur.lastrowid)


def reclaim_expired_leases() -> int:
    """Return expired jobs to pending, except work that must not run twice.

    An execute job that already has a workspace is failed and the workspace is
    kept. An expired publish job becomes publish_failed instead of pushing again.
    Jobs with no workspace (the lease-reclaim test) are still re-claimed.
    """
    from orchestrator import tasks

    now = db.now()
    with db.DB_LOCK, db.connect() as c:
        rows = c.execute(
            """SELECT id, task_id, kind FROM jobs
               WHERE status='running' AND leased_until IS NOT NULL AND leased_until < ?""",
            (now,),
        ).fetchall()
    changed = 0
    for row in rows:
        task = tasks.get_task(row["task_id"])
        kind = row["kind"] or ""
        if kind == "execute" and task and task.get("workspace"):
            tasks.recover_task(
                row["task_id"],
                "failed",
                "Lease expired after a workspace was created; workspace preserved.",
            )
            fail(int(row["id"]), "lease expired; workspace preserved", retry=False)
            changed += 1
            continue
        if kind.startswith("publish:"):
            if task and task["status"] == "publishing":
                tasks.recover_task(
                    row["task_id"],
                    "publish_failed",
                    "Publish lease expired. Approve again after checking the remote; "
                    "a matching SHA is not force-pushed.",
                )
            fail(int(row["id"]), "lease expired; publish not resumed", retry=False)
            changed += 1
            continue
        with db.DB_LOCK, db.connect() as c:
            cur = c.execute(
                """UPDATE jobs
                   SET status='pending', leased_until=NULL, updated_at=?,
                       last_error=COALESCE(last_error, '') || ' lease expired;'
                   WHERE id=? AND status='running'""",
                (now, row["id"]),
            )
            changed += cur.rowcount
    return changed


def claim_next() -> dict[str, Any] | None:
    reclaim_expired_leases()
    now = db.now()
    lease_until = now + config.JOB_LEASE_SEC
    with db.DB_LOCK, db.connect() as c:
        row = c.execute(
            """SELECT * FROM jobs
               WHERE status='pending' AND available_at <= ?
               ORDER BY id ASC LIMIT 1""",
            (now,),
        ).fetchone()
        if not row:
            return None
        job_id = row["id"]
        fence = secrets.token_hex(8)
        cur = c.execute(
            """UPDATE jobs
               SET status='running', attempts=attempts+1, leased_until=?, updated_at=?, fence=?
               WHERE id=? AND status='pending'""",
            (lease_until, now, fence, job_id),
        )
        if cur.rowcount != 1:
            return None
        refreshed = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(refreshed) if refreshed else None


def renew_lease(job_id: int, fence: str | None = None) -> bool:
    """Extend the lease while this worker still owns the running job."""
    now = db.now()
    until = now + config.JOB_LEASE_SEC
    with db.DB_LOCK, db.connect() as c:
        if fence:
            cur = c.execute(
                """UPDATE jobs SET leased_until=?, updated_at=?
                   WHERE id=? AND status='running' AND fence=?""",
                (until, now, job_id, fence),
            )
        else:
            cur = c.execute(
                """UPDATE jobs SET leased_until=?, updated_at=?
                   WHERE id=? AND status='running'""",
                (until, now, job_id),
            )
        return cur.rowcount == 1


def fence_matches(job_id: int, fence: str | None) -> bool:
    if not fence:
        return True
    with db.DB_LOCK, db.connect() as c:
        row = c.execute("SELECT status, fence FROM jobs WHERE id=?", (job_id,)).fetchone()
    return bool(row and row["status"] == "running" and row["fence"] == fence)


def complete(job_id: int, *, fence: str | None = None) -> bool:
    now = db.now()
    with db.DB_LOCK, db.connect() as c:
        if fence:
            cur = c.execute(
                """UPDATE jobs SET status='done', leased_until=NULL, updated_at=?
                   WHERE id=? AND status='running' AND fence=?""",
                (now, job_id, fence),
            )
        else:
            cur = c.execute(
                """UPDATE jobs SET status='done', leased_until=NULL, updated_at=? WHERE id=?""",
                (now, job_id),
            )
        return cur.rowcount == 1


def fail_running_for_task(task_id: str, error: str) -> int:
    """Mark every running job for ``task_id`` failed (clear/cancel must free leases)."""
    now = db.now()
    with db.DB_LOCK, db.connect() as c:
        cur = c.execute(
            """UPDATE jobs
               SET status='failed', leased_until=NULL, last_error=?, updated_at=?, fence=NULL
               WHERE task_id=? AND status='running'""",
            ((error or "cancelled")[:1000], now, task_id),
        )
        return int(cur.rowcount or 0)


def fail(
    job_id: int,
    error: str,
    *,
    retry: bool = False,
    delay_sec: int = 30,
    fence: str | None = None,
) -> None:
    now = db.now()
    fence_sql = " AND fence=?" if fence else ""
    fence_args: tuple = (fence,) if fence else ()
    with db.DB_LOCK, db.connect() as c:
        if retry:
            c.execute(
                f"""UPDATE jobs
                   SET status='pending', available_at=?, leased_until=NULL,
                       last_error=?, updated_at=?
                   WHERE id=?{fence_sql}""",
                (now + delay_sec, error[:1000], now, job_id, *fence_args),
            )
        else:
            c.execute(
                f"""UPDATE jobs
                   SET status='failed', leased_until=NULL, last_error=?, updated_at=?
                   WHERE id=? AND status='running'{fence_sql}""",
                (error[:1000], now, job_id, *fence_args),
            )


def recover_interrupted() -> dict[str, int]:
    """On process start, do not re-run a workspace that already exists.

    A dead worker's ``running`` execute job becomes ``failed`` and the workspace
    is left on disk. Execute jobs that died before a workspace existed are queued
    again. In-flight publish jobs become ``publish_failed`` instead of pushing twice.
    """
    from orchestrator import tasks

    preserved = 0
    requeued = 0
    publish_failed = 0
    with db.DB_LOCK, db.connect() as c:
        running_jobs = c.execute(
            "SELECT id, task_id, kind, leased_until FROM jobs WHERE status='running'"
        ).fetchall()
    for job in running_jobs:
        if job["leased_until"] and int(job["leased_until"]) > db.now():
            continue
        task = tasks.get_task(job["task_id"])
        kind = job["kind"] or ""
        if kind == "execute":
            if task and task.get("workspace"):
                tasks.recover_task(
                    job["task_id"],
                    "failed",
                    "Interrupted by process restart after workspace creation; "
                    "workspace preserved. Ask to continue if you want a new run.",
                )
                fail(int(job["id"]), "restart: workspace preserved", retry=False)
                preserved += 1
            else:
                if task and task["status"] == "running":
                    tasks.recover_task(
                        job["task_id"],
                        "queued",
                        "Recovered after restart before workspace creation",
                    )
                with db.DB_LOCK, db.connect() as c:
                    c.execute(
                        """UPDATE jobs SET status='pending', leased_until=NULL, fence=NULL,
                           updated_at=? WHERE id=?""",
                        (db.now(), job["id"]),
                    )
                requeued += 1
        elif kind.startswith("publish:"):
            if task and task["status"] == "publishing":
                tasks.recover_task(
                    job["task_id"],
                    "publish_failed",
                    "Publish interrupted by process restart. Approve again after you "
                    "check the remote branch; a matching remote SHA will not be force-pushed.",
                )
            fail(int(job["id"]), "restart: publish not resumed automatically", retry=False)
            publish_failed += 1
        else:
            fail(int(job["id"]), "restart: unknown job", retry=False)

    with db.DB_LOCK, db.connect() as c:
        queued = c.execute("SELECT id FROM tasks WHERE status='queued'").fetchall()
    for row in queued:
        task_id = row["id"]
        with db.DB_LOCK, db.connect() as c:
            open_job = c.execute(
                """SELECT id FROM jobs
                   WHERE task_id=? AND kind='execute' AND status IN ('pending', 'running')
                   LIMIT 1""",
                (task_id,),
            ).fetchone()
        if open_job:
            continue
        enqueue(task_id, kind="execute")
        requeued += 1
    return {"preserved": preserved, "requeued": requeued, "publish_failed": publish_failed}


def pending_count() -> int:
    with db.DB_LOCK, db.connect() as c:
        return int(c.execute("SELECT COUNT(*) FROM jobs WHERE status='pending'").fetchone()[0])
