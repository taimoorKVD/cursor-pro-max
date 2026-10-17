import json

import httpx
import pytest

from orchestrator import config
from orchestrator.meta_webhook_sync import normalize_callback_url, sync_callback_url


def test_normalize_callback_url_variants():
    assert (
        normalize_callback_url("https://abc.trycloudflare.com")
        == "https://abc.trycloudflare.com/webhook"
    )
    assert (
        normalize_callback_url("https://abc.trycloudflare.com/")
        == "https://abc.trycloudflare.com/webhook"
    )
    assert (
        normalize_callback_url("https://abc.trycloudflare.com/webhook")
        == "https://abc.trycloudflare.com/webhook"
    )
    with pytest.raises(ValueError):
        normalize_callback_url("http://insecure.example/webhook")


def test_sync_requires_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "token")
    monkeypatch.setenv("META_VERIFY_TOKEN", "verify")
    monkeypatch.setenv("META_PHONE_NUMBER_ID", "replace-with-phone-number-id")
    monkeypatch.setenv("META_WABA_ID", "")
    monkeypatch.setenv("META_WEBHOOK_SYNC_ENABLED", "true")
    config.settings.reload()
    monkeypatch.setattr(config, "BASE", tmp_path)

    result = sync_callback_url("https://abc.trycloudflare.com")
    assert result.ok is False
    assert "META_PHONE_NUMBER_ID" in result.detail


def test_sync_phone_override(tmp_path, monkeypatch):
    monkeypatch.setenv("META_ACCESS_TOKEN", "token")
    monkeypatch.setenv("META_VERIFY_TOKEN", "verify")
    monkeypatch.setenv("META_PHONE_NUMBER_ID", "109999")
    monkeypatch.setenv("META_WABA_ID", "")
    monkeypatch.setenv("META_GRAPH_VERSION", "v23.0")
    monkeypatch.setenv("META_WEBHOOK_SYNC_ENABLED", "true")
    config.settings.reload()
    monkeypatch.setattr(config, "BASE", tmp_path)

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((str(request.url), json.loads(request.content.decode())))
        return httpx.Response(200, json={"success": True})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr("orchestrator.meta_webhook_sync.httpx.Client", client_factory)

    result = sync_callback_url("https://abc.trycloudflare.com", force=True)
    assert result.ok is True
    assert result.targets == ("phone:109999",)
    assert calls[0][0].endswith("/109999")
    assert (
        calls[0][1]["webhook_configuration"]["override_callback_uri"]
        == "https://abc.trycloudflare.com/webhook"
    )
    synced = (tmp_path / "data" / "logs" / "cloudflared-meta-synced-url.txt").read_text(
        encoding="utf-8"
    ).strip()
    assert synced == "https://abc.trycloudflare.com/webhook"
