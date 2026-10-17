from pathlib import Path

from orchestrator.publish import apply_to_local, _commit_workspace


def _git(cwd: Path, *args: str):
    from orchestrator.process import run

    r = run(["git", *args], cwd=cwd, timeout=30)
    assert r.returncode == 0, r.stderr
    return r


def test_apply_to_local_fast_forwards(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    from orchestrator import config

    config.settings.reload()
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.txt").write_text("v1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    _git(repo, "branch", "-M", "master")

    # Simulate orchestrator worktree branch tip as a second commit on a branch
    _git(repo, "checkout", "-b", "wa/abc123def456")
    (repo / "app.txt").write_text("v2\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "task change")
    _git(repo, "checkout", "master")

    task = {
        "id": "abc123def456",
        "branch": "wa/abc123def456",
        "workspace": str(repo),
    }
    msg = apply_to_local(task, {"path": str(repo)})
    assert "fast-forwarded" in msg or "merged" in msg
    assert (repo / "app.txt").read_text(encoding="utf-8") == "v2\n"


def test_commit_workspace_idempotent(tmp_path: Path):
    repo = tmp_path / "wt"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "f.txt").write_text("a\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    (repo / "f.txt").write_text("b\n", encoding="utf-8")
    task = {"id": "deadbeef0001", "branch": "wa/x", "workspace": str(repo)}
    sha1 = _commit_workspace(task, repo)
    sha2 = _commit_workspace(task, repo)
    assert sha1 == sha2
