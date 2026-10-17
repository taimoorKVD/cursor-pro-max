"""Workspace collision recovery and clear-chat cleanup."""
from __future__ import annotations

from pathlib import Path

from orchestrator import config, db, retention, tasks, workspace
from orchestrator.process import run


def test_setup_replaces_stale_local_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    config.settings.reload()
    db.initialize()

    src = tmp_path / "proj"
    src.mkdir()
    (src / "a.txt").write_text("one", encoding="utf-8")
    cfg = {"path": str(src), "type": "local"}

    first, branch = workspace.setup("aabbccddeeff", cfg)
    assert first.exists()
    assert branch == ""
    (first / "a.txt").write_text("dirty", encoding="utf-8")

    # Collision path: same task id leftover must be cleared, not fail.
    second, _ = workspace.setup("aabbccddeeff", cfg)
    assert second.exists()
    assert (second / "a.txt").read_text(encoding="utf-8") == "one"


def test_setup_replaces_stale_git_worktree(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    config.settings.reload()
    db.initialize()

    src = tmp_path / "repo"
    src.mkdir()
    run(["git", "init"], cwd=str(src), timeout=30)
    run(["git", "-C", str(src), "config", "user.email", "test@example.com"], timeout=15)
    run(["git", "-C", str(src), "config", "user.name", "Test"], timeout=15)
    (src / "readme.md").write_text("hi", encoding="utf-8")
    run(["git", "-C", str(src), "add", "."], timeout=30)
    run(["git", "-C", str(src), "commit", "-m", "init"], timeout=30)

    cfg = {"path": str(src), "type": "git"}
    target, branch = workspace.setup("gitworktree01", cfg)
    assert target.exists()
    assert branch == "wa/gitworktree01"

    again, branch2 = workspace.setup("gitworktree01", cfg)
    assert again.exists()
    assert branch2 == "wa/gitworktree01"
    assert not (Path(config.WORK_ROOT) / "gitworktree01" / "missing").exists()


def test_setup_allows_dirty_git_source_without_touching_wip(tmp_path, monkeypatch):
    """Operator WIP stays in the main tree; worktree is a clean checkout of HEAD."""
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    config.settings.reload()
    db.initialize()

    src = tmp_path / "repo"
    src.mkdir()
    run(["git", "init"], cwd=str(src), timeout=30)
    run(["git", "-C", str(src), "config", "user.email", "test@example.com"], timeout=15)
    run(["git", "-C", str(src), "config", "user.name", "Test"], timeout=15)
    (src / "readme.md").write_text("hi", encoding="utf-8")
    run(["git", "-C", str(src), "add", "."], timeout=30)
    run(["git", "-C", str(src), "commit", "-m", "init"], timeout=30)
    (src / "wip.txt").write_text("local edits", encoding="utf-8")
    (src / "readme.md").write_text("hi dirty", encoding="utf-8")

    from orchestrator import preflight

    ok, reason = preflight.project_ready("demo", {"path": str(src), "type": "git"})
    assert ok is True, reason

    target, branch = workspace.setup(
        "dirtyok000001", {"path": str(src), "type": "git"}
    )
    assert target.exists()
    assert branch == "wa/dirtyok000001"
    # Source WIP must remain (critical for self-improving this orchestrator).
    status = run(["git", "-C", str(src), "status", "--porcelain"], timeout=30)
    assert status.returncode == 0
    assert "readme.md" in status.stdout
    assert "wip.txt" in status.stdout
    assert (src / "readme.md").read_text(encoding="utf-8") == "hi dirty"
    assert (src / "wip.txt").read_text(encoding="utf-8") == "local edits"
    # Worktree is based on clean HEAD.
    assert (target / "readme.md").read_text(encoding="utf-8") == "hi"
    assert not (target / "wip.txt").exists()


def test_remove_quarantines_when_rmtree_blocked(tmp_path, monkeypatch):
    """Locked dirs are renamed aside so the next setup is not a collision."""
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    config.settings.reload()
    db.initialize()

    root = Path(config.WORK_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    stuck = root / "lockedtask0001"
    stuck.mkdir()
    (stuck / "hold.txt").write_text("x", encoding="utf-8")

    def _boom(_path):
        raise OSError("sharing violation")

    monkeypatch.setattr(workspace, "_rmtree_windows_safe", _boom)
    assert workspace.remove(stuck) is True
    assert not stuck.exists()
    trash = list(root.glob(".trash-lockedtask0001-*"))
    # Trash may already be gone if a later delete succeeded; path must be free.
    assert not stuck.exists()
    assert trash == [] or all(p.name.startswith(".trash-") for p in trash)


def test_setup_succeeds_after_quarantine(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    config.settings.reload()
    db.initialize()

    src = tmp_path / "proj"
    src.mkdir()
    (src / "a.txt").write_text("one", encoding="utf-8")
    cfg = {"path": str(src), "type": "local"}
    first, _ = workspace.setup("quarantine0001", cfg)
    assert first.exists()

    calls = {"n": 0}

    def _boom(_path):
        calls["n"] += 1
        raise OSError("locked")

    monkeypatch.setattr(workspace, "_rmtree_windows_safe", _boom)
    # remove() quarantines; setup must still recreate the canonical path.
    second, _ = workspace.setup("quarantine0001", cfg)
    assert second.exists()
    assert (second / "a.txt").read_text(encoding="utf-8") == "one"
    assert calls["n"] >= 1


def test_clear_sender_workspaces_removes_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    config.settings.reload()
    db.initialize()

    src = tmp_path / "lifeos"
    src.mkdir()
    (src / "x.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        "orchestrator.retention.projects.projects",
        lambda: {"lifeos": {"path": str(src), "type": "local"}},
    )

    tasks.create_task("clearme000001", "web:owner", "lifeos", "do stuff")
    target, _ = workspace.setup(
        "clearme000001",
        {"path": str(src), "type": "local"},
    )
    tasks.update_task("clearme000001", workspace=str(target), status="failed")
    assert target.exists()

    result = retention.cleanup_sender_workspaces("web:owner", project="lifeos")
    assert result["removed"] >= 1
    assert not target.exists()
    task = tasks.get_task("clearme000001")
    assert not (task.get("workspace") or "").strip()


def test_clear_dismisses_review_so_progress_goes_idle(tmp_path, monkeypatch):
    """Clear chat must cancel review tasks; progress must not stick to them."""
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    config.settings.reload()
    db.initialize()

    from orchestrator import session, task_events

    tasks.create_task("reviewclear001", "web:owner", "lifeos", "remember me")
    tasks.update_task("reviewclear001", status="running", execution_stage="agent_running")
    tasks.update_task(
        "reviewclear001",
        status="review",
        execution_stage="ready_for_review",
        summary="Agent: done",
    )
    task_events.record("reviewclear001", "agent_stream", "Read: app/login.php")
    session.set_active_task("web:owner", "reviewclear001", project="lifeos")

    assert tasks.active_task_for_sender("web:owner", project="lifeos")["id"] == "reviewclear001"
    assert task_events.list_events("reviewclear001")

    result = retention.cleanup_sender_workspaces("web:owner", project="lifeos")
    assert result["canceled"] >= 1
    session.set_active_task("web:owner", None, project="lifeos")

    task = tasks.get_task("reviewclear001")
    assert task["status"] == "failed"
    assert task["execution_stage"] == "canceled"
    assert tasks.active_task_for_sender("web:owner", project="lifeos") is None
    assert task_events.list_events("reviewclear001") == []
