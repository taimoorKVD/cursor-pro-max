"""Environment and path configuration (reloadable for tests)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE = Path(__file__).resolve().parent.parent


class Settings:
    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        self.DATABASE_FILE = self._path("DATABASE_FILE", "data/orchestrator.sqlite")
        self.WORK_ROOT = self._path("WORK_ROOT", "data/workspaces")
        self.PROJECTS_FILE = self._path("PROJECTS_FILE", "projects.json")
        # Default scan root from env (runtime override may replace this).
        _projects_root = os.getenv("PROJECTS_ROOT", "").strip()
        self.PROJECTS_ROOT = Path(_projects_root).expanduser() if _projects_root else None
        # Persisted runtime override for the scan directory (survives restarts).
        self.PROJECTS_ROOT_FILE = self._path("PROJECTS_ROOT_FILE", "data/projects_root.json")
        self.AGENT_BIN = os.getenv("AGENT_BIN", "agent")
        self.DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
        self.WEBHOOK_REPLY_ENABLED = os.getenv("WEBHOOK_REPLY_ENABLED", "true").lower() == "true"
        self.META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "")
        self.META_APP_SECRET = os.getenv("META_APP_SECRET", "")
        self.META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
        self.META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
        self.META_WABA_ID = os.getenv("META_WABA_ID", "")
        self.META_GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v23.0")
        self.META_WEBHOOK_SYNC_ENABLED = os.getenv("META_WEBHOOK_SYNC_ENABLED", "true").lower() == "true"
        self.ALLOWED_WHATSAPP_NUMBERS = {
            "".join(ch for ch in s.strip() if ch.isdigit())
            for s in os.getenv("ALLOWED_WHATSAPP_NUMBERS", "").split(",")
            if s.strip()
        }
        self.TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.TELEGRAM_POLLING_ENABLED = os.getenv("TELEGRAM_POLLING_ENABLED", "true").lower() == "true"
        self.ALLOWED_TELEGRAM_USER_IDS = {
            "".join(ch for ch in s.strip() if ch.isdigit())
            for s in os.getenv("ALLOWED_TELEGRAM_USER_IDS", "").split(",")
            if s.strip()
        }
        self.REPLY_LOG_ENABLED = os.getenv("REPLY_LOG_ENABLED", "true").lower() == "true"
        self.WEBCHAT_PASSWORD = os.getenv("WEBCHAT_PASSWORD", "")
        self.WEBCHAT_SESSION_DAYS = int(os.getenv("WEBCHAT_SESSION_DAYS", "7"))
        # Cursor sandbox is macOS/Linux-only; default off on Windows.
        _default_sandbox = "disabled" if os.name == "nt" else "enabled"
        self.AGENT_SANDBOX = os.getenv("AGENT_SANDBOX", _default_sandbox).strip().lower()
        self.AGENT_TIMEOUT_SEC = int(os.getenv("AGENT_TIMEOUT_SEC", "1200"))
        # text | stream-json — stream-json enables evidence-based mid-run events
        self.AGENT_OUTPUT_FORMAT = os.getenv("AGENT_OUTPUT_FORMAT", "stream-json").strip().lower()
        if self.AGENT_OUTPUT_FORMAT not in {"text", "json", "stream-json"}:
            self.AGENT_OUTPUT_FORMAT = "stream-json"
        self.JOB_LEASE_SEC = int(os.getenv("JOB_LEASE_SEC", "1800"))
        self.WORKER_POLL_SEC = float(os.getenv("WORKER_POLL_SEC", "1.0"))
        # Parallel agent jobs across project chats (each claimed job is exclusive).
        self.WORKER_COUNT = max(1, min(8, int(os.getenv("WORKER_COUNT", "3"))))
        self.WORKSPACE_RETENTION_DAYS = int(os.getenv("WORKSPACE_RETENTION_DAYS", "14"))
        # Groq for natural chat understanding (optional; regex fallback always works)
        self.GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
        self.GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()
        self.GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").strip()
        self.GROQ_CHAT_ENABLED = os.getenv("GROQ_CHAT_ENABLED", "true").lower() == "true"
        # Webchat mic → Whisper (uses device microphone; needed on iPhone where Web Speech is unavailable)
        self.GROQ_VOICE_ENABLED = os.getenv("GROQ_VOICE_ENABLED", "true").lower() == "true"
        self.GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo").strip()
        # Cursor Agent auth (API key preferred for unattended runs; auto-login as fallback)
        self.CURSOR_API_KEY = os.getenv("CURSOR_API_KEY", "").strip()
        self.CURSOR_ACCOUNT_EMAIL = os.getenv(
            "CURSOR_ACCOUNT_EMAIL", "info@kingdom-vision.com"
        ).strip()
        self.CURSOR_AUTO_LOGIN = os.getenv("CURSOR_AUTO_LOGIN", "true").lower() == "true"
        self.CURSOR_LOGIN_TIMEOUT_SEC = int(os.getenv("CURSOR_LOGIN_TIMEOUT_SEC", "180"))
        # Live agent on Windows requires the AppContainer probe unless this is true.
        self.AGENT_ISOLATION_BREAK_GLASS = (
            os.getenv("AGENT_ISOLATION_BREAK_GLASS", "false").lower() == "true"
        )
        # Production deploy stays off. R8 health/rollback is not implemented.
        self.DEPLOY_ENABLED = os.getenv("DEPLOY_ENABLED", "false").lower() == "true"
        self.APPROVAL_TTL_SEC = int(os.getenv("APPROVAL_TTL_SEC", "86400"))
        self.QUOTAS_ENABLED = os.getenv("ORCH_QUOTAS", "true").lower() == "true"
        self.MAX_TASKS_PER_SENDER_PER_DAY = int(os.getenv("MAX_TASKS_PER_SENDER_PER_DAY", "40"))
        self.MAX_AGENT_STARTS_PER_DAY = int(os.getenv("MAX_AGENT_STARTS_PER_DAY", "40"))
        self.MAX_GROQ_CALLS_PER_DAY = int(os.getenv("MAX_GROQ_CALLS_PER_DAY", "300"))
        self.EXPOSE_API_DOCS = os.getenv("EXPOSE_API_DOCS", "false").lower() == "true"
        self.PROJECTS_STRICT = os.getenv("PROJECTS_STRICT", "true").lower() == "true"
        # Closed-loop learning (outcomes / playbook / intent few-shots) — not model fine-tuning.
        self.LEARNING_ENABLED = os.getenv("LEARNING_ENABLED", "true").lower() == "true"
        self.LEARNING_PLAYBOOK_MAX_RULES = max(
            1, min(50, int(os.getenv("LEARNING_PLAYBOOK_MAX_RULES", "12")))
        )
        self.LEARNING_PAST_SUCCESSES_MAX = max(
            0, min(20, int(os.getenv("LEARNING_PAST_SUCCESSES_MAX", "5")))
        )
        self.LEARNING_FEWSHOT_MAX = max(
            0, min(30, int(os.getenv("LEARNING_FEWSHOT_MAX", "8")))
        )

    @staticmethod
    def _path(name: str, default: str) -> Path:
        value = Path(os.getenv(name, default))
        return value if value.is_absolute() else BASE / value


settings = Settings()


def __getattr__(name: str):
    """Allow `from orchestrator import config; config.DRY_RUN` style access."""
    if name == "settings":
        return settings
    if hasattr(settings, name):
        return getattr(settings, name)
    raise AttributeError(name)
