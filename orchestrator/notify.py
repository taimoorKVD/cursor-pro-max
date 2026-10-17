"""Outbound replies across messaging channels."""
from __future__ import annotations

import logging
import re

from orchestrator import config
from orchestrator import telegram as tg
from orchestrator import whatsapp as wa

log = logging.getLogger("orchestrator.notify")

LEVELS = frozenset({"info", "success", "warning", "error"})


def infer_level(text: str, level: str | None = None) -> str:
    """Classify reply severity for badges/notifications.

    Prefer an explicit ``level``. Auto-detect only clear failure/success
    phrasing — not status words inside task lists (e.g. ``[failed]``).
    """
    if level and level in LEVELS:
        return level
    t = (text or "").lower()
    if re.search(
        r"(sorry\s*-|didn't work|did not work|cannot |can't |"
        r"error:|operation failed|task failed|failed while|failed:|"
        r"\bfailure\b)",
        t,
    ):
        return "error"
    if re.search(
        r"\b(heads up|warning|dry-run|isn't enabled|isn't configured|isn't ready|"
        r"not enabled|not configured|blocked)\b",
        t,
    ):
        return "warning"
    if re.search(
        r"\b(finished|ready for your review|done for task|got it - working|"
        r"published successfully|workspace is ready)\b",
        t,
    ):
        return "success"
    return "info"


def send_text(sender: str, text: str, *, level: str | None = None) -> None:
    """Route a reply to web chat (`web:`), Telegram (`tg:<id>`) or WhatsApp (digits)."""
    from orchestrator.scrub import scrub

    body = scrub((text or "")[:3900])
    kind = infer_level(body, level)
    if config.REPLY_LOG_ENABLED:
        log.info("REPLY [%s] -> %s: %s", kind, sender, body.replace("\n", " | ")[:500])
    # Shared conversation layer (all channels) — identity-isolated by sender.
    try:
        from orchestrator import history

        history.append(sender, "out", body, level=kind)
    except Exception:  # noqa: BLE001
        log.exception("Failed to persist conversation turn for %s", sender)
    if sender.startswith("web:"):
        from orchestrator import webchat

        webchat.store("out", body, level=kind, mirror_history=False)
        return
    if not config.WEBHOOK_REPLY_ENABLED:
        return
    if sender.startswith("tg:"):
        tg.send_text(sender, body)
        return
    wa.send_text(sender, body)
