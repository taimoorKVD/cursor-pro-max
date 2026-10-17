"""Agent and publish environments must not carry application secrets."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from orchestrator import config, isolation


def test_agent_env_drops_application_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("META_ACCESS_TOKEN", "meta-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "gh-secret")
    monkeypatch.setenv("GH_TOKEN", "gh-secret-2")
    monkeypatch.setenv("WEBCHAT_PASSWORD", "web-secret")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setattr(config.settings, "CURSOR_API_KEY", "cursor-secret")
    env = isolation.agent_env(tmp_path)
    blob = " ".join(f"{k}={v}" for k, v in env.items())
    for secret in ("meta-secret", "gh-secret", "gh-secret-2", "web-secret", "smtp-secret"):
        assert secret not in blob
    assert "META_ACCESS_TOKEN" not in env
    assert "GITHUB_TOKEN" not in env
    assert "WEBCHAT_PASSWORD" not in env
    assert "SMTP_PASSWORD" not in env
    assert env.get("CURSOR_API_KEY") == "cursor-secret"
    assert env.get("__ORCH_MERGE__") == "0"
    assert "--api-key" not in blob


def test_publish_env_keeps_profile_and_drops_tokens(monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "meta-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "gh-secret")
    monkeypatch.setenv("GH_TOKEN", "gh-secret-2")
    monkeypatch.setenv("WEBCHAT_PASSWORD", "web-secret")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setenv("CURSOR_API_KEY", "cursor-secret")
    monkeypatch.setenv("USERPROFILE", os.environ.get("USERPROFILE", r"C:\Users\orch"))
    env = isolation.publish_env()
    blob = " ".join(env.values())
    for secret in ("meta-secret", "gh-secret", "web-secret", "smtp-secret", "cursor-secret"):
        assert secret not in blob
    assert "META_ACCESS_TOKEN" not in env
    assert "GITHUB_TOKEN" not in env
    assert "GH_TOKEN" not in env
    assert "WEBCHAT_PASSWORD" not in env
    assert "SMTP_PASSWORD" not in env
    assert "CURSOR_API_KEY" not in env
    assert env.get("USERPROFILE")


def test_live_agent_refused_without_windows_boundary(monkeypatch):
    monkeypatch.setattr(isolation, "break_glass", lambda: False)
    monkeypatch.setattr(isolation, "boundary_status", lambda: "unavailable")
    monkeypatch.setattr(isolation.os, "name", "nt")
    allowed, detail = isolation.live_agent_allowed()
    assert allowed is False
    assert "AGENT_ISOLATION_BREAK_GLASS" in detail


def test_break_glass_allows_live_agent(monkeypatch):
    monkeypatch.setattr(isolation, "break_glass", lambda: True)
    allowed, detail = isolation.live_agent_allowed()
    assert allowed is True
    assert "BREAK_GLASS" in detail


@pytest.mark.skipif(os.name != "nt", reason="AppContainer is Windows-only")
def test_windows_container_denies_outside_read(tmp_path):
    from orchestrator import win_boundary

    secret = tmp_path / "secret.txt"
    secret.write_text("token=supersecret\n", encoding="utf-8")
    result = win_boundary.probe(secret, tmp_path / "ws")
    assert result == "denied"


@pytest.mark.skipif(os.name != "nt", reason="AppContainer is Windows-only")
def test_windows_agent_argv_skips_node_realpath_on_drive_root():
    """Drive-root ACL grants are denied; Node must boot without realpathSync(C:\\)."""
    from orchestrator import agent

    argv = agent.resolve_agent_argv()
    assert any(Path(p).name.lower() == "node.exe" for p in argv), argv
    assert "--preserve-symlinks" in argv
    assert "--preserve-symlinks-main" in argv


@pytest.mark.skipif(os.name != "nt", reason="AppContainer is Windows-only")
def test_windows_container_can_boot_node_on_c_drive(tmp_path):
    """Contained node must start a main module under C:\\…\\cursor-agent without EPERM."""
    import uuid

    from orchestrator import agent, win_boundary

    argv = agent.resolve_agent_argv()
    node = next((Path(p) for p in argv if Path(p).name.lower() == "node.exe"), None)
    if node is None:
        pytest.skip("resolved agent entry is not node.exe + index.js")
    ws = tmp_path / "ws"
    ws.mkdir()
    # Unique name under the granted runtime dir (avoids races with cleanup of fixed names).
    probe = node.parent / f"_orch_boot_probe_{uuid.uuid4().hex}.js"
    probe.write_text("console.log('boot-ok');\n", encoding="utf-8")
    assert probe.is_file()
    read_paths = [node.parent]
    for parent in node.parents:
        if parent.name.lower() == "cursor-agent":
            read_paths.append(parent)
            break
    try:
        proc = win_boundary.popen(
            [
                str(node),
                "--preserve-symlinks",
                "--preserve-symlinks-main",
                str(probe),
            ],
            cwd=ws,
            env={"PATH": str(node.parent)},
            read_paths=read_paths,
            write_paths=[ws],
        )
        code = proc.wait(timeout=30)
        out = (proc.stdout.read() if proc.stdout else "").strip()
        err = (proc.stderr.read() if proc.stderr else "").strip()
    finally:
        probe.unlink(missing_ok=True)
    assert code == 0, f"boot failed exit={code} out={out!r} err={err!r}"
    assert "boot-ok" in out
    assert "EPERM" not in err
