"""Backward-compatible entrypoint: `uvicorn app:app` and legacy test imports."""
from __future__ import annotations

import importlib

from orchestrator.config import settings

settings.reload()

from orchestrator import api as _api  # noqa: E402
from orchestrator import db as _db  # noqa: E402
from orchestrator import handlers as _handlers  # noqa: E402
from orchestrator import tasks as _tasks  # noqa: E402
from orchestrator.worker import start_worker  # noqa: E402

# Ensure schema exists even when startup hook is not run (some test clients).
_db.initialize()
start_worker()

app = _api.app


def db():
    """Legacy test helper."""
    return _db.connect()


def one(task_id: str):
    return _tasks.get_task(task_id)


def handle(sender: str, body: str):
    return _handlers.handle(sender, body)


def reload_runtime():
    """Re-read env and refresh module bindings after monkeypatch."""
    settings.reload()
    importlib.reload(_api)
    global app
    app = _api.app
    _db.initialize()
    start_worker()
