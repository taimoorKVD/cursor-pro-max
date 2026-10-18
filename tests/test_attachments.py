"""Image attachments: upload, staging, workspace materialize, prompt injection."""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"

# Minimal valid PNG (1x1)
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


def test_attach_requires_auth(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    resp = client.post(
        "/chat/attach",
        files={"image": ("shot.png", _PNG, "image/png")},
    )
    assert resp.status_code == 401


def test_attach_and_fetch_image(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200
    up = client.post(
        "/chat/attach",
        files={"image": ("shot.png", _PNG, "image/png")},
    )
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["ok"] is True
    assert body["id"]
    assert body["content_type"] == "image/png"
    assert body["url"].startswith("/chat/attachments/")

    got = client.get(body["url"])
    assert got.status_code == 200
    assert got.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert "image/png" in got.headers.get("content-type", "")


def test_attach_rejects_non_image(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200
    resp = client.post(
        "/chat/attach",
        files={"image": ("evil.exe", b"MZ\x00\x00not-an-image-file!!", "application/octet-stream")},
    )
    assert resp.status_code == 422


def test_send_with_attachment_stores_message(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200
    up = client.post(
        "/chat/attach",
        files={"image": ("ui.png", _PNG, "image/png")},
    ).json()
    sent = client.post(
        "/chat/send",
        json={
            "text": "what projects do I have?",
            "attachments": [up["id"]],
            "cid": "att-1",
        },
    )
    assert sent.status_code == 200
    msgs = client.get("/chat/messages").json()["messages"]
    inbound = [m for m in msgs if m["direction"] == "in" and "projects" in m["text"]]
    assert inbound
    assert inbound[-1]["attachments"]
    assert inbound[-1]["attachments"][0]["id"] == up["id"]


def test_send_image_only(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200
    up = client.post(
        "/chat/attach",
        files={"image": ("only.png", _PNG, "image/png")},
    ).json()
    sent = client.post(
        "/chat/send",
        json={"text": "", "attachments": [up["id"]], "cid": "img-only-1"},
    )
    assert sent.status_code == 200
    msgs = client.get("/chat/messages").json()["messages"]
    inbound = [m for m in msgs if m["direction"] == "in" and m.get("attachments")]
    assert inbound
    assert inbound[-1]["text"] == "[Image attached]"


def test_materialize_and_build_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    from orchestrator import attachments, config, db
    from orchestrator.agent import build_prompt

    config.settings.reload()
    db.initialize()
    meta = attachments.save_upload(
        "web:owner", _PNG, filename="bug.png", content_type="image/png"
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()
    paths = attachments.materialize_into_workspace(workspace, [meta["id"]])
    assert paths == [".orchestrator-attachments/bug.png"]
    assert (workspace / paths[0]).is_file()
    assert (workspace / paths[0]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    prompt = build_prompt(
        "on demo, fix the layout shown in the screenshot",
        attachment_paths=paths,
    )
    assert "ATTACHED IMAGES" in prompt
    assert ".orchestrator-attachments/bug.png" in prompt
    assert "fix the layout" in prompt


def test_materialize_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    from orchestrator import attachments, config, db

    config.settings.reload()
    db.initialize()
    meta = attachments.save_upload(
        "web:owner", _PNG, filename="ok.png", content_type="image/png"
    )
    # Poison the stored path to escape staging.
    outside = tmp_path / "outside.png"
    outside.write_bytes(_PNG)
    with db.DB_LOCK, db.connect() as c:
        attachments.ensure_schema(c)
        c.execute(
            "UPDATE chat_attachments SET path=? WHERE id=?",
            (str(outside.resolve()), meta["id"]),
        )
    workspace = tmp_path / "ws2"
    workspace.mkdir()
    paths = attachments.materialize_into_workspace(workspace, [meta["id"]])
    assert paths == []


def test_chat_ui_mentions_attach_input(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert _login(client).status_code == 200
    page = client.get("/chat")
    assert page.status_code == 200
    assert 'id="attachInput"' in page.text
    assert 'id="attachPreview"' in page.text
    assert "Attachments coming soon" not in page.text
    assert "/chat/attach" in page.text
