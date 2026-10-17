"""Pre-flight checks before queueing a coding task."""
from __future__ import annotations

import shutil
from pathlib import Path

from orchestrator import config
from orchestrator.process import run


def agent_available() -> tuple[bool, str]:
    bin_name = config.AGENT_BIN or "agent"
    resolved = shutil.which(bin_name)
    if not resolved:
        local = Path.home() / "AppData" / "Local" / "cursor-agent" / "agent.cmd"
        if local.is_file():
            return True, str(local)
        return False, f"Cursor CLI '{bin_name}' not found on PATH. Install from https://cursor.com/cli and run: agent login"
    return True, resolved


def project_ready(project_id: str, project_config: dict) -> tuple[bool, str]:
    path = Path(project_config["path"]).expanduser()
    try:
        source = path.resolve(strict=True)
    except FileNotFoundError:
        return False, f"Project path does not exist: {path}"
    if not source.is_dir():
        return False, f"Project path is not a directory: {path}"
    if project_config.get("type") == "git":
        git_dir = source / ".git"
        if not git_dir.exists():
            return False, f"{project_id}: marked as git but has no .git folder. Change type to local in projects.json."
        check = run(["git", "-C", str(source), "status", "--porcelain"], timeout=30)
        if check.returncode:
            return False, f"{project_id}: git status failed: {(check.stderr or check.stdout)[:300]}"
        if check.stdout.strip():
            dirty = len([ln for ln in check.stdout.splitlines() if ln.strip()])
            return (
                False,
                f"{project_id}: git working tree has {dirty} uncommitted change(s). "
                "Commit or stash in Laragon before running TASK (worktree requires a clean tree).",
            )
    if not config.DRY_RUN:
        ok, detail = agent_available()
        if not ok:
            return False, detail
    return True, "ok"
