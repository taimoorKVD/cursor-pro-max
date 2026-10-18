"""Project-scoped chat: LifeOS thread must not leak after switching projects."""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("TELEGRAM_POLLING_ENABLED", "false")
    monkeypatch.setenv("WEBCHAT_PASSWORD", PASSWORD)
    monkeypatch.setenv("REPLY_LOG_ENABLED", "false")
    monkeypatch.setenv("GROQ_CHAT_ENABLED", "false")
    monkeypatch.setenv("GROQ_API_KEY", "")
    import orchestrator.config as cfg

    cfg.settings.reload()
    import app

    importlib.reload(app)
    app.settings.reload()
    app._db.initialize()
    from orchestrator import converse, session, webchat

    webchat._failures.clear()
    converse.clear_pending("web:owner")
    session.clear("web:owner")
    return TestClient(app.app)


def _login(client):
    assert client.post("/chat/login", json={"password": PASSWORD}).status_code == 200


def test_switch_project_clears_lifeos_thread_from_ui(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    _login(client)

    lifeos = tmp_path / "lifeos"
    other = tmp_path / "other-app"
    lifeos.mkdir()
    other.mkdir()

    monkeypatch.setattr(
        "orchestrator.handlers.projects.projects",
        lambda: {
            "lifeos": {
                "path": str(lifeos),
                "type": "local",
                "allow_push": False,
                "allow_deploy": False,
                "deploy_command": "",
                "test_command": "",
            },
            "other-app": {
                "path": str(other),
                "type": "local",
                "allow_push": False,
                "allow_deploy": False,
                "deploy_command": "",
                "test_command": "",
            },
        },
    )
    monkeypatch.setattr(
        "orchestrator.projects.projects",
        lambda: {
            "lifeos": {
                "path": str(lifeos),
                "type": "local",
                "allow_push": False,
                "allow_deploy": False,
                "deploy_command": "",
                "test_command": "",
            },
            "other-app": {
                "path": str(other),
                "type": "local",
                "allow_push": False,
                "allow_deploy": False,
                "deploy_command": "",
                "test_command": "",
            },
        },
    )

    # Simulate a LifeOS conversation.
    sw = client.post("/chat/active-project", json={"project": "lifeos"})
    assert sw.status_code == 200
    assert sw.json()["active_project"] == "lifeos"
    client.post("/chat/send", json={"text": "fix dark mode on the login page", "cid": "life-1"})

    life_msgs = client.get("/chat/messages?project=lifeos").json()["messages"]
    assert any("dark mode" in m["text"].lower() for m in life_msgs)

    # Switch to an unused project — UI must not keep LifeOS turns.
    switched = client.post("/chat/active-project", json={"project": "other-app"})
    assert switched.status_code == 200
    body = switched.json()
    assert body["changed"] is True
    assert body["previous"] == "lifeos"
    assert body["active_project"] == "other-app"
    other_msgs = body["messages"]
    assert not any("dark mode" in m["text"].lower() for m in other_msgs)
    assert not any("lifeos" in m["text"].lower() and "dark" in m["text"].lower() for m in other_msgs)
    # Unused project: empty thread — no auto "Switched to …" notice, never prior LifeOS work.
    assert other_msgs == []
    assert not any("Switched to" in (m.get("text") or "") for m in other_msgs)

    polled = client.get("/chat/messages?project=other-app").json()
    assert polled["active_project"] == "other-app"
    assert not any("dark mode" in m["text"].lower() for m in polled["messages"])

    # LifeOS thread is still intact when selected again.
    back = client.get("/chat/messages?project=lifeos").json()["messages"]
    assert any("dark mode" in m["text"].lower() for m in back)


def test_history_and_llm_context_scoped_after_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("GROQ_API_KEY", "")
    from orchestrator import config, db, history, llm_chat, session

    config.settings.reload()
    db.initialize()

    session.switch_project("web:owner", "lifeos")
    history.append("web:owner", "in", "Let's work on lifeos", project="lifeos")
    history.append("web:owner", "out", "Okay — dark mode on LifeOS?", project="lifeos")
    history.append("web:owner", "in", "yes fix dark mode", project="lifeos")

    session.switch_project("web:owner", "other-app")
    # Unused project: no prior turns.
    assert history.recent("web:owner", limit=20, project="other-app") == []

    turns = llm_chat._chat_history("web:owner", current="improve form validation")
    assert not any("dark mode" in t["content"].lower() for t in turns)
    assert not any("lifeos" in t["content"].lower() for t in turns)

    # LifeOS history remains when that project is active again.
    session.switch_project("web:owner", "lifeos")
    life_turns = llm_chat._chat_history("web:owner", current="status?")
    assert any("dark mode" in t["content"].lower() for t in life_turns)


def test_handler_switch_announces_fresh_thread(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("WEBHOOK_REPLY_ENABLED", "false")
    monkeypatch.setenv("REPLY_LOG_ENABLED", "false")
    monkeypatch.setenv("GROQ_API_KEY", "")
    from orchestrator import config, db, session
    from orchestrator.handlers import handle

    config.settings.reload()
    db.initialize()
    session.clear("web:owner")

    lifeos = tmp_path / "lifeos"
    other = tmp_path / "other-app"
    lifeos.mkdir()
    other.mkdir()
    registry = {
        "lifeos": {
            "path": str(lifeos),
            "type": "local",
            "allow_push": False,
            "allow_deploy": False,
            "deploy_command": "",
            "test_command": "",
        },
        "other-app": {
            "path": str(other),
            "type": "local",
            "allow_push": False,
            "allow_deploy": False,
            "deploy_command": "",
            "test_command": "",
        },
    }
    replies: list[str] = []
    monkeypatch.setattr(
        "orchestrator.handlers.send_text",
        lambda s, t, **k: replies.append(t),
    )
    monkeypatch.setattr("orchestrator.handlers.projects.projects", lambda: registry)
    monkeypatch.setattr("orchestrator.handlers.llm_chat.understand", lambda *a, **k: None)

    handle("web:owner", "Let's work on lifeos.")
    assert session.get("web:owner")["active_project"] == "lifeos"
    handle("web:owner", "Let's work on other-app.")
    assert session.get("web:owner")["active_project"] == "other-app"
    assert any("switched from lifeos" in r.lower() for r in replies)
    assert any("fresh" in r.lower() or "only for other-app" in r.lower() for r in replies)
