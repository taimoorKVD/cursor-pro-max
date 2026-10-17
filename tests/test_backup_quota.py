"""SQLite backup, log scrubbing, and spend ceilings."""
from __future__ import annotations

import sqlite3

import pytest

from orchestrator import audit, config, db, quotas, tasks
from orchestrator.backup import backup_database, restore_database, verify_database
from orchestrator.scrub import scrub


def _db(tmp_path, monkeypatch, **env: str):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "live.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    config.settings.reload()
    db.initialize()


def test_backup_and_restore_roundtrip(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    tasks.create_task("backup0000001", "web:owner", "demo", "keep me")
    dest = tmp_path / "backups" / "copy.sqlite"
    backup_database(dest)
    assert verify_database(dest)
    restored = tmp_path / "restored.sqlite"
    restore_database(dest, restored)
    conn = sqlite3.connect(restored)
    try:
        row = conn.execute(
            "SELECT instruction FROM tasks WHERE id=?",
            ("backup0000001",),
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "keep me"
    with pytest.raises(RuntimeError, match="live"):
        restore_database(dest, config.DATABASE_FILE)


def test_audit_scrubs_token(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    assert "supersecret" not in scrub("note token=supersecret end")
    audit.record(
        "approve_queued",
        actor="web:owner",
        task_id="audit00000001",
        detail={"action": "PUSH", "digest_prefix": "abcd", "note": "token=supersecret"},
        ok=True,
    )
    with db.DB_LOCK, db.connect() as c:
        row = c.execute(
            "SELECT action, actor, task_id, detail, ok FROM audit_events WHERE task_id=?",
            ("audit00000001",),
        ).fetchone()
    assert row["action"] == "approve_queued"
    assert row["actor"] == "web:owner"
    assert row["ok"] == 1
    assert "supersecret" not in row["detail"]
    assert "abcd" in row["detail"]


def test_task_and_groq_ceilings(tmp_path, monkeypatch):
    _db(
        tmp_path,
        monkeypatch,
        ORCH_QUOTAS="true",
        MAX_TASKS_PER_SENDER_PER_DAY="1",
        MAX_GROQ_CALLS_PER_DAY="1",
        MAX_AGENT_STARTS_PER_DAY="1",
    )
    tasks.create_task("quota00000001", "web:owner", "demo", "first")
    with pytest.raises(quotas.QuotaExceeded, match="task limit"):
        quotas.assert_task_allowed("web:owner")
    quotas.record("groq", "web:owner")
    with pytest.raises(quotas.QuotaExceeded, match="Groq"):
        quotas.assert_groq_allowed()
    quotas.record("cursor_agent", "web:owner")
    with pytest.raises(quotas.QuotaExceeded, match="agent"):
        quotas.assert_agent_allowed()
