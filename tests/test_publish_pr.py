from pathlib import Path
from types import SimpleNamespace

from orchestrator.publish import (
    _create_pull_request,
    _github_owner_repo,
    _pr_body,
    publish,
)


def test_github_owner_repo_ssh_and_https():
    assert _github_owner_repo("git@github.com:acme/lifeos.git") == ("acme", "lifeos")
    assert _github_owner_repo("https://github.com/acme/lifeos.git") == ("acme", "lifeos")
    assert _github_owner_repo("https://gitlab.com/acme/lifeos.git") is None


def test_pr_body_includes_instruction_and_test_plan():
    body = _pr_body(
        {
            "id": "abcdef123456",
            "project": "lifeos",
            "branch": "wa/abcdef123456",
            "instruction": "Add CRM field",
            "summary": "Changed Form.tsx\nTests: ok",
        }
    )
    assert "Add CRM field" in body
    assert "abcdef123456" in body
    assert "Test plan" in body
    assert "Changed Form.tsx" in body


def test_create_pull_request_uses_gh(monkeypatch, tmp_path: Path):
    calls: list[list[str]] = []

    def fake_run(argv, cwd=None, timeout=None, env=None):
        calls.append(list(argv))
        if argv[:3] == ["gh", "pr", "create"]:
            return SimpleNamespace(
                returncode=0,
                stdout="https://github.com/acme/lifeos/pull/42\n",
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("orchestrator.publish.run", fake_run)
    msg = _create_pull_request(
        {
            "id": "abcdef123456",
            "branch": "wa/abcdef123456",
            "instruction": "Fix login",
            "summary": "notes",
            "project": "lifeos",
        },
        tmp_path,
        {"default_branch": "master"},
    )
    assert "pull/42" in msg
    assert calls[0][:3] == ["gh", "pr", "create"]
    assert "--base" in calls[0] and "master" in calls[0]
    assert "--head" in calls[0] and "wa/abcdef123456" in calls[0]


def test_publish_pr_action(monkeypatch, tmp_path: Path):
    repo = tmp_path / "wt"
    repo.mkdir()
    from orchestrator.process import run as real_run

    def _git(*args: str):
        r = real_run(["git", *args], cwd=repo, timeout=30)
        assert r.returncode == 0, r.stderr

    _git("init")
    _git("config", "user.email", "t@example.com")
    _git("config", "user.name", "Test")
    (repo / "a.txt").write_text("1\n", encoding="utf-8")
    _git("add", "-A")
    _git("commit", "-m", "init")
    _git("checkout", "-b", "wa/deadbeef0001")
    (repo / "a.txt").write_text("2\n", encoding="utf-8")

    task = {
        "id": "deadbeef0001",
        "sender": "web:owner",
        "project": "lifeos",
        "branch": "wa/deadbeef0001",
        "workspace": str(repo),
        "instruction": "Bump file",
        "summary": "ready",
        "content_digest": "digest1",
        "status": "review",
    }
    updates: list[dict] = []

    monkeypatch.setattr(
        "orchestrator.publish.tasks.update_task",
        lambda tid, **kw: updates.append(kw),
    )
    monkeypatch.setattr("orchestrator.publish.audit.record", lambda *a, **k: None)
    monkeypatch.setattr("orchestrator.publish.send_text", lambda *a, **k: None)
    monkeypatch.setattr(
        "orchestrator.publish.workspace.content_digest",
        lambda *a, **k: "digest1",
    )

    def fake_run(argv, cwd=None, timeout=None, env=None):
        if argv[:2] == ["git", "push"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[:2] == ["git", "remote"]:
            return SimpleNamespace(
                returncode=0,
                stdout="https://github.com/acme/lifeos.git\n",
                stderr="",
            )
        if argv[:3] == ["gh", "pr", "create"]:
            return SimpleNamespace(
                returncode=0,
                stdout="https://github.com/acme/lifeos/pull/7\n",
                stderr="",
            )
        return real_run(argv, cwd=cwd, timeout=timeout)

    monkeypatch.setattr("orchestrator.publish.run", fake_run)

    publish(
        task,
        {
            "type": "git",
            "path": str(repo),
            "allow_push": True,
            "apply_local": False,
            "default_branch": "master",
        },
        "PR",
    )
    assert any(u.get("status") == "published" for u in updates)
    assert any("Pull request created" in (u.get("summary") or "") for u in updates)
