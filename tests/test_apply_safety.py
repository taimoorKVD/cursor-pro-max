"""Local apply keeps a backup and aborts a conflicted merge."""
from __future__ import annotations

from pathlib import Path

from orchestrator import config
from orchestrator.process import run
from orchestrator.publish import apply_to_local, publish


def _git(cwd: Path, *args: str):
    result = run(["git", *args], cwd=cwd, timeout=30)
    assert result.returncode == 0, result.stderr
    return result


def _repo(path: Path) -> None:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "app.txt").write_text("base\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-m", "init")
    _git(path, "branch", "-M", "master")


def test_dirty_destination_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    config.settings.reload()
    repo = tmp_path / "repo"
    _repo(repo)
    (repo / "app.txt").write_text("dirty\n", encoding="utf-8")
    before = (repo / "app.txt").read_bytes()
    try:
        apply_to_local(
            {"id": "dirty0000001", "branch": "master", "workspace": str(repo)},
            {"path": str(repo)},
        )
        raised = False
    except ValueError as exc:
        raised = True
        assert "uncommitted" in str(exc).lower()
    assert raised
    assert (repo / "app.txt").read_bytes() == before
    assert not (config.WORK_ROOT / "backups" / "dirty0000001" / "pre-apply.bundle").exists()


def test_conflict_aborts_and_keeps_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    config.settings.reload()
    repo = tmp_path / "repo"
    _repo(repo)
    _git(repo, "checkout", "-b", "wa/conflict0001")
    (repo / "app.txt").write_text("from-branch\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "branch")
    _git(repo, "checkout", "master")
    (repo / "app.txt").write_text("from-master\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "local")
    before = (repo / "app.txt").read_bytes()
    try:
        apply_to_local(
            {"id": "conflict0001", "branch": "wa/conflict0001", "workspace": str(repo)},
            {"path": str(repo)},
        )
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    assert (repo / "app.txt").read_bytes() == before
    assert not (repo / ".git" / "MERGE_HEAD").exists()
    bundle = config.WORK_ROOT / "backups" / "conflict0001" / "pre-apply.bundle"
    assert bundle.is_file()
    assert bundle.stat().st_size > 0


def test_pr_apply_local_false_does_not_change_destination(tmp_path, monkeypatch):
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    config.settings.reload()
    dest = tmp_path / "dest"
    _repo(dest)
    before = (dest / "app.txt").read_bytes()
    work = tmp_path / "wt"
    _repo(work)
    _git(work, "checkout", "-b", "wa/applyoff0001")
    (work / "app.txt").write_text("agent\n", encoding="utf-8")
    from orchestrator import workspace

    digest = workspace.content_digest(work, "wa/applyoff0001")
    updates: list[dict] = []
    monkeypatch.setattr(
        "orchestrator.publish.tasks.update_task",
        lambda tid, **kw: updates.append(kw),
    )
    monkeypatch.setattr("orchestrator.publish.audit.record", lambda *a, **k: None)
    monkeypatch.setattr("orchestrator.publish.send_text", lambda *a, **k: None)

    def fake_run(argv, cwd=None, timeout=None, env=None):
        if argv[:2] == ["git", "push"] or argv[:2] == ["gh", "pr"]:
            from types import SimpleNamespace

            return SimpleNamespace(returncode=0, stdout="https://github.com/acme/app/pull/1\n", stderr="")
        if argv[:2] == ["git", "remote"]:
            from types import SimpleNamespace

            return SimpleNamespace(returncode=0, stdout="https://github.com/acme/app.git\n", stderr="")
        if argv[:2] == ["git", "ls-remote"]:
            from types import SimpleNamespace

            return SimpleNamespace(returncode=1, stdout="", stderr="no origin")
        return run(argv, cwd=cwd, timeout=timeout)

    monkeypatch.setattr("orchestrator.publish.run", fake_run)
    publish(
        {
            "id": "applyoff0001",
            "sender": "web:owner",
            "project": "demo",
            "branch": "wa/applyoff0001",
            "workspace": str(work),
            "instruction": "edit",
            "summary": "ready",
            "content_digest": digest,
        },
        {
            "type": "git",
            "path": str(dest),
            "allow_push": True,
            "apply_local": False,
            "default_branch": "master",
        },
        "PR",
    )
    assert (dest / "app.txt").read_bytes() == before
    assert any(u.get("status") == "published" for u in updates)
