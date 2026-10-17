"""Task execution pipeline with evidence-backed stages and events."""
from __future__ import annotations

import logging
import re
import shlex
from pathlib import Path

from orchestrator import agent, audit, config, db, projects, queue, task_events, tasks, workspace
from orchestrator.notify import send_text
from orchestrator.process import run, tracked_info
from orchestrator.scrub import scrub

log = logging.getLogger("orchestrator.execute")

# Deduplicate milestone chat spam per task+event_type
_milestone_sent: set[str] = set()


def _notify_milestone(sender: str, task_id: str, key: str, text: str, *, level: str = "info") -> None:
    """Chat update for meaningful stage transitions only (no spam)."""
    token = f"{task_id}:{key}"
    if token in _milestone_sent:
        return
    _milestone_sent.add(token)
    send_text(sender, text, level=level)


def _cancelled(task_id: str) -> bool:
    latest = tasks.get_task(task_id)
    if not latest:
        return True
    if latest["status"] == "failed" and (latest.get("summary") or "").startswith("Cancelled"):
        return True
    if latest.get("execution_stage") == "canceled":
        return True
    return False


def execute_task(task_id: str, *, job_id: int | None = None, fence: str | None = None) -> None:
    task = tasks.get_task(task_id)
    if not task:
        return
    project_config = projects.projects().get(task["project"])
    if not project_config:
        tasks.update_task(
            task_id,
            status="failed",
            execution_stage="failed",
            summary="Project not registered",
            blocker="Project not registered",
            ended_at=db.now(),
        )
        task_events.record(task_id, "failed", "Project not registered", stage="failed")
        audit.record("execute_failed", task_id=task_id, detail={"reason": "missing_project"}, ok=False)
        return

    sender = task["sender"]
    project = task["project"]

    try:
        now = db.now()
        tasks.update_task(
            task_id,
            status="running",
            execution_stage="preparing_workspace",
            started_at=now,
            last_activity_at=now,
            blocker=None,
        )
        task_events.record(
            task_id,
            "workspace_preparing",
            f"Preparing isolated workspace for {project}",
            stage="preparing_workspace",
        )
        audit.record(
            "execute_started",
            actor=sender,
            task_id=task_id,
            detail={"project": project},
        )

        resume_chat_id = (task.get("agent_chat_id") or "").strip()
        reuse_workspace = (
            int(task.get("revision") or 1) > 1
            and bool(resume_chat_id)
            and tasks.can_resume_agent(task)
        )
        if reuse_workspace:
            target = Path(str(task["workspace"])).resolve()
            branch = str(task.get("branch") or "")
            task_events.record(
                task_id,
                "workspace_reused",
                f"Reusing workspace for Cursor --resume ({target.name})"
                + (f" branch {branch}" if branch else ""),
                stage="preparing_workspace",
                detail={
                    "workspace": str(target),
                    "branch": branch or None,
                    "agent_chat_id": resume_chat_id[:64],
                    "revision": int(task.get("revision") or 1),
                },
            )
            _notify_milestone(
                sender,
                task_id,
                "workspace_reused",
                f"Continuing on {project} in the same isolated workspace "
                f"(Cursor session resume, revision {int(task.get('revision') or 1)}).",
            )
        else:
            resume_chat_id = ""
            target, branch = workspace.setup(task_id, project_config)
            tasks.update_task(task_id, workspace=str(target), branch=branch)
            task_events.record(
                task_id,
                "workspace_ready",
                f"Workspace ready at {target.name}" + (f" (branch {branch})" if branch else ""),
                stage="preparing_workspace",
                detail={"workspace": str(target), "branch": branch or None},
            )
            _notify_milestone(
                sender,
                task_id,
                "workspace_ready",
                f"Workspace ready for {project} (isolated copy). Next: start Cursor agent process.",
            )

        if _cancelled(task_id):
            return

        prompt = agent.build_prompt(
            task["instruction"],
            project_instructions=str(project_config.get("instructions") or ""),
        )
        if reuse_workspace:
            prompt = (
                "FOLLOW-UP TURN (continue prior agent session in this workspace):\n"
                + prompt
            )

        before_snapshot = workspace.file_snapshot(target) if not branch else None

        if config.DRY_RUN:
            task_events.record(
                task_id,
                "dry_run",
                "Dry-run: workspace prepared; Cursor agent not invoked",
                stage="preparing_workspace",
            )
            agent_result = "DRY RUN: Workspace created; coding agent deliberately not invoked."
            exit_code = 0
            modified: list[str] = []
        else:
            from orchestrator.agent_stream import StreamEvidence, stage_from_evidence

            evidence = StreamEvidence()
            # Honest default: process alive without tool stream evidence yet.
            tasks.set_stage(task_id, "agent_running")
            task_events.record(
                task_id,
                "agent_started",
                "Cursor agent process started — awaiting stream-json tool evidence",
                stage="agent_running",
            )
            _notify_milestone(
                sender,
                task_id,
                "agent_started",
                f"Cursor agent process started on {project}. "
                f"{task_events.AGENT_UNAVAILABLE_DETAIL} "
                "Stream events will be recorded when the CLI emits them.",
            )

            def _on_pid(pid: int) -> None:
                tasks.update_task(task_id, agent_pid=pid)
                task_events.record(
                    task_id,
                    "agent_pid",
                    f"Cursor agent pid={pid}",
                    stage="agent_running",
                    detail={"pid": pid},
                )

            def _on_heartbeat(info: dict) -> None:
                tasks.touch(task_id)
                if job_id is not None:
                    queue.renew_lease(job_id, fence)
                if _cancelled(task_id):
                    from orchestrator.process import cancel_tracked

                    cancel_tracked(task_id)

            _stream_event_count = {"n": 0}

            def _on_stream_event(ev: dict) -> None:
                # Rate-limit event rows; still allow stage upgrades from evidence.
                _stream_event_count["n"] += 1
                msg = str(ev.get("message") or ev.get("kind") or "stream")[:400]
                stage_now = (tasks.get_task(task_id) or {}).get("execution_stage") or "agent_running"
                keep = (
                    _stream_event_count["n"] <= 60
                    or ev.get("write")
                    or ev.get("kind") == "result"
                    or (ev.get("kind") == "tool" and ev.get("path"))
                    or ev.get("kind") == "assistant"
                )
                if keep:
                    task_events.record(
                        task_id,
                        "agent_stream",
                        msg,
                        stage=stage_now,
                        detail={
                            k: ev.get(k)
                            for k in ("kind", "tool", "path", "write")
                            if ev.get(k) is not None
                        },
                    )
                tasks.touch(task_id)
                upgrade = stage_from_evidence(evidence)
                if upgrade and upgrade != stage_now:
                    tasks.set_stage(task_id, upgrade)
                    task_events.record(
                        task_id,
                        "stage_evidence",
                        f"Stage advanced to {upgrade} from Cursor stream evidence",
                        stage=upgrade,
                    )
                    if upgrade == "investigating":
                        _notify_milestone(
                            sender,
                            task_id,
                            "investigating",
                            f"Stream evidence: agent is reading/searching files in {project}.",
                        )
                    elif upgrade == "implementing":
                        _notify_milestone(
                            sender,
                            task_id,
                            "implementing",
                            f"Stream evidence: agent is writing/editing files in {project}.",
                        )

            agent_result, exit_code = agent.run_agent(
                prompt,
                target,
                task_id=task_id,
                on_pid=_on_pid,
                on_heartbeat=_on_heartbeat,
                on_stream_event=_on_stream_event,
                evidence=evidence,
                resume_chat_id=resume_chat_id or None,
            )
            session_id = (getattr(evidence, "session_id", None) or "").strip()
            update_fields: dict = {"exit_code": exit_code, "agent_pid": None}
            if session_id:
                update_fields["agent_chat_id"] = session_id
            tasks.update_task(task_id, **update_fields)
            cur_stage = (tasks.get_task(task_id) or {}).get("execution_stage") or "agent_running"
            task_events.record(
                task_id,
                "agent_exited",
                f"Cursor agent process exited with code {exit_code}",
                stage=cur_stage,
                detail={
                    "exit_code": exit_code,
                    "stream_events": evidence.raw_events,
                    "tools": evidence.tool_calls[:20],
                    "session_id": session_id or None,
                    "resumed": bool(resume_chat_id),
                },
            )

            if _cancelled(task_id):
                return

            modified = agent.list_modified_files(
                target, branch, before_snapshot=before_snapshot
            )
            if modified:
                tasks.update_task(task_id, modified_files=modified)
                task_events.record(
                    task_id,
                    "files_changed",
                    f"Workspace evidence: {len(modified)} modified file(s)",
                    stage=(tasks.get_task(task_id) or {}).get("execution_stage") or "agent_running",
                    detail={"files": modified[:50]},
                )
                _notify_milestone(
                    sender,
                    task_id,
                    "files_changed",
                    f"Detected {len(modified)} changed file(s) in the isolated workspace for {project}.",
                )

        if _cancelled(task_id):
            return

        test_output = "Tests not configured"
        if project_config.get("test_command") and not config.DRY_RUN:
            tasks.set_stage(task_id, "testing")
            task_events.record(
                task_id,
                "tests_started",
                "Running configured project tests",
                stage="testing",
            )
            _notify_milestone(
                sender,
                task_id,
                "tests_started",
                f"Running configured tests for {project}.",
            )
            test = run(shlex.split(project_config["test_command"]), cwd=str(target), timeout=300)
            test_output = ("PASS" if test.returncode == 0 else "FAIL") + ": " + (
                test.stdout + test.stderr
            )[-700:]
            task_events.record(
                task_id,
                "tests_completed",
                f"Tests {'passed' if test.returncode == 0 else 'failed'} (exit {test.returncode})",
                stage="testing",
                detail={"exit_code": test.returncode},
            )
            if not modified:
                modified = agent.list_modified_files(
                    target, branch, before_snapshot=before_snapshot
                )
                if modified:
                    tasks.update_task(task_id, modified_files=modified)

        digest = workspace.content_digest(target, branch)
        report = scrub(
            f"Agent: {agent_result}\nTests: {test_output}\n"
            f"Changes: {workspace.change_summary(target, branch, before=before_snapshot)}"
        )
        if job_id is not None and fence and not queue.fence_matches(job_id, fence):
            return
        if _cancelled(task_id):
            return
        ended = db.now()
        latest = tasks.get_task(task_id)
        won = tasks.cas_update(
            task_id,
            "running",
            status="review",
            execution_stage="ready_for_review",
            summary=report[:4500],
            content_digest=digest,
            ended_at=ended,
            last_activity_at=ended,
            modified_files=modified or (latest.get("modified_files") if latest else None),
        )
        if not won:
            return
        task_events.record(
            task_id,
            "ready_for_review",
            "Coding complete — ready for review",
            stage="ready_for_review",
            detail={"digest_prefix": digest[:16], "files": len(modified or [])},
        )
        audit.record(
            "execute_review",
            actor=sender,
            task_id=task_id,
            detail={"digest_prefix": digest[:16], "dry_run": config.DRY_RUN, "branch": branch or None},
        )
        approve_hint = 'say "approve and push"'
        if project_config.get("type") == "git" and project_config.get("apply_local", True):
            if project_config.get("allow_push"):
                approve_hint = (
                    'say "approve and push" (local folder + review branch), '
                    'or "create a pull request" (branch + GitHub PR)'
                )
            else:
                approve_hint = (
                    'say "approve and apply" or "apply locally" (updates your local project folder)'
                )
        file_bits = ""
        if modified:
            preview = ", ".join(modified[:8])
            more = f" (+{len(modified) - 8} more)" if len(modified) > 8 else ""
            file_bits = f"\n\nFiles changed: {preview}{more}"
        if config.DRY_RUN:
            send_text(
                sender,
                f"Workspace is ready for {project} (practice/dry-run — I skipped the coding agent). "
                "Say if you want a live run next.",
                level="success",
            )
        else:
            send_text(
                sender,
                f"Finished working on {project} — ready for your review.\n\n"
                f"{report[:2000]}{file_bits}\n\n"
                "Isolated workspace only so far — your project folder is unchanged until you approve.\n"
                f"If this looks good, {approve_hint}. "
                'If not, say "reject that".',
                level="success",
            )
    except Exception as exc:
        log.exception("Task failed")
        err = str(exc)[:1000]
        stage = "timeout" if re.search(r"timed out", err, re.I) else "failed"
        live = tracked_info(task_id)
        tasks.update_task(
            task_id,
            status="failed",
            execution_stage=stage,
            summary=err[:1000],
            blocker=err[:500],
            ended_at=db.now(),
            agent_pid=None,
        )
        task_events.record(
            task_id,
            "failed" if stage == "failed" else "timeout",
            err[:800],
            stage=stage,
            detail={"process": live} if live else None,
        )
        audit.record(
            "execute_failed",
            actor=sender,
            task_id=task_id,
            detail={"error": err[:300]},
            ok=False,
        )
        short = err[:350]
        if re.search(
            r"authentication required|agent login|not logged in|cursor_api_key|"
            r"auto-login|re-authenticated|CURSOR_ACCOUNT_EMAIL",
            short,
            re.I,
        ):
            account = config.CURSOR_ACCOUNT_EMAIL or "your Cursor account"
            msg = (
                f"I couldn't start coding on {project} because Cursor Agent "
                f"isn't authenticated for {account}.\n\n"
                "I already tried automatic login. If this keeps happening, add a "
                "CURSOR_API_KEY from that Cursor account to the orchestrator .env "
                "(Dashboard → API Keys), then ask me again."
            )
        elif re.search(r"workspace collision", short, re.I):
            msg = (
                f"I couldn't start coding on {project} because a previous isolated "
                "workspace is still locked on disk.\n\n"
                'Say "clear chat" to remove stale workspaces for this project, then '
                'retry with "continue working".'
            )
        elif re.search(r"empty output", short, re.I):
            msg = (
                f"Cursor Agent exited without a usable summary on {project} "
                "(and no file changes were detected).\n\n"
                "I already retried once. Check that the agent CLI is logged in "
                "(or CURSOR_API_KEY is set) and AGENT_SANDBOX=disabled on Windows, "
                'then say "continue working".'
            )
        else:
            msg = (
                f"Sorry — the work on {project} didn't finish:\n{short}\n\n"
                'Ask "why is it stuck?" for a health check, or "continue working" to retry.'
            )
        send_text(sender, msg, level="error")
