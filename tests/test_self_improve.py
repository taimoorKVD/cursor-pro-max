"""Self-improving orchestrator: git apply, resume, restart honesty."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator import config, converse
from orchestrator.agent import build_argv
from orchestrator.agent_stream import StreamEvidence, parse_line
from orchestrator.projects import ProjectConfigError, _validate_one, load_projects


def test_local_apply_local_still_rejected():
    with pytest.raises(ProjectConfigError, match="apply_local"):
        _validate_one(
            "snap",
            {
                "path": "C:/tmp/snap",
                "type": "local",
                "apply_local": True,
                "allow_push": False,
                "allow_deploy": False,
            },
        )


def test_git_apply_local_orchestrator_shape_ok(tmp_path: Path):
    repo = tmp_path / "orch"
    repo.mkdir()
    meta = _validate_one(
        "whatsapp-cursor-orchestrator",
        {
            "path": str(repo),
            "type": "git",
            "apply_local": True,
            "allow_push": False,
            "allow_deploy": False,
            "test_command": "python -m pytest -q",
            "instructions": "self-improve",
        },
    )
    assert meta["type"] == "git"
    assert meta["apply_local"] is True
    assert meta["allow_push"] is False


def test_load_projects_rejects_local_apply(tmp_path: Path):
    projects_file = tmp_path / "projects.json"
    projects_file.write_text(
        '{"bad":{"path":"C:/x","type":"local","apply_local":true,'
        '"allow_push":false,"allow_deploy":false}}',
        encoding="utf-8",
    )
    with pytest.raises(ProjectConfigError, match="apply_local"):
        load_projects(projects_file, strict=True)


def test_build_argv_resume_flag(tmp_path, monkeypatch):
    monkeypatch.setattr("orchestrator.agent.resolve_agent_argv", lambda: ["agent"])
    monkeypatch.setattr("orchestrator.agent._effective_sandbox", lambda: "")
    argv = build_argv(tmp_path, resume_chat_id="sess-abc-123")
    assert any(a.startswith("--resume=sess-abc-123") for a in argv)
    assert "-p" in argv


def test_stream_captures_session_id():
    ev = StreamEvidence()
    parse_line(
        '{"type":"system","subtype":"init","session_id":"0c79b9f5-d4a6-433b-ab10-2212d47390af"}',
        ev,
    )
    assert ev.session_id == "0c79b9f5-d4a6-433b-ab10-2212d47390af"
    parse_line(
        '{"type":"result","subtype":"success","result":"done",'
        '"session_id":"0c79b9f5-d4a6-433b-ab10-2212d47390af"}',
        ev,
    )
    assert ev.session_id == "0c79b9f5-d4a6-433b-ab10-2212d47390af"
    assert "done" in ev.result_text


def test_continue_work_resumes_same_task(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("WEBHOOK_REPLY_ENABLED", "false")
    monkeypatch.setenv("REPLY_LOG_ENABLED", "false")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("GROQ_API_KEY", "")
    config.settings.reload()
    from orchestrator import db, queue, tasks
    from orchestrator.handlers import handle

    db.initialize()
    converse.clear_pending("web:owner")
    replies: list[str] = []
    monkeypatch.setattr(
        "orchestrator.handlers.send_text",
        lambda s, t, **k: replies.append(t),
    )
    monkeypatch.setattr("orchestrator.handlers.llm_chat.understand", lambda *a, **k: None)
    monkeypatch.setattr("orchestrator.handlers.llm_chat.phrase", lambda *a, **k: None)

    ws = tmp_path / "work" / "abc123def456"
    ws.mkdir(parents=True)
    tasks.create_task("abc123def456", "web:owner", "whatsapp-cursor-orchestrator", "fix help text")
    tasks.update_task("abc123def456", status="running", execution_stage="agent_running")
    tasks.update_task(
        "abc123def456",
        status="review",
        execution_stage="ready_for_review",
        workspace=str(ws),
        branch="wa/abc123def456",
        agent_chat_id="chat-session-xyz",
        content_digest="deadbeef",
        revision=1,
    )
    converse.remember_work(
        "web:owner",
        project="whatsapp-cursor-orchestrator",
        instruction="fix help text",
        task_id="abc123def456",
    )

    enqueued: list[tuple] = []
    monkeypatch.setattr(
        "orchestrator.handlers.queue.enqueue",
        lambda tid, kind="execute": enqueued.append((tid, kind)),
    )

    handle("web:owner", "continue working")
    assert enqueued == [("abc123def456", "execute")]
    row = tasks.get_task("abc123def456")
    assert row is not None
    assert row["status"] == "queued"
    assert int(row["revision"]) == 2
    assert row["agent_chat_id"] == "chat-session-xyz"
    assert row["workspace"] == str(ws)
    assert not (row.get("content_digest") or "").strip()
    assert "resume" in replies[-1].lower()


def test_apply_dirty_tree_clear_message(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    config.settings.reload()
    from orchestrator.process import run
    from orchestrator.publish import apply_to_local

    repo = tmp_path / "repo"
    repo.mkdir()

    def _git(*args: str):
        r = run(["git", *args], cwd=repo, timeout=30)
        assert r.returncode == 0, r.stderr
        return r

    _git("init")
    _git("config", "user.email", "t@example.com")
    _git("config", "user.name", "Test")
    (repo / "app.txt").write_text("v1\n", encoding="utf-8")
    _git("add", "-A")
    _git("commit", "-m", "init")
    _git("branch", "-M", "master")
    _git("checkout", "-b", "wa/taskdeadbeef")
    (repo / "app.txt").write_text("v2\n", encoding="utf-8")
    _git("add", "-A")
    _git("commit", "-m", "change")
    _git("checkout", "master")
    (repo / "dirty.txt").write_text("nope\n", encoding="utf-8")

    task = {
        "id": "taskdeadbeef",
        "branch": "wa/taskdeadbeef",
        "workspace": str(repo),
    }
    with pytest.raises(ValueError, match="uncommitted changes"):
        apply_to_local(task, {"path": str(repo)})


def test_publish_apply_mentions_restart_for_orchestrator(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("DEPLOY_ENABLED", "false")
    config.settings.reload()
    from orchestrator import db, tasks
    from orchestrator import publish as pub

    db.initialize()
    replies: list[str] = []
    monkeypatch.setattr(pub, "send_text", lambda s, t, **k: replies.append(t))
    monkeypatch.setattr(pub, "apply_to_local", lambda *a, **k: "Local project fast-forwarded: ok")
    monkeypatch.setattr(pub, "_commit_workspace", lambda *a, **k: "abc1234")
    monkeypatch.setattr(pub, "_head_sha", lambda *a, **k: "abc1234deadbeef")
    monkeypatch.setattr(pub, "_worktree_clean", lambda *a, **k: True)
    monkeypatch.setattr(
        "orchestrator.workspace.content_digest",
        lambda *a, **k: "digest123",
    )
    monkeypatch.setattr(pub, "_is_orchestrator_checkout", lambda *_a, **_k: True)

    ws = tmp_path / "wt"
    ws.mkdir()
    tasks.create_task("aabbccddeeff", "web:owner", "whatsapp-cursor-orchestrator", "tweak")
    tasks.update_task("aabbccddeeff", status="running")
    tasks.update_task(
        "aabbccddeeff",
        status="review",
        workspace=str(ws),
        branch="wa/aabbccddeeff",
        content_digest="digest123",
        approved_sha="abc1234deadbeef",
    )
    assert tasks.claim_publishing("aabbccddeeff")
    task = tasks.get_task("aabbccddeeff")
    assert task
    pub.publish(
        task,
        {
            "path": str(config.BASE),
            "type": "git",
            "apply_local": True,
            "allow_push": False,
        },
        "APPLY",
    )
    assert replies
    assert "restart" in replies[-1].lower()
    done = tasks.get_task("aabbccddeeff")
    assert done and done["status"] == "published"


def test_run_agent_passes_resume(tmp_path, monkeypatch):
    from orchestrator import agent as agent_mod
    from orchestrator.agent_stream import StreamEvidence

    monkeypatch.setattr(config.settings, "CURSOR_API_KEY", "k")
    monkeypatch.setattr(config.settings, "AGENT_OUTPUT_FORMAT", "stream-json")
    monkeypatch.setattr(agent_mod, "ensure_auth", lambda **k: (True, "ok"))
    monkeypatch.setattr(
        "orchestrator.isolation.live_agent_allowed",
        lambda: (True, "ok"),
    )
    monkeypatch.setattr("orchestrator.isolation.use_container", lambda: False)
    monkeypatch.setattr("orchestrator.quotas.assert_agent_allowed", lambda: None)
    monkeypatch.setattr("orchestrator.quotas.record", lambda *_a, **_k: None)

    captured: dict = {}

    def fake_build_argv(workspace, *, resume_chat_id=None, prompt_pointer=None):
        captured["resume"] = resume_chat_id
        captured["pointer"] = prompt_pointer
        return ["agent", "-p", "pointer"]

    monkeypatch.setattr(agent_mod, "build_argv", fake_build_argv)

    def fake_tracked(*_a, **kwargs):
        on_line = kwargs.get("on_stdout_line")
        line = (
            '{"type":"result","subtype":"success","result":"All good",'
            '"session_id":"new-sess"}'
        )
        if on_line:
            on_line(line)
        result = MagicMock()
        result.returncode = 0
        result.stdout = line + "\n"
        result.stderr = ""
        return result

    monkeypatch.setattr("orchestrator.process.run_tracked", fake_tracked)

    ev = StreamEvidence()
    summary, code = agent_mod.run_agent(
        "USER TASK:\nfix it",
        tmp_path,
        task_id="tid123",
        evidence=ev,
        resume_chat_id="old-sess",
    )
    assert code == 0
    assert captured["resume"] == "old-sess"
    assert "follow-up" in (captured["pointer"] or "").lower() or "TASK_FILE" in (
        captured["pointer"] or ""
    ) or ".orchestrator-task.md" in (captured["pointer"] or "")
    assert "All good" in summary
    assert ev.session_id == "new-sess"
