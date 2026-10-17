"""Playwright fixtures for go-live browser investigation against a live orchestrator."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

# Default: live Windows service on :8000. Override with ORCH_BROWSER_BASE_URL.
DEFAULT_BASE = os.getenv("ORCH_BROWSER_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "browser_live: hits the live orchestrator (needs WEBCHAT_PASSWORD + running server)",
    )
    config.addinivalue_line(
        "markers",
        "browser_agent: optional long Cursor agent smoke (set ORCH_BROWSER_LIVE_AGENT=1)",
    )


@pytest.fixture(scope="session")
def base_url() -> str:
    # Opt-in so default `pytest` (unit suite) does not hit the live service.
    if os.getenv("ORCH_BROWSER_RUN", "").strip().lower() not in {"1", "true", "yes"}:
        pytest.skip("Set ORCH_BROWSER_RUN=1 to run live browser investigation against the orchestrator")
    return DEFAULT_BASE


@pytest.fixture(scope="session")
def webchat_password() -> str:
    pw = (os.getenv("WEBCHAT_PASSWORD") or "").strip()
    if len(pw) < 12:
        pytest.skip("WEBCHAT_PASSWORD missing or too short — cannot run live browser investigation")
    return pw


@pytest.fixture(scope="session")
def report_dir() -> Path:
    out = ROOT / "docs" / "golive-browser"
    out.mkdir(parents=True, exist_ok=True)
    return out
