"""Inbound chat handling - natural language first, classic commands still work."""
from __future__ import annotations

import uuid

from orchestrator import (
    audit,
    config,
    converse,
    db,
    llm_chat,
    preflight,
    progress,
    projects,
    queue,
    session,
    task_events,
    tasks,
)
from orchestrator.notify import send_text
from orchestrator.process import cancel_tracked


def _help() -> str:
    return (
        "I help you change code on your laptop projects - just chat like you would "
        "with ChatGPT, and I'll run the work safely in a copy first.\n\n"
        "For example:\n"
        '- "Let\'s work on lifeos" then describe the bug\n'
        '- "What\'s remaining?" / "Done?" / "What changes did you make?"\n'
        '- "Show my tasks" or "Why is it stuck?"\n'
        '- "Approve and apply" / "Apply locally" (or push) when review looks good\n'
        '- "Continue working" to resume the same Cursor session when possible\n'
        '- "Reject that" to discard a review\n'
        '- "Set projects root C:/laragon/www" then "Scan projects" / "Add project velora"\n'
        '- "Update project lifeos set allow_push true"\n\n'
        "Status answers come from real execution events — I won't invent progress."
    )


_STATUS_PLAIN = {
    "queued": "Waiting to start",
    "running": "In progress",
    "review": "Ready for you to review",
    "publishing": "Applying your approval",
    "published": "Done",
    "publish_failed": "Couldn't finish publishing",
    "rejected": "Rejected",
    "failed": "Didn't finish",
}


def _format_scan_candidates(root: str | None = None) -> str:
    info = projects.projects_root_info()
    scan_root = root or info.get("path")
    try:
        if root:
            projects.set_projects_root(root, persist=True)
            info = projects.projects_root_info()
            scan_root = info.get("path")
        candidates = projects.discover_candidates()
    except projects.ProjectConfigError as exc:
        return str(exc)
    fresh = [c for c in candidates if not c.get("registered")]
    header = f"Scanning {scan_root or '(no folder set)'}:"
    if not fresh:
        registered = sum(1 for c in candidates if c.get("registered"))
        return (
            f"{header}\nEverything there is already registered ({registered} project(s)). "
            'Say "add project <folder>" if you create a new one later, or '
            '"set projects root <path>" to scan a different folder.'
        )
    lines = [
        header,
        f"Found {len(fresh)} folder(s) not registered yet:",
    ]
    for c in fresh:
        lines.append(f"- {c['id']} ({c['type']}) — {c['path']}")
    lines.append("")
    lines.append('To register one: "add project <id>" (safe defaults: push/deploy off).')
    lines.append('Change folder anytime: "set projects root C:/path/to/folder".')
    return "\n".join(lines)


def _format_projects() -> str:
    registry = projects.projects()
    if not registry:
        return (
            "I don't have any projects set up yet. "
            'Say "scan projects" to find folders on your laptop, then '
            '"add project <name>" to register one.'
        )
    lines = ["Here are your projects:"]
    for name, cfg in registry.items():
        kind = cfg.get("type", "project")
        if kind == "git":
            where = "linked to GitHub"
        elif kind == "local":
            where = "local folder on your laptop"
        else:
            where = str(kind)
        bits = [where]
        if cfg.get("allow_push"):
            bits.append("can push when you approve")
        if cfg.get("allow_deploy"):
            bits.append("can deploy when you approve")
        lines.append(f"- {name}: {', '.join(bits)}")
    lines.append("")
    if config.DRY_RUN:
        lines.append(
            "I'm in practice mode right now (dry-run), so I'll prepare work but "
            "won't run the coding agent yet."
        )
    else:
        lines.append(
            "I'm ready to make real changes in a safe copy - nothing goes live until you approve."
        )
    lines.append('Just tell me what you want, e.g. "on lifeos, improve the login validation."')
    return "\n".join(lines)


def _format_tasks(sender: str) -> str:
    rows = tasks.list_tasks_for_sender(sender)
    if not rows:
        return (
            "You don't have any tasks yet. "
            'Try something like: "on lifeos, add a short note to the README."'
        )
    lines = ["Here's your recent work:"]
    for row in rows:
        instr = (row.get("instruction") or "").replace("\n", " ").strip()
        if len(instr) > 90:
            instr = instr[:87] + "..."
        status = _STATUS_PLAIN.get(row["status"], row["status"])
        stage = row.get("execution_stage") or ""
        stage_bit = f" · {stage}" if stage else ""
        lines.append(f"- {row['project']}: {status}{stage_bit} ({row['id']})")
        if instr:
            lines.append(f"  {instr}")
    lines.append("")
    lines.append(
        'Want more detail? Ask "how is my last task going?" '
        'When something is ready to review, say "approve and push" or "reject that".'
    )
    return "\n".join(lines)


def _resolve_task(sender: str, task_id: str | None) -> dict | None:
    if task_id:
        task = tasks.get_task(task_id)
        if task and task["sender"] == sender:
            return task
        return None
    ctx = session.get(sender)
    active_project = ctx.get("active_project") or None
    if ctx.get("active_task_id"):
        task = tasks.get_task(str(ctx["active_task_id"]))
        if task and task["sender"] == sender:
            if not active_project or task.get("project") == active_project:
                return task
    return tasks.active_task_for_sender(sender, project=active_project)


def _start_task(sender: str, project: str, instruction: str) -> None:
    registry = projects.projects()
    if project not in registry:
        known = ", ".join(registry) or "(none)"
        send_text(
            sender,
            f"I don't know a project called \"{project}\". "
            f"These are the ones I have: {known}. "
            "Which should I use?",
        )
        audit.record("task_unknown_project", actor=sender, detail={"project": project}, ok=False)
        return
    from orchestrator.quotas import QuotaExceeded, assert_task_allowed

    try:
        assert_task_allowed(sender)
    except QuotaExceeded as exc:
        send_text(sender, str(exc), level="warning")
        audit.record("task_quota", actor=sender, detail={"project": project}, ok=False)
        return
    ok, reason = preflight.project_ready(project, registry[project])
    if not ok:
        send_text(
            sender,
            f"I'd love to start on {project}, but I can't right now:\n\n{reason}\n\n"
            "Fix that on the laptop and ask me again - or pick another project.",
        )
        audit.record(
            "task_preflight_failed",
            actor=sender,
            detail={"project": project, "reason": reason[:300]},
            ok=False,
        )
        return
    task_id = uuid.uuid4().hex[:12]
    tasks.create_task(task_id, sender, project, instruction)
    task_events.record(
        task_id,
        "task_accepted",
        f"Task accepted for {project} — investigation pending",
        stage="queued",
    )
    queue.enqueue(task_id, kind="execute")
    converse.remember_work(sender, project=project, instruction=instruction, task_id=task_id)
    session.set_active_task(sender, task_id, project=project)
    audit.record(
        "task_queued",
        actor=sender,
        task_id=task_id,
        detail={"project": project, "instruction_len": len(instruction)},
    )
    instr_preview = instruction.strip().replace("\n", " ")
    if len(instr_preview) > 220:
        instr_preview = instr_preview[:217] + "..."
    if config.DRY_RUN:
        send_text(
            sender,
            f"I'll investigate {project} in an isolated workspace (practice/dry-run — "
            "Cursor agent won't run yet).\n\n"
            f"Task created · {task_id}\n"
            f"Request: {instr_preview}\n\n"
            'Ask "what\'s remaining?" anytime for evidenced progress.',
            level="info",
        )
    else:
        send_text(
            sender,
            f"I'll investigate {project} and work in an isolated workspace without "
            f"changing production.\n\n"
            f"Task created · {task_id} · Investigation pending\n"
            f"Request: {instr_preview}\n\n"
            'Ask "what\'s remaining?", "done?", or "what changes did you make?" for '
            "updates grounded in execution events.",
            level="success",
        )


def _status_reply(sender: str, task: dict) -> str:
    """Prefer evidence-backed progress; optionally soften with Groq using facts only."""
    base = progress.reply_status(task)
    phrased = llm_chat.phrase(
        "status update from evidence only",
        progress.facts_for_llm(task),
        user_question="status",
    )
    # Only use phrasing if it doesn't invent timing claims without evidence.
    if phrased and "just a few minutes" not in phrased.lower():
        return phrased
    return base


def _progress_reply(sender: str, intent_kind: str, task: dict) -> str:
    if intent_kind == "remaining":
        base = progress.reply_remaining(task)
        purpose = "explain what remains using only evidenced stages"
    elif intent_kind == "done_check":
        base = progress.reply_done(task)
        purpose = "say whether the task is done using only task status"
    elif intent_kind == "estimate":
        base = progress.reply_estimate(task)
        purpose = "time estimate — refuse if evidence is insufficient"
    elif intent_kind == "changes":
        base = progress.reply_changes(task)
        purpose = "summarize recorded file changes only"
    elif intent_kind == "stuck":
        base = progress.reply_stuck(task, pending_jobs=queue.pending_count())
        purpose = "diagnose stuck/failed state from health facts only"
    else:
        base = progress.reply_status(task)
        purpose = "status from evidence"
    phrased = llm_chat.phrase(purpose, progress.facts_for_llm(task) + "\n\nDraft:\n" + base)
    if phrased and "just a few minutes" not in phrased.lower():
        return phrased
    return base


def handle(sender: str, body: str) -> None:
    body = (body or "").strip()
    if not body:
        send_text(sender, _help(), level="info")
        return

    registry = projects.projects()
    llm = llm_chat.understand(body, registry, sender=sender)
    intent = llm.intent if llm else converse.parse_intent(body, registry, sender=sender)
    soft_reply = (llm.reply if llm else None) or None

    if intent.kind == "greet":
        send_text(
            sender,
            soft_reply or "Hi - what can I help you with?",
            level="info",
        )
        return

    if intent.kind == "thanks":
        send_text(
            sender,
            soft_reply or "You're welcome - anytime you want something built or fixed.",
            level="info",
        )
        return

    if intent.kind == "cancel":
        send_text(
            sender,
            soft_reply or "Okay, cancelled. What would you like to do instead?",
            level="info",
        )
        return

    if intent.kind == "help":
        send_text(sender, soft_reply or _help(), level="info")
        return

    if intent.kind == "chat":
        send_text(
            sender,
            soft_reply
            or (
                "I'm here to help with your projects. "
                'Ask "what projects do I have?", "show my tasks", '
                "or tell me what you'd like changed."
            ),
            level="info",
        )
        return

    if intent.kind == "has_project":
        project = intent.project or ""
        cfg = registry.get(project)
        if not cfg:
            send_text(
                sender,
                f"No - I don't have a project called \"{project}\". "
                'Ask "what projects do I have?" to see the full list.',
            )
            return
        # Remember this project so "yes, remove the welcome text..." continues here.
        converse.set_pending(sender, kind="offer_project", project=project)
        switched = session.switch_project(sender, project)
        base = soft_reply or (
            f"Yes — {project} is registered ({cfg.get('type', 'project')}). "
            "Want me to work on it? Just tell me what to change "
            '(e.g. "fix dark mode on the login page").'
        )
        if switched.get("changed") and switched.get("previous"):
            base = (
                f"Switched from {switched['previous']} to {project}. "
                f"This chat is a fresh thread for {project} only "
                f"(work on {switched['previous']} keeps running if it was in progress).\n\n{base}"
            )
        send_text(sender, base)
        return

    if intent.kind == "ask_instruction":
        project = intent.project or "that project"
        converse.set_pending(sender, kind="offer_project", project=project)
        switched = {"changed": False, "previous": None}
        if intent.project:
            switched = session.switch_project(sender, intent.project)
        base = soft_reply or (
            f"Okay — I'll use {project} as the active project. "
            "What should I investigate or change there?"
        )
        if switched.get("changed") and switched.get("previous"):
            base = (
                f"Switched from {switched['previous']} to {project}. "
                f"Prior {switched['previous']} chat stays in that project's thread — "
                f"this conversation is only for {project} now. "
                f"Background agent work on {switched['previous']} is not cancelled.\n\n{base}"
            )
        elif switched.get("changed"):
            base = (
                f"Okay — {project} is active. Starting a fresh chat thread for this project.\n\n"
                "What should I investigate or change there?"
            )
        send_text(sender, base)
        return

    if intent.kind == "projects":
        facts = llm_chat.project_facts(registry)
        text = (
            soft_reply
            or llm_chat.phrase("projects", facts, user_question=body)
            or _format_projects()
        )
        send_text(sender, text, level="info")
        audit.record("projects_listed", actor=sender, detail={"count": len(registry)})
        return

    if intent.kind == "show_projects_root":
        info = projects.projects_root_info()
        if not info.get("path"):
            send_text(
                sender,
                'No scan folder is set yet. Say '
                '"set projects root C:/laragon/www" (or use Manage in the sidebar).',
                level="info",
            )
            return
        source = info.get("source") or "unknown"
        send_text(
            sender,
            f"Projects scan folder: {info['path']} (source: {source}). "
            'Say "scan projects" to list unregistered folders, or '
            '"set projects root <path>" to change it.',
            level="info",
        )
        return

    if intent.kind == "set_projects_root":
        path = (intent.instruction or "").strip()
        if not path:
            send_text(
                sender,
                'Tell me the folder path, e.g. "set projects root C:/laragon/www".',
            )
            return
        try:
            info = projects.set_projects_root(path, persist=True)
        except projects.ProjectConfigError as exc:
            send_text(sender, str(exc))
            return
        send_text(
            sender,
            f"Scan folder set to {info.get('path')}. "
            'Say "scan projects" to find folders to register.',
            level="info",
        )
        audit.record(
            "projects_root_set",
            actor=sender,
            detail={"path": info.get("path")},
        )
        return

    if intent.kind == "scan_projects":
        text = _format_scan_candidates(intent.instruction)
        send_text(sender, text, level="info")
        audit.record(
            "projects_scanned",
            actor=sender,
            detail={"root": intent.instruction or projects.projects_root_info().get("path")},
        )
        return

    if intent.kind == "register_project":
        token = (intent.project or "").strip()
        if not token:
            send_text(sender, 'Tell me which folder to add, e.g. "add project velora".')
            return
        try:
            candidates = projects.discover_candidates()
        except projects.ProjectConfigError as exc:
            send_text(sender, str(exc))
            return
        match = next(
            (
                c
                for c in candidates
                if c["id"].lower() == token.lower() or str(c.get("name", "")).lower() == token.lower()
            ),
            None,
        )
        if not match:
            send_text(
                sender,
                f'I couldn\'t find a folder matching "{token}" under your projects root. '
                'Say "scan projects" to see candidates.',
            )
            return
        if match.get("registered"):
            send_text(
                sender,
                f"{match['id']} is already registered"
                + (f" as {match['registered_as']}" if match.get("registered_as") else "")
                + ".",
            )
            return
        try:
            created = projects.register_project(match["id"], match["path"], type=match["type"])
        except projects.ProjectConfigError as exc:
            send_text(sender, str(exc))
            return
        send_text(
            sender,
            f"Registered {created['id']} ({created['type']}) at {created['path']}. "
            "Push and deploy stay off until you enable them. "
            f'Say "let\'s work on {created["id"]}" when you\'re ready.',
            level="info",
        )
        audit.record(
            "project_registered",
            actor=sender,
            detail={"project": created["id"], "path": created.get("path")},
        )
        return

    if intent.kind == "update_project":
        project = (intent.project or "").strip()
        updates = intent.updates or {}
        if not project or not updates:
            send_text(
                sender,
                'Example: "update project lifeos set allow_push true".',
            )
            return
        # Resolve case-insensitive id
        resolved = next((n for n in registry if n.lower() == project.lower()), project)
        try:
            updated = projects.update_project(resolved, **updates)
        except projects.ProjectConfigError as exc:
            send_text(sender, str(exc))
            return
        bits = ", ".join(f"{k}={updates[k]!r}" for k in sorted(updates))
        send_text(
            sender,
            f"Updated {updated['id']}: {bits}.",
            level="info",
        )
        audit.record(
            "project_updated",
            actor=sender,
            detail={"project": updated["id"], "fields": sorted(updates)},
        )
        return

    if intent.kind == "remove_project":
        project = (intent.project or "").strip()
        if not project:
            send_text(sender, 'Example: "remove project velora".')
            return
        resolved = next((n for n in registry if n.lower() == project.lower()), None)
        if not resolved:
            # Still allow confirming a pending remove after registry reload edge cases
            if intent.action == "CONFIRM":
                pending = converse.get_pending(sender)
                resolved = (pending or {}).get("project")
            if not resolved:
                send_text(sender, f'No registered project named "{project}".')
                return
        if intent.action != "CONFIRM":
            converse.set_pending(sender, kind="confirm_remove_project", project=resolved)
            send_text(
                sender,
                f'Remove "{resolved}" from the registry? Reply yes to confirm, or cancel.',
                level="info",
            )
            return
        try:
            removed = projects.remove_project(resolved)
        except projects.ProjectConfigError as exc:
            converse.clear_pending(sender)
            send_text(sender, str(exc))
            return
        converse.clear_pending(sender)
        ctx = session.get(sender)
        if (ctx.get("active_project") or "") == resolved:
            session.switch_project(sender, None)
        send_text(
            sender,
            f'Removed "{removed["id"]}" from the registry. The folder on disk is unchanged.',
            level="info",
        )
        audit.record("project_removed", actor=sender, detail={"project": resolved})
        return

    if intent.kind == "tasks":
        rows = tasks.list_tasks_for_sender(sender)
        facts = llm_chat.task_facts(rows)
        text = (
            soft_reply
            or llm_chat.phrase("tasks", facts, user_question=body)
            or _format_tasks(sender)
        )
        send_text(sender, text, level="info")
        audit.record("tasks_listed", actor=sender)
        return

    if intent.kind == "task_need_project":
        names = ", ".join(registry) if registry else "(none registered)"
        converse.set_pending(sender, kind="need_project", instruction=intent.instruction)
        fallback = (
            f"Sure - I can do that. Which project should I use?\n\n{names}\n\n"
            "Just reply with the project name (or say cancel)."
        )
        text = soft_reply or llm_chat.phrase(
            "ask which project",
            f"User wants: {intent.instruction}\nAvailable projects: {names}",
            user_question=body,
        ) or fallback
        send_text(sender, text, level="info")
        return

    if intent.kind == "task":
        assert intent.project and intent.instruction
        converse.clear_pending(sender)
        _start_task(sender, intent.project, intent.instruction)
        return

    if intent.kind == "retry":
        project = intent.project
        instruction = intent.instruction
        if not (project and instruction):
            remembered = converse.last_work(sender)
            if remembered:
                project = project or remembered.get("project")
                instruction = instruction or remembered.get("instruction")
        if not (project and instruction):
            # Fall back to newest remembered task for this sender (failed first, else latest).
            rows = tasks.list_tasks_for_sender(sender, limit=8)
            preferred = [
                r
                for r in rows
                if r.get("status") in {"failed", "rejected"} and r.get("instruction")
            ] or [r for r in rows if r.get("instruction")]
            if preferred:
                project = preferred[0].get("project")
                instruction = preferred[0].get("instruction")

        if not (project and instruction):
            send_text(
                sender,
                soft_reply
                or (
                    "I don't still have that earlier request. "
                    "Tell me the project and what to change, and I'll run it."
                ),
                level="info",
            )
            return
        converse.clear_pending(sender)
        _start_task(sender, str(project), str(instruction))
        return

    if intent.kind in {"status", "remaining", "done_check", "estimate", "changes", "stuck"}:
        # Classic mistaken "status of <project>"
        if intent.kind == "status" and intent.task_id is None:
            maybe_project = converse.find_project_in_text(body, registry)
            if maybe_project and not extract_looks_like_status_of_task(body):
                if re_status_of_project(body, maybe_project):
                    send_text(
                        sender,
                        f"\"{maybe_project}\" is a project, not a task. "
                        "Want me to show your recent tasks, or start new work on that project?",
                    )
                    return
        task = _resolve_task(sender, intent.task_id)
        if not task:
            send_text(
                sender,
                "I couldn't find an active task to answer from. "
                'Say "show my tasks", or start work like "on lifeos, fix the login page".',
            )
            return
        session.set_active_task(sender, task["id"], project=task.get("project"))
        if intent.kind == "status":
            text = _status_reply(sender, task)
        else:
            text = _progress_reply(sender, intent.kind, task)
        level = "info"
        if task["status"] == "review":
            level = "success"
        elif task["status"] in {"failed", "publish_failed"}:
            level = "error"
        send_text(sender, text, level=level)
        return

    if intent.kind == "continue_work":
        task = _resolve_task(sender, intent.task_id)
        remembered = converse.last_work(sender)
        if task and task["status"] in {"queued", "running"}:
            send_text(
                sender,
                _progress_reply(sender, "status", task),
                level="info",
            )
            return
        # Prefer real Cursor --resume in the same workspace when we have a session id.
        # Re-fetch full row: list/active helpers may omit columns used for resume.
        if task and task["status"] in {"review", "failed"}:
            task = tasks.get_task(task["id"]) or task
        if (
            task
            and task["status"] in {"review", "failed"}
            and tasks.can_resume_agent(task)
        ):
            instruction = (
                (remembered or {}).get("instruction")
                or task.get("instruction")
                or ""
            )
            if tasks.queue_for_resume(task["id"], instruction=str(instruction) or None):
                queue.enqueue(task["id"], kind="execute")
                converse.remember_work(
                    sender,
                    project=str(task.get("project") or ""),
                    instruction=str(instruction or task.get("instruction") or ""),
                    task_id=task["id"],
                )
                session.set_active_task(
                    sender, task["id"], project=str(task.get("project") or "") or None
                )
                audit.record(
                    "task_resume_queued",
                    actor=sender,
                    task_id=task["id"],
                    detail={
                        "project": task.get("project"),
                        "agent_chat_id": (task.get("agent_chat_id") or "")[:64],
                    },
                )
                send_text(
                    sender,
                    f"Continuing task {task['id']} on {task.get('project')} "
                    "with the same Cursor agent session (resume).",
                    level="info",
                )
                return
        if task and task["status"] in {"failed", "rejected"}:
            instruction = task.get("instruction") or (remembered or {}).get("instruction")
            project = task.get("project") or (remembered or {}).get("project")
            if project and instruction:
                send_text(
                    sender,
                    f"Retrying {project} from the last failed/rejected task state "
                    "(fresh workspace — no resumable Cursor session).",
                    level="info",
                )
                _start_task(sender, str(project), str(instruction))
                return
        if remembered and remembered.get("project") and remembered.get("instruction"):
            send_text(
                sender,
                f"Continuing with the last request on {remembered['project']}.",
                level="info",
            )
            _start_task(sender, str(remembered["project"]), str(remembered["instruction"]))
            return
        send_text(
            sender,
            "There's nothing safe to resume right now. "
            "Tell me the project and what to change, or retry a failed task.",
            level="info",
        )
        return

    if intent.kind == "reject":
        task = _resolve_task(sender, intent.task_id)
        if not task:
            send_text(sender, "I don't have a task to reject. Ask me to show your tasks first.")
            return
        if task["status"] != "review":
            send_text(
                sender,
                f"Task {task['id']} isn't waiting for review (it's {task['status']}), "
                "so there's nothing to reject right now.",
            )
            return
        tasks.update_task(task["id"], status="rejected")
        audit.record("task_rejected", actor=sender, task_id=task["id"])
        send_text(
            sender,
            f"Okay - I rejected task {task['id']}. "
            "The workspace is still on disk if you want to inspect it later.",
        )
        return

    if intent.kind == "approve":
        task = _resolve_task(sender, intent.task_id)
        if not task:
            send_text(sender, "I don't have a task to approve yet. Start one, or ask to see your tasks.")
            return
        action = intent.action or "PUSH"
        project_config = registry.get(task["project"], {})
        retry_ok = action == "PR" and task["status"] == "publish_failed"
        if task["status"] != "review" and not retry_ok:
            send_text(
                sender,
                f"Task {task['id']} isn't ready for approval yet - it's currently {task['status']}. "
                'Ask "how is my last task going?" for an update.',
            )
            return
        if config.DRY_RUN:
            send_text(
                sender,
                "Dry-run is still on, so I can't push, open a PR, or deploy. "
                "Turn DRY_RUN=false in .env after you've reviewed a real agent run.",
            )
            audit.record(
                "approve_blocked_dry_run",
                actor=sender,
                task_id=task["id"],
                detail={"action": action},
                ok=False,
            )
            return
        reviewed_at = int(task.get("ended_at") or 0)
        if reviewed_at and db.now() - reviewed_at > int(getattr(config, "APPROVAL_TTL_SEC", 86400)):
            send_text(
                sender,
                f"The review for task {task['id']} has expired. "
                "Ask me to continue the work so I can prepare a fresh review.",
                level="warning",
            )
            audit.record(
                "approve_expired",
                actor=sender,
                task_id=task["id"],
                detail={"action": action},
                ok=False,
            )
            return
        if not (task.get("content_digest") or "").strip() and action != "DEPLOY":
            send_text(
                sender,
                f"Task {task['id']} has no approval digest, so I won't publish it. "
                "Ask me to run it again and review the new result.",
                level="warning",
            )
            audit.record(
                "approve_missing_digest",
                actor=sender,
                task_id=task["id"],
                detail={"action": action},
                ok=False,
            )
            return
        if action in {"PUSH", "APPLY", "PR"}:
            if not task.get("branch") or project_config.get("type") != "git":
                send_text(
                    sender,
                    f"{task['project']} is a local snapshot, so I can't merge a git branch into it. "
                    "Inspect the workspace on the laptop, or register it as a git project.",
                )
                return
            can_push = bool(project_config.get("allow_push"))
            can_apply = bool(project_config.get("apply_local", True))
            if action == "PUSH" and not can_push and not can_apply:
                send_text(
                    sender,
                    f"Neither push nor local apply is enabled for {task['project']}. "
                    "Turn on allow_push and/or apply_local in projects.json.",
                )
                return
            if action == "APPLY" and not can_apply:
                send_text(
                    sender,
                    f"Local apply is disabled for {task['project']} (apply_local is off).",
                )
                return
            if action == "PR" and not can_push:
                send_text(
                    sender,
                    f"Pull requests need allow_push for {task['project']} "
                    "so the review branch can reach GitHub.",
                )
                return
        if action == "DEPLOY" and (
            not project_config.get("allow_deploy") or not project_config.get("deploy_command")
        ):
            send_text(sender, f"Deploy isn't configured for {task['project']}.")
            return
        if not tasks.claim_publishing(task["id"]):
            send_text(
                sender,
                f"Task {task['id']} was already being published, so I didn't queue it twice.",
                level="info",
            )
            return
        queue.enqueue(task["id"], kind=f"publish:{action}")
        audit.record(
            "approve_queued",
            actor=sender,
            task_id=task["id"],
            detail={
                "action": action,
                "digest_prefix": (task.get("content_digest") or "")[:16],
            },
        )
        if action == "APPLY":
            verb = "merging the changes into your local project"
        elif action == "PR":
            verb = "pushing the branch and opening a GitHub pull request"
        elif action == "PUSH":
            bits = []
            if project_config.get("allow_push"):
                bits.append("pushing the branch")
            if project_config.get("apply_local", True):
                bits.append("updating your local project folder")
            verb = " and ".join(bits) or "publishing"
        else:
            verb = "running the deploy command"
        send_text(sender, f"On it - {verb} for task {task['id']}. I'll confirm when it's done.")
        return

    if intent.kind == "cancel_task":
        task = _resolve_task(sender, intent.task_id)
        if not task:
            send_text(sender, "I don't have a task to cancel. Ask me to show your tasks.")
            return
        if task["status"] not in {"queued", "running", "publishing"}:
            send_text(
                sender,
                f"Task {task['id']} is {task['status']}, so it can't be cancelled. "
                'If it\'s waiting for review, say "reject that" instead.',
            )
            return
        killed = cancel_tracked(task["id"])
        from orchestrator import db as _db

        tasks.update_task(
            task["id"],
            status="failed",
            execution_stage="canceled",
            summary="Cancelled by user",
            blocker="Cancelled by user",
            ended_at=_db.now(),
            agent_pid=None,
        )
        task_events.record(
            task["id"],
            "canceled",
            "Cancelled by user" + (" (agent process signaled)" if killed else ""),
            stage="canceled",
            detail={"process_signaled": killed},
        )
        audit.record("task_cancelled", actor=sender, task_id=task["id"])
        send_text(
            sender,
            f"Cancelled task {task['id']}."
            + (
                " The Cursor agent process was signaled to stop."
                if killed
                else " No live agent process was registered (it may already have finished or not started)."
            )
            + " I won't publish those workspace files unless you start a new review.",
            level="warning",
        )
        return

    # Unknown - stay conversational, don't dump a command manual
    send_text(
        sender,
        soft_reply
        or (
            "I'm not quite sure what you mean yet. Try something like:\n"
            '- "What projects do I have?"\n'
            '- "On lifeos, fix the login validation"\n'
            '- "Show my tasks"\n'
            '- "Approve and push" when something is ready\n\n'
            "What would you like to work on?"
        ),
        level="info",
    )


def re_status_of_project(body: str, project: str) -> bool:
    import re

    return bool(re.search(rf"(?i)\bstatus\b.{{0,20}}\b{re.escape(project)}\b", body))


def extract_looks_like_status_of_task(body: str) -> bool:
    import re

    return bool(re.search(r"(?i)\bstatus\b.{0,10}\b[a-f0-9]{12}\b", body))
