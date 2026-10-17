"""Parallel project chats keep working independently after switching."""
from __future__ import annotations

import threading
import time

from orchestrator import config, db, queue, session, tasks


def _init_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "multi.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    config.settings.reload()
    db.initialize()
    session.clear("web:owner")


def test_active_task_scoped_by_project(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch)
    tasks.create_task("aaaaaaaaaaaa", "web:owner", "lifeos", "dark mode")
    tasks.create_task("bbbbbbbbbbbb", "web:owner", "other-app", "form validation")
    tasks.update_task("aaaaaaaaaaaa", status="running", execution_stage="agent_running")
    tasks.update_task("bbbbbbbbbbbb", status="queued", execution_stage="queued")

    life = tasks.active_task_for_sender("web:owner", project="lifeos")
    other = tasks.active_task_for_sender("web:owner", project="other-app")
    assert life["id"] == "aaaaaaaaaaaa"
    assert other["id"] == "bbbbbbbbbbbb"
    assert set(tasks.inflight_projects_for_sender("web:owner")) == {"lifeos", "other-app"}


def test_switch_project_restores_inflight_task(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch)
    tasks.create_task("aaaaaaaaaaaa", "web:owner", "lifeos", "dark mode")
    tasks.create_task("bbbbbbbbbbbb", "web:owner", "other-app", "form validation")
    tasks.update_task("aaaaaaaaaaaa", status="running", execution_stage="agent_running")
    tasks.update_task("bbbbbbbbbbbb", status="running", execution_stage="agent_running")
    session.set_active_task("web:owner", "aaaaaaaaaaaa", project="lifeos")

    switched = session.switch_project("web:owner", "other-app")
    assert switched["changed"] is True
    ctx = session.get("web:owner")
    assert ctx["active_project"] == "other-app"
    assert ctx["active_task_id"] == "bbbbbbbbbbbb"

    back = session.switch_project("web:owner", "lifeos")
    assert back["changed"] is True
    ctx = session.get("web:owner")
    assert ctx["active_project"] == "lifeos"
    assert ctx["active_task_id"] == "aaaaaaaaaaaa"
    # Prior project task is still running — switch only rebinds the pointer.
    assert tasks.get_task("bbbbbbbbbbbb")["status"] == "running"


def test_claim_next_allows_parallel_jobs(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch)
    tasks.create_task("aaaaaaaaaaaa", "web:owner", "lifeos", "a")
    tasks.create_task("bbbbbbbbbbbb", "web:owner", "other-app", "b")
    queue.enqueue("aaaaaaaaaaaa", kind="execute")
    queue.enqueue("bbbbbbbbbbbb", kind="execute")

    first = queue.claim_next()
    second = queue.claim_next()
    assert first is not None
    assert second is not None
    assert first["id"] != second["id"]
    assert {first["task_id"], second["task_id"]} == {"aaaaaaaaaaaa", "bbbbbbbbbbbb"}
    assert queue.claim_next() is None


def test_claim_next_allows_same_project_parallel_jobs(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch)
    tasks.create_task("aaaaaaaaaaaa", "web:owner", "lifeos", "dark mode")
    tasks.create_task("bbbbbbbbbbbb", "web:owner", "lifeos", "form validation")
    queue.enqueue("aaaaaaaaaaaa", kind="execute")
    queue.enqueue("bbbbbbbbbbbb", kind="execute")

    first = queue.claim_next()
    second = queue.claim_next()
    assert first is not None
    assert second is not None
    assert first["id"] != second["id"]
    assert {first["task_id"], second["task_id"]} == {"aaaaaaaaaaaa", "bbbbbbbbbbbb"}
    inflight = tasks.inflight_tasks_for_sender("web:owner", project="lifeos")
    assert {t["id"] for t in inflight} == {"aaaaaaaaaaaa", "bbbbbbbbbbbb"}


def test_multiple_worker_threads_claim_distinct_jobs(tmp_path, monkeypatch):
    _init_db(tmp_path, monkeypatch)
    monkeypatch.setenv("WORKER_COUNT", "3")
    config.settings.reload()
    from orchestrator import worker

    claimed: list[str] = []
    lock = threading.Lock()

    def fake_process(job: dict) -> None:
        with lock:
            claimed.append(job["task_id"])
        time.sleep(0.05)
        queue.complete(job["id"])

    monkeypatch.setattr(worker, "process_job", fake_process)
    stop = threading.Event()
    threads = [
        threading.Thread(target=worker.worker_loop, args=(stop,), daemon=True)
        for _ in range(3)
    ]
    for i in range(3):
        tid = f"{'c' * 11}{i}"
        tasks.create_task(tid, "web:owner", f"proj-{i}", f"work {i}")
        queue.enqueue(tid, kind="execute")
    for t in threads:
        t.start()
    deadline = time.time() + 3
    while time.time() < deadline and len(claimed) < 3:
        time.sleep(0.05)
    stop.set()
    for t in threads:
        t.join(timeout=1)
    assert set(claimed) == {f"{'c' * 11}{i}" for i in range(3)}
