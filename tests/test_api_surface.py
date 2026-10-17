"""Docs stay off and invalid project files fail closed."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from orchestrator import config
from orchestrator.projects import ProjectConfigError, load_projects, projects


def test_docs_are_hidden(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("ORCHESTRATOR_WORKER", "false")
    monkeypatch.setenv("TELEGRAM_POLLING_ENABLED", "false")
    monkeypatch.setenv("EXPOSE_API_DOCS", "false")
    monkeypatch.setenv("WEBHOOK_REPLY_ENABLED", "false")
    config.settings.reload()
    from orchestrator.api import app

    client = TestClient(app)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/health").status_code == 200


def test_projects_strict_rejects_invalid_file(tmp_path, monkeypatch):
    bad = tmp_path / "projects.json"
    bad.write_text(
        json.dumps(
            {
                "bad": {
                    "path": str(tmp_path),
                    "type": "local",
                    "allow_push": True,
                    "allow_deploy": False,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(config.settings, "PROJECTS_FILE", bad)
    monkeypatch.setattr(config.settings, "PROJECTS_STRICT", True)
    with pytest.raises(ProjectConfigError):
        projects()


def test_registered_projects_load_strict():
    path = config.PROJECTS_FILE
    if not path.is_file():
        pytest.skip("projects.json is local and is not committed")
    loaded = load_projects(path, strict=True)
    assert loaded
    assert all(item.get("allow_deploy") is False for item in loaded.values())
