from orchestrator import config, converse
from orchestrator.handlers import handle


def _setup(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("WEBHOOK_REPLY_ENABLED", "false")
    monkeypatch.setenv("REPLY_LOG_ENABLED", "false")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("GROQ_API_KEY", "")
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
    return replies


def test_natural_status_and_tasks(tmp_path, monkeypatch):
    replies = _setup(tmp_path, monkeypatch)
    from orchestrator import tasks

    handle("web:owner", "status of valoracares")
    assert "project" in replies[-1].lower()

    handle("web:owner", "show my tasks")
    assert "don't have any tasks" in replies[-1].lower() or "no tasks" in replies[-1].lower()

    tasks.create_task("abcdef123456", "web:owner", "lifeos", "demo instruction here")
    handle("web:owner", "my tasks")
    assert "abcdef123456" in replies[-1]

    handle("web:owner", "how is my last task going?")
    assert "lifeos" in replies[-1]
    assert "queued" in replies[-1].lower()


def test_natural_help_and_greet(tmp_path, monkeypatch):
    replies = _setup(tmp_path, monkeypatch)
    handle("web:owner", "hi")
    assert "help" in replies[-1].lower() or "what" in replies[-1].lower()
    handle("web:owner", "what can you do?")
    assert "project" in replies[-1].lower() or "approve" in replies[-1].lower()


def test_natural_task_and_clarify_project(tmp_path, monkeypatch):
    replies = _setup(tmp_path, monkeypatch)
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
    (tmp_path / "lifeos").mkdir()
    monkeypatch.setattr("orchestrator.handlers.preflight.project_ready", lambda *a, **k: (True, "ok"))

    handle("web:owner", "please improve the login validation")
    assert "which project" in replies[-1].lower() or "project" in replies[-1].lower()

    handle("web:owner", "lifeos")
    assert "lifeos" in replies[-1].lower()
    assert "task" in replies[-1].lower()


def test_classic_task_syntax_still_works(tmp_path, monkeypatch):
    replies = _setup(tmp_path, monkeypatch)
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
    (tmp_path / "lifeos").mkdir()
    monkeypatch.setattr("orchestrator.handlers.preflight.project_ready", lambda *a, **k: (True, "ok"))
    handle("web:owner", "TASK lifeos: Add a short README note please")
    assert "lifeos" in replies[-1].lower()


def test_second_task_while_running_starts_parallel(tmp_path, monkeypatch):
    replies = _setup(tmp_path, monkeypatch)
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
    (tmp_path / "lifeos").mkdir()
    monkeypatch.setattr("orchestrator.handlers.preflight.project_ready", lambda *a, **k: (True, "ok"))
    from orchestrator import session, tasks

    tasks.create_task("run0000000001", "web:owner", "lifeos", "first change")
    tasks.update_task("run0000000001", status="running", execution_stage="agent_running")
    session.set_active_task("web:owner", "run0000000001", project="lifeos")

    handle("web:owner", "TASK lifeos: Add a second independent change")
    assert "parallel" in replies[-1].lower()
    assert "2 agents" in replies[-1].lower()
    inflight = tasks.inflight_tasks_for_sender("web:owner", project="lifeos")
    assert len(inflight) == 2
    ctx = session.get("web:owner")
    assert ctx["active_task_id"] != "run0000000001"
    assert ctx["active_task_id"] in {t["id"] for t in inflight}


def test_continue_work_while_running_reports_status_only(tmp_path, monkeypatch):
    replies = _setup(tmp_path, monkeypatch)
    from orchestrator import session, tasks

    tasks.create_task("cont000000001", "web:owner", "lifeos", "ongoing work")
    tasks.update_task("cont000000001", status="running", execution_stage="agent_running")
    session.set_active_task("web:owner", "cont000000001", project="lifeos")
    before = len(tasks.inflight_tasks_for_sender("web:owner", project="lifeos"))

    handle("web:owner", "continue working")
    assert "already running" in replies[-1].lower()
    after = tasks.inflight_tasks_for_sender("web:owner", project="lifeos")
    assert len(after) == before


def test_chat_scan_and_register_project(tmp_path, monkeypatch):
    replies = _setup(tmp_path, monkeypatch)
    root = tmp_path / "www"
    root.mkdir()
    (root / "newapp").mkdir()
    other = tmp_path / "other"
    other.mkdir()
    (other / "side").mkdir()
    projects_file = tmp_path / "projects.json"
    monkeypatch.setenv("PROJECTS_ROOT", str(root))
    monkeypatch.setenv("PROJECTS_FILE", str(projects_file))
    monkeypatch.setenv("PROJECTS_ROOT_FILE", str(tmp_path / "projects_root.json"))
    config.settings.reload()

    handle("web:owner", "scan projects")
    assert "newapp" in replies[-1].lower()
    assert "not registered" in replies[-1].lower() or "folder" in replies[-1].lower()

    handle("web:owner", f"set projects root {other}")
    assert "scan folder set" in replies[-1].lower() or str(other).lower() in replies[-1].lower()
    handle("web:owner", "scan projects")
    assert "side" in replies[-1].lower()

    handle("web:owner", f"set projects root {root}")
    handle("web:owner", "add project newapp")
    assert "registered" in replies[-1].lower()
    assert "newapp" in replies[-1].lower()

    from orchestrator.projects import load_projects

    assert "newapp" in load_projects(projects_file, strict=True)

    handle("web:owner", "remove project newapp")
    assert "yes" in replies[-1].lower() or "confirm" in replies[-1].lower()
    handle("web:owner", "yes")
    assert "removed" in replies[-1].lower()
    assert load_projects(projects_file, strict=True) == {}
