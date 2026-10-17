"""Isolated task workspace creation and change summaries."""
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from pathlib import Path

from orchestrator import config
from orchestrator.process import run

log = logging.getLogger("orchestrator.workspace")

_SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    ".venv",
    "vendor",
    "data",
    "__pycache__",
    "public/build",
    "storage",
}
_SKIP_FILE_NAMES = {".orchestrator-task.md", ".env"}


def _under_work_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(config.WORK_ROOT.resolve())
        return True
    except ValueError:
        return False


def remove(
    target: Path | str,
    *,
    source: Path | str | None = None,
    branch: str | None = None,
) -> bool:
    """Remove an isolated workspace (git worktree + directory).

    Returns True when the path is gone (or was already gone). Retries and
    rename-aside on Windows so stale locks after a crashed agent do not block
    the next run with a workspace collision.
    """
    path = Path(target)
    if not path.exists():
        return True
    if not _under_work_root(path):
        log.warning("Refusing to remove path outside WORK_ROOT: %s", path)
        return False

    src = Path(source).expanduser().resolve() if source else None
    for attempt in range(1, 4):
        if _remove_once(path, source=src, branch=branch):
            return True
        log.warning("Workspace remove attempt %s/3 failed for %s", attempt, path)
        time.sleep(0.35 * attempt)

    # Last resort: move aside so setup can recreate the canonical path.
    if _quarantine(path):
        log.warning("Quarantined locked workspace %s so setup can continue", path)
        return True
    return False


def _remove_once(
    path: Path,
    *,
    source: Path | None,
    branch: str | None,
) -> bool:
    removed = False
    if source and source.is_dir() and (source / ".git").exists():
        result = run(
            ["git", "-C", str(source), "worktree", "remove", "--force", str(path.resolve())],
            timeout=90,
        )
        if result.returncode == 0:
            removed = True
        else:
            log.warning(
                "git worktree remove failed for %s: %s",
                path,
                (result.stderr or result.stdout or "")[-300:],
            )
            run(["git", "-C", str(source), "worktree", "prune"], timeout=60)
        if branch and branch.startswith("wa/"):
            # Best-effort: drop the ephemeral task branch if nothing else uses it.
            run(["git", "-C", str(source), "branch", "-D", branch], timeout=30)

    if path.exists():
        try:
            _rmtree_windows_safe(path)
            removed = True
        except OSError:
            log.exception("Failed to rmtree workspace %s", path)
            return False
    return removed or not path.exists()


def _quarantine(path: Path) -> bool:
    """Rename a stubborn workspace out of the way (still under WORK_ROOT)."""
    if not path.exists():
        return True
    if not _under_work_root(path):
        return False
    stamp = int(time.time())
    trash = path.with_name(f".trash-{path.name}-{stamp}")
    try:
        path.rename(trash)
    except OSError:
        log.exception("Failed to quarantine workspace %s → %s", path, trash)
        return False
    # Best-effort async cleanup of the trash folder.
    try:
        _rmtree_windows_safe(trash)
    except OSError:
        log.warning("Quarantined workspace left at %s (delete later)", trash)
    return not path.exists()


def _rmtree_windows_safe(path: Path) -> None:
    """``shutil.rmtree`` with readonly/lock-bit clearing (common on Windows worktrees)."""
    import os
    import stat

    def _onerror(func, p, _exc_info):  # noqa: ANN001
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            raise

    shutil.rmtree(path, onerror=_onerror)


def remove_for_task(
    task: dict,
    *,
    project_config: dict | None = None,
) -> bool:
    """Remove workspace recorded on a task row (and clear DB path when successful)."""
    raw = (task.get("workspace") or "").strip()
    if not raw:
        # Fall back to conventional WORK_ROOT/<task_id>
        candidate = config.WORK_ROOT / str(task["id"])
        if not candidate.exists():
            return True
        raw = str(candidate)

    source = None
    if project_config and project_config.get("path"):
        source = project_config["path"]
    ok = remove(raw, source=source, branch=task.get("branch") or None)
    if ok:
        from orchestrator import db, tasks

        tasks.update_task(task["id"], workspace=None)
        # Avoid bumping last_activity meaningfully for cleanup-only — still fine.
        _ = db.now()
    return ok


def setup(task_id: str, project_config: dict) -> tuple[Path, str]:
    """Create an isolated workspace. Returns ``(path, branch)``.

    Git sources may be dirty: ``git worktree add`` checks out HEAD into a new
    worktree and leaves the operator's uncommitted WIP untouched in the main tree.
    """
    source = Path(project_config["path"]).expanduser().resolve(strict=True)
    if not source.is_dir():
        raise ValueError("Project path must be a directory")
    target = config.WORK_ROOT / task_id
    if target.exists():
        # Stale leftover from a crashed/retried run — clear it for a fresh workspace.
        log.warning("Removing stale workspace before setup: %s", target)
        if not remove(target, source=source, branch=f"wa/{task_id}"):
            # One more quarantine-only attempt before failing the task.
            if not _quarantine(target):
                raise ValueError(
                    "Workspace collision: could not clear the previous isolated copy. "
                    "Clear chat or remove data/workspaces/" + task_id + " and try again."
                )
    if project_config.get("type") == "git":
        # Confirm git works; do not require a clean tree (dirty WIP stays in source).
        check = run(["git", "-C", str(source), "status", "--porcelain"], timeout=30)
        if check.returncode:
            detail = (check.stderr or check.stdout or "")[:300]
            raise ValueError(f"git status failed: {detail or 'unknown error'}")
        branch = f"wa/{task_id}"
        # If a previous run left the branch behind, delete it so worktree add -b succeeds.
        existing = run(["git", "-C", str(source), "rev-parse", "--verify", branch], timeout=20)
        if existing.returncode == 0:
            run(["git", "-C", str(source), "branch", "-D", branch], timeout=30)
        result = run(
            ["git", "-C", str(source), "worktree", "add", "-b", branch, str(target), "HEAD"],
            timeout=90,
        )
        if result.returncode:
            detail = (result.stderr or result.stdout or "")[-500:]
            raise RuntimeError(detail or "git worktree add failed")
        return target, branch
    if project_config.get("type") != "local":
        raise ValueError("Project type must be git or local")
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(
            ".git", "node_modules", ".venv", "vendor", ".env", ".env.*", "data"
        ),
    )
    return target, ""


def file_snapshot(target: Path) -> dict[str, str]:
    """Map relative path → sha256 for local change detection (content, not mtime)."""
    target = Path(target)
    out: dict[str, str] = {}
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(target).as_posix()
        if rel in _SKIP_FILE_NAMES or any(part in _SKIP_DIR_NAMES for part in Path(rel).parts):
            continue
        if any(rel.startswith(p + "/") for p in _SKIP_DIR_NAMES if "/" in p):
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        out[rel] = digest
    return out


def diff_snapshots(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Return sorted relative paths that were added, removed, or content-changed."""
    changed: list[str] = []
    for path, digest in after.items():
        if before.get(path) != digest:
            changed.append(path)
    for path in before:
        if path not in after:
            changed.append(path)
    return sorted(set(changed))[:200]


def list_changed_files(target: Path, branch: str, *, before: dict[str, str] | None = None) -> list[str]:
    """Evidence-based changed file list (git status or snapshot diff)."""
    target = Path(target)
    if branch:
        result = run(["git", "-C", str(target), "status", "--short"], timeout=30)
        files: list[str] = []
        for ln in (result.stdout or "").splitlines():
            if ".orchestrator-task.md" in ln or not ln.strip():
                continue
            path = ln[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1].strip()
            if path:
                files.append(path)
        return files
    if before is None:
        return []
    return diff_snapshots(before, file_snapshot(target))


def change_summary(target: Path, branch: str, *, before: dict[str, str] | None = None) -> str:
    if branch:
        result = run(["git", "-C", str(target), "status", "--short"], timeout=30)
        lines = [
            ln
            for ln in (result.stdout or "").splitlines()
            if ".orchestrator-task.md" not in ln
        ]
        text = "\n".join(lines).strip()
        return text[-2500:] if text else "No tracked changes detected"
    changed = list_changed_files(target, branch, before=before)
    if not changed:
        return "No content changes detected vs pre-agent snapshot"
    return "Local snapshot content changes:\n" + "\n".join(f" M {p}" for p in changed[:80])


def content_digest(target: Path, branch: str) -> str:
    """Stable-ish digest of current workspace changes for approval binding."""
    h = hashlib.sha256()
    if branch:
        diff = run(["git", "-C", str(target), "diff", "HEAD"], timeout=60)
        status = run(["git", "-C", str(target), "status", "--porcelain"], timeout=30)
        status_text = "\n".join(
            ln
            for ln in (status.stdout or "").splitlines()
            if ".orchestrator-task.md" not in ln
        )
        h.update((diff.stdout or "").encode("utf-8", errors="replace"))
        h.update(b"\0")
        h.update(status_text.encode("utf-8", errors="replace"))
    else:
        for path, digest in sorted(file_snapshot(target).items()):
            h.update(path.encode())
            h.update(b"\0")
            h.update(digest.encode())
            h.update(b"\0")
    return h.hexdigest()
