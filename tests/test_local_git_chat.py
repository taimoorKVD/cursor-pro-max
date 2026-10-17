"""Chat can commit/stash local WIP and retry apply after publish_failed."""
from __future__ import annotations

from pathlib import Path

from orchestrator import config, converse
from orchestrator.converse import parse_intent
from orchestrator.handlers import handle
from orchestrator.process import run


def _git_init(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init"], cwd=path, timeout=30)
    run(["git", "config", "user.email", "test@example.com"], cwd=path, timeout=15)
    run(["git", "config", "user.name", "Test"], cwd=path, timeout=15)
    (path / "README.md").write_text("hi\n", encoding="utf-8")
    run(["git", "add", "README.md"], cwd=path, timeout=15)
    run(["git", "commit", "-m", "init"], cwd=path, timeout=30)


def _setup(tmp_path, monkeypatch, project_path: Path):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("WEBHOOK_REPLY_ENABLED", "false")
    monkeypatch.setenv("REPLY_LOG_ENABLED", "false")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("APPROVAL_TTL_SEC", "86400")
    config.settings.reload()
    from orchestrator import db

    db.initialize()
    converse.clear_pending("web:owner")
    replies = []
    monkeypatch.setattr(
        "orchestrator.handlers.send_text",
        lambda s, t, **k: replies.append(t),
    )
    monkeypatch.setattr("orchestrator.handlers.llm_chat.understand", lambda *a, **k: None)
    monkeypatch.setattr("orchestrator.handlers.llm_chat.phrase", lambda *a, **k: None)
    monkeypatch.setattr(
        "orchestrator.handlers.projects.projects",
        lambda: {
            "demo": {
                "path": str(project_path),
                "type": "git",
                "allow_push": True,
                "allow_deploy": False,
                "apply_local": True,
                "deploy_command": "",
                "test_command": "",
            }
        },
    )
    return replies


REGISTRY = {"demo": {"type": "git", "path": ".", "allow_push": True, "apply_local": True}}


def test_parse_local_git_intents():
    assert parse_intent("commit my local changes", REGISTRY).kind == "local_git"
    assert parse_intent("commit my local changes", REGISTRY).action == "COMMIT"
    assert parse_intent("stash local changes", REGISTRY).action == "STASH"
    assert parse_intent("commit local and apply", REGISTRY).action == "COMMIT_APPLY"
    assert parse_intent("commit local changes: chore wip", REGISTRY).instruction == "chore wip"


def _to_publish_failed(task_id: str, **fields) -> None:
    from orchestrator import db, tasks

    now = fields.get("ended_at") or db.now()
    tasks.update_task(task_id, status="running")
    tasks.update_task(
        task_id,
        status="review",
        content_digest=fields.get("content_digest") or ("d" * 40),
        ended_at=now,
        branch=fields.get("branch") or "wa/demo",
    )
    tasks.update_task(task_id, status="publishing")
    tasks.update_task(
        task_id,
        status="publish_failed",
        summary=fields.get("summary") or "uncommitted changes",
        ended_at=now,
    )


def test_commit_local_then_hint_apply(tmp_path, monkeypatch):
    src = tmp_path / "demo"
    _git_init(src)
    (src / "README.md").write_text("changed\n", encoding="utf-8")
    replies = _setup(tmp_path, monkeypatch, src)
    from orchestrator import session, tasks

    tid = "abcd1234ef00"
    tasks.create_task(tid, "web:owner", "demo", "demo work")
    _to_publish_failed(tid)
    session.set_active_task("web:owner", tid, project="demo")

    handle("web:owner", "commit my local changes")
    assert any("committed" in r.lower() for r in replies)
    status = run(["git", "status", "--porcelain"], cwd=src, timeout=15)
    assert (status.stdout or "").strip() == ""


def test_approve_retry_allowed_after_publish_failed(tmp_path, monkeypatch):
    src = tmp_path / "demo"
    _git_init(src)
    replies = _setup(tmp_path, monkeypatch, src)
    from orchestrator import session, tasks

    tid = "abcd1234ef01"
    tasks.create_task(tid, "web:owner", "demo", "demo work")
    _to_publish_failed(tid, content_digest="x" * 40)
    session.set_active_task("web:owner", tid, project="demo")
    enqueued = []
    monkeypatch.setattr(
        "orchestrator.handlers.queue.enqueue",
        lambda task_id, kind="execute": enqueued.append((task_id, kind)) or 1,
    )
    monkeypatch.setattr(
        "orchestrator.handlers.tasks.claim_publishing",
        lambda task_id: True,
    )
    from orchestrator import config as cfg
    from orchestrator import db as dbmod

    snap = tasks.get_task(tid)
    assert snap and snap["status"] == "publish_failed"
    assert dbmod.now() - int(snap.get("ended_at") or 0) <= int(cfg.APPROVAL_TTL_SEC)
    handle("web:owner", "apply locally")
    assert enqueued == [(tid, "publish:APPLY")], replies
    assert any("merging" in r.lower() or "on it" in r.lower() for r in replies)
