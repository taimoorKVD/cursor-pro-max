"""Approval digests fail closed and a publish is single-flight."""
from __future__ import annotations

from types import SimpleNamespace

from orchestrator import config, db, queue, tasks
from orchestrator.handlers import handle
from orchestrator.publish import publish


def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("WEBHOOK_REPLY_ENABLED", "false")
    config.settings.reload()
    db.initialize()


def _fake_git(calls):
    def fake_run(argv, cwd=None, timeout=None, env=None):
        calls.append(list(argv))
        if env and "META_ACCESS_TOKEN" in env:
            raise AssertionError("publish env leaked META_ACCESS_TOKEN")
        if argv[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(returncode=0, stdout="abc123\n", stderr="")
        if argv[:2] == ["git", "status"]:
            return SimpleNamespace(returncode=0, stdout=" M a.txt\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return fake_run


def test_empty_digest_does_not_push(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    monkeypatch.setattr("orchestrator.publish.run", _fake_git(calls))
    monkeypatch.setattr("orchestrator.publish.send_text", lambda *a, **k: None)
    monkeypatch.setattr("orchestrator.publish.audit.record", lambda *a, **k: None)
    monkeypatch.setattr("orchestrator.publish.tasks.update_task", lambda *a, **k: None)
    publish(
        {
            "id": "nodigest0001",
            "sender": "web:owner",
            "project": "demo",
            "branch": "wa/nodigest0001",
            "workspace": str(tmp_path),
            "instruction": "x",
            "content_digest": "",
            "approved_sha": "",
        },
        {"type": "git", "path": str(tmp_path), "allow_push": True, "apply_local": False},
        "PUSH",
    )
    assert not any(argv[:2] == ["git", "push"] for argv in calls)


def test_digest_mismatch_does_not_push(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    monkeypatch.setattr("orchestrator.publish.run", _fake_git(calls))
    monkeypatch.setattr("orchestrator.publish.send_text", lambda *a, **k: None)
    monkeypatch.setattr("orchestrator.publish.audit.record", lambda *a, **k: None)
    monkeypatch.setattr("orchestrator.publish.tasks.update_task", lambda *a, **k: None)
    monkeypatch.setattr(
        "orchestrator.publish.workspace.content_digest",
        lambda *a, **k: "different",
    )
    publish(
        {
            "id": "mismatch0001",
            "sender": "web:owner",
            "project": "demo",
            "branch": "wa/mismatch0001",
            "workspace": str(tmp_path),
            "instruction": "x",
            "content_digest": "approved-digest",
            "approved_sha": "",
        },
        {"type": "git", "path": str(tmp_path), "allow_push": True, "apply_local": False},
        "PUSH",
    )
    assert not any(argv[:2] == ["git", "push"] for argv in calls)
    assert not any(argv[:2] == ["gh", "pr"] for argv in calls)


def test_identical_remote_sha_skips_push(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(argv, cwd=None, timeout=None, env=None):
        calls.append(list(argv))
        if argv[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(returncode=0, stdout="abc123def456\n", stderr="")
        if argv[:2] == ["git", "status"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[:2] == ["git", "ls-remote"]:
            return SimpleNamespace(
                returncode=0,
                stdout="abc123def456\trefs/heads/wa/same00000001\n",
                stderr="",
            )
        if argv[:2] == ["git", "remote"]:
            return SimpleNamespace(returncode=0, stdout="https://github.com/acme/app.git\n", stderr="")
        if argv[:2] == ["git", "push"]:
            raise AssertionError("identical remote SHA must not push")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    updates: list[dict] = []
    monkeypatch.setattr("orchestrator.publish.run", fake_run)
    monkeypatch.setattr("orchestrator.publish.send_text", lambda *a, **k: None)
    monkeypatch.setattr("orchestrator.publish.audit.record", lambda *a, **k: None)
    monkeypatch.setattr(
        "orchestrator.publish.tasks.update_task",
        lambda tid, **kw: updates.append(kw),
    )
    publish(
        {
            "id": "same00000001",
            "sender": "web:owner",
            "project": "demo",
            "branch": "wa/same00000001",
            "workspace": str(tmp_path),
            "instruction": "x",
            "content_digest": "kept",
            "approved_sha": "abc123def456",
        },
        {"type": "git", "path": str(tmp_path), "allow_push": True, "apply_local": False},
        "PUSH",
    )
    assert any(argv[:2] == ["git", "ls-remote"] for argv in calls)
    assert not any("--force" in argv for argv in calls)
    assert any(u.get("status") == "published" for u in updates)


def test_non_fast_forward_is_refused(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(argv, cwd=None, timeout=None, env=None):
        calls.append(list(argv))
        if argv[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(returncode=0, stdout="localsha111\n", stderr="")
        if argv[:2] == ["git", "status"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[:2] == ["git", "ls-remote"]:
            return SimpleNamespace(
                returncode=0,
                stdout="othersha999\trefs/heads/wa/diverge0001\n",
                stderr="",
            )
        if argv[:2] == ["git", "push"]:
            assert "--force" not in argv
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="! [rejected] non-fast-forward",
            )
        if argv[:2] == ["git", "remote"]:
            return SimpleNamespace(returncode=0, stdout="https://github.com/acme/app.git\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    updates: list[dict] = []
    monkeypatch.setattr("orchestrator.publish.run", fake_run)
    monkeypatch.setattr("orchestrator.publish.send_text", lambda *a, **k: None)
    monkeypatch.setattr("orchestrator.publish.audit.record", lambda *a, **k: None)
    monkeypatch.setattr(
        "orchestrator.publish.tasks.update_task",
        lambda tid, **kw: updates.append(kw),
    )
    publish(
        {
            "id": "diverge0001",
            "sender": "web:owner",
            "project": "demo",
            "branch": "wa/diverge0001",
            "workspace": str(tmp_path),
            "instruction": "x",
            "content_digest": "kept",
            "approved_sha": "localsha111",
        },
        {"type": "git", "path": str(tmp_path), "allow_push": True, "apply_local": False},
        "PUSH",
    )
    assert updates[-1]["status"] == "publish_failed"
    assert "non-fast-forward" in updates[-1]["summary"].lower()
    assert not any("--force" in argv for argv in calls)


def test_deploy_stays_disabled(monkeypatch, tmp_path):
    calls: list[list[str]] = []
    monkeypatch.setattr("orchestrator.publish.run", _fake_git(calls))
    monkeypatch.setattr("orchestrator.publish.send_text", lambda *a, **k: None)
    monkeypatch.setattr("orchestrator.publish.audit.record", lambda *a, **k: None)
    monkeypatch.setattr(config.settings, "DEPLOY_ENABLED", False)
    updates: list[dict] = []
    monkeypatch.setattr(
        "orchestrator.publish.tasks.update_task",
        lambda tid, **kw: updates.append(kw),
    )
    publish(
        {
            "id": "deploy0000001",
            "sender": "web:owner",
            "project": "demo",
            "branch": "",
            "workspace": str(tmp_path),
            "instruction": "ship",
            "content_digest": "d",
        },
        {"type": "git", "deploy_command": "echo no", "allow_deploy": True},
        "DEPLOY",
    )
    assert updates[-1]["status"] == "publish_failed"
    assert "disabled" in updates[-1]["summary"].lower()
    assert calls == []


def test_two_approves_enqueue_one_job(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    tasks.create_task("approve000001", "web:owner", "demo", "ship it")
    tasks.update_task("approve000001", status="running")
    tasks.update_task(
        "approve000001",
        status="review",
        content_digest="digest-ok",
        ended_at=db.now(),
    )
    assert tasks.claim_publishing("approve000001") is True
    assert tasks.claim_publishing("approve000001") is False
    queue.enqueue("approve000001", kind="publish:PUSH")
    with db.DB_LOCK, db.connect() as c:
        count = c.execute(
            "SELECT COUNT(*) FROM jobs WHERE task_id=?",
            ("approve000001",),
        ).fetchone()[0]
    assert count == 1
    assert tasks.get_task("approve000001")["status"] == "publishing"


def test_expired_approval_is_rejected(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    monkeypatch.setattr(config.settings, "APPROVAL_TTL_SEC", 60)
    tasks.create_task("expired00001", "web:owner", "demo", "old review")
    tasks.update_task("expired00001", status="running")
    tasks.update_task(
        "expired00001",
        status="review",
        content_digest="digest-ok",
        ended_at=db.now() - 3600,
        workspace=str(tmp_path),
        branch="wa/expired00001",
    )
    from orchestrator import session

    session.set_active_task("web:owner", "expired00001", project="demo")
    replies: list[str] = []
    monkeypatch.setattr("orchestrator.handlers.send_text", lambda s, t, **k: replies.append(t))
    monkeypatch.setattr("orchestrator.handlers.llm_chat.understand", lambda *a, **k: None)
    handle("web:owner", "approve and push")
    assert tasks.get_task("expired00001")["status"] == "review"
    assert any("expired" in text.lower() for text in replies)
    assert queue.claim_next() is None


def test_published_cannot_retry_pr(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    tasks.create_task("published0001", "web:owner", "demo", "done")
    tasks.update_task("published0001", status="running")
    tasks.update_task("published0001", status="review", content_digest="digest-ok")
    tasks.update_task("published0001", status="publishing")
    tasks.update_task("published0001", status="published")
    from orchestrator import session

    session.set_active_task("web:owner", "published0001", project="demo")
    replies: list[str] = []
    monkeypatch.setattr("orchestrator.handlers.send_text", lambda s, t, **k: replies.append(t))
    monkeypatch.setattr("orchestrator.handlers.llm_chat.understand", lambda *a, **k: None)
    handle("web:owner", "approve and create a pull request")
    assert tasks.get_task("published0001")["status"] == "published"
    assert queue.claim_next() is None
