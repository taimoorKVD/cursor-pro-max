"""Cursor CLI adapter — Windows-safe prompt delivery via task file + stdin."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any

from orchestrator import config, preflight
from orchestrator.process import run

log = logging.getLogger("orchestrator.agent")

# Matches YYYY.MM.DD-commit and YYYY.MM.DD-HH-MM-SS-commit
_VERSION_RE = re.compile(
    r"^(\d{4})\.(\d{1,2})\.(\d{1,2})(?:-(\d{2})-(\d{2})-(\d{2}))?-([0-9a-fA-F]+)$"
)

TASK_FILE = ".orchestrator-task.md"
CLI_POINTER = (
    f"Read the file {TASK_FILE} in this workspace first. "
    "It contains the USER TASK under the heading 'USER TASK'. "
    "Implement that task completely now. "
    "Do not ask me to paste the task — it is already in that file."
)


def _version_sort_key(name: str) -> tuple:
    m = _VERSION_RE.match(name)
    if not m:
        return (0,)
    year, month, day, hh, mm, ss, commit = m.groups()
    return (
        int(year),
        int(month),
        int(day),
        int(hh or "0"),
        int(mm or "0"),
        int(ss or "0"),
        (commit or "").lower(),
    )


def _resolve_windows_entrypoint(agent_bin: str) -> list[str]:
    """Avoid cmd.exe / agent.cmd — %* mangling kills multiline prompts."""
    path = Path(agent_bin)
    # PowerShell Get-Command may resolve to .ps1; which() often returns .cmd
    candidates_dirs = []
    if path.suffix.lower() in {".cmd", ".bat", ".ps1", ".exe"}:
        candidates_dirs.append(path.parent)
    else:
        candidates_dirs.append(path.parent)

    local = Path(os.environ.get("LOCALAPPDATA", "")) / "cursor-agent"
    if local.is_dir() and local not in candidates_dirs:
        candidates_dirs.append(local)

    for shim_dir in candidates_dirs:
        exe = shim_dir / "agent.exe"
        if exe.is_file():
            return [str(exe)]

        versions = shim_dir / "versions"
        best: Path | None = None
        best_key: tuple = (0,)
        if versions.is_dir():
            for child in versions.iterdir():
                if not child.is_dir() or not _VERSION_RE.match(child.name):
                    continue
                node = child / "node.exe"
                index = child / "index.js"
                if node.is_file() and index.is_file():
                    key = _version_sort_key(child.name)
                    if key > best_key:
                        best_key = key
                        best = child
        if best is not None:
            # AppContainers cannot lstat drive roots (EPERM on C:\). Node's
            # default main-module realpath walks from the root — skip it.
            return [
                str(best / "node.exe"),
                "--preserve-symlinks",
                "--preserve-symlinks-main",
                str(best / "index.js"),
            ]

        direct_node = shim_dir / "node.exe"
        direct_js = shim_dir / "index.js"
        if direct_node.is_file() and direct_js.is_file():
            return [
                str(direct_node),
                "--preserve-symlinks",
                "--preserve-symlinks-main",
                str(direct_js),
            ]

        ps1 = shim_dir / "agent.ps1"
        if ps1.is_file():
            powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
            if powershell:
                return [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(ps1),
                ]

    log.warning(
        "Could not resolve Node entrypoint for %s; using shim (prompt may truncate)",
        agent_bin,
    )
    return [agent_bin]


def resolve_agent_argv() -> list[str]:
    ok, agent_bin = preflight.agent_available()
    if not ok:
        raise RuntimeError(agent_bin)
    if os.name == "nt":
        return _resolve_windows_entrypoint(agent_bin)
    return [agent_bin]


def _effective_sandbox() -> str:
    """Return sandbox mode safe for this OS (empty string = omit flag)."""
    mode = (config.AGENT_SANDBOX or "").strip().lower()
    if mode not in {"enabled", "disabled"}:
        return ""
    if os.name == "nt" and mode == "enabled":
        log.warning(
            "AGENT_SANDBOX=enabled is unsupported on Windows; forcing --sandbox disabled"
        )
        return "disabled"
    return mode


_SENSITIVE_ENV_PREFIXES = (
    "META_",
    "SMTP_",
    "WEBCHAT_",
    "TELEGRAM_",
    "GROQ_",
    "TUNNEL_",
    "AWS_",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "NPM_TOKEN",
    "DATABASE_",
    "REDIS_",
    "STRIPE_",
    "OPENAI_",
    "ANTHROPIC_",
)


def _agent_env(workspace: Path | None = None) -> dict[str, str]:
    """Allowlisted agent environment. See ``isolation.agent_env``."""
    from orchestrator.isolation import agent_env

    return agent_env(workspace)


def build_argv(
    workspace: Path,
    *,
    resume_chat_id: str | None = None,
    prompt_pointer: str | None = None,
) -> list[str]:
    """CLI argv. Short pointer prompt only — full task lives in TASK_FILE / stdin."""
    workspace = Path(workspace).resolve()
    out_fmt = getattr(config, "AGENT_OUTPUT_FORMAT", "stream-json") or "stream-json"
    argv = [
        *resolve_agent_argv(),
        "-p",
        "--force",
        "--trust",
        "--workspace",
        str(workspace),
        "--output-format",
        out_fmt,
    ]
    # API key stays in the environment only. Never put it on argv (process list / logs).
    sandbox = _effective_sandbox()
    if sandbox:
        argv.extend(["--sandbox", sandbox])
    chat_id = (resume_chat_id or "").strip()
    if chat_id:
        # Prefer --resume=<id> so Windows/PowerShell never drop a bare optional arg.
        argv.append(f"--resume={chat_id}")
    # Short single-line argv prompt (Windows-safe). Full text also on stdin + file.
    pointer = (prompt_pointer or "").strip() or CLI_POINTER
    if len(pointer) > 400:
        pointer = pointer[:397] + "..."
    argv.append(pointer)
    return argv


def auth_status() -> dict[str, Any]:
    """Return {ok, email, detail} for the Cursor agent session / API key."""
    if config.CURSOR_API_KEY:
        return {
            "ok": True,
            "email": config.CURSOR_ACCOUNT_EMAIL or None,
            "mode": "api-key",
            "detail": "CURSOR_API_KEY is set",
        }
    try:
        result = run(
            [*resolve_agent_argv(), "status", "--format", "json"],
            timeout=45,
            env=_agent_env() or None,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "email": None, "mode": "session", "detail": str(exc)[:300]}
    raw = (result.stdout or result.stderr or "").strip()
    email = None
    ok = False
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            user = data.get("userInfo") or data.get("user") or data.get("account") or {}
            if not isinstance(user, dict):
                user = {}
            email = data.get("email") or user.get("email")
            status_word = str(data.get("status") or "").lower()
            ok = bool(
                data.get("isAuthenticated")
                or data.get("authenticated")
                or data.get("loggedIn")
                or data.get("ok")
                or data.get("hasAccessToken")
                or status_word in {"authenticated", "logged_in", "ok"}
                or email
            )
        except json.JSONDecodeError:
            pass
    text = raw.lower()
    if not ok:
        ok = ("logged in" in text or "authenticated" in text) and "not logged in" not in text
    if not email:
        m = re.search(r"[\w.+-]+@[\w.-]+\.\w+", raw)
        email = m.group(0) if m else None
    expected = (config.CURSOR_ACCOUNT_EMAIL or "").strip().lower()
    if expected and email and email.lower() != expected:
        return {
            "ok": False,
            "email": email,
            "mode": "session",
            "detail": (
                f"Logged in as {email}, but CURSOR_ACCOUNT_EMAIL is "
                f"{config.CURSOR_ACCOUNT_EMAIL}. Run agent logout && agent login."
            ),
        }
    return {
        "ok": ok,
        "email": email,
        "mode": "session",
        "detail": raw[:400] if raw else f"exit {result.returncode}",
    }


def ensure_auth(*, force_login: bool = False) -> tuple[bool, str]:
    """
    Make sure Cursor Agent can run unattended.

    Preference order:
    1. CURSOR_API_KEY (fully automatic / headless)
    2. Existing `agent login` session for CURSOR_ACCOUNT_EMAIL
    3. If CURSOR_AUTO_LOGIN, run `agent login` again (browser SSO for that account)
    """
    status = auth_status()
    if status["ok"] and not force_login:
        who = status.get("email") or config.CURSOR_ACCOUNT_EMAIL or "cursor account"
        return True, f"Authenticated ({status.get('mode')}: {who})"

    if config.CURSOR_API_KEY:
        return True, "Using CURSOR_API_KEY"

    if not config.CURSOR_AUTO_LOGIN:
        return (
            False,
            "Cursor Agent is not signed in. Set CURSOR_API_KEY or run agent login "
            f"as {config.CURSOR_ACCOUNT_EMAIL}.",
        )

    log.warning(
        "Cursor Agent auth missing/expired - running agent login for %s",
        config.CURSOR_ACCOUNT_EMAIL or "default account",
    )
    try:
        result = run(
            [*resolve_agent_argv(), "login"],
            timeout=config.CURSOR_LOGIN_TIMEOUT_SEC,
            env=_agent_env() or None,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"Automatic agent login failed: {exc}"

    out = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
    status = auth_status()
    if status["ok"]:
        who = status.get("email") or config.CURSOR_ACCOUNT_EMAIL or "cursor account"
        return True, f"Re-authenticated as {who}"
    return (
        False,
        "Automatic agent login did not finish in time. "
        f"Sign in once as {config.CURSOR_ACCOUNT_EMAIL} (browser), "
        "or set CURSOR_API_KEY in .env for fully unattended auth. "
        f"Detail: {out[-400:]}",
    )


def build_prompt(instruction: str, *, project_instructions: str = "") -> str:
    """Lead with the real user task so the model cannot miss it."""
    task = (instruction or "").strip()
    task = re.sub(
        r"^(yes|yeah|yep|sure|ok|okay|please|do it|go ahead)[,!.\s\-]*",
        "",
        task,
        flags=re.I,
    ).strip()
    if len(task) < 5:
        raise ValueError("Task instruction is empty after cleanup")

    parts = [
        "USER TASK (implement this now):",
        task,
        "",
        "CONSTRAINTS:",
        "- Work only inside this workspace.",
        "- Do not read or use credentials, .env secrets, production services, or deploy endpoints.",
        "- Do not run git push or deployment commands.",
        "- Make the code changes required to complete the user task.",
        "- When done, summarize what you changed and how to verify it.",
    ]
    if project_instructions.strip():
        parts.extend(["", "PROJECT NOTES:", project_instructions.strip()])
    return "\n".join(parts)


def run_agent(
    prompt: str,
    workspace: Path,
    *,
    task_id: str | None = None,
    on_pid: Any = None,
    on_heartbeat: Any = None,
    on_stream_event: Any = None,
    evidence: Any = None,
    resume_chat_id: str | None = None,
) -> tuple[str, int]:
    """Run Cursor CLI. Returns (summary_text, exit_code).

    When ``resume_chat_id`` is set, invokes ``agent --resume=<id>`` in the same
    workspace so follow-ups keep Cursor conversation context.
    """
    from orchestrator.agent_stream import StreamEvidence, make_line_handler
    from orchestrator.process import run_tracked

    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise RuntimeError(f"Workspace does not exist: {workspace}")

    task_path = workspace / TASK_FILE
    task_path.write_text(prompt, encoding="utf-8")
    # Keep the helper file out of git status noise in the worktree.
    exclude = workspace / ".git" / "info" / "exclude"
    try:
        if (workspace / ".git").exists():
            exclude.parent.mkdir(parents=True, exist_ok=True)
            existing = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
            if TASK_FILE not in existing.splitlines():
                with exclude.open("a", encoding="utf-8") as fh:
                    fh.write(f"\n{TASK_FILE}\n")
    except OSError:
        pass

    ok_auth, auth_detail = ensure_auth()
    if not ok_auth:
        raise RuntimeError(auth_detail)

    from orchestrator import isolation, quotas

    allowed, boundary_detail = isolation.live_agent_allowed()
    if not allowed:
        raise RuntimeError(boundary_detail)
    quotas.assert_agent_allowed()

    resume_id = (resume_chat_id or "").strip() or None
    pointer = CLI_POINTER
    if resume_id:
        pointer = (
            f"Read {TASK_FILE} for the follow-up USER TASK, then continue from "
            "our previous work in this workspace. Implement the follow-up now."
        )
    argv = build_argv(workspace, resume_chat_id=resume_id, prompt_pointer=pointer)
    log.info(
        "Running agent entry=%s prompt_chars=%s task_file=%s auth=%s task_id=%s fmt=%s boundary=%s",
        argv[:2],
        len(prompt),
        task_path,
        auth_detail,
        task_id,
        getattr(config, "AGENT_OUTPUT_FORMAT", "stream-json"),
        boundary_detail[:120],
    )

    stream_evidence = evidence if evidence is not None else StreamEvidence()
    on_line = None
    if getattr(config, "AGENT_OUTPUT_FORMAT", "stream-json") == "stream-json":
        on_line = make_line_handler(stream_evidence, on_event=on_stream_event)

    def _invoke() -> Any:
        # Do NOT pipe stdin: Cursor CLI treats a closed/piped stdin as empty input and
        # can exit with blank stdout. Full task text lives in TASK_FILE; argv is a
        # short Windows-safe pointer.
        agent_env = _agent_env(workspace)
        read_paths = []
        exe = Path(argv[0])
        if exe.is_file():
            read_paths.append(exe.parent)
            # cursor-agent layout: …/cursor-agent/versions/<ver>/{node.exe,index.js}
            # Grant the install root so sibling assets resolve under AppContainer.
            for parent in exe.parents:
                if parent.name.lower() == "cursor-agent":
                    read_paths.append(parent)
                    break
        for extra in argv[1:]:
            extra_path = Path(extra)
            if extra_path.suffix.lower() in {".js", ".mjs", ".cjs"} and extra_path.is_file():
                read_paths.append(extra_path.parent)
        if task_id:
            return run_tracked(
                task_id,
                argv,
                cwd=str(workspace),
                timeout=config.AGENT_TIMEOUT_SEC,
                env=agent_env,
                on_pid=on_pid,
                on_heartbeat=on_heartbeat,
                on_stdout_line=on_line,
                contained=isolation.use_container(),
                read_paths=read_paths,
                write_paths=[workspace],
            )
        return run(
            argv,
            cwd=str(workspace),
            timeout=config.AGENT_TIMEOUT_SEC,
            env=agent_env,
        )

    quotas.record("cursor_agent")
    result = _invoke()
    out = result.stdout or ""
    err = result.stderr or ""
    if result.returncode:
        detail = (err or out or f"exit code {result.returncode}").strip()
        if "TIMEOUT" in (err or "") or result.returncode == -9:
            raise RuntimeError(
                f"Cursor agent timed out after {config.AGENT_TIMEOUT_SEC}s. "
                f"Detail: {detail[-700:]}"
            )
        if re.search(r"sandbox.*(not available|requires macOS|requires linux)", detail, re.I):
            raise RuntimeError(
                "Cursor agent sandbox is enabled but unavailable on this OS. "
                "Set AGENT_SANDBOX=disabled in .env and run: agent sandbox disable"
            )
        if re.search(r"authentication required|agent login|not logged in|cursor_api_key", detail, re.I):
            ok_auth, auth_detail = ensure_auth(force_login=True)
            if ok_auth:
                log.warning("Auth recovered (%s); retrying agent once", auth_detail)
                result = _invoke()
                out = result.stdout or ""
                err = result.stderr or ""
                if not result.returncode:
                    text = (out or err).strip()
                    if text:
                        return text[-2200:], int(result.returncode or 0)
                    recovered = _summary_from_evidence(workspace, stream_evidence)
                    if recovered:
                        return recovered, int(result.returncode or 0)
            raise RuntimeError(
                "Cursor Agent authentication failed even after auto-login. "
                f"Use account {config.CURSOR_ACCOUNT_EMAIL}, or set CURSOR_API_KEY. "
                f"Detail: {detail[-700:]}"
            )
        raise RuntimeError("Cursor agent failed: " + detail[-1000:])
    text = _usable_agent_text(out, err, stream_evidence)
    if not text:
        recovered = _summary_from_evidence(workspace, stream_evidence)
        if recovered:
            log.warning(
                "Agent returned empty/unusable CLI output; recovering review summary from evidence"
            )
            return recovered, int(result.returncode or 0)
        # One automatic retry — Cursor occasionally exits 0 with blank stdout.
        log.warning("Empty agent output with no recoverable evidence; retrying once")
        result = _invoke()
        out = result.stdout or ""
        err = result.stderr or ""
        if result.returncode:
            detail = (err or out or f"exit code {result.returncode}").strip()
            raise RuntimeError("Cursor agent failed on empty-output retry: " + detail[-1000:])
        text = _usable_agent_text(out, err, stream_evidence)
        if not text:
            recovered = _summary_from_evidence(workspace, stream_evidence)
            if recovered:
                return recovered, int(result.returncode or 0)
            raise RuntimeError(
                "Cursor agent finished with empty output and no workspace changes "
                "after one automatic retry. "
                "Check AGENT_BIN / agent login / CURSOR_API_KEY, and that "
                "AGENT_SANDBOX=disabled on Windows."
            )
    if re.search(r"no software task was included|paste the actual task", text, re.I):
        raise RuntimeError(
            "Agent did not receive the user task (prompt delivery failure). "
            f"Check {TASK_FILE} in the workspace and agent spawn logs."
        )
    return text[-2200:], int(result.returncode or 0)


def list_modified_files(
    workspace: Path,
    branch: str,
    *,
    before_snapshot: dict[str, str] | None = None,
    since_ts: int | None = None,  # retained for callers; unused (content snapshot preferred)
) -> list[str]:
    """Return file paths changed in the workspace (git status or content snapshot)."""
    from orchestrator import workspace as ws

    return ws.list_changed_files(Path(workspace), branch, before=before_snapshot)


def _usable_agent_text(out: str, err: str, stream_evidence: Any) -> str:
    """Prefer stream result/text over raw stdout (often NDJSON noise)."""
    text = (out or err).strip()
    if getattr(stream_evidence, "result_text", None):
        return str(stream_evidence.result_text).strip()
    chunks = getattr(stream_evidence, "text_chunks", None) or []
    if chunks and (
        text.startswith("{") or getattr(config, "AGENT_OUTPUT_FORMAT", "") == "stream-json"
    ):
        return "\n".join(chunks)[-2200:].strip()
    if not text or (text.startswith("{") and "USER TASK" not in text):
        return ""
    return text


def _summary_from_evidence(workspace: Path, stream_evidence: Any | None = None) -> str:
    """Build a review summary when the CLI prints nothing but evidence exists."""
    recovered = _summary_from_workspace_changes(workspace)
    if recovered:
        return recovered
    if stream_evidence is None:
        return ""
    files = [
        str(p)
        for p in (getattr(stream_evidence, "files_touched", None) or [])
        if p and TASK_FILE not in str(p)
    ]
    tools = list(getattr(stream_evidence, "tool_calls", None) or [])[:12]
    if not files and not getattr(stream_evidence, "saw_write", False) and not tools:
        return ""
    parts = ["Agent completed (CLI printed no summary)."]
    if files:
        parts.append("Files touched (from stream evidence):")
        parts.extend(f"- {p}" for p in files[:30])
    elif tools:
        parts.append("Tool activity observed:")
        parts.extend(f"- {t}" for t in tools)
    return "\n".join(parts)[:2200]


def _summary_from_workspace_changes(workspace: Path) -> str:
    """Build a review summary when the CLI prints nothing but edited files.

    Git worktrees use ``git status``. Local snapshot workspaces rely on stream
    evidence (``_summary_from_evidence``) — mtime heuristics are too noisy after
    ``copytree``.
    """
    workspace = Path(workspace)
    status = run(["git", "-C", str(workspace), "status", "--short"], timeout=30)
    if status.returncode:
        return ""
    lines = [
        ln
        for ln in (status.stdout or "").splitlines()
        if TASK_FILE not in ln and ln.strip()
    ]
    if not lines:
        return ""
    body = "\n".join(lines)[:2000]
    return (
        "Agent completed (CLI printed no summary). Detected workspace changes:\n"
        f"{body}"
    )
