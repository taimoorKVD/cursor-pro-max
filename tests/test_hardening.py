"""Production hardening: stream evidence, snapshots, process-tree cancel, env scrub."""
from __future__ import annotations

import os

from orchestrator.agent_stream import StreamEvidence, parse_line, stage_from_evidence
from orchestrator import agent as agent_mod
from orchestrator import workspace


def test_stream_json_tool_write_advances_implementing():
    ev = StreamEvidence()
    parsed = parse_line(
        '{"type":"tool_call","name":"Write","arguments":{"path":"resources/css/app.css"}}',
        ev,
    )
    assert parsed and parsed["kind"] == "tool"
    assert ev.saw_write
    assert stage_from_evidence(ev) == "implementing"


def test_stream_json_read_tool_advances_investigating():
    ev = StreamEvidence()
    parse_line('{"type":"tool_call","name":"Read","path":"resources/views/auth/login.blade.php"}', ev)
    assert stage_from_evidence(ev) == "investigating"


def test_cursor_read_tool_call_shape():
    """Real Cursor CLI: tool_call.readToolCall.args.path"""
    ev = StreamEvidence()
    line = (
        '{"type":"tool_call","subtype":"started","call_id":"x",'
        '"tool_call":{"readToolCall":{"args":{"path":"README.md"}}}}'
    )
    parsed = parse_line(line, ev)
    assert parsed and parsed["kind"] == "tool"
    assert parsed["tool"] == "Read"
    assert parsed["path"] == "README.md"
    assert "README.md" in parsed["message"]
    assert ev.saw_read
    assert stage_from_evidence(ev) == "investigating"


def test_cursor_write_tool_call_shape():
    ev = StreamEvidence()
    line = (
        '{"type":"tool_call","subtype":"started","call_id":"y",'
        '"tool_call":{"writeToolCall":{"args":{"path":"summary.txt","fileText":"hi"}}}}'
    )
    parsed = parse_line(line, ev)
    assert parsed and parsed["write"] is True
    assert parsed["tool"] == "Write"
    assert parsed["path"] == "summary.txt"
    assert stage_from_evidence(ev) == "implementing"


def test_cursor_edit_tool_call_shape():
    ev = StreamEvidence()
    line = (
        '{"type":"tool_call","subtype":"started","call_id":"z",'
        '"tool_call":{"editToolCall":{"args":{"path":"app.css"}}}}'
    )
    parsed = parse_line(line, ev)
    assert parsed and parsed["write"] is True
    assert stage_from_evidence(ev) == "implementing"


def test_cursor_completed_tool_is_silent():
    """Completion echoes must not spam the progress log."""
    ev = StreamEvidence()
    started = (
        '{"type":"tool_call","subtype":"started","call_id":"x",'
        '"tool_call":{"grepToolCall":{"args":{"pattern":"dark"}}}}'
    )
    completed = (
        '{"type":"tool_call","subtype":"completed","call_id":"x",'
        '"tool_call":{"grepToolCall":{"args":{"pattern":"dark"},"result":{"success":{}}}}}'
    )
    assert parse_line(started, ev) is not None
    assert parse_line(completed, ev) is None
    assert stage_from_evidence(ev) == "investigating"


def test_cursor_assistant_message_surfaces():
    ev = StreamEvidence()
    line = (
        '{"type":"assistant","message":{"role":"assistant",'
        '"content":[{"type":"text","text":"I will inspect the auth layouts next."}]}}'
    )
    parsed = parse_line(line, ev)
    assert parsed and parsed["kind"] == "assistant"
    assert "auth layouts" in parsed["message"]
    assert stage_from_evidence(ev) is None  # text alone does not advance stage


def test_no_stage_without_tool_evidence():
    ev = StreamEvidence()
    parse_line('{"type":"assistant","content":"Looking into the theme toggle"}', ev)
    assert stage_from_evidence(ev) is None


def test_local_snapshot_diff_detects_content_change(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    f = root / "a.txt"
    f.write_text("one", encoding="utf-8")
    before = workspace.file_snapshot(root)
    f.write_text("two", encoding="utf-8")
    (root / "b.txt").write_text("new", encoding="utf-8")
    changed = workspace.diff_snapshots(before, workspace.file_snapshot(root))
    assert "a.txt" in changed
    assert "b.txt" in changed


def test_agent_env_strips_orchestrator_secrets(monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "secret-meta")
    monkeypatch.setenv("GROQ_API_KEY", "secret-groq")
    monkeypatch.setenv("SMTP_PASSWORD", "secret-smtp")
    monkeypatch.setenv("WEBCHAT_PASSWORD", "secret-web")
    monkeypatch.setenv("CURSOR_API_KEY", "cursor-key")
    from orchestrator import config

    config.settings.reload()
    env = agent_mod._agent_env()
    assert env.get("CURSOR_API_KEY") == "cursor-key"
    assert "META_ACCESS_TOKEN" not in env
    assert "GROQ_API_KEY" not in env
    assert "SMTP_PASSWORD" not in env
    assert "WEBCHAT_PASSWORD" not in env
    assert env.get("__ORCH_MERGE__") == "0"


def test_kill_process_tree_noop_safe():
    from orchestrator.process import kill_process_tree

    kill_process_tree(None)
    kill_process_tree(0)


def test_completed_and_remaining_shows_investigating_label():
    from orchestrator import task_events

    done, rem, label = task_events.completed_and_remaining("investigating", "running")
    assert label == "Investigating codebase"
    assert "Preparing isolated workspace" in done
    assert any("test" in x.lower() or "review" in x.lower() for x in rem)


def test_empty_output_recovers_from_stream_write_evidence(tmp_path):
    ev = StreamEvidence()
    ev.saw_write = True
    ev.files_touched = ["app/Http/Controllers/Auth/AuthController.php"]
    ev.tool_calls = ["Write:app/Http/Controllers/Auth/AuthController.php"]
    text = agent_mod._summary_from_evidence(tmp_path, ev)
    assert "AuthController.php" in text
    assert "CLI printed no summary" in text


def test_empty_output_recovers_from_git_status(tmp_path):
    from orchestrator.process import run

    repo = tmp_path / "repo"
    repo.mkdir()
    run(["git", "init"], cwd=str(repo), timeout=30)
    run(["git", "-C", str(repo), "config", "user.email", "t@example.com"], timeout=15)
    run(["git", "-C", str(repo), "config", "user.name", "T"], timeout=15)
    (repo / "a.txt").write_text("one", encoding="utf-8")
    run(["git", "-C", str(repo), "add", "."], timeout=30)
    run(["git", "-C", str(repo), "commit", "-m", "init"], timeout=30)
    (repo / "a.txt").write_text("two", encoding="utf-8")
    text = agent_mod._summary_from_workspace_changes(repo)
    assert "a.txt" in text


def test_usable_agent_text_prefers_stream_result():
    ev = StreamEvidence()
    ev.result_text = "Remember-me cookie wired for 30 days."
    assert "30 days" in agent_mod._usable_agent_text("{ndjson}", "", ev)


def test_run_agent_recovers_blank_stdout_via_stream_evidence(tmp_path, monkeypatch):
    """Exit 0 + blank stdout still succeeds when stream evidence shows writes."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "hello.txt").write_text("hi", encoding="utf-8")

    class FakeResult:
        def __init__(self, code=0, stdout="", stderr=""):
            self.returncode = code
            self.stdout = stdout
            self.stderr = stderr

    calls = {"n": 0}

    def fake_tracked(*_a, **_k):
        calls["n"] += 1
        return FakeResult(0, "", "")

    monkeypatch.setattr(agent_mod, "ensure_auth", lambda force_login=False: (True, "ok"))
    monkeypatch.setattr(agent_mod, "build_argv", lambda _w: ["agent", "-p"])
    from orchestrator import process as process_mod

    monkeypatch.setattr(process_mod, "run_tracked", fake_tracked)

    ev = StreamEvidence()
    ev.saw_write = True
    ev.files_touched = ["hello.txt"]
    summary, code = agent_mod.run_agent(
        "USER TASK\nappend NOTE=ok",
        ws,
        task_id="emptyretry0001",
        evidence=ev,
    )
    assert code == 0
    assert "hello.txt" in summary
    assert calls["n"] == 1


def test_run_agent_retries_once_when_still_blank(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()

    class FakeResult:
        def __init__(self, code=0, stdout="", stderr=""):
            self.returncode = code
            self.stdout = stdout
            self.stderr = stderr

    calls = {"n": 0}
    ev = StreamEvidence()

    def fake_tracked(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 2:
            ev.saw_write = True
            ev.files_touched = ["note.txt"]
        return FakeResult(0, "", "")

    monkeypatch.setattr(agent_mod, "ensure_auth", lambda force_login=False: (True, "ok"))
    monkeypatch.setattr(agent_mod, "build_argv", lambda _w: ["agent", "-p"])
    from orchestrator import process as process_mod

    monkeypatch.setattr(process_mod, "run_tracked", fake_tracked)

    summary, code = agent_mod.run_agent(
        "USER TASK\nwrite note",
        ws,
        task_id="emptyretry0002",
        evidence=ev,
    )
    assert code == 0
    assert calls["n"] == 2
    assert "note.txt" in summary
