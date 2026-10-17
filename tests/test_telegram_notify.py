from orchestrator import config
from orchestrator.notify import send_text
from orchestrator.telegram import _allowed, _handle_update


def test_allowed_telegram_ids(monkeypatch):
    monkeypatch.setenv("ALLOWED_TELEGRAM_USER_IDS", "111, 222")
    config.settings.reload()
    assert _allowed("111")
    assert _allowed("222")
    assert not _allowed("333")


def test_notify_routes_telegram(monkeypatch):
    monkeypatch.setenv("WEBHOOK_REPLY_ENABLED", "true")
    monkeypatch.setenv("REPLY_LOG_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    config.settings.reload()
    called = {}

    def fake_tg(sender, text):
        called["tg"] = (sender, text)

    def fake_wa(sender, text):
        called["wa"] = (sender, text)

    monkeypatch.setattr("orchestrator.notify.tg.send_text", fake_tg)
    monkeypatch.setattr("orchestrator.notify.wa.send_text", fake_wa)

    send_text("tg:111", "hello")
    send_text("923001111111", "hi wa")
    assert called["tg"] == ("tg:111", "hello")
    assert called["wa"] == ("923001111111", "hi wa")


def test_handle_update_allowlisted(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("ALLOWED_TELEGRAM_USER_IDS", "42")
    monkeypatch.setenv("WEBHOOK_REPLY_ENABLED", "false")
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    config.settings.reload()
    from orchestrator import db

    db.initialize()
    seen = []

    monkeypatch.setattr("orchestrator.handlers.handle", lambda sender, body: seen.append((sender, body)))

    _handle_update(
        {
            "update_id": 99,
            "message": {"message_id": 1, "text": "PROJECTS", "from": {"id": 42}},
        }
    )
    assert seen == [("tg:42", "PROJECTS")]
