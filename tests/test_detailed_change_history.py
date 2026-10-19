"""Detailed change history: diffs, persistence, API, and chat excerpts."""
from __future__ import annotations

import importlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import db, progress, tasks, workspace
from orchestrator.process import run

PASSWORD = "correct-horse-battery"


def _git_init(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    run(["git", "init"], cwd=str(repo), timeout=30)
    run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], timeout=15)
    run(["git", "-C", str(repo), "config", "user.name", "T"], timeout=15)


def test_detailed_changes_git_add_modify_delete(tmp_path):
    repo = tmp_path / "repo"
    _git_init(repo)
    (repo / "keep.txt").write_text("keep\n", encoding="utf-8")
    (repo / "edit.txt").write_text("old\n", encoding="utf-8")
    (repo / "gone.txt").write_text("bye\n", encoding="utf-8")
    run(["git", "-C", str(repo), "add", "."], timeout=30)
    run(["git", "-C", str(repo), "commit", "-m", "init"], timeout=30)

    (repo / "edit.txt").write_text("new\n", encoding="utf-8")
    (repo / "gone.txt").unlink()
    (repo / "added.txt").write_text("hello\n", encoding="utf-8")
    (repo / ".orchestrator-task.md").write_text("meta\n", encoding="utf-8")

    details = workspace.detailed_changes(repo, "wa/test")
    paths = {f["path"] for f in details["files"]}
    assert "edit.txt" in paths
    assert "added.txt" in paths
    assert "gone.txt" in paths
    assert ".orchestrator-task.md" not in paths
    by_path = {f["path"]: f for f in details["files"]}
    assert by_path["edit.txt"]["status"] == "M"
    assert "+" in by_path["edit.txt"]["patch"] or "new" in by_path["edit.txt"]["patch"]
    assert by_path["added.txt"]["status"] == "A"
    assert "hello" in by_path["added.txt"]["patch"]
    assert by_path["gone.txt"]["status"] == "D"
    assert details["stats"]["files"] >= 3


def test_detailed_changes_local_snapshot(tmp_path):
    root = tmp_path / "local"
    root.mkdir()
    (root / "a.txt").write_text("one\n", encoding="utf-8")
    (root / "b.txt").write_text("stay\n", encoding="utf-8")
    before = workspace.file_snapshot(root)
    before_texts = workspace.text_snapshot(root, before)

    (root / "a.txt").write_text("two\n", encoding="utf-8")
    (root / "c.txt").write_text("new\n", encoding="utf-8")
    (root / "b.txt").unlink()
    (root / ".orchestrator-task.md").write_text("skip\n", encoding="utf-8")

    details = workspace.detailed_changes(
        root, "", before=before, before_texts=before_texts
    )
    by_path = {f["path"]: f for f in details["files"]}
    assert "a.txt" in by_path and by_path["a.txt"]["status"] == "M"
    assert "one" in by_path["a.txt"]["patch"]
    assert "two" in by_path["a.txt"]["patch"]
    assert by_path["c.txt"]["status"] == "A"
    assert by_path["b.txt"]["status"] == "D"
    assert ".orchestrator-task.md" not in by_path


def test_reply_changes_includes_patch_excerpt(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    from orchestrator import config

    config.settings.reload()
    db.initialize()
    tasks.create_task("changehist0001", "web:owner", "lifeos", "edit files")
    details = {
        "files": [
            {
                "path": "app.py",
                "status": "M",
                "additions": 1,
                "deletions": 1,
                "patch": "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n",
            }
        ],
        "stats": {"files": 1, "additions": 1, "deletions": 1},
        "truncated": False,
    }
    tasks.update_task("changehist0001", status="running", execution_stage="agent_running")
    tasks.update_task(
        "changehist0001",
        status="review",
        execution_stage="ready_for_review",
        modified_files=["app.py"],
        change_details=details,
        summary="Agent: done",
    )
    task = tasks.get_task("changehist0001")
    text = progress.reply_changes(task)
    assert "Patch excerpts" in text
    assert "app.py" in text
    assert "+new" in text
    assert "Review changes" in text or "webchat" in text.lower()


def _web_client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("RESTART_REQUEST_FILE", str(tmp_path / "restart.request"))
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
    from orchestrator import webchat

    webchat._failures.clear()
    return TestClient(app.app)


def test_changes_api_returns_stored_details(tmp_path, monkeypatch):
    client = _web_client(monkeypatch, tmp_path)
    assert client.post("/chat/login", json={"password": PASSWORD}).status_code == 200

    details = {
        "files": [
            {
                "path": "x.py",
                "status": "A",
                "additions": 1,
                "deletions": 0,
                "patch": "+++ b/x.py\n+hi\n",
            }
        ],
        "stats": {"files": 1, "additions": 1, "deletions": 0},
        "truncated": False,
    }
    tasks.create_task("changehist0002", "web:owner", "lifeos", "add x")
    tasks.update_task("changehist0002", status="running")
    tasks.update_task(
        "changehist0002",
        status="review",
        execution_stage="ready_for_review",
        modified_files=["x.py"],
        change_details=details,
    )

    unauth = TestClient(client.app)
    assert unauth.get("/chat/tasks/changehist0002/changes").status_code == 401

    resp = client.get("/chat/tasks/changehist0002/changes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["source"] == "stored"
    assert body["files"][0]["path"] == "x.py"
    assert body["stats"]["additions"] == 1

    # Wrong sender → 404
    tasks.create_task("changehist0003", "web:other", "lifeos", "secret")
    tasks.update_task("changehist0003", status="running")
    tasks.update_task(
        "changehist0003",
        status="review",
        change_details=details,
    )
    assert client.get("/chat/tasks/changehist0003/changes").status_code == 404
    assert client.get("/chat/tasks/missingmissing/changes").status_code == 404


def test_change_details_json_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    from orchestrator import config

    config.settings.reload()
    db.initialize()
    tasks.create_task("changehist0004", "web:owner", "lifeos", "roundtrip")
    payload = {
        "files": [{"path": "y.py", "status": "M", "additions": 2, "deletions": 1, "patch": "+a\n"}],
        "stats": {"files": 1, "additions": 2, "deletions": 1},
        "truncated": True,
    }
    tasks.update_task("changehist0004", change_details=payload)
    row = tasks.get_task("changehist0004")
    assert isinstance(row["change_details"], str)
    assert json.loads(row["change_details"])["truncated"] is True
    parsed = progress.parse_change_details(row)
    assert parsed["stats"]["additions"] == 2
