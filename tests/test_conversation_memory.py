"""Durable conversation memory survives process restart (in-memory cache wipe)."""
from __future__ import annotations

from orchestrator import config, converse, db


def _simulate_restart() -> None:
    """Drop process-local caches the way a fresh uvicorn worker would."""
    converse._pending.clear()
    converse._memory.clear()


def test_remember_work_survives_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "mem.sqlite"))
    config.settings.reload()
    db.initialize()

    converse.forget_work("web:owner")
    converse.remember_work(
        "web:owner",
        project="lifeos",
        instruction="fix light/dark on login",
        task_id="abc123def456",
    )
    _simulate_restart()

    remembered = converse.last_work("web:owner")
    assert remembered is not None
    assert remembered["project"] == "lifeos"
    assert "light/dark" in remembered["instruction"]
    assert remembered["task_id"] == "abc123def456"


def test_pending_clarification_survives_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "pending.sqlite"))
    config.settings.reload()
    db.initialize()

    converse.clear_pending("tg:42")
    converse.set_pending(
        "tg:42",
        kind="need_project",
        instruction="improve form validation",
    )
    _simulate_restart()

    pending = converse.get_pending("tg:42")
    assert pending is not None
    assert pending["kind"] == "need_project"
    assert "form validation" in (pending.get("instruction") or "")


def test_retry_after_restart_uses_remembered_work(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "retry.sqlite"))
    config.settings.reload()
    db.initialize()

    registry = {"lifeos": {"display_name": "lifeOS", "type": "git"}}
    converse.remember_work(
        "web:owner",
        project="lifeos",
        instruction="fix dark mode on login",
        task_id="deadbeefcafe",
    )
    _simulate_restart()

    intent = converse.parse_intent(
        "yeah let's do it again",
        registry,
        sender="web:owner",
    )
    assert intent.kind == "retry"
    assert intent.project == "lifeos"
    assert "dark mode" in (intent.instruction or "")


def test_clear_conversation_state_forgets_work(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "clear.sqlite"))
    config.settings.reload()
    db.initialize()

    converse.remember_work(
        "web:owner",
        project="lifeos",
        instruction="add remember me",
    )
    converse.set_pending("web:owner", kind="offer_project", project="lifeos")
    converse.clear_conversation_state("web:owner")
    _simulate_restart()

    assert converse.last_work("web:owner") is None
    assert converse.get_pending("web:owner") is None


def test_memory_isolated_by_sender(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "iso.sqlite"))
    config.settings.reload()
    db.initialize()

    converse.remember_work(
        "web:owner",
        project="lifeos",
        instruction="owner only work",
    )
    converse.remember_work(
        "tg:99",
        project="kv-hrms",
        instruction="telegram only work",
    )
    _simulate_restart()

    web = converse.last_work("web:owner")
    tg = converse.last_work("tg:99")
    assert web and web["project"] == "lifeos"
    assert "owner" in web["instruction"]
    assert tg and tg["project"] == "kv-hrms"
    assert "telegram" in tg["instruction"]
