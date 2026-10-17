"""Reproduce the original LifeOS conversation against evidence-backed replies."""
from __future__ import annotations

from orchestrator import config, converse, db, history, progress, session, task_events, tasks
from orchestrator.execute import execute_task
from orchestrator.handlers import handle


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("WEBHOOK_REPLY_ENABLED", "false")
    monkeypatch.setenv("REPLY_LOG_ENABLED", "false")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("GROQ_API_KEY", "")
    config.settings.reload()
    db.initialize()
    converse.clear_pending("web:owner")
    session.clear("web:owner")
    history.clear_sender("web:owner")
    replies: list[str] = []
    monkeypatch.setattr(
        "orchestrator.handlers.send_text",
        lambda s, t, **k: replies.append(t),
    )
    monkeypatch.setattr("orchestrator.handlers.llm_chat.understand", lambda *a, **k: None)
    monkeypatch.setattr("orchestrator.handlers.llm_chat.phrase", lambda *a, **k: None)
    src = tmp_path / "lifeos"
    src.mkdir()
    (src / "login.css").write_text("body{background:#fff}", encoding="utf-8")
    monkeypatch.setattr(
        "orchestrator.handlers.projects.projects",
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
        "orchestrator.handlers.preflight.project_ready",
        lambda *a, **k: (True, "ok"),
    )
    return replies, src


def test_lifeos_conversation_followups_evidence_backed(tmp_path, monkeypatch):
    replies, src = _setup(tmp_path, monkeypatch)

    # 1) Select project
    handle("web:owner", "Let's work on lifeos.")
    assert session.get("web:owner")["active_project"] == "lifeos"
    assert "lifeos" in replies[-1].lower()

    # 2) Queue coding task
    handle(
        "web:owner",
        "Fix the light/dark feature on the login and registration pages. "
        "Switching to dark mode makes the screen black.",
    )
    assert any("investigation pending" in r.lower() or "task created" in r.lower() for r in replies)
    rows = tasks.list_tasks_for_sender("web:owner", limit=1)
    assert rows
    task_id = rows[0]["id"]

    # Mid-run: agent process alive without detailed stages
    tasks.update_task(
        task_id,
        status="running",
        execution_stage="agent_running",
        started_at=db.now(),
        agent_pid=9991,
        workspace=str(tmp_path / "work" / task_id),
    )
    task_events.record(
        task_id,
        "workspace_ready",
        "Workspace ready",
        stage="preparing_workspace",
    )
    task_events.record(
        task_id,
        "agent_started",
        "Cursor agent process started — detailed activity unavailable until it exits",
        stage="agent_running",
    )
    session.set_active_task("web:owner", task_id, project="lifeos")

    # 3) What's remaining?
    handle("web:owner", "What's remaining?")
    rem = replies[-1].lower()
    assert "detailed activity unavailable" in rem
    assert "investigating" not in rem
    assert "just a few minutes" not in rem

    # 4) Done?
    handle("web:owner", "Done?")
    assert "not yet" in replies[-1].lower()

    # 5) Why taking so long?
    handle("web:owner", "Why is it taking so long?")
    est = replies[-1].lower()
    assert "don't invent" in est or "cannot give" in est or "no mid-run" in est
    assert "just a few minutes" not in est
    assert "detailed activity unavailable" in est

    # Simulate agent completion with file evidence
    (tmp_path / "work" / task_id).mkdir(parents=True, exist_ok=True)
    tasks.update_task(
        task_id,
        status="review",
        execution_stage="ready_for_review",
        modified_files=["resources/css/auth.css"],
        summary="Agent: fixed dark mode contrast on auth pages",
        ended_at=db.now(),
        exit_code=0,
    )
    task_events.record(
        task_id,
        "files_changed",
        "Workspace evidence: 1 modified file(s)",
        stage="agent_running",
        detail={"files": ["resources/css/auth.css"]},
    )
    task_events.record(
        task_id,
        "ready_for_review",
        "Coding complete — ready for review",
        stage="ready_for_review",
    )

    handle("web:owner", "Done?")
    assert "ready for your review" in replies[-1].lower() or "finished" in replies[-1].lower()

    handle("web:owner", "What changes did you make?")
    assert "auth.css" in replies[-1].lower()


def test_execute_live_uses_agent_running_not_inferred_stages(tmp_path, monkeypatch):
    replies, src = _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "orchestrator.execute.send_text",
        lambda s, t, **k: replies.append(t),
    )

    def fake_agent(
        prompt,
        target,
        *,
        task_id=None,
        on_pid=None,
        on_heartbeat=None,
        on_stream_event=None,
        evidence=None,
    ):
        if on_pid:
            on_pid(7777)
        # Prove we never set investigating/implementing mid-run without stream evidence
        mid = tasks.get_task(task_id)
        assert mid["execution_stage"] == "agent_running"
        (target / "login.css").write_text("body{background:#111;color:#eee}", encoding="utf-8")
        return "Updated login.css contrast", 0

    monkeypatch.setattr("orchestrator.execute.agent.run_agent", fake_agent)
    monkeypatch.setattr(
        "orchestrator.execute.agent.list_modified_files",
        lambda target, branch, before_snapshot=None, **k: ["login.css"],
    )

    tasks.create_task("dddddddddddd", "web:owner", "lifeos", "fix dark mode black screen")
    execute_task("dddddddddddd")

    task = tasks.get_task("dddddddddddd")
    assert task["status"] == "review"
    assert task["execution_stage"] == "ready_for_review"
    assert task["exit_code"] == 0
    types = [e["event_type"] for e in task_events.list_events("dddddddddddd")]
    assert "agent_started" in types
    assert "agent_exited" in types
    assert "files_changed" in types
    stages = {e.get("stage") for e in task_events.list_events("dddddddddddd")}
    assert "investigating" not in stages
    assert "implementing" not in stages
    assert "agent_running" in stages
