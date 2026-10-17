"""Shared conversation history across channels with sender isolation."""
from __future__ import annotations

from orchestrator import config, db, history, llm_chat


def test_history_isolated_by_sender(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    config.settings.reload()
    db.initialize()

    history.append("web:owner", "in", "Let's work on lifeos")
    history.append("web:owner", "out", "Okay — I'll use lifeos.")
    history.append("tg:99", "in", "secret telegram turn")
    history.append("923001234567", "in", "secret whatsapp turn")

    web = history.recent("web:owner", limit=10)
    assert len(web) == 2
    assert all(r["sender"] == "web:owner" for r in web)
    assert "lifeos" in web[0]["text"].lower()

    tg = history.recent("tg:99", limit=10)
    assert len(tg) == 1
    assert "telegram" in tg[0]["text"].lower()

    wa = history.recent("923001234567", limit=10)
    assert len(wa) == 1
    assert "whatsapp" in wa[0]["text"].lower()


def test_llm_chat_history_reads_shared_layer(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("GROQ_API_KEY", "")
    config.settings.reload()
    db.initialize()

    history.append("tg:42", "in", "Let's work on lifeos.")
    history.append("tg:42", "out", "Okay — I'll use lifeos. What should I change?")
    history.append("tg:42", "in", "fix dark mode on login")

    turns = llm_chat._chat_history("tg:42", current="fix dark mode on login")
    assert turns
    assert turns[0]["role"] == "user"
    assert "lifeos" in turns[0]["content"].lower()
    assert turns[1]["role"] == "assistant"
    # Current user turn skipped because it is passed separately.
    assert not any(t["content"] == "fix dark mode on login" for t in turns)
