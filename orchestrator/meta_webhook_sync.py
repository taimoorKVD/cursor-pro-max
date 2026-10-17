"""Sync the public webhook callback URL to Meta (phone / WABA override)."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from orchestrator import config

log = logging.getLogger("orchestrator.meta_webhook_sync")

PLACEHOLDER_MARKERS = ("replace-with-", "your-", "changeme", "todo")


@dataclass(frozen=True)
class SyncResult:
    ok: bool
    callback_url: str
    targets: tuple[str, ...]
    detail: str


def _is_configured(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    return not any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def normalize_callback_url(public_base_or_webhook: str) -> str:
    raw = (public_base_or_webhook or "").strip().rstrip("/")
    if not raw:
        raise ValueError("callback URL is empty")
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("callback URL must be an https URL")
    if parsed.path.endswith("/webhook"):
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    if parsed.path in ("", "/"):
        return f"{parsed.scheme}://{parsed.netloc}/webhook"
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}/webhook"


def _graph_url(path: str) -> str:
    return f"https://graph.facebook.com/{config.META_GRAPH_VERSION}/{path.lstrip('/')}"


def _post_override(client: httpx.Client, url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        url,
        headers={
            "Authorization": f"Bearer {config.META_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    try:
        body: Any = response.json()
    except Exception:
        body = {"raw": response.text}
    if response.status_code >= 400:
        raise RuntimeError(
            f"Meta API {response.status_code} for {url}: {json.dumps(body)[:800]}"
        )
    return body if isinstance(body, dict) else {"data": body}


def sync_callback_url(public_base_or_webhook: str, *, force: bool = False) -> SyncResult:
    """Point Meta message webhooks at the given public URL via override APIs."""
    callback_url = normalize_callback_url(public_base_or_webhook)
    if len(callback_url) > 200:
        return SyncResult(False, callback_url, (), "callback URL exceeds Meta 200-char limit")

    if not config.META_WEBHOOK_SYNC_ENABLED and not force:
        return SyncResult(False, callback_url, (), "META_WEBHOOK_SYNC_ENABLED=false")

    if not _is_configured(config.META_ACCESS_TOKEN):
        return SyncResult(False, callback_url, (), "META_ACCESS_TOKEN is missing/placeholder")
    if not _is_configured(config.META_VERIFY_TOKEN):
        return SyncResult(False, callback_url, (), "META_VERIFY_TOKEN is missing/placeholder")

    phone_id = config.META_PHONE_NUMBER_ID
    waba_id = config.META_WABA_ID
    targets: list[str] = []
    notes: list[str] = []

    if not _is_configured(phone_id) and not _is_configured(waba_id):
        return SyncResult(
            False,
            callback_url,
            (),
            "Set META_PHONE_NUMBER_ID and/or META_WABA_ID in .env before syncing",
        )

    state_file = Path(config.BASE) / "data" / "logs" / "cloudflared-meta-synced-url.txt"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if not force and state_file.exists():
        previous = state_file.read_text(encoding="utf-8").strip()
        if previous == callback_url:
            return SyncResult(True, callback_url, ("unchanged",), "already synced")

    with httpx.Client(timeout=30) as client:
        if _is_configured(phone_id):
            body = _post_override(
                client,
                _graph_url(phone_id),
                {
                    "webhook_configuration": {
                        "override_callback_uri": callback_url,
                        "verify_token": config.META_VERIFY_TOKEN,
                    }
                },
            )
            targets.append(f"phone:{phone_id}")
            notes.append(f"phone={body.get('success', body)}")

        if _is_configured(waba_id):
            body = _post_override(
                client,
                _graph_url(f"{waba_id}/subscribed_apps"),
                {
                    "override_callback_uri": callback_url,
                    "verify_token": config.META_VERIFY_TOKEN,
                },
            )
            targets.append(f"waba:{waba_id}")
            notes.append(f"waba={body.get('success', body)}")

    state_file.write_text(callback_url + "\n", encoding="utf-8")
    return SyncResult(True, callback_url, tuple(targets), "; ".join(notes) or "ok")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Sync public webhook URL to Meta overrides")
    parser.add_argument(
        "url",
        nargs="?",
        help="Public base or full /webhook URL. Defaults to data/logs/cloudflared-public-url.txt",
    )
    parser.add_argument("--force", action="store_true", help="Sync even if URL unchanged / sync disabled")
    args = parser.parse_args(argv)

    config.settings.reload()
    url = args.url
    if not url:
        url_file = config.BASE / "data" / "logs" / "cloudflared-public-url.txt"
        if not url_file.exists():
            print("No URL argument and cloudflared-public-url.txt is missing", file=sys.stderr)
            return 2
        url = url_file.read_text(encoding="utf-8").strip()

    try:
        result = sync_callback_url(url, force=args.force)
    except Exception as exc:
        print(f"SYNC_FAILED {exc}", file=sys.stderr)
        return 1

    status = "SYNC_OK" if result.ok else "SYNC_SKIP"
    print(f"{status} callback={result.callback_url} targets={','.join(result.targets) or '-'} detail={result.detail}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
