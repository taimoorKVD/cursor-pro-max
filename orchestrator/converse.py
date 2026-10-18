"""Natural-language intent parsing for chat (ChatGPT/Cursor-style)."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

# sender -> pending clarification (short-lived; also persisted for restarts)
_pending: dict[str, dict[str, Any]] = {}
_PENDING_TTL = 600
# sender -> last work request (survives failed runs / "do it again" / process restart)
_memory: dict[str, dict[str, Any]] = {}
_MEMORY_TTL = 86400


def ensure_schema(conn) -> None:
    """Durable pending clarifications + last-work memory (survive orchestrator restart)."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS conversation_pending (
            sender TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            ts REAL NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS conversation_memory (
            sender TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            instruction TEXT NOT NULL,
            task_id TEXT,
            ts REAL NOT NULL
        )"""
    )


def _db_write_pending(sender: str, item: dict[str, Any] | None) -> None:
    try:
        from orchestrator import db

        with db.DB_LOCK, db.connect() as c:
            ensure_schema(c)
            if item is None:
                c.execute("DELETE FROM conversation_pending WHERE sender=?", (sender,))
                return
            c.execute(
                """INSERT INTO conversation_pending (sender, payload, ts)
                   VALUES (?, ?, ?)
                   ON CONFLICT(sender) DO UPDATE SET
                     payload=excluded.payload,
                     ts=excluded.ts""",
                (
                    sender,
                    json.dumps(item, ensure_ascii=False),
                    float(item.get("ts") or time.time()),
                ),
            )
    except Exception:  # noqa: BLE001
        pass


def _db_read_pending(sender: str) -> dict[str, Any] | None:
    try:
        from orchestrator import db

        with db.DB_LOCK, db.connect() as c:
            ensure_schema(c)
            row = c.execute(
                "SELECT payload, ts FROM conversation_pending WHERE sender=?",
                (sender,),
            ).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload"] or "{}")
        if not isinstance(payload, dict):
            return None
        payload.setdefault("ts", float(row["ts"] or 0))
        return payload
    except Exception:  # noqa: BLE001
        return None


def _db_write_memory(sender: str, item: dict[str, Any] | None) -> None:
    try:
        from orchestrator import db

        with db.DB_LOCK, db.connect() as c:
            ensure_schema(c)
            if item is None:
                c.execute("DELETE FROM conversation_memory WHERE sender=?", (sender,))
                return
            c.execute(
                """INSERT INTO conversation_memory
                   (sender, project, instruction, task_id, ts)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(sender) DO UPDATE SET
                     project=excluded.project,
                     instruction=excluded.instruction,
                     task_id=excluded.task_id,
                     ts=excluded.ts""",
                (
                    sender,
                    str(item.get("project") or ""),
                    str(item.get("instruction") or ""),
                    item.get("task_id"),
                    float(item.get("ts") or time.time()),
                ),
            )
    except Exception:  # noqa: BLE001
        pass


def _db_read_memory(sender: str) -> dict[str, Any] | None:
    try:
        from orchestrator import db

        with db.DB_LOCK, db.connect() as c:
            ensure_schema(c)
            row = c.execute(
                """SELECT project, instruction, task_id, ts
                   FROM conversation_memory WHERE sender=?""",
                (sender,),
            ).fetchone()
        if not row:
            return None
        project = (row["project"] or "").strip()
        instruction = (row["instruction"] or "").strip()
        if not project or not instruction:
            return None
        return {
            "ts": float(row["ts"] or 0),
            "project": project,
            "instruction": instruction,
            "task_id": row["task_id"],
        }
    except Exception:  # noqa: BLE001
        return None


@dataclass
class Intent:
    kind: str
    project: str | None = None
    instruction: str | None = None
    task_id: str | None = None
    action: str | None = None
    updates: dict[str, Any] | None = None
    raw: str = ""


def _parse_bool_token(value: str) -> bool | None:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on", "enable", "enabled"}:
        return True
    if lowered in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return None


def parse_project_updates(spec: str) -> dict[str, Any]:
    """Parse 'allow_push true' / 'allow_push=true, apply_local false' style updates."""
    updates: dict[str, Any] = {}
    chunks = re.split(r"[,;]+", spec.strip())
    for chunk in chunks:
        piece = chunk.strip()
        if not piece:
            continue
        m = re.match(
            r"^(?:set\s+)?([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|:|\s)\s*(.+)$",
            piece,
            re.I,
        )
        if not m:
            raise ValueError(f"Could not parse update field: {piece!r}")
        key = m.group(1).strip().lower()
        raw_val = m.group(2).strip().strip("'\"")
        if key in {"allow_push", "allow_deploy", "apply_local"}:
            parsed = _parse_bool_token(raw_val)
            if parsed is None:
                raise ValueError(f"{key} must be true or false, got {raw_val!r}")
            updates[key] = parsed
        elif key in {
            "path",
            "type",
            "test_command",
            "deploy_command",
            "display_name",
            "description",
            "instructions",
            "default_branch",
        }:
            updates[key] = raw_val
        else:
            raise ValueError(f"Unsupported update field: {key}")
    if not updates:
        raise ValueError("No update fields provided")
    return updates


def _is_scan_projects_request(lowered: str) -> bool:
    if re.search(
        r"\b(scan|discover)\b.{0,40}\bprojects?\b|"
        r"\bfind\b.{0,20}\b(new\s+)?projects?\b|"
        r"\b(new|unregistered)\s+(folders?|projects?)\b|"
        r"\bfolders?\b.{0,40}\b(aren't|arent|not)\s+registered\b|"
        r"\bwhat\s+folders\b",
        lowered,
    ):
        return True
    return False


def _extract_scan_root_path(raw: str) -> str | None:
    """Pull a filesystem path from 'scan projects from C:/laragon/www'."""
    m = re.search(
        r"\b(?:from|in|at)\s+((?:[a-zA-Z]:[\\/]|\\\\|~/|/)[^\r\n]+)$",
        raw.strip(),
        re.I,
    )
    if not m:
        return None
    return m.group(1).strip().strip("\"'")


def _extract_set_root_path(raw: str) -> str | None:
    m = re.match(
        r"^(?:set|use|change)\s+(?:the\s+)?(?:projects?\s+)?"
        r"(?:root|folder|directory|dir)\s+(?:to\s+)?(.+)$",
        raw.strip(),
        re.I,
    )
    if not m:
        return None
    return m.group(1).strip().strip("\"'")


def _is_show_projects_root_request(lowered: str) -> bool:
    return bool(
        re.search(
            r"\b(what|where|show|which)\b.{0,40}\bprojects?\s+(root|folder|directory|dir)\b|"
            r"\bprojects?\s+(root|folder|directory|dir)\b\s*\??$",
            lowered,
        )
    )


def clear_pending(sender: str) -> None:
    if not sender:
        return
    _pending.pop(sender, None)
    _db_write_pending(sender, None)


def get_pending(sender: str) -> dict[str, Any] | None:
    if not sender:
        return None
    item = _pending.get(sender)
    if item is None:
        item = _db_read_pending(sender)
        if item is not None:
            _pending[sender] = item
    if not item:
        return None
    if time.time() - float(item.get("ts") or 0) > _PENDING_TTL:
        clear_pending(sender)
        return None
    return item


def set_pending(sender: str, **fields: Any) -> None:
    if not sender:
        return
    fields["ts"] = time.time()
    _pending[sender] = fields
    _db_write_pending(sender, fields)


def remember_work(
    sender: str,
    *,
    project: str,
    instruction: str,
    task_id: str | None = None,
) -> None:
    """Remember the last coding request so retry / continue works after restart."""
    if not sender:
        return
    item = {
        "ts": time.time(),
        "project": project,
        "instruction": instruction,
        "task_id": task_id,
    }
    _memory[sender] = item
    _db_write_memory(sender, item)


def forget_work(sender: str) -> None:
    """Drop remembered work for a sender (e.g. chat clear)."""
    if not sender:
        return
    _memory.pop(sender, None)
    _db_write_memory(sender, None)


def last_work(sender: str) -> dict[str, Any] | None:
    """Return last work request, loading from SQLite after process restart if needed."""
    if not sender:
        return None
    item = _memory.get(sender)
    if item is None:
        item = _db_read_memory(sender)
        if item is not None:
            _memory[sender] = item
    if not item:
        return None
    if time.time() - float(item.get("ts") or 0) > _MEMORY_TTL:
        forget_work(sender)
        return None
    return item


def clear_conversation_state(sender: str) -> None:
    """Clear pending clarifications and remembered work for a sender."""
    clear_pending(sender)
    forget_work(sender)


def looks_like_retry(text: str) -> bool:
    lowered = _norm(text).lower()
    return bool(
        re.search(
            r"\b(try|do|run|start)\s+(it\s+)?again\b|"
            r"\blet'?s\s+do\s+it\s+again\b|"
            r"\bretry\b|"
            r"\bthe\s+(same\s+)?(task|request|one)\s+(i\s+)?(gave|mentioned|asked)\b|"
            r"\bearlier\s+(task|request)\b|"
            r"\bsame\s+(task|thing|request)\b|"
            r"\byeah\b.*\bagain\b|"
            r"\byes\b.*\bagain\b",
            lowered,
        )
    )


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _project_aliases(registry: dict[str, Any]) -> dict[str, str]:
    """Map lowercase tokens -> canonical project id."""
    aliases: dict[str, str] = {}
    for name, cfg in registry.items():
        aliases[name.lower()] = name
        display = str(cfg.get("display_name") or "").strip()
        if display:
            aliases[display.lower()] = name
        # lifeOS folder style
        aliases[name.replace("-", " ").lower()] = name
        aliases[name.replace("_", " ").lower()] = name
    return aliases


def find_project_in_text(text: str, registry: dict[str, Any]) -> str | None:
    aliases = _project_aliases(registry)
    lowered = text.lower()
    # Longer names first so "staging-beydountech" wins over "beydountech"
    for alias in sorted(aliases, key=len, reverse=True):
        if re.search(rf"(?<![a-z0-9_-]){re.escape(alias)}(?![a-z0-9_-])", lowered):
            return aliases[alias]
    return None


def extract_task_id(text: str) -> str | None:
    m = re.search(r"\b([a-f0-9]{12})\b", text, re.I)
    return m.group(1).lower() if m else None


_WORK_VERBS = (
    r"add|fix|update|improve|create|implement|refactor|write|change|"
    r"build|remove|delete|make|please|can you|could you|help me"
)


# Verbs that mean "change code", not polite list questions like "can you show projects".
_MUTATION_VERBS = (
    r"add|fix|update|improve|create|implement|refactor|write|change|"
    r"build|remove|delete|make"
)


def _is_projects_list_request(lowered: str) -> bool:
    """True for casual project-list asks, not '... from the lifeos project' work requests."""
    if re.fullmatch(r"projects?", lowered):
        return True
    if not re.search(r"\bprojects?\b", lowered):
        return False
    # Work requests that merely mention "project" must not be stolen
    # (e.g. "remove dark mode from the lifeos project").
    if re.search(rf"\b({_MUTATION_VERBS})\b", lowered):
        return False
    # Any question / inventory phrasing around "project(s)".
    if re.search(
        r"\b(what|which|how many|list|show|see|tell|give|got|have|has|we've|"
        r"we('ve| have)|you('ve| have)|i('ve| have)|our|my|your|available|"
        r"registered|type|types|kind|kinds|sort|work on)\b",
        lowered,
    ):
        return True
    return False


def _strip_project_mention(raw: str, project: str, registry: dict[str, Any]) -> str:
    """Remove 'on lifeos' / 'from the lifeos project' style mentions from the instruction."""
    instruction = raw
    aliases = [
        alias
        for alias, name in _project_aliases(registry).items()
        if name == project
    ]
    for alias in sorted(aliases, key=len, reverse=True):
        instruction = re.sub(
            rf"(?i)\b(?:on|in|for|using|from)\s+(?:the\s+)?{re.escape(alias)}"
            rf"(?:\s+project)?\b[:,\-]?\s*",
            "",
            instruction,
            count=1,
        )
        instruction = re.sub(
            rf"(?i)\b{re.escape(alias)}(?:\s+project)?\b[:,\-]?\s*",
            "",
            instruction,
            count=1,
        )
        if instruction != raw:
            break
    instruction = re.sub(r"(?i)\s+\bproject\b\s*$", "", instruction)
    return instruction.strip(" ,:-")


def parse_intent(text: str, registry: dict[str, Any], sender: str = "") -> Intent:
    raw = _norm(text)
    lowered = raw.lower()

    # Resolve pending clarifications / offered project from prior turn
    pending = get_pending(sender) if sender else None
    if pending and lowered in {"cancel", "nevermind", "never mind", "stop", "no"}:
        clear_pending(sender)
        return Intent(kind="cancel", raw=raw)

    if pending and pending.get("kind") == "confirm_remove_project" and pending.get("project"):
        if lowered in {"yes", "y", "confirm", "ok", "okay", "do it"}:
            return Intent(
                kind="remove_project",
                project=str(pending["project"]),
                action="CONFIRM",
                raw=raw,
            )
        # Any other reply drops the confirmation and continues parsing.
        clear_pending(sender)

    if pending and pending.get("kind") == "need_project":
        project = find_project_in_text(raw, registry)
        if project or lowered in {n.lower() for n in registry}:
            if not project:
                project = next(n for n in registry if n.lower() == lowered)
            attach_ids = [
                str(a).strip()
                for a in (pending.get("attachment_ids") or [])
                if str(a).strip()
            ]
            clear_pending(sender)
            if attach_ids:
                try:
                    from orchestrator import attachments as chat_attachments

                    chat_attachments.set_pending(sender, attach_ids)
                except Exception:  # noqa: BLE001
                    pass
            return Intent(
                kind="task",
                project=project,
                instruction=pending.get("instruction") or raw,
                raw=raw,
            )

    # After "Yes - lifeos is registered. Want me to work on it?"
    # accept: "yes, remove the welcome back text..."
    # Do NOT steal unrelated questions (e.g. "what projects do I have?").
    # Do NOT steal registry commands ("create project X", "scan projects", …).
    if pending and pending.get("kind") == "offer_project" and pending.get("project"):
        offered = pending["project"]
        if _is_projects_list_request(lowered):
            clear_pending(sender)
            return Intent(kind="projects", raw=raw)
        registry_cmd = bool(
            re.match(
                r"^(?:create|new)\s+(?:a\s+)?(?:new\s+)?project\b|"
                r"^(?:add|register|remove|unregister|delete)\s+(?:project\s+)?|"
                r"^(?:scan|discover)\b|"
                r"^(?:set|use|change)\s+(?:the\s+)?(?:projects?\s+)?"
                r"(?:root|folder|directory|dir)\b|"
                r"^(?:update|edit)\s+project\b|"
                r"^(?:find)\b.{0,20}\b(?:new\s+)?projects?\b",
                lowered,
            )
        )
        workish = (not registry_cmd) and bool(
            re.search(
                rf"\b({_WORK_VERBS}|yes|yeah|yep|sure|ok|okay|do it|go ahead)\b",
                lowered,
            )
        )
        # Require an affirmative or a mutation verb — not every long message.
        if workish:
            instruction = raw
            # Strip leading yes/sure/ok
            instruction = re.sub(
                r"^(yes|yeah|yep|sure|ok|okay|please|do it|go ahead)[,!.\s\-]*",
                "",
                instruction,
                flags=re.I,
            ).strip()
            if len(instruction) < 5:
                # bare "yes" - ask what to do
                return Intent(kind="ask_instruction", project=offered, raw=raw)
            clear_pending(sender)
            return Intent(kind="task", project=offered, instruction=instruction, raw=raw)

    # Greetings
    if re.fullmatch(
        r"(hi|hello|hey|yo|good\s+(morning|afternoon|evening)|howdy)[!?.]*",
        lowered,
    ):
        return Intent(kind="greet", raw=raw)

    # Thanks
    if re.fullmatch(r"(thanks|thank you|thx|ty)[!!.]*", lowered):
        return Intent(kind="thanks", raw=raw)

    # Explicit classic commands still work
    if re.fullmatch(r"(help|\?|commands|/help|/start|what can you do)", lowered):
        return Intent(kind="help", raw=raw)

    # Product / architecture questions — grounded facts, never a coding task
    try:
        from orchestrator import product_facts

        if product_facts.looks_like_product_question(raw) or re.fullmatch(
            r"how does this work\??",
            lowered,
        ):
            return Intent(kind="how_it_works", raw=raw)
    except Exception:  # noqa: BLE001
        if re.fullmatch(r"how does this work\??", lowered):
            return Intent(kind="how_it_works", raw=raw)

    # Registry management (must beat generic "add/remove … project" work intents)
    set_root = _extract_set_root_path(raw)
    if set_root:
        return Intent(kind="set_projects_root", instruction=set_root, raw=raw)

    if _is_show_projects_root_request(lowered):
        return Intent(kind="show_projects_root", raw=raw)

    # Create-from-scratch before scan: "new project demo" must not match scan's
    # "new projects" phrasing.
    m = re.fullmatch(
        r"(?:create|new)\s+(?:a\s+)?(?:new\s+)?project\s+"
        r"(?:called\s+|named\s+|folder\s+)?"
        r"([a-zA-Z0-9][a-zA-Z0-9 _-]{0,63}?)"
        r"(?:\s*:\s*(.+))?$",
        raw,
        re.I | re.S,
    )
    if m:
        name = m.group(1).strip().rstrip(".,!")
        instruction = (m.group(2) or "").strip() or None
        if name:
            return Intent(
                kind="create_project",
                project=name,
                instruction=instruction,
                raw=raw,
            )

    if _is_scan_projects_request(lowered):
        scan_root = _extract_scan_root_path(raw)
        return Intent(kind="scan_projects", instruction=scan_root, raw=raw)

    m = re.fullmatch(
        r"(?:add|register)\s+(?:project\s+)?([a-zA-Z0-9_-]+)",
        raw,
        re.I,
    )
    if m:
        return Intent(kind="register_project", project=m.group(1), raw=raw)

    m = re.fullmatch(
        r"(?:remove|unregister|delete)\s+(?:project\s+)?([a-zA-Z0-9_-]+)",
        raw,
        re.I,
    )
    if m:
        return Intent(kind="remove_project", project=m.group(1), raw=raw)

    m = re.match(
        r"^(?:update|edit)\s+project\s+([a-zA-Z0-9_-]+)\s+(?:set\s+)?(.+)$",
        raw,
        re.I | re.S,
    )
    if m:
        try:
            updates = parse_project_updates(m.group(2))
        except ValueError:
            return Intent(kind="unknown", raw=raw)
        return Intent(
            kind="update_project",
            project=m.group(1),
            updates=updates,
            raw=raw,
        )

    # Rename chat / project display name (keeps project id).
    # Prefer the "... name ..." forms first so "name" is not treated as an id.
    rename_name = re.fullmatch(
        r"(?:rename|change|set)\s+(?:(?:the|this)\s+)?(?:chat|project)\s+name"
        r"(?:\s+(?:of|for)\s+([a-zA-Z0-9_-]+))?\s+(?:to|as|=)\s+(.+)",
        raw,
        re.I | re.S,
    )
    rename_id = re.fullmatch(
        r"(?:rename|change)\s+(?:(?:the|this)\s+)?(?:chat|project)\s+"
        r"(?!name\b)([a-zA-Z0-9_-]+)\s+(?:to|as)\s+(.+)",
        raw,
        re.I | re.S,
    )
    if rename_name or rename_id:
        if rename_name:
            project = (rename_name.group(1) or "").strip()
            new_name = rename_name.group(2).strip().strip("'\"")
            if not project and sender:
                try:
                    from orchestrator import session

                    project = (
                        session.get(sender).get("active_project") or ""
                    ).strip()
                except Exception:  # noqa: BLE001
                    project = ""
        else:
            project = rename_id.group(1).strip()
            new_name = rename_id.group(2).strip().strip("'\"")
        if new_name:
            return Intent(
                kind="update_project",
                project=project,
                updates={"display_name": new_name},
                raw=raw,
            )

    # "Do we have lifeos project?" / "is there a kv-hrms project?"
    project_ask = find_project_in_text(raw, registry)
    if project_ask and re.search(
        r"\b(do (we|you|i) have|is there|have you got|exists?|available)\b",
        lowered,
    ):
        return Intent(kind="has_project", project=project_ask, raw=raw)

    # List-projects only — do not match trailing "… lifeos project" work requests.
    if _is_projects_list_request(lowered):
        return Intent(kind="projects", raw=raw)

    if re.search(
        r"\b(list|show|my|recent)\s+tasks?\b|"
        r"\bwhat('s| is) (running|queued)\b|"
        r"^tasks?$",
        lowered,
    ):
        return Intent(kind="tasks", raw=raw)

    # Commit / stash local project WIP (so apply/push is not blocked by a dirty tree)
    if re.search(
        r"\b(commit(\s+and\s+apply)?|stash)\b.*\b(local|wip|changes|uncommitted)\b|"
        r"\b(commit|stash)\s+(my\s+)?(local\s+)?(changes|wip)\b|"
        r"\b(commit|stash)\s+local\b|"
        r"^(commit|stash)(\s+local)?(\s+changes)?$",
        lowered,
    ):
        action = "STASH" if re.search(r"\bstash\b", lowered) else "COMMIT"
        if action == "COMMIT" and re.search(r"\band\s+apply\b|\bthen\s+apply\b", lowered):
            action = "COMMIT_APPLY"
        msg = None
        m_msg = re.search(
            r"(?:commit(?:\s+and\s+apply)?|stash)\s+(?:my\s+)?"
            r"(?:local\s+)?(?:changes)?\s*"
            r"(?:with\s+message\s+|:\s*|—\s+|-\s+)(.+)$",
            raw.strip(),
            re.I,
        )
        if m_msg:
            msg = m_msg.group(1).strip().strip("\"'")
        return Intent(
            kind="local_git",
            project=None,
            instruction=msg,
            task_id=extract_task_id(raw),
            action=action,
            raw=raw,
        )

    # Approve / reject / push / apply / deploy / cancel in natural language
    task_id = extract_task_id(raw)
    if re.search(r"\b(reject|discard)\b", lowered) and (
        task_id or re.search(r"\b(it|that|this|last)\b", lowered) or lowered.strip() in {"reject", "discard"}
    ):
        return Intent(kind="reject", task_id=task_id, action="REJECT", raw=raw)

    if re.search(r"\b(cancel|stop|abort)\b", lowered) and (
        task_id
        or re.search(r"\b(task|job|run|it|that|this|last)\b", lowered)
        or lowered.strip() in {"cancel", "stop", "abort"}
    ):
        return Intent(kind="cancel_task", task_id=task_id, raw=raw)

    # "Create a pull request instead" / "open a PR" / "approve and create PR"
    if re.search(r"\b(pull[\s-]?request|pr)\b", lowered) and re.search(
        r"\b(create|open|make|file|raise|submit|approve)\b", lowered
    ):
        return Intent(kind="approve", task_id=task_id, action="PR", raw=raw)

    if re.search(r"\b(approve|push|deploy|ship|merge|apply)\b", lowered):
        if re.search(r"\bdeploy\b", lowered):
            action = "DEPLOY"
        elif re.search(r"\b(push|ship)\b", lowered):
            # "apply and push" / "approve and push" → PUSH (still applies locally when enabled)
            action = "PUSH"
        elif re.search(
            r"\bapply\b|"
            r"\b(merge (it |that )?locally|merge into (my )?project)\b",
            lowered,
        ):
            # Bare "apply" / "apply locally" / "approve and apply" → local merge only
            action = "APPLY"
        else:
            # "approve" / "merge" alone → PUSH path (push if allowed + apply_local)
            action = "PUSH"
        return Intent(kind="approve", task_id=task_id, action=action, raw=raw)

    # Done? (status question — not "please complete the form")
    if (
        re.fullmatch(r"done\??", lowered)
        or re.search(
            r"\b(are you|is it|is (the )?task)\s+done\??\b|"
            r"\b(are you|is it)\s+(finished|complete|completed)\??\b|"
            r"\bis (it|that|this) (done|finished|ready)\b|"
            r"^(all )?done\??$",
            lowered,
        )
    ) and not re.search(rf"\b({_MUTATION_VERBS})\b", lowered):
        return Intent(kind="done_check", task_id=task_id, raw=raw)

    # What's remaining / left
    if re.search(
        r"\bwhat('?s| is)?\s+(remaining|left|next)\b|"
        r"\b(remaining|left to do|what'?s left)\b|"
        r"\bhow much (is )?(left|remaining)\b",
        lowered,
    ):
        return Intent(kind="remaining", task_id=task_id, raw=raw)

    # How long / ETA / why taking so long
    if re.search(
        r"\bhow long\b|"
        r"\b(eta|estimate|time left|how much time)\b|"
        r"\bwhen (will|is) (it|this|that) (be )?(done|ready|finished)\b|"
        r"\bwhy (is it |are you )?(taking|so )?(so )?long\b|"
        r"\btaking so long\b",
        lowered,
    ):
        return Intent(kind="estimate", task_id=task_id, raw=raw)

    # What changes
    if re.search(
        r"\bwhat (did you |have you )?(change|changed|modify|modified|edit|edited)\b|"
        r"\bwhat changes?\b|"
        r"\b(show|list) (the )?(diff|changes|files)\b|"
        r"\bwhich files?\b",
        lowered,
    ):
        return Intent(kind="changes", task_id=task_id, raw=raw)

    # Why stuck
    if re.search(
        r"\b(why|are you|is it|is this|is that)\b.{0,40}\b(stuck|hanging|hung|frozen|stalled)\b|"
        r"\b(stuck|hanging|stalled)\b|"
        r"\bwhat('?s| is) (wrong|blocking|the (error|blocker))\b|"
        r"\b(any|what) errors?\b",
        lowered,
    ):
        return Intent(kind="stuck", task_id=task_id, raw=raw)

    # Continue working / resume
    if re.search(
        r"\bcontinue (working|please)?\b|"
        r"\b(resume|keep going|pick (it |this )?up)\b|"
        r"\btry (again|one more time)\b",
        lowered,
    ) and not looks_like_retry(raw):
        # "try again" also matches retry — prefer retry when memory exists; handled later
        return Intent(kind="continue_work", task_id=task_id, raw=raw)

    # Status
    if (
        re.search(r"\b(status|progress|what happened)\b", lowered)
        or re.search(r"how('s| is) .+ going", lowered)
        or re.search(r"\b(last|latest|current) task\b", lowered)
    ):
        return Intent(kind="status", task_id=task_id, raw=raw)

    # "Let's work on lifeos" / "work on lifeos" → select project, ask for instruction
    m = re.match(
        r"^(?:let'?s\s+)?(?:work\s+on|switch\s+to|use|work)\s+(?:the\s+)?"
        r"([a-zA-Z0-9_-]+)\s*[.!?]*$",
        raw,
        re.I,
    )
    if m:
        token = m.group(1).lower()
        project = next((n for n in registry if n.lower() == token), None)
        if not project:
            project = find_project_in_text(raw, registry)
        if project:
            return Intent(kind="ask_instruction", project=project, raw=raw)

    # Classic TASK syntax
    m = re.fullmatch(r"TASK\s+([a-zA-Z0-9_-]+)\s*:\s*(.{5,})", raw, re.I | re.S)
    if m:
        return Intent(kind="task", project=m.group(1), instruction=m.group(2).strip(), raw=raw)

    # Natural task: "on lifeos, add a README note"
    m = re.match(
        r"^(?:on|in|for|using)\s+([a-zA-Z0-9_-]+)\s*[,:\-]?\s+(.{5,})$",
        raw,
        re.I | re.S,
    )
    if m and m.group(1).lower() in {n.lower() for n in registry}:
        project = next(n for n in registry if n.lower() == m.group(1).lower())
        return Intent(kind="task", project=project, instruction=m.group(2).strip(), raw=raw)

    # "lifeos: fix login" or "lifeos - fix login"
    m = re.match(r"^([a-zA-Z0-9_-]+)\s*[:\-]\s*(.{5,})$", raw, re.I | re.S)
    if m and m.group(1).lower() in {n.lower() for n in registry}:
        project = next(n for n in registry if n.lower() == m.group(1).lower())
        return Intent(kind="task", project=project, instruction=m.group(2).strip(), raw=raw)

    # Mentions a known project + looks like a work request
    project = find_project_in_text(raw, registry)
    workish = bool(re.search(rf"\b({_WORK_VERBS})\b", lowered))
    if project and workish and len(raw) >= 12:
        instruction = _strip_project_mention(raw, project, registry)
        if len(instruction) < 5:
            instruction = raw
        return Intent(kind="task", project=project, instruction=instruction, raw=raw)

    # Work request without project — use durable active project when set
    if workish and len(raw) >= 12 and not project:
        active = None
        if sender:
            try:
                from orchestrator import session

                active = (session.get(sender).get("active_project") or "").strip() or None
            except Exception:  # noqa: BLE001
                active = None
        if active and active in registry:
            return Intent(kind="task", project=active, instruction=raw, raw=raw)
        # Pending offer_project also counts
        if pending and pending.get("kind") == "offer_project" and pending.get("project"):
            return Intent(
                kind="task",
                project=pending["project"],
                instruction=raw,
                raw=raw,
            )
        return Intent(kind="task_need_project", instruction=raw, raw=raw)

    # Last / latest task shorthand
    if re.fullmatch(r"(last|latest|current)( task)?", lowered):
        return Intent(kind="status", task_id=None, raw=raw)

    # "yeah let's do it again" / "the task I gave you earlier"
    if looks_like_retry(raw):
        work = last_work(sender) if sender else None
        if work and work.get("project") and work.get("instruction"):
            return Intent(
                kind="retry",
                project=str(work["project"]),
                instruction=str(work["instruction"]),
                task_id=work.get("task_id"),
                raw=raw,
            )
        return Intent(kind="retry", raw=raw)

    return Intent(kind="unknown", raw=raw)


# Publish / control verbs must not become Cursor coding tasks when Groq mislabels them.
_CONTROL_KINDS = frozenset({"approve", "reject", "cancel_task", "local_git"})


def resolve_intent(
    text: str,
    registry: dict[str, Any],
    *,
    sender: str = "",
    llm_intent: Intent | None = None,
) -> Intent:
    """Prefer deterministic regex for approve/apply/commit over LLM mislabels."""
    regex = parse_intent(text, registry, sender=sender)
    if llm_intent is None:
        return regex
    # Control phrases (apply / commit local / reject / …) always win — including
    # when the model returns a different control kind (e.g. approve/PUSH for
    # "commit local and apply"), or soft kinds like task/chat.
    if regex.kind in _CONTROL_KINDS or regex.kind == "how_it_works":
        return regex
    return llm_intent
