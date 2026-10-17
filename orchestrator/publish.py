"""Authorized publish operations (push / apply local / PR / deploy)."""
from __future__ import annotations

import logging
import re
import shlex
from pathlib import Path

from orchestrator import audit, projects, tasks, workspace
from orchestrator.isolation import publish_env
from orchestrator.process import run as process_run
from orchestrator.notify import send_text

log = logging.getLogger("orchestrator.publish")
run = process_run


def _run(argv: list[str], cwd=None, timeout: int = 60):
    return run(argv, cwd=cwd, timeout=timeout, env=publish_env())


def _github_owner_repo(remote_url: str) -> tuple[str, str] | None:
    url = (remote_url or "").strip()
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+?)(?:\.git)?$", url, re.I)
    if not m:
        return None
    return m.group(1), m.group(2)


def _pr_body(task: dict) -> str:
    instruction = (task.get("instruction") or "").strip() or "(no instruction recorded)"
    summary = (task.get("summary") or "").strip()
    # Prefer the review report; drop prior publish chatter if re-running PR.
    if summary.startswith("Committed ") or summary.startswith("Done for"):
        summary = ""
    lines = [
        "## Summary",
        instruction[:2000],
        "",
        f"- Orchestrator task: `{task['id']}`",
        f"- Project: `{task.get('project') or ''}`",
        f"- Branch: `{task.get('branch') or ''}`",
    ]
    if summary:
        lines.extend(["", "## Agent / test notes", summary[:3500]])
    lines.extend(
        [
            "",
            "## Test plan",
            "- [ ] Review the diff on this PR",
            "- [ ] Confirm recorded test output (if any) in the notes above",
            "- [ ] Verify no unrelated files changed",
        ]
    )
    return "\n".join(lines)


def _commit_workspace(task: dict, target: Path) -> str:
    """Commit approved changes in the isolated worktree. Returns short SHA."""
    helper = target / ".orchestrator-task.md"
    if helper.is_file():
        helper.unlink()
    diff = _run(["git", "status", "--porcelain"], cwd=target, timeout=30)
    real = [
        ln
        for ln in (diff.stdout or "").splitlines()
        if ln.strip() and ".orchestrator-task.md" not in ln
    ]
    if diff.returncode:
        raise RuntimeError((diff.stderr or "git status failed")[-700:])
    if not real:
        # Already committed on a prior partial publish — reuse HEAD.
        sha = _run(["git", "rev-parse", "--short", "HEAD"], cwd=target, timeout=10).stdout.strip()
        if not sha:
            raise ValueError("No changes to publish")
        return sha
    for argv in (
        ["git", "add", "-A"],
        [
            "git",
            "-c",
            "user.name=WhatsApp Cursor Agent",
            "-c",
            "user.email=automation@localhost",
            "commit",
            "-m",
            f"Task {task['id']}: approved changes",
        ],
    ):
        result = _run(argv, cwd=target, timeout=90)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout)[-700:])
    sha = _run(["git", "rev-parse", "--short", "HEAD"], cwd=target, timeout=10).stdout.strip()
    return sha


def _head_sha(target: Path) -> str:
    result = _run(["git", "rev-parse", "HEAD"], cwd=target, timeout=15)
    sha = (result.stdout or "").strip()
    if result.returncode or not sha:
        raise RuntimeError((result.stderr or "Could not read HEAD")[-300:])
    return sha


def _remote_sha(target: Path, branch: str) -> str | None:
    """Return the remote branch SHA, or None when origin has no such branch."""
    result = _run(
        ["git", "ls-remote", "origin", f"refs/heads/{branch}"],
        cwd=target,
        timeout=30,
    )
    if result.returncode:
        return None
    line = ((result.stdout or "").strip().splitlines() or [""])[0].strip()
    if not line:
        return None
    return line.split()[0]


def _host_label(target: Path) -> str:
    remote = _run(["git", "remote", "get-url", "origin"], cwd=target, timeout=10)
    if remote.returncode == 0 and "github.com" in remote.stdout.strip().lower():
        return "GitHub"
    return "origin"


def _push_branch(task: dict, target: Path) -> str:
    """Push only when the remote can fast-forward. Identical SHAs are a no-op."""
    label = _host_label(target)
    local = _head_sha(target)
    branch = task["branch"]
    remote = _remote_sha(target, branch)
    if remote and remote == local:
        return f"{label} branch already matches {branch} ({local[:7]}); push skipped"
    result = _run(
        ["git", "push", "origin", f"HEAD:refs/heads/{branch}"],
        cwd=target,
        timeout=120,
    )
    if result.returncode:
        text = (result.stderr or result.stdout or "")
        lowered = text.lower()
        if "non-fast-forward" in lowered or "[rejected]" in lowered or "rejected" in lowered:
            raise RuntimeError(
                f"Remote branch {branch} diverged; refusing non-fast-forward push. {text[-400:]}"
            )
        raise RuntimeError(text[-700:])
    confirmed = _remote_sha(target, branch)
    if confirmed and confirmed != local:
        raise RuntimeError(
            f"Push finished but remote {branch} is {confirmed[:7]}, not local {local[:7]}"
        )
    return f"{label} branch pushed: {branch} ({local[:7]})"


def _create_pull_request(task: dict, target: Path, project_config: dict) -> str:
    """Create a GitHub PR for the task branch via `gh`. Requires gh auth."""
    base = (project_config.get("default_branch") or "main").strip() or "main"
    head = (task.get("branch") or "").strip()
    if not head:
        raise ValueError("No task branch for pull request")

    title_src = (task.get("instruction") or "approved changes").strip().replace("\n", " ")
    title = f"Task {task['id']}: {title_src[:72]}"
    body = _pr_body(task)

    result = _run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            base,
            "--head",
            head,
            "--title",
            title,
            "--body",
            body,
        ],
        cwd=target,
        timeout=120,
    )
    out = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    if result.returncode == 0:
        # gh prints the PR URL on the last line
        url = ""
        for line in reversed((result.stdout or "").splitlines()):
            if line.strip().startswith("http"):
                url = line.strip()
                break
        return f"Pull request created: {url}" if url else "Pull request created"

    lowered = out.lower()
    if "already exists" in lowered:
        viewed = _run(
            ["gh", "pr", "view", head, "--json", "url", "--jq", ".url"],
            cwd=target,
            timeout=30,
        )
        url = (viewed.stdout or "").strip()
        if url:
            return f"Pull request already exists: {url}"
        return f"Pull request already exists for {head}"

    remote = _run(["git", "remote", "get-url", "origin"], cwd=target, timeout=10)
    compare = ""
    if remote.returncode == 0:
        parsed = _github_owner_repo(remote.stdout.strip())
        if parsed:
            owner, repo = parsed
            compare = f"https://github.com/{owner}/{repo}/compare/{base}...{head}?expand=1"

    detail = out[-500:] if out else "gh pr create failed"
    if compare:
        raise RuntimeError(
            f"Could not create pull request ({detail}). "
            f"Branch is on the remote — open manually: {compare}"
        )
    raise RuntimeError(f"Could not create pull request: {detail}")


def apply_to_local(task: dict, project_config: dict) -> str:
    """Fast-forward (or merge) the task branch into the user's local project checkout."""
    source = Path(project_config["path"]).expanduser().resolve()
    branch = (task.get("branch") or "").strip()
    if not branch:
        raise ValueError("No task branch to apply locally")
    if not source.is_dir() or not (source / ".git").exists() and not (source / ".git").is_file():
        # worktrees use .git file; still "exists"
        if not (source / ".git").exists():
            raise ValueError(f"Local project path is not a git repo: {source}")

    dirty = _run(["git", "status", "--porcelain"], cwd=source, timeout=30)
    if dirty.returncode:
        raise RuntimeError(f"git status failed in {source}: {(dirty.stderr or '')[:300]}")
    if dirty.stdout.strip():
        raise ValueError(
            f"Your local project at {source} has uncommitted changes. "
            f"Stash or commit them, then say \"apply locally\" again for task {task['id']}."
        )

    # Ensure the branch ref is visible from the main checkout (shared object store / worktree).
    show = _run(["git", "rev-parse", "--verify", branch], cwd=source, timeout=30)
    if show.returncode:
        # Try the worktree path as a commit-ish
        ws = Path(task["workspace"]).resolve()
        tip = _run(["git", "rev-parse", "HEAD"], cwd=ws, timeout=30)
        if tip.returncode:
            raise RuntimeError(f"Cannot resolve branch {branch} in {source}")
        branch = tip.stdout.strip()

    current = _run(["git", "branch", "--show-current"], cwd=source, timeout=15).stdout.strip() or "HEAD"
    backup = _backup_checkout(source, str(task.get("id") or "task"))
    merged = _run(["git", "merge", "--ff-only", branch], cwd=source, timeout=60)
    if merged.returncode:
        merged = _run(["git", "merge", "--no-edit", branch], cwd=source, timeout=60)
        if merged.returncode:
            _run(["git", "merge", "--abort"], cwd=source, timeout=30)
            raise RuntimeError(
                f"Could not merge into local {current}: {(merged.stderr or merged.stdout)[-700:]} "
                f"The checkout was left unchanged. Backup: {backup}"
            )
        mode = "merged"
    else:
        mode = "fast-forwarded"
    return f"Local project {mode}: {source} ({current} ← {task.get('branch') or branch}). Backup: {backup}"


def _backup_checkout(source: Path, task_id: str) -> Path:
    """Bundle HEAD before applying. Apply is refused when the bundle cannot be written."""
    from orchestrator import config

    dest = config.WORK_ROOT / "backups" / task_id
    dest.mkdir(parents=True, exist_ok=True)
    sha = _run(["git", "rev-parse", "HEAD"], cwd=source, timeout=15)
    (dest / "HEAD").write_text((sha.stdout or "").strip(), encoding="utf-8")
    bundle = dest / "pre-apply.bundle"
    if bundle.exists():
        bundle.unlink()
    bundled = _run(["git", "bundle", "create", str(bundle), "HEAD"], cwd=source, timeout=60)
    if bundled.returncode or not bundle.is_file():
        raise RuntimeError(
            "Refusing to apply without a backup bundle: "
            + (bundled.stderr or bundled.stdout or "git bundle failed")[-300:]
        )
    return bundle


def _worktree_clean(target: Path) -> bool:
    status = _run(["git", "status", "--porcelain"], cwd=target, timeout=30)
    lines = [
        ln
        for ln in (status.stdout or "").splitlines()
        if ln.strip() and ".orchestrator-task.md" not in ln
    ]
    return status.returncode == 0 and not lines


def publish(
    task: dict,
    project_config: dict,
    action: str,
    *,
    job_id: int | None = None,
    fence: str | None = None,
) -> None:
    from orchestrator import config as cfg
    from orchestrator import queue

    if job_id is not None and fence and not queue.fence_matches(job_id, fence):
        return
    target = Path(task["workspace"])
    try:
        if action == "DEPLOY":
            if not getattr(cfg, "DEPLOY_ENABLED", False):
                raise RuntimeError(
                    "Production deploy is disabled. Keep allow_deploy false until "
                    "health checks and rollback exist."
                )
            command = shlex.split(project_config["deploy_command"])
            result = _run(command, cwd=str(target), timeout=600)
            if result.returncode:
                raise RuntimeError((result.stderr + result.stdout)[-850:])
            detail = (
                "Deployment command exited successfully. "
                "Independently verify running service, health, and version."
            )
        else:
            # PUSH, APPLY, or PR — commit only when the review digest still matches.
            if project_config.get("type") != "git" or not task.get("branch"):
                raise ValueError("Only git worktree tasks can be approved for push/apply/PR")
            expected = (task.get("content_digest") or "").strip()
            approved = (task.get("approved_sha") or "").strip()
            head = ""
            try:
                head = _head_sha(target)
            except RuntimeError:
                head = ""
            if approved and head == approved and _worktree_clean(target):
                sha = approved[:12]
            else:
                if not expected:
                    raise ValueError(
                        "Refusing to publish: task has no approval content digest."
                    )
                current = workspace.content_digest(target, task.get("branch") or "")
                if current != expected:
                    raise ValueError(
                        "Workspace changed since review; approval digest mismatch. "
                        "Re-run or re-review before publishing."
                    )
                sha = _commit_workspace(task, target)
                full = _head_sha(target)
                tasks.update_task(task["id"], approved_sha=full)
                task = dict(task)
                task["approved_sha"] = full

            parts: list[str] = [f"Committed {sha} on {task['branch']}"]
            errors: list[str] = []

            do_push = False
            do_pr = False
            do_apply = False
            if action == "APPLY":
                do_apply = True
            elif action == "PR":
                if not project_config.get("allow_push"):
                    raise ValueError(
                        "Pull requests require allow_push so the review branch can reach GitHub."
                    )
                do_push = True
                do_pr = True
                do_apply = bool(project_config.get("apply_local", True))
            elif action == "PUSH":
                do_push = bool(project_config.get("allow_push"))
                do_apply = bool(project_config.get("apply_local", True))
                if not do_push:
                    # Still apply locally when push is disabled — matches user expectation.
                    do_apply = True
            else:
                raise ValueError(f"Unknown publish action: {action}")

            if not do_push and not do_apply and not do_pr:
                raise ValueError(
                    "Nothing to do: allow_push is off and apply_local is off for this project."
                )

            if do_push:
                try:
                    parts.append(_push_branch(task, target))
                except Exception as exc:
                    errors.append(f"Push failed: {exc}")

            if do_pr:
                if any(e.startswith("Push failed:") for e in errors):
                    raise RuntimeError(" | ".join(errors))
                # PR failure is hard — user asked for a pull request.
                parts.append(_create_pull_request(task, target, project_config))

            if do_apply:
                try:
                    parts.append(apply_to_local(task, project_config))
                except Exception as exc:
                    errors.append(f"Local apply failed: {exc}")

            if errors and len(errors) == (int(do_push) + int(do_apply)):
                raise RuntimeError(" | ".join(errors))

            detail = ". ".join(parts) + "."
            if errors:
                detail += " Warnings: " + " | ".join(errors)
            detail += " No production deploy was run."

        tasks.update_task(task["id"], status="published", summary=detail[:4500])
        audit.record(
            "publish_succeeded",
            actor=task["sender"],
            task_id=task["id"],
            detail={"action": action},
        )
        send_text(task["sender"], f"Done for task {task['id']}. {detail}", level="success")
    except Exception as exc:
        log.exception("Publication failed")
        tasks.update_task(task["id"], status="publish_failed", summary=str(exc)[:1000])
        audit.record(
            "publish_failed",
            actor=task["sender"],
            task_id=task["id"],
            detail={"action": action, "error": str(exc)[:300]},
            ok=False,
        )
        send_text(
            task["sender"],
            f"That didn't work for task {task['id']}:\n{str(exc)[:650]}\n\n"
            "You can ask me to show the task status or try again after fixing the issue.",
            level="error",
        )


def start_publish(task_id: str, action: str) -> None:
    """Claim review→publishing then run publish (used by handler / job worker)."""
    task = tasks.get_task(task_id)
    if not task:
        return
    project_config = projects.projects().get(task["project"], {})
    publish(task, project_config, action)
