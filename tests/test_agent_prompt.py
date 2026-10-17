from pathlib import Path
import subprocess

from orchestrator.agent import CLI_POINTER, TASK_FILE, build_prompt, build_argv, run_agent


def test_build_prompt_leads_with_task():
    prompt = build_prompt("yes, remove the welcome back text from the login page")
    assert prompt.startswith("USER TASK")
    assert "remove the welcome back text from the login page" in prompt
    assert "yes, remove" not in prompt.lower()
    assert "CONSTRAINTS" in prompt


def test_build_argv_uses_short_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "orchestrator.agent.resolve_agent_argv",
        lambda: ["agent"],
    )
    monkeypatch.setenv("AGENT_SANDBOX", "disabled")
    from orchestrator import config

    config.settings.reload()
    argv = build_argv(tmp_path)
    assert "-p" in argv
    assert "--workspace" in argv
    assert "--output-format" in argv
    assert "stream-json" in argv
    assert "--stream-partial-output" in argv
    assert argv[-1] == CLI_POINTER
    assert TASK_FILE in argv[-1]
    # Full task text must never appear as a CLI arg.
    assert "welcome back" not in " ".join(argv)


def test_run_agent_recovers_empty_output_when_files_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "orchestrator.agent.resolve_agent_argv",
        lambda: ["agent"],
    )
    monkeypatch.setenv("AGENT_SANDBOX", "disabled")
    from orchestrator import config

    config.settings.reload()

    # Fake a git worktree with a real edit and blank CLI stdout.
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    target = tmp_path / "resources" / "views" / "auth"
    target.mkdir(parents=True)
    login = target / "login.blade.php"
    login.write_text("old\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    login.write_text("new\n", encoding="utf-8")

    def fake_run(argv, cwd=None, timeout=600, input_text=None, env=None):
        if argv[:2] == ["git", "-C"]:
            from orchestrator.process import run as real_run

            return real_run(argv, cwd=cwd, timeout=timeout, input_text=input_text)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr("orchestrator.agent.run", fake_run)
    text, code = run_agent(build_prompt("remove theme toggle"), tmp_path)
    assert code == 0
    assert "Detected workspace changes" in text
    assert "login.blade.php" in text
