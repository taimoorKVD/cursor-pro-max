"""Conversational follow-ups and evidence-backed progress replies."""
from __future__ import annotations

from orchestrator import converse, db, progress, session, task_events, tasks
from orchestrator.converse import clear_pending, parse_intent
from orchestrator.handlers import handle

REGISTRY = {
    "lifeos": {"display_name": "lifeOS", "type": "git"},
    "kv-hrms": {"display_name": "kv-hrms", "type": "git"},
}


def test_work_on_project_sets_ask_instruction():
    i = parse_intent("Let's work on lifeos.", REGISTRY)
    assert i.kind == "ask_instruction"
    assert i.project == "lifeos"


def test_followup_intents():
    assert parse_intent("what's remaining?", REGISTRY).kind == "remaining"
    assert parse_intent("What's left?", REGISTRY).kind == "remaining"
    assert parse_intent("done?", REGISTRY).kind == "done_check"
    assert parse_intent("are you done?", REGISTRY).kind == "done_check"
    assert parse_intent("How long will it take?", REGISTRY).kind == "estimate"
    assert parse_intent("what changes did you make?", REGISTRY).kind == "changes"
    assert parse_intent("why is it stuck?", REGISTRY).kind == "stuck"
    assert parse_intent("continue working", REGISTRY).kind == "continue_work"


def test_active_project_used_for_task_without_name(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    from orchestrator import config

    config.settings.reload()
    db.initialize()
    session.set_active_project("u-ctx", "lifeos")
    i = parse_intent(
        "fix dark mode on the login and registration pages",
        REGISTRY,
        sender="u-ctx",
    )
    assert i.kind == "task"
    assert i.project == "lifeos"


def test_progress_remaining_from_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    from orchestrator import config

    config.settings.reload()
    db.initialize()
    tasks.create_task("aaaaaaaaaaaa", "web:owner", "lifeos", "fix dark mode")
    tasks.update_task(
        "aaaaaaaaaaaa",
        status="running",
        execution_stage="agent_running",
        started_at=db.now(),
        agent_pid=4242,
    )
    task_events.record(
        "aaaaaaaaaaaa",
        "workspace_ready",
        "Workspace ready",
        stage="preparing_workspace",
    )
    task_events.record(
        "aaaaaaaaaaaa",
        "agent_started",
        "Cursor agent process started — detailed activity unavailable until it exits",
        stage="agent_running",
    )
    task = tasks.get_task("aaaaaaaaaaaa")
    text = progress.reply_remaining(task)
    assert "detailed activity unavailable" in text.lower()
    assert "investigating" not in text.lower()
    assert "testing" in text.lower() or "ready for review" in text.lower()
    assert "Just a few minutes" not in text

    est = progress.reply_estimate(task)
    assert "don't invent" in est.lower() or "evidence" in est.lower() or "cannot give" in est.lower()
    assert "just a few minutes" not in est.lower()
    assert "detailed activity unavailable" in est.lower()


def test_taking_so_long_is_estimate():
    assert parse_intent("Why is it taking so long?", REGISTRY).kind == "estimate"


def test_handler_remaining_uses_events(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("WEBHOOK_REPLY_ENABLED", "false")
    monkeypatch.setenv("REPLY_LOG_ENABLED", "false")
    monkeypatch.setenv("GROQ_API_KEY", "")
    from orchestrator import config

    config.settings.reload()
    db.initialize()
    clear_pending("web:owner")
    replies = []
    monkeypatch.setattr(
        "orchestrator.handlers.send_text",
        lambda s, t, **k: replies.append(t),
    )
    monkeypatch.setattr("orchestrator.handlers.llm_chat.phrase", lambda *a, **k: None)
    monkeypatch.setattr("orchestrator.handlers.llm_chat.understand", lambda *a, **k: None)

    tasks.create_task("bbbbbbbbbbbb", "web:owner", "lifeos", "fix dark mode black screen")
    tasks.update_task("bbbbbbbbbbbb", status="running", execution_stage="preparing_workspace")
    task_events.record(
        "bbbbbbbbbbbb", "workspace_preparing", "Preparing isolated workspace", stage="preparing_workspace"
    )
    session.set_active_task("web:owner", "bbbbbbbbbbbb", project="lifeos")

    handle("web:owner", "what's remaining?")
    assert replies
    assert "lifeos" in replies[-1].lower()
    assert "preparing" in replies[-1].lower() or "workspace" in replies[-1].lower()
    assert "in progress" != replies[-1].strip().lower()


def test_handler_ask_instruction_persists_session(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("WEBHOOK_REPLY_ENABLED", "false")
    monkeypatch.setenv("REPLY_LOG_ENABLED", "false")
    monkeypatch.setenv("GROQ_API_KEY", "")
    from orchestrator import config

    config.settings.reload()
    db.initialize()
    clear_pending("web:owner")
    replies = []
    monkeypatch.setattr(
        "orchestrator.handlers.send_text",
        lambda s, t, **k: replies.append(t),
    )
    monkeypatch.setattr(
        "orchestrator.handlers.projects.projects",
        lambda: {
            "lifeos": {
                "path": str(tmp_path / "lifeos"),
                "type": "local",
                "allow_push": False,
                "allow_deploy": False,
                "deploy_command": "",
                "test_command": "",
            }
        },
    )
    monkeypatch.setattr("orchestrator.handlers.llm_chat.understand", lambda *a, **k: None)
    (tmp_path / "lifeos").mkdir()

    handle("web:owner", "Let's work on lifeos.")
    assert session.get("web:owner").get("active_project") == "lifeos"
    assert "lifeos" in replies[-1].lower()
