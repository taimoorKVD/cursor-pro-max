"""FastAPI application and webhook routes."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from orchestrator import config, db, webchat
from orchestrator.handlers import handle
from orchestrator.tasks import seen_message
from orchestrator.worker import start_worker

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("orchestrator.api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.initialize()
    from orchestrator.retention import cleanup_workspaces

    removed = cleanup_workspaces()
    if removed:
        log.info("Startup retention removed %s workspaces", removed)
    from orchestrator import queue

    recovered = queue.recover_interrupted()
    if recovered:
        log.warning("startup recovery: %s", recovered)
    start_worker()
    from orchestrator.telegram import start_polling, stop_polling

    start_polling()
    try:
        yield
    finally:
        stop_polling()


_docs = "/docs" if config.EXPOSE_API_DOCS else None
app = FastAPI(
    title="Cursor Messaging Orchestrator",
    lifespan=lifespan,
    docs_url=_docs,
    redoc_url="/redoc" if config.EXPOSE_API_DOCS else None,
    openapi_url="/openapi.json" if config.EXPOSE_API_DOCS else None,
)
app.include_router(webchat.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/webhook")
async def verify(request: Request):
    q = request.query_params
    token = config.META_VERIFY_TOKEN
    if (
        token
        and q.get("hub.mode") == "subscribe"
        and hmac.compare_digest(q.get("hub.verify_token", ""), token)
    ):
        return Response(content=q.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook")
async def webhook(request: Request):
    raw = await request.body()
    secret = config.META_APP_SECRET
    signature = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(expected, signature):
        log.warning("webhook rejected: bad signature or missing META_APP_SECRET")
        return Response(status_code=403)
    try:
        payload = json.loads(raw)
    except ValueError:
        return Response(status_code=400)
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for message in change.get("value", {}).get("messages", []):
                sender = message.get("from", "").lstrip("+")
                mid = message.get("id")
                if not mid:
                    continue
                if sender not in config.ALLOWED_WHATSAPP_NUMBERS:
                    log.info("webhook ignored: sender %s not in allowlist", sender)
                    continue
                if message.get("type") != "text":
                    continue
                if seen_message(mid):
                    body = message.get("text", {}).get("body", "")
                    try:
                        from orchestrator import history

                        history.append(sender, "in", body)
                    except Exception:  # noqa: BLE001
                        pass
                    handle(sender, body)
    return {"ok": True}
