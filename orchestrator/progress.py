"""Evidence-grounded natural-language status answers.

Never invents file changes, timings, or test results — only cites task rows and events.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from orchestrator import task_events, tasks


def _ago(ts: int | None) -> str:
    if not ts:
        return "unknown"
    sec = max(0, int(time.time()) - int(ts))
    if sec < 60:
        return f"{sec}s ago"
    if sec < 3600:
        return f"{sec // 60}m ago"
    if sec < 86400:
        return f"{sec // 3600}h ago"
    return f"{sec // 86400}d ago"


def _duration(start: int | None, end: int | None = None) -> str | None:
    if not start:
        return None
    end_ts = int(end or time.time())
    sec = max(0, end_ts - int(start))
    if sec < 60:
        return f"{sec} seconds"
    if sec < 3600:
        return f"{sec // 60} minutes"
    return f"{sec // 3600}h {(sec % 3600) // 60}m"


def _files(task: dict[str, Any]) -> list[str]:
    raw = task.get("modified_files")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def parse_change_details(task: dict[str, Any]) -> dict[str, Any] | None:
    """Return structured change_details dict, or None if missing/invalid."""
    raw = task.get("change_details")
    if not raw:
        return None
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(data, dict):
        return None
    files = data.get("files")
    if not isinstance(files, list):
        return None
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    return {
        "files": files,
        "stats": {
            "files": int(stats.get("files") or len(files)),
            "additions": int(stats.get("additions") or 0),
            "deletions": int(stats.get("deletions") or 0),
        },
        "truncated": bool(data.get("truncated")),
    }


def snapshot(task: dict[str, Any]) -> dict[str, Any]:
    """Structured progress view for APIs and phrasing."""
    stage = task.get("execution_stage") or (
        "queued" if task.get("status") == "queued" else None
    )
    completed, remaining, current_label = task_events.completed_and_remaining(
        stage, task.get("status") or ""
    )
    # Prefer an honest starting label until the Cursor pid exists.
    if (
        (task.get("status") or "") == "running"
        and stage == "agent_running"
        and not task.get("agent_pid")
    ):
        current_label = task_events.AGENT_STARTING_DETAIL
    events = task_events.list_events(task["id"], limit=50)
    publish_steps = _publish_steps_from_events(events)
    summary_text = (task.get("summary") or "")[:2000]
    # Prefer structured completion report steps when the task already finished.
    if not publish_steps and summary_text.startswith("=== Task completion ==="):
        parsed = parse_completion_report(summary_text)
        if parsed:
            publish_steps = parsed["steps"]
    change_details = parse_change_details(task)
    return {
        "task_id": task["id"],
        "project": task.get("project"),
        "status": task.get("status"),
        "execution_stage": stage,
        "current_label": current_label,
        "completed": completed,
        "remaining": remaining,
        "instruction": (task.get("instruction") or "")[:500],
        "started_at": task.get("started_at"),
        "last_activity_at": task.get("last_activity_at") or task.get("updated_at"),
        "ended_at": task.get("ended_at"),
        "duration": _duration(task.get("started_at"), task.get("ended_at")),
        "last_activity": _ago(task.get("last_activity_at") or task.get("updated_at")),
        "modified_files": _files(task),
        "change_stats": (change_details or {}).get("stats"),
        "has_change_details": bool(change_details),
        "exit_code": task.get("exit_code"),
        "blocker": task.get("blocker"),
        "workspace": task.get("workspace"),
        "summary": summary_text,
        "publish_steps": publish_steps,
        "events": [
            {
                "id": e["id"],
                "ts": e["ts"],
                "stage": e.get("stage"),
                "event_type": e["event_type"],
                "message": e["message"],
            }
            for e in events
        ],
    }


def _publish_steps_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse local_commit + publish_step events into a timeline for Activity UI."""
    steps: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for ev in events:
        et = ev.get("event_type") or ""
        detail = ev.get("detail") if isinstance(ev.get("detail"), dict) else {}
        if et == "local_commit":
            title = str(detail.get("title") or "Committing local changes")
            body = str(detail.get("detail") or ev.get("message") or "")
        elif et == "publish_step":
            title = str(detail.get("title") or "").strip()
            body = str(detail.get("detail") or ev.get("message") or "").strip()
            if not title and ":" in body:
                title, body = [p.strip() for p in body.split(":", 1)]
            if not title:
                continue
            # Hide internal worktree commit when a local-commit prelude is present.
            if title == "Committing approved changes" and any(
                s.get("title") == "Committing local changes" for s in steps
            ):
                continue
        else:
            continue
        key = title.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        steps.append(
            {
                "title": title,
                "detail": body,
                "status": str(detail.get("status") or "completed"),
            }
        )
    return steps


def reply_status(task: dict[str, Any]) -> str:
    snap = snapshot(task)
    status = snap["status"]
    lines = [
        f"Here's the verified progress for {snap['project']} (task {snap['task_id']}):",
        "",
        f"Status: {status}",
        f"Current stage: {snap['current_label']}",
    ]
    if snap["duration"] and status in {"running", "queued", "publishing"}:
        lines.append(f"Elapsed: {snap['duration']} (last activity {snap['last_activity']})")
    elif snap["duration"] and snap.get("ended_at"):
        lines.append(f"Ran for: {snap['duration']}")

    if snap["completed"]:
        lines.append("")
        lines.append("Completed:")
        for item in snap["completed"]:
            lines.append(f"- {item}")

    if status in {"queued", "running"}:
        lines.append("")
        lines.append(f"Currently: {snap['current_label']}")
        stage = snap.get("execution_stage")
        if stage == "agent_running":
            lines.append(
                "The Cursor process is running; tool/file activity will show here once "
                "the CLI stream emits it — I will not invent investigating/implementing steps."
            )
        elif stage == "investigating":
            lines.append("Stream evidence: agent is reading/searching files.")
        elif stage == "implementing":
            lines.append("Stream evidence: agent is writing/editing files.")
        if snap["remaining"]:
            lines.append("Still ahead (planned pipeline — not yet evidenced as done):")
            for item in snap["remaining"]:
                lines.append(f"- {item}")
    elif status == "review":
        lines.append("")
        lines.append("Coding pipeline finished — waiting for your review/approval.")
    elif status == "failed":
        lines.append("")
        lines.append("This task did not complete successfully.")
        if snap.get("blocker"):
            lines.append(f"Blocker: {snap['blocker'][:500]}")
        elif snap.get("summary"):
            lines.append(f"Detail: {snap['summary'][:500]}")

    if snap["modified_files"]:
        lines.append("")
        lines.append("Files changed (from workspace evidence):")
        for path in snap["modified_files"][:20]:
            lines.append(f"- {path}")
        if len(snap["modified_files"]) > 20:
            lines.append(f"- …and {len(snap['modified_files']) - 20} more")

    recent = snap["events"][-5:]
    if recent:
        lines.append("")
        lines.append("Recent execution events:")
        for ev in recent:
            lines.append(f"- {ev['message']}")

    if status == "review":
        lines.append("")
        lines.append(
            'If it looks good, say "approve and push" or "create a pull request". '
            'Or say "reject that".'
        )
    return "\n".join(lines)


def reply_remaining(task: dict[str, Any]) -> str:
    snap = snapshot(task)
    status = snap["status"]
    lines = [f"What's remaining on {snap['project']} (task {snap['task_id']}):", ""]

    if snap["completed"]:
        lines.append("Already done (evidenced):")
        for item in snap["completed"]:
            lines.append(f"- {item}")
        lines.append("")

    lines.append(f"Active stage: {snap['current_label']}")

    if status in {"queued", "running"}:
        stage = snap.get("execution_stage")
        if stage == "agent_running":
            lines.append("")
            lines.append(task_events.AGENT_UNAVAILABLE_DETAIL)
            if task.get("agent_pid"):
                lines.append(f"Recorded agent pid: {task['agent_pid']}")
        elif stage in {"investigating", "implementing"} and task.get("agent_pid"):
            lines.append("")
            lines.append(f"Recorded agent pid: {task['agent_pid']}")
        if snap["remaining"]:
            lines.append("")
            lines.append("Still ahead in the coding pipeline:")
            for item in snap["remaining"]:
                lines.append(f"- {item}")
        lines.append("")
        lines.append(
            "I only mark a step complete when the worker records evidence for it — "
            "not from chat guesses."
        )
    elif status == "review":
        lines.append("")
        lines.append(
            "Coding work is done. Remaining: your review, then approve/apply/push or reject."
        )
        if snap["modified_files"]:
            lines.append(f"Changed files on record: {len(snap['modified_files'])}.")
    elif status == "failed":
        lines.append("")
        lines.append("Nothing left in the pipeline — the run failed.")
        if snap.get("blocker"):
            lines.append(f"Blocker: {snap['blocker'][:500]}")
        lines.append('Say "continue working" or "try again" to retry if you want.')
    elif status in {"published", "publishing"}:
        lines.append("")
        lines.append("Publishing path — coding remaining work is empty.")
    else:
        lines.append("")
        lines.append(f"Task is in status `{status}`; no further coding steps are scheduled.")

    return "\n".join(lines)


def reply_done(task: dict[str, Any]) -> str:
    status = task.get("status")
    if status == "review":
        files = _files(task)
        extra = ""
        if files:
            extra = f"\n\nVerified changed files ({len(files)}):\n" + "\n".join(
                f"- {p}" for p in files[:15]
            )
        return (
            f"Yes — coding for {task['project']} finished and is ready for your review "
            f"(task {task['id']}).{extra}\n\n"
            'Say "approve and push", "apply locally", "create a pull request", or "reject that".'
        )
    if status == "published":
        summary = (task.get("summary") or "").strip()
        if summary.startswith("=== Task completion ==="):
            return summary
        return f"Yes — task {task['id']} on {task['project']} was published."
    if status == "failed":
        blocker = (task.get("blocker") or task.get("summary") or "unknown error")[:400]
        return f"No — task {task['id']} failed.\n\n{blocker}"
    if status in {"queued", "running", "publishing"}:
        snap = snapshot(task)
        return (
            f"Not yet. {task['project']} is still {status} "
            f"(stage: {snap['current_label']}, last activity {snap['last_activity']})."
        )
    return f"Task {task['id']} is currently `{status}` — not marked complete."


def reply_estimate(task: dict[str, Any]) -> str:
    """Only give a reasoned estimate when evidence supports one; otherwise refuse."""
    status = task.get("status")
    stage = task.get("execution_stage")
    started = task.get("started_at")
    elapsed = _duration(started) if started else None

    if status in {"review", "published", "rejected"}:
        return (
            f"This task already finished coding ({status}). "
            "No remaining runtime estimate applies."
        )
    if status == "failed":
        return (
            "The last run failed, so I don't have a reliable remaining-time estimate. "
            'Fix the blocker or say "try again".'
        )
    if status == "queued":
        return (
            "The job is still queued — I don't have a reliable time estimate until the "
            "worker starts preparing the workspace and the Cursor agent begins."
        )
    if status == "running":
        display_stage = stage or "unknown"
        label = task_events.STAGE_LABELS.get(display_stage, display_stage)
        if display_stage == "agent_running":
            label = task_events.AGENT_UNAVAILABLE_DETAIL
        bits = [
            f"I don't invent ETAs. Here's what is evidenced so far for task {task['id']}:",
            f"- Stage: {label}",
        ]
        if elapsed:
            bits.append(f"- Elapsed: {elapsed}")
        bits.append(
            f"- Last activity: {_ago(task.get('last_activity_at') or task.get('updated_at'))}"
        )
        if task.get("agent_pid"):
            bits.append(f"- Agent pid (recorded): {task['agent_pid']}")
        if display_stage == "agent_running":
            bits.append(
                "- The Cursor process is alive, but I have no mid-run activity stream, "
                "so I cannot give a reliable finish time."
            )
        elif display_stage == "investigating":
            bits.append(
                "- Stream evidence shows the agent is reading/searching files; "
                "finish time still depends on the remaining work."
            )
        elif display_stage == "implementing":
            bits.append(
                "- Stream evidence shows the agent is writing/editing files; "
                "finish time still depends on the remaining work."
            )
        elif display_stage == "testing":
            bits.append("- Tests are running now; remaining time depends on the project test suite.")
        elif display_stage == "preparing_workspace":
            bits.append("- Workspace prep is usually short; the coding agent has not started yet.")
        bits.append(
            'Ask "what\'s remaining?" for the pipeline checklist based on recorded stages.'
        )
        return "\n".join(bits)
    return (
        "I don't have enough execution evidence for a reliable time estimate. "
        "I can tell you the current stage and recorded events instead."
    )


def reply_changes(task: dict[str, Any]) -> str:
    files = _files(task)
    summary = (task.get("summary") or "").strip()
    details = parse_change_details(task)
    if not files and not summary and not details:
        status = task.get("status")
        if status in {"queued", "running"}:
            return (
                f"No file changes are on record yet for task {task['id']} "
                f"(status `{status}`). I'll list them when the workspace shows modifications."
            )
        return f"I don't have a recorded diff summary for task {task['id']} yet."

    lines = [f"Changes on record for {task['project']} (task {task['id']}):", ""]
    if details and details["stats"]:
        st = details["stats"]
        lines.append(
            f"Diff stats: {st['files']} file(s), +{st['additions']} / -{st['deletions']}"
            + (" (truncated)" if details.get("truncated") else "")
        )
        lines.append("")
    if files:
        lines.append("Files:")
        for path in files[:40]:
            lines.append(f"- {path}")
        if len(files) > 40:
            lines.append(f"- …and {len(files) - 40} more")
        lines.append("")
    if details and details["files"]:
        lines.append("Patch excerpts:")
        for entry in details["files"][:5]:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or "")
            patch = str(entry.get("patch") or "")
            if not path:
                continue
            status = str(entry.get("status") or "M")
            adds = int(entry.get("additions") or 0)
            dels = int(entry.get("deletions") or 0)
            lines.append(f"### {path} ({status} +{adds}/-{dels})")
            excerpt = "\n".join(patch.splitlines()[:40])
            if excerpt:
                lines.append(excerpt)
            if len(patch.splitlines()) > 40:
                lines.append("…")
            lines.append("")
        if len(details["files"]) > 5:
            lines.append(f"…and {len(details['files']) - 5} more file(s) in the full review.")
            lines.append("")
        lines.append(
            "Open Review changes in the webchat Activity UI to inspect the full diffs "
            "before approve & push."
        )
        lines.append("")
    if summary:
        lines.append("Agent / test summary (scrubbed):")
        lines.append(summary[:2200])
    return "\n".join(lines)


def reply_stuck(task: dict[str, Any], *, pending_jobs: int | None = None) -> str:
    from orchestrator.process import tracked_info

    status = task.get("status")
    stage = task.get("execution_stage")
    last = task.get("last_activity_at") or task.get("updated_at")
    idle = int(time.time()) - int(last or time.time())
    label = task_events.STAGE_LABELS.get(stage or "", stage or "unknown")
    if stage == "agent_running":
        label = task_events.AGENT_UNAVAILABLE_DETAIL
    lines = [
        f"Health check for task {task['id']} ({task['project']}):",
        f"- Status: {status}",
        f"- Stage: {label}",
        f"- Last activity: {_ago(last)}",
    ]
    live = tracked_info(task["id"])
    if live:
        lines.append(
            f"- Live process: pid={live['pid']} alive={live['alive']} "
            f"elapsed={live.get('elapsed_sec')}s"
        )
    elif task.get("agent_pid"):
        lines.append(f"- Last recorded agent pid: {task['agent_pid']} (not in process registry)")
    if pending_jobs is not None:
        lines.append(f"- Pending jobs in queue: {pending_jobs}")
    if task.get("blocker"):
        lines.append(f"- Blocker: {task['blocker'][:500]}")
    if task.get("exit_code") is not None:
        lines.append(f"- Last process exit code: {task['exit_code']}")

    if status == "failed":
        lines.append("")
        lines.append("The run already failed — it isn't mid-flight.")
        if task.get("summary"):
            lines.append(task["summary"][:600])
    elif status == "queued" and idle > 120:
        lines.append("")
        lines.append(
            "This looks stalled in the queue. Check that ORCHESTRATOR_WORKER is enabled "
            "and the worker thread is running."
        )
    elif status == "running" and idle > 600:
        lines.append("")
        lines.append(
            "No recorded heartbeat for over 10 minutes while status is running. "
            "The Cursor agent process may be hung. "
            'You can say "stop this task" to cancel, then retry.'
        )
    elif status == "running":
        lines.append("")
        lines.append(
            "Heartbeats are recent enough that I won't call it stuck yet. "
            "Cursor stdout/stderr is only available when the process exits."
        )
    else:
        lines.append("")
        lines.append(f"Task is `{status}` — not in an active coding run.")

    latest = task_events.latest_event(task["id"])
    if latest:
        lines.append(f"- Latest event: {latest['message']}")
    return "\n".join(lines)


def facts_for_llm(task: dict[str, Any]) -> str:
    """Compact factual block for Groq phrasing — no invention allowed beyond this."""
    snap = snapshot(task)
    lines = [
        f"task_id={snap['task_id']}",
        f"project={snap['project']}",
        f"status={snap['status']}",
        f"stage={snap['execution_stage']}",
        f"current={snap['current_label']}",
        f"elapsed={snap['duration']}",
        f"last_activity={snap['last_activity']}",
        f"files={len(snap['modified_files'])}",
        f"blocker={snap.get('blocker') or ''}",
    ]
    if snap["completed"]:
        lines.append("completed=" + "; ".join(snap["completed"]))
    if snap["remaining"]:
        lines.append("remaining=" + "; ".join(snap["remaining"]))
    for ev in snap["events"][-8:]:
        lines.append(f"event: {ev['message']}")
    return "\n".join(lines)


def refresh_task(task_id: str) -> dict[str, Any] | None:
    return tasks.get_task(task_id)


# Stable markers so webchat can render a timeline card without guessing prose.
_COMPLETION_BEGIN = "=== Task completion ==="
_COMPLETION_END = "=== End ==="


def format_completion_report(
    *,
    task_id: str,
    title: str,
    steps: list[dict[str, Any]],
    status_label: str = "Completed",
    footnotes: list[str] | None = None,
) -> str:
    """Build a detailed step timeline for publish/apply completion (chat + web UI).

    ``steps`` items: ``{title, detail, status}`` where status is
    ``completed`` | ``in_progress`` | ``ready`` | ``failed``.
    """
    lines = [
        _COMPLETION_BEGIN,
        f"Task {task_id}",
        f"Status: {status_label}",
        (title or "").strip() or "Task finished.",
        "",
    ]
    for i, step in enumerate(steps, start=1):
        st = (step.get("status") or "completed").strip().lower()
        # ASCII markers stay reliable on Windows consoles and WhatsApp clients.
        mark = {
            "completed": "[done]",
            "in_progress": "[live]",
            "ready": "[ ]",
            "failed": "[fail]",
        }.get(st, "[done]")
        title_s = (step.get("title") or f"Step {i}").strip()
        detail_s = (step.get("detail") or "").strip()
        lines.append(f"{i}. {mark} {title_s}")
        if detail_s:
            lines.append(f"   {detail_s}")
    notes = [n.strip() for n in (footnotes or []) if n and str(n).strip()]
    if notes:
        lines.append("")
        for note in notes:
            lines.append(note)
    lines.append(_COMPLETION_END)
    return "\n".join(lines)


def parse_completion_report(text: str) -> dict[str, Any] | None:
    """Parse a completion report produced by ``format_completion_report``."""
    raw = (text or "").strip()
    if not raw.startswith(_COMPLETION_BEGIN) or _COMPLETION_END not in raw:
        return None
    body = raw[len(_COMPLETION_BEGIN) :].split(_COMPLETION_END, 1)[0].strip()
    lines = [ln.rstrip() for ln in body.splitlines()]
    if len(lines) < 3:
        return None
    task_line = lines[0].strip()
    status_line = lines[1].strip()
    title = lines[2].strip()
    task_id = ""
    if task_line.lower().startswith("task "):
        task_id = task_line[5:].strip()
    status_label = status_line
    if status_line.lower().startswith("status:"):
        status_label = status_line.split(":", 1)[1].strip() or "Completed"
    steps: list[dict[str, Any]] = []
    footnotes: list[str] = []
    i = 3
    while i < len(lines):
        ln = lines[i].strip()
        if not ln:
            i += 1
            # Blank lines before any step are spacing; after steps they start footnotes.
            if steps:
                while i < len(lines):
                    rest = lines[i].strip()
                    if rest:
                        footnotes.append(rest)
                    i += 1
                break
            continue
        m = re.match(
            r"^(\d+)\.\s*(?:\[(done|live|fail| )\]|([✓●○✗]))\s+(.+)$",
            ln,
        )
        if not m:
            if steps:
                footnotes.append(ln)
                i += 1
                continue
            i += 1
            continue
        ascii_mark = (m.group(2) or "").strip().lower()
        uni_mark = m.group(3) or ""
        step_title = m.group(4).strip()
        if ascii_mark == "done" or uni_mark == "✓":
            status = "completed"
        elif ascii_mark == "live" or uni_mark == "●":
            status = "in_progress"
        elif ascii_mark == "fail" or uni_mark == "✗":
            status = "failed"
        elif ascii_mark == "" or uni_mark == "○":
            status = "ready"
        else:
            status = "completed"
        detail = ""
        if i + 1 < len(lines) and lines[i + 1].startswith("   "):
            detail = lines[i + 1].strip()
            i += 1
        steps.append({"title": step_title, "detail": detail, "status": status})
        i += 1
    if not steps:
        return None
    return {
        "task_id": task_id,
        "status_label": status_label,
        "title": title,
        "steps": steps,
        "footnotes": footnotes,
    }


def publish_action_title(action: str) -> str:
    """Human title for a publish/apply completion card."""
    key = (action or "").upper()
    return {
        "APPLY": "Apply changes to project.",
        "PUSH": "Approve, push, and apply to project.",
        "PR": "Open pull request and apply to project.",
        "DEPLOY": "Run configured deploy command.",
        "COMMIT_APPLY": "Commit local changes and apply to project.",
    }.get(key, "Publish task changes.")
