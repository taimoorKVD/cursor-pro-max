"""Least-privilege process environments and the Windows live-agent gate.

Prompt text is not a boundary. The agent receives an allowlisted environment and,
on Windows, runs inside the AppContainer started by ``win_boundary`` unless the
operator sets ``AGENT_ISOLATION_BREAK_GLASS=true``.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from orchestrator import config

# Names copied into the agent process. Everything else is dropped.
_AGENT_ALLOW = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "SYSTEMDRIVE",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMW6432",
        "COMMONPROGRAMFILES",
        "COMMONPROGRAMFILES(X86)",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "PROCESSOR_LEVEL",
        "PROCESSOR_REVISION",
        "OS",
        "LANG",
        "LC_ALL",
        "PYTHONUTF8",
        "PYTHONIOENCODING",
        "TERM",
        "PUBLIC",
        "DRIVERDATA",
        "ALLUSERSPROFILE",
    }
)

_PUBLISH_DENY_PREFIXES = (
    "META_",
    "SMTP_",
    "WEBCHAT_",
    "TELEGRAM_",
    "GROQ_",
    "TUNNEL_",
    "AWS_",
    "GH_",
    "GITHUB_",
    "NPM_",
    "DATABASE_",
    "REDIS_",
    "STRIPE_",
    "OPENAI_",
    "ANTHROPIC_",
    "CURSOR_",
    "ORCH_",
)
_PUBLISH_DENY_EXACT = frozenset(
    {
        "WEBHOOK_REPLY_ENABLED",
        "ALLOWED_WHATSAPP_NUMBERS",
        "ALLOWED_TELEGRAM_USER_IDS",
    }
)

_boundary: str | None = None


def _copy_allow(env: dict[str, str]) -> None:
    for key in _AGENT_ALLOW:
        value = os.environ.get(key)
        if value:
            env[key] = value


def agent_env(workspace: Path | None = None) -> dict[str, str]:
    """Environment for the coding agent. ``__ORCH_MERGE__=0`` blocks host inheritance."""
    env: dict[str, str] = {}
    _copy_allow(env)
    if workspace is not None:
        home = Path(workspace) / ".orch-agent-home"
        (home / "AppData" / "Local").mkdir(parents=True, exist_ok=True)
        (home / "AppData" / "Roaming").mkdir(parents=True, exist_ok=True)
        env["USERPROFILE"] = str(home)
        env["HOME"] = str(home)
        env["LOCALAPPDATA"] = str(home / "AppData" / "Local")
        env["APPDATA"] = str(home / "AppData" / "Roaming")
        env["TEMP"] = str(home)
        env["TMP"] = str(home)
        # Do not consult the user Git credential manager or ssh-agent.
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GCM_INTERACTIVE"] = "Never"
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "credential.helper"
        env["GIT_CONFIG_VALUE_0"] = ""
    else:
        for key in ("USERPROFILE", "HOME", "APPDATA", "LOCALAPPDATA", "HOMEDRIVE", "HOMEPATH", "TEMP", "TMP"):
            value = os.environ.get(key)
            if value:
                env[key] = value
    if config.CURSOR_API_KEY:
        env["CURSOR_API_KEY"] = config.CURSOR_API_KEY
    env["__ORCH_MERGE__"] = "0"
    return env


def publish_env() -> dict[str, str]:
    """Git/gh environment: real profile for the credential manager, no app secrets."""
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if upper in _PUBLISH_DENY_EXACT or upper == "CURSOR_API_KEY":
            continue
        if any(upper.startswith(prefix) for prefix in _PUBLISH_DENY_PREFIXES):
            continue
        env[key] = value
    env.pop("CURSOR_API_KEY", None)
    env["__ORCH_MERGE__"] = "0"
    return env


def break_glass() -> bool:
    return bool(getattr(config, "AGENT_ISOLATION_BREAK_GLASS", False))


def boundary_status() -> str:
    """``denied`` when a Windows container cannot read a file outside its workspace."""
    global _boundary
    if _boundary:
        return _boundary
    if os.name != "nt":
        _boundary = "env-allowlist"
        return _boundary
    from orchestrator import win_boundary

    root = Path(tempfile.mkdtemp(prefix="orch-boundary-"))
    secret = root.parent / f"orch-secret-{os.getpid()}.txt"
    _boundary = win_boundary.probe(secret, root / "ws")
    return _boundary


def live_agent_allowed() -> tuple[bool, str]:
    if break_glass():
        return True, "AGENT_ISOLATION_BREAK_GLASS: env allowlist only"
    status = boundary_status()
    if os.name != "nt":
        return True, "env allowlist (no Windows AppContainer on this OS)"
    if status == "denied":
        return True, "Windows AppContainer refused a read outside the workspace"
    return (
        False,
        "Windows AppContainer boundary is not active "
        f"(probe={status}). Refusing a live agent. "
        "Set AGENT_ISOLATION_BREAK_GLASS=true only to accept same-user execution.",
    )


def use_container() -> bool:
    return os.name == "nt" and not break_glass() and boundary_status() == "denied"
