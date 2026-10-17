"""Groq (OpenAI-compatible) helper for natural chat understanding.

Classifies user messages into orchestrator intents and drafts ChatGPT-style
replies for informational turns. Uses recent chat history so follow-ups like
"do it again" / "the task I gave you earlier" keep context.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from orchestrator import config
from orchestrator.converse import Intent, get_pending, last_work

log = logging.getLogger("orchestrator.llm_chat")

KINDS = frozenset(
    {
        "greet",
        "thanks",
        "help",
        "cancel",
        "projects",
        "scan_projects",
        "set_projects_root",
        "show_projects_root",
        "register_project",
        "update_project",
        "remove_project",
        "tasks",
        "status",
        "remaining",
        "done_check",
        "estimate",
        "changes",
        "stuck",
        "continue_work",
        "has_project",
        "ask_instruction",
        "task",
        "task_need_project",
        "approve",
        "reject",
        "cancel_task",
        "local_git",
        "retry",
        "chat",
    }
)
ACTIONS = frozenset({"PUSH", "APPLY", "PR", "DEPLOY", "REJECT", "COMMIT", "STASH", "COMMIT_APPLY"})
REPLY_KINDS = frozenset(
    {
        "greet",
        "thanks",
        "help",
        "cancel",
        "chat",
        "projects",
        "tasks",
        "has_project",
        "ask_instruction",
        "task_need_project",
    }
)


@dataclass
class LlmResult:
    intent: Intent
    reply: str | None = None


def enabled() -> bool:
    return bool(config.GROQ_API_KEY) and config.GROQ_CHAT_ENABLED


def voice_enabled() -> bool:
    return bool(config.GROQ_API_KEY) and config.GROQ_VOICE_ENABLED


def transcribe(
    audio: bytes,
    *,
    filename: str = "voice.webm",
    content_type: str = "application/octet-stream",
    language: str | None = "en",
) -> str:
    """Transcribe a short voice clip via Groq Whisper. Raises on failure."""
    if not voice_enabled():
        raise RuntimeError("Voice transcription is not configured")
    if not audio:
        raise ValueError("Empty audio")
    _charge_groq()
    url = config.GROQ_BASE_URL.rstrip("/") + "/audio/transcriptions"
    headers = {"Authorization": f"Bearer {config.GROQ_API_KEY}"}
    data: dict[str, str] = {
        "model": config.GROQ_WHISPER_MODEL or "whisper-large-v3-turbo",
        "response_format": "json",
    }
    if language:
        data["language"] = language
    files = {
        "file": (
            filename or "voice.webm",
            audio,
            content_type or "application/octet-stream",
        )
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(url, headers=headers, data=data, files=files)
        resp.raise_for_status()
        body = resp.json()
    text = str(body.get("text") or "").strip()
    if not text:
        raise ValueError("No speech detected")
    return text[:4000]


def understand(
    text: str,
    registry: dict[str, Any],
    *,
    sender: str = "",
) -> LlmResult | None:
    """Return classified intent (+ optional natural reply), or None to use regex."""
    if not enabled():
        return None
    body = (text or "").strip()
    if not body:
        return None
    try:
        payload = _chat_completion(
            _system_prompt(registry, sender),
            body,
            temperature=0.35,
            history=_chat_history(sender, current=body),
        )
        return _parse_payload(payload, registry, body)
    except Exception as exc:  # noqa: BLE001 - fall back quietly
        log.warning("Groq understand failed: %s", exc)
        return None


def phrase(
    purpose: str,
    facts: str,
    *,
    user_question: str = "",
) -> str | None:
    """Rewrite factual notes into a natural ChatGPT-style reply."""
    if not enabled():
        return None
    facts = (facts or "").strip()
    if not facts:
        return None
    system = (
        "You write short, warm replies for a coding assistant chat "
        "(same tone as ChatGPT). Use ONLY the facts given. "
        "Do not invent projects, tasks, capabilities, file changes, "
        "test results, or time estimates.\n\n"
        "Style:\n"
        "- Sound like a helpful person, not a status report or CLI dump\n"
        "- Prefer 1-3 short paragraphs; light bullets only if the list is long\n"
        "- End with one natural next-step question or invitation\n"
        "- No markdown headings, no JSON\n"
        "- Never say 'just a few minutes' or invent ETAs\n"
        "- Keep under 700 characters when possible (900 max)\n\n"
        "Return ONLY JSON: {\"reply\": \"...\"}"
    )
    user = f"Purpose: {purpose}\n\nFacts:\n{facts}"
    if user_question.strip():
        user = f"User asked: {user_question.strip()}\n\n{user}"
    try:
        data = _chat_completion(system, user, temperature=0.55)
        return _clean_reply(data.get("reply"))
    except Exception as exc:  # noqa: BLE001
        log.warning("Groq phrase failed: %s", exc)
        return None


def project_facts(registry: dict[str, Any]) -> str:
    if not registry:
        return "No projects are registered yet."
    lines = [f"There are {len(registry)} projects:"]
    for name, cfg in registry.items():
        kind = cfg.get("type", "project")
        if kind == "git":
            where = "GitHub-linked"
        elif kind == "local":
            where = "local folder on the laptop"
        else:
            where = str(kind)
        extras = []
        if cfg.get("allow_push"):
            extras.append("push allowed after approval")
        if cfg.get("allow_deploy"):
            extras.append("deploy allowed after approval")
        extra = f" ({', '.join(extras)})" if extras else ""
        lines.append(f"- {name}: {where}{extra}")
    if config.DRY_RUN:
        lines.append("Mode: practice/dry-run (prepare work, do not run coding agent yet).")
    else:
        lines.append("Mode: live (changes happen in a safe copy until the user approves).")
    return "\n".join(lines)


def task_facts(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "The user has no recent tasks yet."
    lines = ["Recent tasks (newest first):"]
    for row in rows[:12]:
        instr = (row.get("instruction") or "").replace("\n", " ").strip()
        if len(instr) > 100:
            instr = instr[:97] + "..."
        status = row.get("status") or "?"
        stage = row.get("execution_stage") or ""
        stage_bit = f" stage={stage}" if stage else ""
        lines.append(f"- {row.get('id')} {row.get('project')}: {status}{stage_bit} — {instr}")
    return "\n".join(lines)


def _chat_history(sender: str, *, current: str) -> list[dict[str, str]]:
    """Load shared conversation turns for any channel (web / Telegram / WhatsApp).

    Scoped to the sender's active project so LifeOS history does not leak after a switch.
    """
    if not sender:
        return []
    try:
        from orchestrator import history, session

        project = (session.get(sender).get("active_project") or None) or None
        rows = history.recent(sender, limit=14, project=project)
    except Exception:  # noqa: BLE001
        return []
    out: list[dict[str, str]] = []
    current_norm = (current or "").strip()
    skipped_current = False
    for row in rows:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        # Drop the just-stored current user turn (we send it as the final user msg).
        if (
            not skipped_current
            and row.get("direction") == "in"
            and text == current_norm
        ):
            skipped_current = True
            continue
        role = "user" if row.get("direction") == "in" else "assistant"
        # Keep history compact for the classifier.
        if len(text) > 500:
            text = text[:497] + "..."
        out.append({"role": role, "content": text})
    return out[-12:]


def _system_prompt(registry: dict[str, Any], sender: str) -> str:
    facts = project_facts(registry)
    pending = get_pending(sender) if sender else None
    pending_bits = ""
    if pending:
        pending_bits = (
            f"\nPending clarification: kind={pending.get('kind')}, "
            f"project={pending.get('project')}, "
            f"instruction={str(pending.get('instruction') or '')[:200]}"
        )
    remembered = last_work(sender) if sender else None
    memory_bits = ""
    if remembered:
        memory_bits = (
            f"\nLast work request to remember: project={remembered.get('project')}, "
            f"instruction={str(remembered.get('instruction') or '')[:300]}"
        )
    session_bits = ""
    task_bits = ""
    if sender:
        try:
            from orchestrator import session, tasks

            ctx = session.get(sender)
            if ctx.get("active_project") or ctx.get("active_task_id"):
                session_bits = (
                    f"\nActive session: project={ctx.get('active_project')}, "
                    f"task_id={ctx.get('active_task_id')}"
                )
            rows = tasks.list_tasks_for_sender(sender, limit=8)
            if rows:
                task_bits = "\n\n" + task_facts(rows)
        except Exception:  # noqa: BLE001
            task_bits = ""
    return (
        "You are the conversational brain for a coding orchestrator chat. "
        "Users talk casually (like ChatGPT). You receive recent conversation "
        "history — use it so follow-ups make sense.\n\n"
        "IMPORTANT: You are NOT the coding agent. You classify intents and draft "
        "informational replies. Never invent execution progress, file changes, "
        "timings, or test results. Status/remaining/done/estimate/changes/stuck "
        "replies must set reply=null so the server answers from task evidence.\n\n"
        f"{facts}"
        f"{task_bits}"
        f"{pending_bits}"
        f"{memory_bits}"
        f"{session_bits}\n\n"
        "Return ONLY a JSON object with keys:\n"
        "- kind: one of greet, thanks, help, cancel, projects, scan_projects, "
        "set_projects_root, show_projects_root, register_project, update_project, "
        "remove_project, tasks, status, "
        "remaining, done_check, estimate, changes, stuck, continue_work, "
        "has_project, ask_instruction, task, task_need_project, approve, reject, "
        "cancel_task, retry, chat\n"
        "- project: project id from the list (or folder id for register_project), or null\n"
        "- instruction: what to change (for task / task_need_project / retry), or null\n"
        "- updates: object of fields for update_project "
        "(allow_push/allow_deploy/apply_local bools, or display_name/description/…), else null\n"
        "- task_id: 12-char hex id if mentioned, else null\n"
        "- action: PUSH, APPLY, PR, DEPLOY, or REJECT when approving/rejecting, else null\n"
        "- reply: natural message ONLY for greet, thanks, help, cancel, chat, "
        "projects, tasks, has_project, ask_instruction, task_need_project; "
        "null for status/remaining/done_check/estimate/changes/stuck/continue_work/"
        "approve/reject/cancel_task/task/retry/scan_projects/set_projects_root/"
        "show_projects_root/register_project/update_project/remove_project\n\n"
        "Rules:\n"
        "- Use conversation history + Active session. If the user already chose a "
        "project and then describes a bug/change, kind=task with that project + instruction.\n"
        '- \"let\'s work on X\" / \"work on X\" without a change → kind \"ask_instruction\"\n'
        '- \"what\'s remaining?\" / \"what\'s left?\" → kind \"remaining\"\n'
        '- \"done?\" / \"are you finished?\" → kind \"done_check\"\n'
        '- \"how long will it take?\" → kind \"estimate\" (reply null; server refuses unsupported ETAs)\n'
        '- \"what did you change?\" / \"which files?\" → kind \"changes\"\n'
        '- \"why is it stuck?\" / \"any errors?\" → kind \"stuck\"\n'
        '- \"continue working\" / \"resume\" / \"keep going on that\" → kind \"continue_work\" '
        "(ONLY explicit continue/resume wording — never for a new change request)\n"
        "- If Recent tasks show queued/running/publishing work and the user describes a "
        "NEW distinct change/bug/feature, kind=task (starts a parallel Cursor agent on "
        "the same project). Do NOT fold a new request into continue_work or status.\n"
        '- \"do it again\", \"retry\", \"yeah let\'s do it again\" → kind \"retry\"\n'
        '- Asking what / which / how many / types of projects → kind \"projects\"\n'
        '- \"scan projects\" / find unregistered folders → kind \"scan_projects\" '
        "(put an optional folder path in instruction for \"scan projects from C:/…\")\n"
        '- \"set projects root C:/laragon/www\" → kind \"set_projects_root\" '
        "with instruction=path\n"
        '- \"where is the projects root?\" → kind \"show_projects_root\"\n'
        '- \"add project X\" / \"register X\" → kind \"register_project\" with project=X\n'
        '- \"update project X set allow_push true\" → kind \"update_project\" with updates\n'
        '- \"remove project X\" / \"unregister X\" → kind \"remove_project\"\n'
        '- Asking about recent work / tasks → kind \"tasks\"\n'
        '- Wanting code changed on a known project → kind \"task\"\n'
        '- Wanting code changed but no project named → kind \"task_need_project\" '
        "(unless Active session has a project — then kind task)\n"
        '- Approve / push / apply / PR / deploy → kind \"approve\" with action\n'
        '- \"commit my local changes\" / \"stash local changes\" / '
        '\"commit local and apply\" → kind \"local_git\" with action '
        "COMMIT, STASH, or COMMIT_APPLY (optional commit message in instruction)\n"
        '- Reject / discard → kind \"reject\"\n'
        '- Cancel a running task → kind \"cancel_task\"\n'
        '- Cancel clarifying a question → kind \"cancel\"\n'
        '- Small talk only when nothing actionable → kind \"chat\"\n'
        "- Never invent registered project names outside the known list "
        "(register_project may use a new folder id)\n"
        "- Keep reply under 900 characters, no markdown headings\n"
        "- Do not apologize repeatedly or re-ask for the project if history already has it"
    )


def _charge_groq() -> None:
    from orchestrator.quotas import assert_groq_allowed, record

    assert_groq_allowed()
    record("groq")


def _chat_completion(
    system: str,
    user: str,
    *,
    temperature: float = 0.2,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    url = config.GROQ_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})
    _charge_groq()
    data = {
        "model": config.GROQ_MODEL,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }
    with httpx.Client(timeout=25) as client:
        resp = client.post(url, headers=headers, json=data)
        resp.raise_for_status()
        body = resp.json()
    content = body["choices"][0]["message"]["content"]
    return _extract_json(content)


def _extract_json(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _clean_reply(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    for ch in ("\u202f", "\u00a0", "\u2009", "\u200a", "\u200b"):
        text = text.replace(ch, " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return None
    return text[:900]


def _parse_payload(data: dict[str, Any], registry: dict[str, Any], raw: str) -> LlmResult | None:
    kind = str(data.get("kind") or "").strip().lower()
    if kind not in KINDS:
        return None

    project = data.get("project")
    project_s = str(project).strip() if project else None
    if project_s:
        match = next((n for n in registry if n.lower() == project_s.lower()), None)
        if match:
            project_s = match
        elif kind in {"register_project", "remove_project", "update_project"}:
            # Keep the token (new folder id or case-insensitive name).
            pass
        elif kind in {"task", "has_project", "ask_instruction", "retry"}:
            project_s = None
            kind = "task_need_project" if kind in {"task", "retry"} else kind
            if kind == "has_project":
                kind = "chat"
        else:
            project_s = None

    instruction = data.get("instruction")
    instruction_s = str(instruction).strip() if instruction else None
    if instruction_s and len(instruction_s) > 2000:
        instruction_s = instruction_s[:2000]

    updates: dict[str, Any] | None = None
    raw_updates = data.get("updates")
    if kind == "update_project" and isinstance(raw_updates, dict):
        from orchestrator.converse import parse_project_updates
        from orchestrator.projects import UPDATABLE_FIELDS

        try:
            # Normalize via the same parser used by regex intents when possible.
            bits = []
            for key, value in raw_updates.items():
                if key not in UPDATABLE_FIELDS:
                    continue
                bits.append(f"{key}={value}")
            updates = parse_project_updates(", ".join(bits)) if bits else None
        except ValueError:
            updates = None
        if not updates:
            return None

    task_id = data.get("task_id")
    task_id_s = str(task_id).strip().lower() if task_id else None
    if task_id_s and not re.fullmatch(r"[a-f0-9]{12}", task_id_s):
        task_id_s = None

    action = data.get("action")
    action_s = str(action).strip().upper() if action else None
    if action_s and action_s not in ACTIONS:
        action_s = None
    if kind == "approve" and not action_s:
        action_s = "PUSH"
    if kind == "reject":
        action_s = "REJECT"
    if kind == "local_git" and action_s not in {"COMMIT", "STASH", "COMMIT_APPLY"}:
        action_s = "COMMIT"

    reply_s = _clean_reply(data.get("reply"))
    if kind not in REPLY_KINDS:
        reply_s = None
    elif reply_s and kind == "projects":
        if registry and not any(name.lower() in reply_s.lower() for name in registry):
            reply_s = None

    if kind == "retry":
        # Prefer model-filled fields; caller may also fill from memory.
        pass
    elif kind == "task" and (not project_s or not instruction_s):
        if instruction_s and not project_s:
            kind = "task_need_project"
        else:
            return None
    elif kind in {"register_project", "remove_project"} and not project_s:
        return None
    elif kind == "update_project" and (not project_s or not updates):
        return None
    elif kind == "set_projects_root" and not instruction_s:
        return None

    intent = Intent(
        kind=kind,
        project=project_s,
        instruction=instruction_s,
        task_id=task_id_s,
        action=action_s,
        updates=updates,
        raw=raw,
    )
    return LlmResult(intent=intent, reply=reply_s)
