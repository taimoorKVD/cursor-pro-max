"""Token spend capture from Cursor stream-json and sidebar status payload."""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from orchestrator.agent_stream import StreamEvidence, parse_line
from orchestrator import config, db, token_spend


PASSWORD = "correct-horse-battery"


def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "token.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    config.settings.reload()
    db.initialize()


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("RESTART_REQUEST_FILE", str(tmp_path / "restart-orchestrator.request"))
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("TELEGRAM_POLLING_ENABLED", "false")
    monkeypatch.setenv("WEBCHAT_PASSWORD", PASSWORD)
    monkeypatch.setenv("REPLY_LOG_ENABLED", "false")
    monkeypatch.setenv("GROQ_CHAT_ENABLED", "false")
    monkeypatch.setenv("GROQ_API_KEY", "")
    import orchestrator.config as cfg

    cfg.settings.reload()
    import app

    importlib.reload(app)
    app.settings.reload()
    app._db.initialize()
    from orchestrator import webchat

    webchat._failures.clear()
    return TestClient(app.app)


def test_parse_result_usage_camel_case():
    ev = StreamEvidence()
    line = (
        '{"type":"result","subtype":"success","result":"done",'
        '"session_id":"sess-1","request_id":"req-1",'
        '"usage":{"inputTokens":5749,"outputTokens":25,'
        '"cacheReadTokens":9728,"cacheWriteTokens":0}}'
    )
    parsed = parse_line(line, ev)
    assert parsed is not None
    assert parsed["kind"] == "result"
    assert parsed["usage"]["input_tokens"] == 5749
    assert parsed["usage"]["output_tokens"] == 25
    assert parsed["usage"]["cache_read_tokens"] == 9728
    assert ev.usage["input_tokens"] == 5749
    assert ev.session_id == "sess-1"
    assert ev.request_id == "req-1"


def test_parse_result_usage_snake_case():
    ev = StreamEvidence()
    parse_line(
        '{"type":"result","usage":{"input_tokens":100,"output_tokens":20,'
        '"cache_read_tokens":50,"cache_write_tokens":5}}',
        ev,
    )
    assert ev.usage == {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_tokens": 50,
        "cache_write_tokens": 5,
    }


def test_token_spend_summary_today_and_all_time(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    token_spend.record(
        kind="cursor_agent",
        task_id="taskaaaa0001",
        sender="web:owner",
        input_tokens=1000,
        output_tokens=200,
        cache_read_tokens=5000,
        cache_write_tokens=10,
    )
    token_spend.record(
        kind="cursor_agent",
        task_id="taskaaaa0002",
        sender="web:owner",
        input_tokens=500,
        output_tokens=50,
        cache_read_tokens=100,
        cache_write_tokens=0,
    )
    summary = token_spend.summary()
    assert summary["today"]["runs"] == 2
    assert summary["today"]["input_tokens"] == 1500
    assert summary["today"]["output_tokens"] == 250
    assert summary["today"]["total_tokens"] == 1750
    assert summary["today"]["cache_read_tokens"] == 5100
    assert summary["all_time"]["total_tokens"] == 1750
    assert summary["last"]["task_id"] == "taskaaaa0002"
    assert summary["last"]["input_tokens"] == 500


def test_record_skips_zero_usage(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    token_spend.record(input_tokens=0, output_tokens=0)
    assert token_spend.summary()["today"]["runs"] == 0


def test_status_includes_token_spend_and_sidebar_markup(tmp_path, monkeypatch):
    client = _client(monkeypatch, tmp_path)
    assert client.post("/chat/login", json={"password": PASSWORD}).status_code == 200

    html = client.get("/chat").text
    assert 'id="tokenSpendPanel"' in html
    assert 'id="tokenSpendBase"' in html
    assert "Detailed spendings" in html
    assert "applyTokenSpend" in html
    assert "formatTokenCount" in html
    # Panel sits in the sidebar bottom stack (before system status).
    assert html.index('id="tokenSpendPanel"') < html.index('id="statusProjects"')

    token_spend.record(
        kind="cursor_agent",
        task_id="webtoken0001",
        sender="web:owner",
        input_tokens=1200,
        output_tokens=80,
        cache_read_tokens=4000,
        cache_write_tokens=0,
    )
    status = client.get("/chat/status").json()
    assert "token_spend" in status
    spend = status["token_spend"]
    assert spend["today"]["input_tokens"] == 1200
    assert spend["today"]["output_tokens"] == 80
    assert spend["today"]["cache_read_tokens"] == 4000
    assert spend["today"]["total_tokens"] == 1280
    assert spend["today"]["runs"] == 1
    assert spend["last"]["task_id"] == "webtoken0001"
