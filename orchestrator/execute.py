"""Task execution pipeline with evidence-backed stages and events."""
from __future__ import annotations

import logging
import re
import shlex
import threading
from pathlib import Path

from orchestrator import agent, audit, config, db, projects, queue, task_events, tasks, workspace
from orchestrator.notify import send_text
from orchestrator.process import run, tracked_info
from orchestrator.scrub import scrub

log = logging.getLogger("orchestrator.execute")

# Deduplicate milestone activity markers per task+event_type (chat stays quiet).
_milestone_sent: set[str] = set()


def _notify_milestone(sender: str, task_id: str, key: str, text: str, *, level: str = "info") -> None:
    """Record stage milestones for Activity only — do not spam chat.

    Callers already ``task_events.record`` the durable event. Chat gets a single
    ack from task creation and one outcome message when coding finishes/fails.
    """
    del sender, text, level  # reserved for signature compatibility / future hooks
    token = f"{task_id}:{key}"
    if token in _milestone_sent:
        return
    _milestone_sent.add(token)
    log.debug("Activity milestone %s (chat suppressed)", token)


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

        from orchestrator import attachments as chat_attachments

        attach_paths: list[str] = []
        try:
            attach_paths = chat_attachments.materialize_into_workspace(
                target, task.get("attachments")
            )
        except ValueError as exc:
            task_events.record(
                task_id,
                "attachments_rejected",
                f"Attachment rejected: {exc}",
                stage="preparing_workspace",
            )
            attach_paths = []
        if attach_paths:
            task_events.record(
                task_id,
                "attachments_ready",
                f"Copied {len(attach_paths)} image attachment(s) into workspace for agent context",
                stage="preparing_workspace",
                detail={"paths": attach_paths},
            )

        # Snapshot after attachments so copied images are not reported as agent edits.
        before_snapshot = workspace.file_snapshot(target) if not branch else None

        learned = ""
        try:
            from orchestrator import learning

            learned = learning.format_playbook_section(
                str(task.get("project") or ""),
                instruction=str(task.get("instruction") or ""),
            )
        except Exception:  # noqa: BLE001
            learned = ""
        prompt = agent.build_prompt(
            task["instruction"],
            project_instructions=str(project_config.get("instructions") or ""),
            learned_memory=learned,
            attachment_paths=attach_paths,
        )
        if reuse_workspace:
            prompt = (
                "FOLLOW-UP TURN (continue prior agent session in this workspace):\n"
                + prompt
            )

        salvaged_disconnect = False
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
            # Do not claim the process started until on_pid — ACL/auth prep can
            # take minutes and cancel must still be able to interrupt it.
            tasks.set_stage(task_id, "agent_running")
            task_events.record(
                task_id,
                "agent_starting",
                task_events.AGENT_STARTING_DETAIL,
                stage="agent_running",
            )
            _notify_milestone(
                sender,
                task_id,
                "agent_starting",
                f"Starting Cursor agent on {project}. "
                f"{task_events.AGENT_STARTING_DETAIL}",
            )

            def _on_pid(pid: int) -> None:
                tasks.update_task(task_id, agent_pid=pid)
                task_events.record(
                    task_id,
                    "agent_started",
                    "Cursor agent process started — awaiting stream-json tool evidence",
                    stage="agent_running",
                    detail={"pid": pid},
                )
                task_events.record(
                    task_id,
                    "agent_pid",
                    f"Cursor agent pid={pid}",
                    stage="agent_running",
                    detail={"pid": pid},
                )
                _notify_milestone(
                    sender,
                    task_id,
                    "agent_started",
                    f"Cursor agent process started on {project} (pid {pid}). "
                    f"{task_events.AGENT_UNAVAILABLE_DETAIL} "
                    "Stream events will be recorded when the CLI emits them.",
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

            stop_prep = threading.Event()

            def _prep_heartbeat() -> None:
                """Renew lease + honor cancel while auth/ACL runs (before pid)."""
                while not stop_prep.wait(5.0):
                    tasks.touch(task_id)
                    if job_id is not None:
                        queue.renew_lease(job_id, fence)
                    if _cancelled(task_id):
                        from orchestrator.process import cancel_tracked

                        cancel_tracked(task_id)
                        return

            prep_thread = threading.Thread(
                target=_prep_heartbeat,
                name=f"agent-prep-{task_id}",
                daemon=True,
            )
            prep_thread.start()
            agent_exc: BaseException | None = None
            try:
                if _cancelled(task_id):
                    raise RuntimeError("Cancelled before Cursor agent start")
                try:
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
                except Exception as exc:  # noqa: BLE001
                    agent_exc = exc
                    agent_result = ""
                    exit_code = -1
            finally:
                stop_prep.set()
                prep_thread.join(timeout=2)

            session_id = (getattr(evidence, "session_id", None) or "").strip()
            update_fields: dict = {"exit_code": exit_code, "agent_pid": None}
            if session_id:
                update_fields["agent_chat_id"] = session_id
            tasks.update_task(task_id, **update_fields)
            cur_stage = (tasks.get_task(task_id) or {}).get("execution_stage") or "agent_running"
            task_events.record(
                task_id,
                "agent_exited",
                (
                    f"Cursor agent process exited with code {exit_code}"
                    if agent_exc is None
                    else f"Cursor agent ended abnormally: {str(agent_exc)[:400]}"
                ),
                stage=cur_stage,
                detail={
                    "exit_code": exit_code,
                    "stream_events": evidence.raw_events,
                    "tools": evidence.tool_calls[:20],
                    "session_id": session_id or None,
                    "resumed": bool(resume_chat_id),
                    "error": (str(agent_exc)[:300] if agent_exc else None),
                },
            )

            if _cancelled(task_id):
                if agent_exc is not None:
                    raise agent_exc
                return

            modified = agent.list_modified_files(
                target, branch, before_snapshot=before_snapshot
            )
            saw_write = bool(getattr(evidence, "saw_write", False))
            if agent_exc is not None:
                # Disconnect / crash after edits: keep changes approvable instead of failed.
                if modified or saw_write:
                    salvaged_disconnect = True
                    err_short = str(agent_exc)[:500]
                    if not modified and saw_write:
                        # Prefer paths from stream evidence when snapshot/git lag.
                        touched = [
                            str(p)
                            for p in (getattr(evidence, "files_touched", None) or [])
                            if p and agent.TASK_FILE not in str(p)
                        ]
                        if touched:
                            modified = touched
                    agent_result = (
                        "Agent ended abnormally (changes preserved in isolated workspace): "
                        + err_short
                    )
                    task_events.record(
                        task_id,
                        "agent_salvaged",
                        f"Salvaged {len(modified)} changed file(s) after agent failure",
                        stage=cur_stage,
                        detail={"files": modified[:50], "error": err_short[:300]},
                    )
                    log.warning(
                        "Salvaging task %s after agent failure (%s file(s))",
                        task_id,
                        len(modified),
                    )
                else:
                    raise agent_exc

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
        tests_failed = bool(
            project_config.get("test_command")
            and not config.DRY_RUN
            and test_output.startswith("FAIL:")
        )
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
        if tests_failed:
            review_blocker = (
                "Configured tests failed — review the test output carefully before approving."
            )
        elif salvaged_disconnect:
            review_blocker = (
                "Agent ended abnormally; workspace changes were preserved for your review."
            )
        else:
            review_blocker = None
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
            blocker=review_blocker,
        )
        if not won:
            return
        if salvaged_disconnect:
            review_label = "Agent ended abnormally — changes preserved for review"
        elif tests_failed:
            review_label = "Coding complete — ready for review (tests failed)"
        else:
            review_label = "Coding complete — ready for review"
        task_events.record(
            task_id,
            "ready_for_review",
            review_label,
            stage="ready_for_review",
            detail={
                "digest_prefix": digest[:16],
                "files": len(modified or []),
                "tests_failed": tests_failed,
                "salvaged": salvaged_disconnect,
            },
        )
        audit.record(
            "execute_review",
            actor=sender,
            task_id=task_id,
            detail={
                "digest_prefix": digest[:16],
                "dry_run": config.DRY_RUN,
                "branch": branch or None,
                "salvaged": salvaged_disconnect,
            },
        )
        if project_config.get("type") == "git" and project_config.get("apply_local", True):
            if project_config.get("allow_push"):
                next_step = (
                    'NEXT: tap Approve & apply (or say "approve and push") to update '
                    "your local folder and review branch — or say \"create a pull request\". "
                    'Say "reject that" to discard.'
                )
            else:
                next_step = (
                    'NEXT: tap Approve & apply (or say "approve and apply") to copy '
                    "these changes into your real project folder. "
                    'Say "reject that" to discard.'
                )
        else:
            next_step = (
                'NEXT: tap Approve & apply (or say "approve and push") when ready. '
                'Say "reject that" to discard.'
            )
        file_bits = ""
        if modified:
            preview = ", ".join(modified[:8])
            more = f" (+{len(modified) - 8} more)" if len(modified) > 8 else ""
            file_bits = f"\n\nFiles changed: {preview}{more}"
        preserve_note = (
            "Changes are in the isolated workspace only — your real project folder "
            "is unchanged until you Approve & apply (open Activity)."
        )
        if config.DRY_RUN:
            send_text(
                sender,
                f"Workspace is ready for {project} (practice/dry-run — I skipped the coding agent). "
                "Say if you want a live run next.",
                level="success",
            )
        elif salvaged_disconnect:
            send_text(
                sender,
                f"Coding on {project} stopped unexpectedly, but your edits were kept.\n\n"
                f"{report[:1800]}{file_bits}\n\n"
                f"{preserve_note}\n"
                f"{next_step}",
                level="warning",
            )
        elif tests_failed:
            send_text(
                sender,
                f"Coding finished for {project}, but configured tests FAILED — "
                "review the output before you approve.\n\n"
                f"{report[:1800]}{file_bits}\n\n"
                f"{preserve_note}\n"
                f"{next_step}",
                level="warning",
            )
        else:
            send_text(
                sender,
                f"Coding finished for {project} in an isolated workspace — ready for your approval.\n\n"
                f"{report[:1800]}{file_bits}\n\n"
                f"{preserve_note}\n"
                f"{next_step}",
                level="success",
            )
    except Exception as exc:
        log.exception("Task failed")
        err = str(exc)[:1000]
        if re.search(r"^cancelled\b", err, re.I):
            stage = "canceled"
            event_type = "canceled"
        elif re.search(r"timed out", err, re.I):
            stage = "timeout"
            event_type = "timeout"
        else:
            stage = "failed"
            event_type = "failed"
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
            event_type,
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
