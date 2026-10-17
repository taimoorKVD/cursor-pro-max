"""Meta WhatsApp Cloud API outbound messaging."""
from __future__ import annotations

import logging

import httpx

from orchestrator import config

log = logging.getLogger("orchestrator.whatsapp")


def send_text(sender: str, text: str) -> None:
    if not config.WEBHOOK_REPLY_ENABLED:
        return
    if not config.META_ACCESS_TOKEN or not config.META_PHONE_NUMBER_ID:
        log.info("WhatsApp not configured; would send to %s: %s", sender, text[:300])
        return
    url = (
        f"https://graph.facebook.com/{config.META_GRAPH_VERSION}/"
        f"{config.META_PHONE_NUMBER_ID}/messages"
    )
    payload = {
        "messaging_product": "whatsapp",
        "to": sender,
        "type": "text",
        "text": {"body": text[:3900]},
    }
    try:
        with httpx.Client(timeout=20) as client:
            response = client.post(
                url,
                headers={"Authorization": f"Bearer {config.META_ACCESS_TOKEN}"},
                json=payload,
            )
            if response.status_code >= 400:
                log.error(
                    "WhatsApp delivery failed status=%s body=%s",
                    response.status_code,
                    response.text[:800],
                )
                return
            response.raise_for_status()
    except Exception:
        log.exception("WhatsApp delivery failed")
