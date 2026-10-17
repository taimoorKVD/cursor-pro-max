"""Background worker: claims durable jobs and runs execute/publish."""
from __future__ import annotations

import logging
import threading
import time

from orchestrator import config, queue, tasks
from orchestrator.execute import execute_task
from orchestrator.publish import publish
from orchestrator.projects import projects

log = logging.getLogger("orchestrator.worker")
_started = False
_lock = threading.Lock()


def process_job(job: dict) -> None:
    kind = job["kind"]
    task_id = job["task_id"]
    fence = job.get("fence")
    try:
        task = tasks.get_task(task_id)
        if task and task["status"] == "failed" and (task.get("summary") or "").startswith("Cancelled"):
            queue.complete(job["id"], fence=fence)
            return
        if not queue.fence_matches(int(job["id"]), fence):
            return
        if kind == "execute":
            execute_task(task_id, job_id=int(job["id"]), fence=fence)
        elif kind.startswith("publish:"):
            action = kind.split(":", 1)[1]
            task = tasks.get_task(task_id)
            if not task:
                raise ValueError("Task missing for publish job")
            project_config = projects().get(task["project"], {})
            publish(task, project_config, action, job_id=int(job["id"]), fence=fence)
        else:
            raise ValueError(f"Unknown job kind: {kind}")
        if fence and not queue.fence_matches(int(job["id"]), fence):
            return
        task = tasks.get_task(task_id)
        # execute_task/publish catch many errors internally and mark the task failed.
        if task and task["status"] in {"failed", "publish_failed"}:
            queue.fail(
                job["id"],
                (task.get("summary") or task["status"])[:1000],
                retry=False,
                fence=fence,
            )
            return
        queue.complete(job["id"], fence=fence)
    except Exception as exc:
        log.exception("Job %s failed", job["id"])
        if fence and not queue.fence_matches(int(job["id"]), fence):
            return
        queue.fail(job["id"], str(exc), retry=False, fence=fence)
        # Ensure task is not stuck in running if execute crashed before update.
        task = tasks.get_task(task_id)
        if task and task["status"] == "running" and kind == "execute":
            try:
                tasks.update_task(task_id, status="failed", summary=str(exc)[:1000])
            except Exception:
                log.exception("Could not mark task failed")


def worker_loop(stop_event: threading.Event | None = None) -> None:
    while stop_event is None or not stop_event.is_set():
        job = queue.claim_next()
        if job:
            process_job(job)
            continue
        time.sleep(config.WORKER_POLL_SEC)


def start_worker() -> None:
    global _started
    import os

    if os.getenv("ORCHESTRATOR_WORKER", "true").lower() in {"0", "false", "no"}:
        return
    with _lock:
        if _started:
            return
        _started = True
        count = max(1, int(getattr(config, "WORKER_COUNT", 1) or 1))
        for i in range(count):
            threading.Thread(
                target=worker_loop,
                name=f"orchestrator-worker-{i + 1}",
                daemon=True,
            ).start()
        log.info("Started %s durable queue worker(s)", count)
