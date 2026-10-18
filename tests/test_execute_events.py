"""Execution pipeline records stages and events (dry-run + salvage)."""
from __future__ import annotations

from orchestrator import config, db, task_events, tasks
from orchestrator.execute import execute_task


def _base_env(tmp_path, monkeypatch, *, dry_run: str = "true") -> None:
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("DRY_RUN", dry_run)
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("WEBHOOK_REPLY_ENABLED", "false")
    monkeypatch.setenv("REPLY_LOG_ENABLED", "false")
    config.settings.reload()
    db.initialize()


def test_dry_run_records_workspace_and_review_stages(tmp_path, monkeypatch):
    _base_env(tmp_path, monkeypatch, dry_run="true")

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
    notices: list[str] = []
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

    # Intermediate milestones stay in Activity events — not chat spam.
    assert len(notices) == 1
    assert "Workspace ready" not in notices[0]
    assert "Starting Cursor" not in notices[0]
    assert "Stream evidence" not in notices[0]
    assert "dry-run" in notices[0].lower() or "practice" in notices[0].lower()


def test_agent_disconnect_with_changes_salvages_to_review(tmp_path, monkeypatch):
    """Agent crash/disconnect after edits → review (approvable), not failed."""
    _base_env(tmp_path, monkeypatch, dry_run="false")

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

    def _fake_run_agent(prompt, workspace, **kwargs):
        (workspace / "readme.txt").write_text("edited after disconnect", encoding="utf-8")
        (workspace / "new_feature.py").write_text("print('ok')\n", encoding="utf-8")
        raise RuntimeError("Cursor agent disconnected mid-run")

    monkeypatch.setattr("orchestrator.execute.agent.run_agent", _fake_run_agent)
    monkeypatch.setattr(
        "orchestrator.execute.agent.ensure_auth",
        lambda **k: (True, "ok"),
    )

    notices: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        "orchestrator.execute.send_text",
        lambda s, t, **k: notices.append((t, k.get("level"))),
    )

    tasks.create_task("salvage000001", "web:owner", "lifeos", "add feature")
    execute_task("salvage000001")

    task = tasks.get_task("salvage000001")
    assert task is not None
    assert task["status"] == "review"
    assert task["execution_stage"] == "ready_for_review"
    assert "abnormally" in (task.get("blocker") or "").lower() or "preserved" in (
        task.get("blocker") or ""
    ).lower()

    events = task_events.list_events("salvage000001")
    types = [e["event_type"] for e in events]
    assert "agent_salvaged" in types
    assert "ready_for_review" in types

    assert len(notices) == 1
    body, level = notices[0]
    assert level == "warning"
    assert "kept" in body.lower() or "preserved" in body.lower()
    assert "Approve" in body or "approve" in body.lower()
    # No intermediate milestone chat spam
    assert "Workspace ready" not in body
    assert "Stream evidence" not in body


def test_agent_failure_without_changes_still_fails(tmp_path, monkeypatch):
    _base_env(tmp_path, monkeypatch, dry_run="false")

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
    monkeypatch.setattr(
        "orchestrator.execute.agent.run_agent",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("auth failed completely")),
    )

    notices: list[str] = []
    monkeypatch.setattr(
        "orchestrator.execute.send_text",
        lambda s, t, **k: notices.append(t),
    )

    tasks.create_task("failsoft00001", "web:owner", "lifeos", "noop")
    execute_task("failsoft00001")

    task = tasks.get_task("failsoft00001")
    assert task["status"] == "failed"
    assert notices
    low = notices[-1].lower()
    assert "didn't finish" in low or "couldn't" in low or "sorry" in low
