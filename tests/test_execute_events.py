"""Execution pipeline records stages and events (dry-run)."""
from __future__ import annotations

from orchestrator import config, db, task_events, tasks
from orchestrator.execute import execute_task


def test_dry_run_records_workspace_and_review_stages(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("WEBHOOK_REPLY_ENABLED", "false")
    monkeypatch.setenv("REPLY_LOG_ENABLED", "false")
    config.settings.reload()
    db.initialize()

    src = tmp_path / "lifeos"
    src.mkdir()
    (src / "readme.txt").write_text("hi", encoding="utf-8")

    monkeypatch.setattr(
        "orchestrator.execute.projects.projects",
        lambda: {
            "lifeos": {
                "path": str(src),
                "type": "local",
                "allow_push": False,
                "allow_deploy": False,
                "deploy_command": "",
                "test_command": "",
            }
        },
    )
    notices = []
    monkeypatch.setattr(
        "orchestrator.execute.send_text",
        lambda s, t, **k: notices.append(t),
    )

    tasks.create_task("cccccccccccc", "web:owner", "lifeos", "fix dark mode")
    execute_task("cccccccccccc")

    task = tasks.get_task("cccccccccccc")
    assert task["status"] == "review"
    assert task["execution_stage"] == "ready_for_review"
    events = task_events.list_events("cccccccccccc")
    types = [e["event_type"] for e in events]
    assert "workspace_preparing" in types or "workspace_ready" in types
    assert "dry_run" in types or "ready_for_review" in types
    assert any("ready" in (e["message"] or "").lower() for e in events) or task["status"] == "review"
