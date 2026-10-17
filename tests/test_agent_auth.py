from orchestrator import agent, config


def test_auth_status_uses_api_key(monkeypatch):
    monkeypatch.setattr(config.settings, "CURSOR_API_KEY", "test-key")
    monkeypatch.setattr(config.settings, "CURSOR_ACCOUNT_EMAIL", "info@kingdom-vision.com")
    status = agent.auth_status()
    assert status["ok"] is True
    assert status["mode"] == "api-key"


def test_ensure_auth_with_api_key(monkeypatch):
    monkeypatch.setattr(config.settings, "CURSOR_API_KEY", "test-key")
    ok, detail = agent.ensure_auth()
    assert ok is True
    assert "API_KEY" in detail or "api-key" in detail.lower() or "Authenticated" in detail


def test_build_argv_includes_api_key(monkeypatch, tmp_path):
    """The key is an environment credential, never a process argument."""
    monkeypatch.setattr(config.settings, "CURSOR_API_KEY", "secret-key")
    monkeypatch.setattr(agent, "resolve_agent_argv", lambda: ["agent"])
    monkeypatch.setattr(agent, "_effective_sandbox", lambda: "disabled")
    argv = agent.build_argv(tmp_path)
    assert "--api-key" not in argv
    assert "secret-key" not in argv
    assert agent._agent_env().get("CURSOR_API_KEY") == "secret-key"
