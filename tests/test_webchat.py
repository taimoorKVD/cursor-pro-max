import importlib

from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"


def _client(monkeypatch, tmp_path, password=PASSWORD):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("TELEGRAM_POLLING_ENABLED", "false")
    monkeypatch.setenv("WEBCHAT_PASSWORD", password)
    monkeypatch.setenv("REPLY_LOG_ENABLED", "false")
    monkeypatch.setenv("GROQ_CHAT_ENABLED", "false")
    monkeypatch.setenv("GROQ_API_KEY", "")
    import orchestrator.config as cfg

    cfg.settings.reload()
    import app

    importlib.reload(app)
    app.settings.reload()
    app._db.initialize()
    from orchestrator import webchat

    webchat._failures.clear()
    from orchestrator import converse, session

    converse.clear_pending("web:owner")
    session.clear("web:owner")
    return TestClient(app.app)


def _login(client, password=PASSWORD):
    return client.post("/chat/login", json={"password": password})


def test_chat_uses_tailwind_stylesheet(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    css = client.get("/chat/app.css")
    assert css.status_code == 200
    assert "text/css" in css.headers["content-type"]
    assert ".bg-accent" in css.text
    assert ".font-display" in css.text
    page = client.get("/chat")
    assert "/chat/app.css" in page.text
    assert "font-display" in page.text
    assert 'nonce="' in page.text
    csp = page.headers.get("content-security-policy", "")
    assert "worker-src 'self'" in csp
    assert f"script-src 'nonce-" in csp


def test_disabled_without_strong_password(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path, password="short")
    assert client.get("/chat").status_code == 503
    assert _login(client, "short").status_code == 503


def test_requires_login(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    page = client.get("/chat")
    assert page.status_code == 200
    assert "Log in" in page.text
    assert client.get("/chat/messages").status_code == 401
    assert client.post("/chat/send", json={"text": "PROJECTS"}).status_code == 401


def test_wrong_password_locks_out(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    for _ in range(5):
        assert _login(client, "wrong-password-123").status_code == 401
    assert _login(client).status_code == 429


def test_projects_round_trip(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200
    assert "Cursor Orchestrator" in client.get("/chat").text

    # Welcome message is injected on first login when history is empty.
    welcome = client.get("/chat/messages").json()["messages"]
    assert welcome and welcome[0]["direction"] == "out"
    assert "what can i help" in welcome[0]["text"].lower()

    sent = client.post("/chat/send", json={"text": "what projects do I have?", "cid": "abc-1"})
    assert sent.status_code == 200
    dup = client.post("/chat/send", json={"text": "what projects do I have?", "cid": "abc-1"})
    assert dup.json().get("duplicate") is True

    msgs = client.get("/chat/messages").json()["messages"]
    assert any(m["direction"] == "in" and "projects" in m["text"] for m in msgs)
    assert any(m["direction"] == "out" and "your projects" in m["text"].lower() for m in msgs)

    soft = client.post("/chat/send", json={"text": "status of valoracares", "cid": "soft-1"})
    assert soft.status_code == 200
    msgs2 = client.get("/chat/messages").json()["messages"]
    assert any("project" in m["text"].lower() for m in msgs2 if m["direction"] == "out")
    assert all("level" in m for m in msgs2)
    assert client.get("/chat/sw.js").status_code == 200
    manifest = client.get("/chat/manifest.webmanifest")
    assert manifest.status_code == 200
    body = manifest.json()
    assert body["display"] == "standalone"
    assert body["start_url"] == "/chat"
    assert client.get("/chat/apple-touch-icon.png").status_code == 200
    assert client.get("/chat/icon.svg").status_code == 200
    chat_html = client.get("/chat").text
    assert "apple-mobile-web-app-capable" in chat_html
    assert "manifest.webmanifest" in chat_html
    assert "safe-area-inset" in chat_html

    status = client.get("/chat/status").json()
    assert status["ok"] is True
    assert "dry_run" in status
    assert "agent_ok" in status

    newer = client.get(f"/chat/messages?after={msgs2[-1]['id']}").json()["messages"]
    assert newer == []

    cleared = client.post("/chat/clear")
    assert cleared.status_code == 200
    after_clear = client.get("/chat/messages").json()["messages"]
    assert len(after_clear) == 1
    assert after_clear[0]["direction"] == "out"
    assert "what can i help" in after_clear[0]["text"].lower()


def test_clear_chat_clears_recent_activity(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200

    from orchestrator import session, tasks

    tasks.create_task("webcleartask01", "web:owner", "lifeos", "remember me")
    tasks.update_task("webcleartask01", status="running", execution_stage="agent_running")
    tasks.update_task(
        "webcleartask01",
        status="review",
        execution_stage="ready_for_review",
        summary="Agent: wired remember me",
    )
    session.set_active_project("web:owner", "lifeos")
    session.set_active_task("web:owner", "webcleartask01", project="lifeos")

    before = client.get("/chat/task-progress").json()
    assert before["ok"] is True
    assert before["task"] is not None
    assert before["task"]["task_id"] == "webcleartask01"

    cleared = client.post("/chat/clear")
    assert cleared.status_code == 200
    assert cleared.json().get("canceled", 0) >= 1

    after = client.get("/chat/task-progress").json()
    assert after["ok"] is True
    assert after["task"] is None
    assert after["events"] == []
    status = client.get("/chat/status").json()
    assert status["active_task"] is None


def test_clear_activity_keeps_chat_messages(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200

    from orchestrator import session, task_events, tasks

    client.post("/chat/send", json={"text": "hello there", "cid": "keep-msg-1"})
    before_msgs = client.get("/chat/messages").json()["messages"]
    assert any(m["direction"] == "in" and "hello" in m["text"].lower() for m in before_msgs)

    tasks.create_task("webactclear001", "web:owner", "lifeos", "remember me")
    tasks.update_task("webactclear001", status="running", execution_stage="agent_running")
    task_events.record("webactclear001", "agent_stream", "Read: app/login.php")
    # Finished task (not in-flight) must also leave history after clear.
    tasks.create_task("webactclear002", "web:owner", "lifeos", "older work")
    tasks.update_task("webactclear002", status="running", execution_stage="agent_running")
    tasks.update_task("webactclear002", status="failed", execution_stage="failed", summary="tests failed")
    session.set_active_project("web:owner", "lifeos")
    session.set_active_task("web:owner", "webactclear001", project="lifeos")

    status_before = client.get("/chat/status").json()
    assert any(t["id"] == "webactclear002" for t in status_before["recent_tasks"])

    cleared = client.post("/chat/clear-activity")
    assert cleared.status_code == 200
    assert cleared.json().get("canceled", 0) >= 1

    after = client.get("/chat/task-progress").json()
    assert after["task"] is None
    assert after["events"] == []
    assert task_events.list_events("webactclear001") == []
    assert task_events.list_events("webactclear002") == []
    assert tasks.get_task("webactclear002")["execution_stage"] == "canceled"

    status_after = client.get("/chat/status").json()
    assert status_after["recent_tasks"] == []
    assert status_after["active_task"] is None

    after_msgs = client.get("/chat/messages").json()["messages"]
    assert any(m["direction"] == "in" and "hello" in m["text"].lower() for m in after_msgs)
    page = client.get("/chat")
    assert "Clear all activity" in page.text
    assert 'id="clearActivityBtn"' in page.text


def test_qr_page_local_only(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    from orchestrator import webchat

    blocked = client.get("/chat/qr", headers={"Host": "example.trycloudflare.com"})
    assert blocked.status_code == 403

    monkeypatch.setattr(
        webchat,
        "_tunnel_chat_url",
        lambda: ("https://example.trycloudflare.com/chat", ""),
    )
    local = client.get("/chat/qr", headers={"Host": "127.0.0.1:8000"})
    assert local.status_code == 200
    assert "Connect on iPhone" in local.text
    assert "data:image/png;base64," in local.text
    js = client.get("/chat/qr.json", headers={"Host": "127.0.0.1:8000"})
    assert js.status_code == 200
    body = js.json()
    assert body.get("ok") is True
    assert "img" in body and "data:image/png;base64," in body["img"]


def test_qr_page_waiting_layout_stable(tmp_path, monkeypatch):
    """No-tunnel state must render a scrollable stacked layout (not clipped/overlapping)."""
    client = _client(monkeypatch, tmp_path)
    from orchestrator import webchat

    monkeypatch.setattr(
        webchat,
        "_tunnel_chat_url",
        lambda: (None, "Tunnel URL not found yet. The Cloudflare tunnel is reconnecting."),
    )
    page = client.get("/chat/qr", headers={"Host": "127.0.0.1:8000"})
    assert page.status_code == 200
    html = page.text
    assert "Connect on iPhone" in html
    assert "Waiting for tunnel" in html
    assert "overflow-y-auto" in html
    assert "h-dvh" in html.split("<body", 1)[-1].split(">", 1)[0]
    assert "overflow-hidden" not in html.split("<body", 1)[-1].split(">", 1)[0]
    assert "h-qr:" in html  # short-viewport compaction
    assert 'data-ready="0"' in html
    assert "Step by step" in html
    assert "Open on this PC" in html


def test_notify_levels(tmp_path, monkeypatch):
    from orchestrator.notify import infer_level

    assert infer_level("Finished working - ready for your review") == "success"
    assert infer_level("Sorry - task failed: boom") == "error"
    assert infer_level("Heads up - dry-run is on") == "warning"
    assert infer_level("Starting on lifeos now") == "info"
    assert infer_level("x", level="success") == "success"
    # Task lists mention statuses like "Didn't finish" / [failed] without being errors.
    assert infer_level("Here's your recent work:\n- lifeos: Didn't finish\n  fix login") == "info"
    assert infer_level("- lifeos [failed] remove dark mode", level="info") == "info"


def test_send_requires_json(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    _login(client)
    resp = client.post("/chat/send", content="PROJECTS", headers={"content-type": "text/plain"})
    assert resp.status_code == 400


def test_voice_requires_auth_and_groq(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert client.post("/chat/voice", files={"audio": ("v.webm", b"abc", "audio/webm")}).status_code == 401
    _login(client)
    # GROQ disabled in _client fixture → voice unavailable
    blocked = client.post("/chat/voice", files={"audio": ("v.webm", b"abc", "audio/webm")})
    assert blocked.status_code == 503

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_VOICE_ENABLED", "true")
    import orchestrator.config as cfg
    import orchestrator.llm_chat as llm_chat

    cfg.settings.reload()
    assert llm_chat.voice_enabled() is True

    def fake_transcribe(audio, **kwargs):
        assert audio == b"abc"
        return "hello from voice"

    monkeypatch.setattr(llm_chat, "transcribe", fake_transcribe)
    ok = client.post("/chat/voice", files={"audio": ("v.webm", b"abc", "audio/webm")})
    assert ok.status_code == 200
    assert ok.json()["text"] == "hello from voice"
    status = client.get("/chat/status").json()
    assert status.get("voice") is True


def test_projects_api_requires_auth(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert client.get("/chat/projects").status_code == 401
    assert client.get("/chat/projects/candidates").status_code == 401
    assert client.get("/chat/projects/browse").status_code == 401
    assert client.post("/chat/projects", json={"path": str(tmp_path)}).status_code == 401


def test_projects_api_scan_register_patch_delete(tmp_path, monkeypatch):
    root = tmp_path / "www"
    root.mkdir()
    folder = root / "demoapp"
    folder.mkdir()
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "extra").mkdir()
    projects_file = tmp_path / "projects.json"
    monkeypatch.setenv("PROJECTS_ROOT", str(root))
    monkeypatch.setenv("PROJECTS_FILE", str(projects_file))
    monkeypatch.setenv("PROJECTS_ROOT_FILE", str(tmp_path / "projects_root.json"))
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200

    # Reload settings after env for PROJECTS_ROOT (client already reloaded once)
    import orchestrator.config as cfg

    cfg.settings.reload()

    root_get = client.get("/chat/projects/root")
    assert root_get.status_code == 200
    assert root_get.json()["projects_root"]["path"]

    browse = client.get("/chat/projects/browse", params={"path": str(root)})
    assert browse.status_code == 200
    browse_body = browse.json()
    assert browse_body["ok"] is True
    assert any(e["name"] == "demoapp" for e in browse_body["entries"])

    moved = client.put("/chat/projects/root", json={"path": str(other)})
    assert moved.status_code == 200
    assert moved.json()["projects_root"]["source"] == "override"

    scan_other = client.get("/chat/projects/candidates")
    assert scan_other.status_code == 200
    assert any(c["id"] == "extra" for c in scan_other.json()["candidates"])

    # Point back at root for register
    assert client.put("/chat/projects/root", json={"path": str(root)}).status_code == 200

    scan = client.get("/chat/projects/candidates")
    assert scan.status_code == 200
    candidates = scan.json()["candidates"]
    assert any(c["id"] == "demoapp" and not c["registered"] for c in candidates)

    created = client.post("/chat/projects", json={"id": "demoapp", "path": str(folder)})
    assert created.status_code == 200
    assert created.json()["project"]["id"] == "demoapp"

    listed = client.get("/chat/projects").json()["projects"]
    assert any(p["id"] == "demoapp" for p in listed)

    status = client.get("/chat/status").json()
    assert any(p.get("id") == "demoapp" and "path" in p for p in status.get("project_list", []))
    assert status.get("projects_root", {}).get("path")

    patched = client.patch(
        "/chat/projects/demoapp",
        json={"display_name": "Demo App", "description": "from test"},
    )
    assert patched.status_code == 200
    assert patched.json()["project"]["display_name"] == "Demo App"

    deleted = client.delete("/chat/projects/demoapp")
    assert deleted.status_code == 200
    assert client.get("/chat/projects").json()["projects"] == []


def test_chat_page_includes_manage_projects_ui(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    _login(client)
    html = client.get("/chat").text
    assert "projectsManageToggle" in html
    assert 'id="manageDrawer"' in html
    assert 'id="manageDrawerBackdrop"' in html
    assert "Manage projects" in html
    assert "projectsScanBtn" in html
    assert "projectsChooseFolderBtn" in html
    assert "folderPickerModal" in html
    assert "Choose folder" in html
    # Folder picker reuses .confirm-modal CSS, which stays invisible until .open.
    assert "folderPickerModal.classList.add('open')" in html
    assert "folderPickerModal.classList.remove('open')" in html
    assert "/chat/projects/browse" in html
    assert "/chat/projects/candidates" in html
    assert "/chat/projects/root" in html
    assert "Templates" not in html
    assert "Knowledge Base" not in html
    assert 'id="settingsBtn"' not in html
    # Manage button stays in the sidebar; content lives in the left drawer.
    manage_btn_idx = html.index("projectsManageToggle")
    drawer_idx = html.index('id="manageDrawer"')
    status_idx = html.index('id="statusProjects"')
    assert manage_btn_idx < status_idx < drawer_idx
