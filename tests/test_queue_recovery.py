"""Lease renewal, restart recovery, and cancellation fencing."""
from __future__ import annotations

import threading
import time

from orchestrator import config, db, queue, tasks


def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("JOB_LEASE_SEC", "30")
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    config.settings.reload()
    db.initialize()


def test_renew_lease_blocks_a_second_claim(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    tasks.create_task("lease00000001", "web:owner", "demo", "hold the lease")
    queue.enqueue("lease00000001")
    job = queue.claim_next()
    assert job is not None
    with db.DB_LOCK, db.connect() as c:
        c.execute(
            "UPDATE jobs SET leased_until=? WHERE id=?",
            (db.now() + 1, job["id"]),
        )
    assert queue.renew_lease(job["id"], job["fence"]) is True
    with db.DB_LOCK, db.connect() as c:
        until = c.execute("SELECT leased_until FROM jobs WHERE id=?", (job["id"],)).fetchone()[0]
    assert int(until) >= db.now() + config.JOB_LEASE_SEC - 2
    assert queue.claim_next() is None


def test_recover_preserves_live_lease_and_workspace(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    tasks.create_task("live000000001", "web:owner", "demo", "still running")
    tasks.update_task("live000000001", status="running", workspace=str(tmp_path / "ws"))
    queue.enqueue("live000000001")
    job = queue.claim_next()
    assert job is not None
    before = queue.recover_interrupted()
    assert before["preserved"] == 0
    again = queue.claim_next()
    assert again is None
    task = tasks.get_task("live000000001")
    assert task["status"] == "running"
    assert task["workspace"] == str(tmp_path / "ws")


def test_recover_expired_workspace_does_not_reexecute(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    tasks.create_task("dead000000001", "web:owner", "demo", "crashed")
    tasks.update_task("dead000000001", status="running", workspace=str(tmp_path / "ws"))
    (tmp_path / "ws").mkdir()
    queue.enqueue("dead000000001")
    job = queue.claim_next()
    with db.DB_LOCK, db.connect() as c:
        c.execute("UPDATE jobs SET leased_until=? WHERE id=?", (db.now() - 5, job["id"]))
    stats = queue.recover_interrupted()
    assert stats["preserved"] == 1
    task = tasks.get_task("dead000000001")
    assert task["status"] == "failed"
    assert task["workspace"] == str(tmp_path / "ws")
    assert (tmp_path / "ws").is_dir()
    assert queue.claim_next() is None


def test_recover_publish_crash_does_not_repush(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    tasks.create_task("pub0000000001", "web:owner", "demo", "publish")
    tasks.update_task("pub0000000001", status="running")
    tasks.update_task("pub0000000001", status="review", content_digest="abc")
    tasks.update_task("pub0000000001", status="publishing")
    queue.enqueue("pub0000000001", kind="publish:PR")
    job = queue.claim_next()
    with db.DB_LOCK, db.connect() as c:
        c.execute("UPDATE jobs SET leased_until=? WHERE id=?", (db.now() - 5, job["id"]))
    stats = queue.recover_interrupted()
    assert stats["publish_failed"] == 1
    assert tasks.get_task("pub0000000001")["status"] == "publish_failed"
    assert queue.claim_next() is None


def test_queued_pending_job_is_not_duplicated(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    tasks.create_task("queue00000001", "web:owner", "demo", "waiting")
    queue.enqueue("queue00000001")
    queue.recover_interrupted()
    with db.DB_LOCK, db.connect() as c:
        count = c.execute(
            "SELECT COUNT(*) FROM jobs WHERE task_id=? AND kind='execute'",
            ("queue00000001",),
        ).fetchone()[0]
    assert count == 1


def test_stolen_fence_cannot_complete_or_review(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    tasks.create_task("fence00000001", "web:owner", "demo", "fence")
    tasks.update_task("fence00000001", status="running")
    queue.enqueue("fence00000001")
    first = queue.claim_next()
    with db.DB_LOCK, db.connect() as c:
        c.execute("UPDATE jobs SET leased_until=? WHERE id=?", (db.now() - 5, first["id"]))
    second = queue.claim_next()
    assert second["id"] == first["id"]
    assert second["fence"] != first["fence"]
    assert queue.fence_matches(first["id"], first["fence"]) is False
    assert queue.complete(first["id"], fence=first["fence"]) is False
    # A late worker stops before compare-and-swap when its fence is gone.
    late_review = False
    if queue.fence_matches(first["id"], first["fence"]):
        late_review = tasks.cas_update(
            "fence00000001",
            "running",
            status="review",
            content_digest="should-not-land",
        )
    assert late_review is False
    assert tasks.get_task("fence00000001")["status"] == "running"
    assert not tasks.get_task("fence00000001").get("content_digest")


def test_cancel_kills_tracked_process(tmp_path, monkeypatch):
    from orchestrator.process import cancel_tracked, run_tracked, tracked_info

    _db(tmp_path, monkeypatch)
    holder: dict = {}

    def _run():
        holder["result"] = run_tracked(
            "cancel0000001",
            ["ping", "-n", "30", "127.0.0.1"],
            cwd=str(tmp_path),
            timeout=40,
        )

    thread = threading.Thread(target=_run)
    thread.start()
    for _ in range(100):
        if tracked_info("cancel0000001"):
            break
        time.sleep(0.05)
    assert tracked_info("cancel0000001")
    assert cancel_tracked("cancel0000001") is True
    thread.join(15)
    assert "result" in holder
    assert holder["result"].returncode != 0
    tasks.create_task("cancel0000001", "web:owner", "demo", "cancel")
    tasks.update_task("cancel0000001", status="failed", summary="Cancelled by operator")
    assert (
        tasks.cas_update("cancel0000001", "running", status="review", content_digest="late")
        is False
    )
    assert tasks.get_task("cancel0000001")["status"] == "failed"
