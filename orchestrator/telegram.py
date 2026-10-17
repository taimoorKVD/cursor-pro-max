"""Telegram Bot API: outbound send + inbound long-polling worker."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx

from orchestrator import config

log = logging.getLogger("orchestrator.telegram")

_poll_thread: threading.Thread | None = None
_stop = threading.Event()


def _api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}"


def send_text(sender: str, text: str) -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        log.info("Telegram not configured; would send to %s: %s", sender, text[:300])
        return
    chat_id = sender.removeprefix("tg:")
    if not chat_id.isdigit():
        log.error("Invalid Telegram sender %s", sender)
        return
    payload = {"chat_id": int(chat_id), "text": text[:3900]}
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(_api_url("sendMessage"), json=payload)
            if response.status_code >= 400:
                log.error(
                    "Telegram delivery failed status=%s body=%s",
                    response.status_code,
                    response.text[:800],
                )
                return
    except Exception:
        log.exception("Telegram delivery failed")


def _allowed(user_id: str) -> bool:
    allowed = config.ALLOWED_TELEGRAM_USER_IDS
    if not allowed:
        return False
    return user_id in allowed


def _handle_update(update: dict[str, Any]) -> None:
    from orchestrator.handlers import handle
    from orchestrator.tasks import seen_message

    message = update.get("message") or update.get("edited_message")
    if not message:
        return
    text = message.get("text")
    if not text:
        return
    user = message.get("from") or {}
    user_id = str(user.get("id") or "")
    if not user_id:
        return
    mid = f"tg:{update.get('update_id')}"
    if not _allowed(user_id):
        log.info("Telegram ignored: user %s not in allowlist", user_id)
        if seen_message(mid):
            send_text(
                f"tg:{user_id}",
                f"Unauthorized. Your Telegram user id is {user_id}. "
                "Add it to ALLOWED_TELEGRAM_USER_IDS in .env and restart the orchestrator.",
            )
        return
    if seen_message(mid):
        sender = f"tg:{user_id}"
        try:
            from orchestrator import history

            history.append(sender, "in", text)
        except Exception:  # noqa: BLE001
            pass
        handle(sender, text)


def _poll_loop() -> None:
    offset = 0
    log.info("Telegram long-polling started")
    while not _stop.is_set():
        if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_POLLING_ENABLED:
            time.sleep(2)
            continue
        try:
            with httpx.Client(timeout=60) as client:
                response = client.get(
                    _api_url("getUpdates"),
                    params={"offset": offset, "timeout": 25},
                )
            if response.status_code >= 400:
                log.error("Telegram getUpdates failed status=%s body=%s", response.status_code, response.text[:500])
                time.sleep(5)
                continue
            data = response.json()
            if not data.get("ok"):
                log.error("Telegram getUpdates not ok: %s", str(data)[:500])
                time.sleep(5)
                continue
            for update in data.get("result") or []:
                try:
                    _handle_update(update)
                except Exception:
                    log.exception("Telegram update handling failed")
                uid = update.get("update_id")
                if isinstance(uid, int):
                    offset = max(offset, uid + 1)
        except Exception:
            log.exception("Telegram poll loop error")
            time.sleep(5)
    log.info("Telegram long-polling stopped")


def start_polling() -> None:
    global _poll_thread
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_POLLING_ENABLED:
        log.info("Telegram polling disabled (set TELEGRAM_BOT_TOKEN and TELEGRAM_POLLING_ENABLED=true)")
        return
    if _poll_thread and _poll_thread.is_alive():
        return
    _stop.clear()
    _poll_thread = threading.Thread(target=_poll_loop, name="telegram-poll", daemon=True)
    _poll_thread.start()


def stop_polling() -> None:
    _stop.set()
