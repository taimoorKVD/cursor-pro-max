import importlib
from pathlib import Path

from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"


def _client(monkeypatch, tmp_path, password=PASSWORD):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("RESTART_REQUEST_FILE", str(tmp_path / "restart-orchestrator.request"))
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


def test_restart_requires_auth_and_writes_signal(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert client.post("/chat/restart").status_code == 401

    assert _login(client).status_code == 200
    page = client.get("/chat")
    assert "restartOrchestratorBtn" in page.text
    assert "reconnectOverlay" in page.text
    assert "Reconnect" in page.text or "Reconnecting" in page.text

    from orchestrator import webchat

    started = []

    class _FakeThread:
        def __init__(self, target=None, name=None, daemon=None):
            self._target = target

        def start(self):
            started.append(True)

    monkeypatch.setattr(webchat.threading, "Thread", _FakeThread)
    resp = client.post("/chat/restart")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") is True
    assert body.get("restarting") is True
    assert (tmp_path / "restart-orchestrator.request").is_file()
    assert started  # exit fallback thread scheduled


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


def test_notifications_default_on_with_manual_off(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200
    html = client.get("/chat").text
    assert "orch_notify_off" in html
    assert "notificationsWanted" in html
    assert "toggleNotifications" in html
    assert "ensureNotifications({quiet: true})" in html
    assert "Notifications on — click to turn off" in html
    assert "enableNotifications" not in html


def test_message_feedback_endpoint(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200
    msgs = client.get("/chat/messages").json()["messages"]
    assert msgs and msgs[0]["direction"] == "out"
    mid = msgs[0]["id"]
    up = client.post("/chat/feedback", json={"message_id": mid, "rating": "up"})
    assert up.status_code == 200
    assert up.json().get("ok") is True
    bad = client.post("/chat/feedback", json={"message_id": mid, "rating": "meh"})
    assert bad.status_code == 400
    missing = client.post("/chat/feedback", json={"message_id": 999999, "rating": "down"})
    assert missing.status_code == 404


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
    assert cleared.json().get("deleted", 0) >= 1
    assert tasks.get_task("webcleartask01") is None

    after = client.get("/chat/task-progress").json()
    assert after["ok"] is True
    assert after["task"] is None
    assert after["events"] == []
    status = client.get("/chat/status").json()
    assert status["active_task"] is None
    assert status["recent_tasks"] == []


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
    assert cleared.json().get("deleted", 0) >= 2

    after = client.get("/chat/task-progress").json()
    assert after["task"] is None
    assert after["events"] == []
    assert task_events.list_events("webactclear001") == []
    assert task_events.list_events("webactclear002") == []
    assert tasks.get_task("webactclear001") is None
    assert tasks.get_task("webactclear002") is None

    status_after = client.get("/chat/status").json()
    assert status_after["recent_tasks"] == []
    assert status_after["active_task"] is None

    after_msgs = client.get("/chat/messages").json()["messages"]
    assert any(m["direction"] == "in" and "hello" in m["text"].lower() for m in after_msgs)
    page = client.get("/chat")
    assert "Clear all activity" in page.text
    assert 'id="clearActivityBtn"' in page.text


def test_focus_task_and_inflight_count(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200

    from orchestrator import session, tasks

    tasks.create_task("focus00000001", "web:owner", "lifeos", "first agent")
    tasks.create_task("focus00000002", "web:owner", "lifeos", "second agent")
    tasks.update_task("focus00000001", status="running", execution_stage="agent_running")
    tasks.update_task("focus00000002", status="queued", execution_stage="queued")
    session.set_active_project("web:owner", "lifeos")
    session.set_active_task("web:owner", "focus00000001", project="lifeos")

    status = client.get("/chat/status").json()
    assert status["inflight_count"] == 2
    assert status["active_task"]["id"] == "focus00000001"

    focused = client.post("/chat/focus-task", json={"task_id": "focus00000002"})
    assert focused.status_code == 200
    assert focused.json()["ok"] is True
    assert focused.json()["task_id"] == "focus00000002"
    ctx = session.get("web:owner")
    assert ctx["active_task_id"] == "focus00000002"
    assert ctx["active_project"] == "lifeos"

    progress = client.get("/chat/task-progress").json()
    assert progress["task"]["task_id"] == "focus00000002"

    missing = client.post("/chat/focus-task", json={"task_id": "doesnotexist1"})
    assert missing.status_code == 404


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
    assert deleted.json().get("ok") is True
    assert client.get("/chat/projects").json()["projects"] == []

    # Create from scratch: mkdir under root + register
    made = client.post("/chat/projects", json={"create": True, "name": "Brand New"})
    assert made.status_code == 200
    body = made.json()
    assert body.get("created") is True
    assert body["project"]["id"] == "brand-new"
    assert (root / "brand-new").is_dir()
    listed_after = client.get("/chat/projects").json()["projects"]
    assert any(p["id"] == "brand-new" for p in listed_after)


def test_delete_project_cancels_inflight_and_clears_chat(tmp_path, monkeypatch):
    root = tmp_path / "www"
    root.mkdir()
    folder = root / "demoapp"
    folder.mkdir()
    projects_file = tmp_path / "projects.json"
    monkeypatch.setenv("PROJECTS_ROOT", str(root))
    monkeypatch.setenv("PROJECTS_FILE", str(projects_file))
    monkeypatch.setenv("PROJECTS_ROOT_FILE", str(tmp_path / "projects_root.json"))
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200

    import orchestrator.config as cfg

    cfg.settings.reload()

    assert client.post("/chat/projects", json={"id": "demoapp", "path": str(folder)}).status_code == 200
    assert client.post("/chat/active-project", json={"project": "demoapp"}).status_code == 200
    assert client.post("/chat/send", json={"text": "hello demo", "cid": "rm-msg-1"}).status_code == 200

    from orchestrator import session, tasks

    tasks.create_task("rmprojtask0001", "web:owner", "demoapp", "in flight")
    tasks.update_task("rmprojtask0001", status="running", execution_stage="agent_running")
    session.set_active_task("web:owner", "rmprojtask0001", project="demoapp")

    deleted = client.delete("/chat/projects/demoapp")
    assert deleted.status_code == 200
    body = deleted.json()
    assert body.get("ok") is True
    assert body.get("canceled", 0) >= 1
    assert body.get("deleted", 0) >= 1
    assert tasks.get_task("rmprojtask0001") is None
    assert client.get("/chat/projects").json()["projects"] == []
    # Folder on disk stays.
    assert folder.is_dir()


def test_cancel_task_api_stops_inflight(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200

    from orchestrator import session, tasks

    tid = "canceltask0001"
    tasks.create_task(tid, "web:owner", "lifeos", "long running")
    tasks.update_task(tid, status="running", execution_stage="agent_running")
    session.set_active_project("web:owner", "lifeos")
    session.set_active_task("web:owner", tid, project="lifeos")

    missing = client.post("/chat/cancel-task", json={"task_id": "doesnotexist1"})
    assert missing.status_code == 404

    ok = client.post("/chat/cancel-task", json={"task_id": tid})
    assert ok.status_code == 200
    body = ok.json()
    assert body["ok"] is True
    assert body["task_id"] == tid
    assert body["status"] == "failed"
    assert body["execution_stage"] == "canceled"
    row = tasks.get_task(tid)
    assert row["status"] == "failed"
    assert row["execution_stage"] == "canceled"

    # Review tasks cannot be cancelled via this endpoint.
    tasks.create_task("cancelreview01", "web:owner", "lifeos", "ready")
    tasks.update_task("cancelreview01", status="running", execution_stage="agent_running")
    tasks.update_task("cancelreview01", status="review", execution_stage="ready_for_review")
    bad = client.post("/chat/cancel-task", json={"task_id": "cancelreview01"})
    assert bad.status_code == 409


def test_chat_page_includes_remove_and_cancel_ui(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    _login(client)
    html = client.get("/chat").text
    assert 'id="removeChatBtn"' in html
    assert 'id="activityCancelActions"' in html
    assert 'id="activityCancelBtn"' in html
    assert 'id="busyCancelTask"' in html
    assert "cancelInProgressTask" in html
    assert "/chat/cancel-task" in html
    assert "activity-history-cancel" in html
    assert "Remove from system" in html
    css = client.get("/chat/app.css")
    assert css.status_code == 200
    assert "activity-history-cancel" in css.text
    assert "work-busy-cancel" in css.text


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
    assert 'id="newProjectNameInput"' in html
    assert 'id="newProjectCreateBtn"' in html
    assert "createNewProject" in html
    assert "New project" in html
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


def test_chat_page_includes_rename_chat_ui(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    _login(client)
    html = client.get("/chat").text
    assert 'id="chatTitle"' in html
    assert 'id="renameChatBtn"' in html
    assert 'id="renameChatModal"' in html
    assert 'id="renameChatInput"' in html
    assert "openRenameChat" in html
    assert "saveRenameChat" in html
    assert "display_name" in html
    assert "Rename chat" in html
    assert "chat-title-editable" in html


def test_activity_format_regexes_use_js_whitespace(tmp_path, monkeypatch):
    """CHAT_HTML is a Python raw string — \\s must not be double-escaped for the browser."""
    _client(monkeypatch, tmp_path)
    from orchestrator.webchat_pages import CHAT_HTML

    # Browser must see \s (whitespace), not \\s (literal backslash + s).
    assert "replace(/^Agent:\\s*/i" in CHAT_HTML
    assert "replace(/^Agent:\\\\s*/i" not in CHAT_HTML
    assert "(Write|Edit|Read|Grep|Glob|Shell|Delete)\\s+(.+)$/i" in CHAT_HTML
    assert "(Write|Edit|Read|Grep|Glob|Shell|Delete)\\\\s+(.+)$/i" not in CHAT_HTML
    assert "activityInstructionPreview" in CHAT_HTML
    assert "projectDisplayName(t.project" in CHAT_HTML
    assert "resolveReviewCta" in CHAT_HTML
    assert "clearResolvedReviewCtas" in CHAT_HTML
    assert "openProgressPanel()" in CHAT_HTML
    assert "retryPublishFailedTask" in CHAT_HTML
    assert "cancelInProgressTask" in CHAT_HTML
    assert "activity-history-try" in CHAT_HTML
    assert "activity-history-cancel" in CHAT_HTML
    assert "Try Again" in CHAT_HTML
    assert "/chat/retry-task" in CHAT_HTML
    assert "/chat/cancel-task" in CHAT_HTML
    assert "Publish failed" in CHAT_HTML


def test_retry_task_requeues_publish_failed(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200

    from orchestrator import session, tasks

    tid = "retryfail0001"
    tasks.create_task(tid, "web:owner", "lifeos", "fix the login")
    tasks.update_task(tid, status="running", execution_stage="agent_running")
    tasks.update_task(
        tid,
        status="review",
        execution_stage="ready_for_review",
        content_digest="a" * 40,
        branch="review/retryfail0001",
    )
    tasks.update_task(tid, status="publishing")
    tasks.update_task(
        tid,
        status="publish_failed",
        execution_stage="failed",
        summary="apply blocked",
        content_digest="a" * 40,
        branch="review/retryfail0001",
    )
    session.set_active_project("web:owner", "lifeos")
    session.set_active_task("web:owner", tid, project="lifeos")

    enqueued = []
    monkeypatch.setattr(
        "orchestrator.queue.enqueue",
        lambda task_id, kind="execute": enqueued.append((task_id, kind)) or 1,
    )

    missing = client.post("/chat/retry-task", json={"task_id": "doesnotexist1"})
    assert missing.status_code == 404

    ok = client.post("/chat/retry-task", json={"task_id": tid})
    assert ok.status_code == 200
    body = ok.json()
    assert body["ok"] is True
    assert body["task_id"] == tid
    assert body["status"] == "publishing"
    assert body["action"] == "APPLY"
    assert enqueued == [(tid, "publish:APPLY")]
    assert tasks.get_task(tid)["status"] == "publishing"

    # Non-publish_failed tasks are rejected.
    tasks.create_task("retryok000001", "web:owner", "lifeos", "other")
    tasks.update_task("retryok000001", status="running", execution_stage="agent_running")
    tasks.update_task("retryok000001", status="review", execution_stage="ready_for_review")
    bad = client.post("/chat/retry-task", json={"task_id": "retryok000001"})
    assert bad.status_code == 409

    css = client.get("/chat/app.css")
    assert css.status_code == 200
    assert "activity-history-try" in css.text


def test_status_recent_tasks_include_instruction(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200

    from orchestrator import session, tasks

    tasks.create_task("instrtask0001", "web:owner", "lifeos", "remember me for 30 days")
    tasks.update_task("instrtask0001", status="running", execution_stage="agent_running")
    tasks.update_task("instrtask0001", status="review", execution_stage="ready_for_review")
    session.set_active_project("web:owner", "lifeos")

    status = client.get("/chat/status").json()
    row = next(t for t in status["recent_tasks"] if t["id"] == "instrtask0001")
    assert row["instruction"] == "remember me for 30 days"


def test_project_switch_rebinds_activity_task(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200

    from orchestrator import session, tasks

    tasks.create_task("switchtask0001", "web:owner", "lifeos", "lifeos work")
    tasks.update_task("switchtask0001", status="running", execution_stage="agent_running")
    tasks.create_task("switchtask0002", "web:owner", "demoapp", "other work")
    tasks.update_task("switchtask0002", status="running", execution_stage="agent_running")
    tasks.update_task("switchtask0002", status="review", execution_stage="ready_for_review")
    session.set_active_project("web:owner", "lifeos")
    session.set_active_task("web:owner", "switchtask0001", project="lifeos")

    before = client.get("/chat/task-progress").json()
    assert before["task"]["task_id"] == "switchtask0001"

    # switch_project rebinds active_task_id to the destination project's work
    # (HTTP /chat/active-project also requires a registered project id).
    result = session.switch_project("web:owner", "demoapp")
    assert result["changed"] is True
    assert session.get("web:owner")["active_task_id"] == "switchtask0002"

    after = client.get("/chat/task-progress").json()
    assert after["task"] is not None
    assert after["task"]["task_id"] == "switchtask0002"
    assert after["task"]["project"] == "demoapp"
