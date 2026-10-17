import hashlib
import hmac
import importlib
import json
import time

from fastapi.testclient import TestClient


def _load_app(monkeypatch, tmp_path, **env):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import orchestrator.config as cfg

    cfg.settings.reload()
    import app

    importlib.reload(app)
    app.settings.reload()
    app._db.initialize()
    return app


def test_health(tmp_path, monkeypatch):
    app = _load_app(monkeypatch, tmp_path)
    assert TestClient(app.app).get("/health").json() == {"status": "ok"}


def test_webhook_signature_and_dedup(tmp_path, monkeypatch):
    app = _load_app(
        monkeypatch,
        tmp_path,
        ALLOWED_WHATSAPP_NUMBERS="923001111111",
        META_APP_SECRET="secret",
        META_VERIFY_TOKEN="verify",
        WEBHOOK_REPLY_ENABLED="false",
    )
    client = TestClient(app.app)
    assert (
        client.get("/webhook?hub.mode=subscribe&hub.verify_token=verify&hub.challenge=abc").text
        == "abc"
    )
    assert client.post("/webhook", json={}).status_code == 403
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": "wa-1",
                                    "from": "923001111111",
                                    "type": "text",
                                    "text": {"body": "PROJECTS"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(b"secret", raw, hashlib.sha256).hexdigest()
    assert client.post("/webhook", content=raw, headers={"x-hub-signature-256": signature}).status_code == 200
    assert client.post("/webhook", content=raw, headers={"x-hub-signature-256": signature}).status_code == 200
    with app.db() as conn:
        assert conn.execute("select count(*) from incoming").fetchone()[0] == 1


def test_dry_run_approval_cannot_publish(tmp_path, monkeypatch):
    app = _load_app(
        monkeypatch,
        tmp_path,
        DRY_RUN="true",
        WEBHOOK_REPLY_ENABLED="false",
    )
    now = 123
    with app.db() as c:
        c.execute(
            "INSERT INTO tasks(id,sender,project,instruction,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            ("abcdef123456", "923001111111", "example", "fix test", "review", now, now),
        )
    app.handle("923001111111", "APPROVE abcdef123456 PUSH")
    assert app.one("abcdef123456")["status"] == "review"


def test_durable_queue_enqueue_and_claim(tmp_path, monkeypatch):
    app = _load_app(monkeypatch, tmp_path, WEBHOOK_REPLY_ENABLED="false")
    from orchestrator import queue, tasks

    tasks.create_task("abcabcabcabc", "923001111111", "demo", "do something useful")
    job_id = queue.enqueue("abcabcabcabc", kind="execute")
    assert job_id > 0
    claimed = queue.claim_next()
    assert claimed is not None
    assert claimed["task_id"] == "abcabcabcabc"
    assert claimed["status"] == "running"
    queue.complete(claimed["id"])
    assert queue.claim_next() is None


def test_lease_reclaim(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_LEASE_SEC", "1")
    app = _load_app(monkeypatch, tmp_path, WEBHOOK_REPLY_ENABLED="false", JOB_LEASE_SEC="1")
    from orchestrator import db, queue, tasks

    tasks.create_task("deadbeefcafe", "923001111111", "demo", "lease test task")
    queue.enqueue("deadbeefcafe", kind="execute")
    claimed = queue.claim_next()
    assert claimed is not None
    # Expire lease artificially.
    with db.DB_LOCK, db.connect() as c:
        c.execute("UPDATE jobs SET leased_until=? WHERE id=?", (db.now() - 5, claimed["id"]))
    time.sleep(0.05)
    reclaimed = queue.claim_next()
    assert reclaimed is not None
    assert reclaimed["id"] == claimed["id"]
    assert reclaimed["attempts"] >= 2


def test_project_schema_rejects_local_push(tmp_path):
    from orchestrator.projects import ProjectConfigError, load_projects

    path = tmp_path / "projects.json"
    path.write_text(
        json.dumps(
            {
                "bad": {
                    "path": str(tmp_path),
                    "type": "local",
                    "allow_push": True,
                }
            }
        ),
        encoding="utf-8",
    )
    try:
        load_projects(path, strict=True)
        assert False, "expected ProjectConfigError"
    except ProjectConfigError as exc:
        assert "allow_push" in str(exc)


def test_state_machine_rejects_illegal_transition():
    from orchestrator.state import assert_transition

    try:
        assert_transition("queued", "published")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_agent_argv_includes_sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_SANDBOX", "enabled")
    monkeypatch.setenv("AGENT_BIN", "agent")
    import orchestrator.config as cfg
    from pathlib import Path

    cfg.settings.reload()
    from orchestrator import agent

    monkeypatch.setattr(agent, "resolve_agent_argv", lambda: ["agent"])
    argv = agent.build_argv(Path(tmp_path))
    assert "--sandbox" in argv
    # Windows forces disabled; other platforms keep enabled.
    import os

    expected = "disabled" if os.name == "nt" else "enabled"
    assert expected in argv
    assert "--workspace" in argv
    assert "--trust" in argv
    assert agent.CLI_POINTER in argv
    assert "hello" not in argv


def test_workspace_retention_cleanup(tmp_path, monkeypatch):
    app = _load_app(monkeypatch, tmp_path, WORKSPACE_RETENTION_DAYS="1", WEBHOOK_REPLY_ENABLED="false")
    from pathlib import Path

    from orchestrator import db, retention, tasks

    task_id = "retent001234"
    ws = Path(tmp_path / "work" / task_id)
    ws.mkdir(parents=True)
    (ws / "file.txt").write_text("x", encoding="utf-8")
    old = db.now() - 3 * 86400
    with db.DB_LOCK, db.connect() as c:
        c.execute(
            """INSERT INTO tasks(id,sender,project,instruction,status,workspace,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (task_id, "923001111111", "demo", "old task here", "rejected", str(ws), old, old),
        )
    assert retention.cleanup_workspaces() == 1
    assert not ws.exists()
    assert tasks.get_task(task_id)["workspace"] is None


def test_audit_record(tmp_path, monkeypatch):
    app = _load_app(monkeypatch, tmp_path, WEBHOOK_REPLY_ENABLED="false")
    from orchestrator import audit, db

    audit.record("unit_test_event", actor="923001111111", task_id="abcdef123456", detail={"k": 1})
    with db.DB_LOCK, db.connect() as c:
        row = c.execute(
            "SELECT action, actor, ok FROM audit_events WHERE action=?",
            ("unit_test_event",),
        ).fetchone()
    assert row["action"] == "unit_test_event"
    assert row["actor"] == "923001111111"
    assert row["ok"] == 1
