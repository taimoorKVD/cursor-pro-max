"""Closed-loop learning: outcomes, thumbs feedback, playbook, intent corrections.

Does not fine-tune any model. Improves the next Cursor run and Groq classifier
via durable SQLite memory injected into prompts / few-shots.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from orchestrator import db

log = logging.getLogger("orchestrator.learning")

# Caps keep prompts small and SQLite tidy (overridable via config / .env).
_PLAYBOOK_MAX_DEFAULT = 12
_PAST_SUCCESS_MAX_DEFAULT = 5
_FEWSHOT_MAX_DEFAULT = 8
_RULE_MAX_CHARS = 280
_INSTRUCTION_SNIP = 160
_SUMMARY_SNIP = 180


def _playbook_max() -> int:
    try:
        from orchestrator import config

        return int(getattr(config, "LEARNING_PLAYBOOK_MAX_RULES", _PLAYBOOK_MAX_DEFAULT))
    except Exception:  # noqa: BLE001
        return _PLAYBOOK_MAX_DEFAULT


def _past_success_max() -> int:
    try:
        from orchestrator import config

        return int(getattr(config, "LEARNING_PAST_SUCCESSES_MAX", _PAST_SUCCESS_MAX_DEFAULT))
    except Exception:  # noqa: BLE001
        return _PAST_SUCCESS_MAX_DEFAULT


def _fewshot_max() -> int:
    try:
        from orchestrator import config

        return int(getattr(config, "LEARNING_FEWSHOT_MAX", _FEWSHOT_MAX_DEFAULT))
    except Exception:  # noqa: BLE001
        return _FEWSHOT_MAX_DEFAULT


def ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS learning_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            task_id TEXT,
            sender TEXT,
            project TEXT,
            instruction TEXT,
            decision TEXT NOT NULL,
            action TEXT,
            summary_excerpt TEXT,
            modified_files TEXT,
            detail TEXT
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_outcomes_project "
        "ON learning_outcomes(project, ts)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_outcomes_task "
        "ON learning_outcomes(task_id, id)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS learning_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            sender TEXT,
            message_id INTEGER,
            rating TEXT NOT NULL,
            message_text TEXT,
            project TEXT,
            task_id TEXT
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_feedback_msg "
        "ON learning_feedback(message_id, id)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS learning_intent_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            sender TEXT,
            message_text TEXT NOT NULL,
            predicted_kind TEXT,
            corrected_kind TEXT NOT NULL,
            source TEXT
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_intent_ts "
        "ON learning_intent_corrections(ts)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS learning_playbook (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            project TEXT NOT NULL,
            rule_text TEXT NOT NULL,
            source_task_id TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_playbook_project "
        "ON learning_playbook(project, active, id)"
    )


def _enabled() -> bool:
    try:
        from orchestrator import config

        return bool(getattr(config, "LEARNING_ENABLED", True))
    except Exception:  # noqa: BLE001
        return True


def record_outcome(
    *,
    decision: str,
    task: dict[str, Any] | None = None,
    task_id: str | None = None,
    sender: str | None = None,
    project: str | None = None,
    instruction: str | None = None,
    action: str | None = None,
    summary_excerpt: str | None = None,
    modified_files: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Persist approve/reject/publish outcomes for later prompt injection."""
    if not _enabled():
        return
    decision_s = (decision or "").strip().lower()
    if decision_s not in {
        "approved",
        "rejected",
        "published",
        "publish_failed",
        "thumbs_up",
        "thumbs_down",
    }:
        return
    if task:
        task_id = task_id or task.get("id")
        sender = sender or task.get("sender")
        project = project or task.get("project")
        instruction = instruction if instruction is not None else task.get("instruction")
        summary_excerpt = summary_excerpt if summary_excerpt is not None else task.get("summary")
        modified_files = modified_files if modified_files is not None else task.get("modified_files")
    payload = json.dumps(detail or {}, separators=(",", ":"), ensure_ascii=True)[:1500]
    try:
        with db.DB_LOCK, db.connect() as c:
            ensure_schema(c)
            c.execute(
                """INSERT INTO learning_outcomes
                   (ts, task_id, sender, project, instruction, decision, action,
                    summary_excerpt, modified_files, detail)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    db.now(),
                    (task_id or "")[:32] or None,
                    (sender or "")[:80] or None,
                    (project or "")[:120] or None,
                    (instruction or "")[:2000] or None,
                    decision_s,
                    (action or "")[:32] or None,
                    (summary_excerpt or "")[:1000] or None,
                    (modified_files or "")[:2000] or None,
                    payload,
                ),
            )
    except Exception:  # noqa: BLE001
        log.exception("record_outcome failed")


def record_feedback(
    *,
    rating: str,
    sender: str,
    message_id: int | None = None,
    message_text: str | None = None,
    project: str | None = None,
    task_id: str | None = None,
) -> bool:
    """Store thumbs up/down from web chat. Returns False if invalid."""
    if not _enabled():
        return False
    rating_s = (rating or "").strip().lower()
    if rating_s in {"up", "helpful", "good", "+1"}:
        rating_s = "up"
    elif rating_s in {"down", "not_helpful", "bad", "-1"}:
        rating_s = "down"
    else:
        return False
    try:
        with db.DB_LOCK, db.connect() as c:
            ensure_schema(c)
            c.execute(
                """INSERT INTO learning_feedback
                   (ts, sender, message_id, rating, message_text, project, task_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    db.now(),
                    (sender or "")[:80],
                    message_id,
                    rating_s,
                    (message_text or "")[:2000] or None,
                    (project or "")[:120] or None,
                    (task_id or "")[:32] or None,
                ),
            )
        record_outcome(
            decision="thumbs_up" if rating_s == "up" else "thumbs_down",
            sender=sender,
            project=project,
            task_id=task_id,
            summary_excerpt=(message_text or "")[:300],
            detail={"message_id": message_id},
        )
        return True
    except Exception:  # noqa: BLE001
        log.exception("record_feedback failed")
        return False


def record_intent_correction(
    *,
    message_text: str,
    predicted_kind: str | None,
    corrected_kind: str,
    sender: str | None = None,
    source: str = "resolve_intent",
) -> None:
    """Remember when regex/control path overrode the LLM classifier."""
    if not _enabled():
        return
    msg = (message_text or "").strip()
    corrected = (corrected_kind or "").strip().lower()
    predicted = (predicted_kind or "").strip().lower() or None
    if not msg or not corrected:
        return
    if predicted and predicted == corrected:
        return
    # Skip noise: unknown→anything is not a useful few-shot.
    if predicted in {None, "", "unknown"} and corrected in {"unknown", "chat"}:
        return
    try:
        with db.DB_LOCK, db.connect() as c:
            ensure_schema(c)
            # Dedup identical recent corrections (same text + kinds).
            row = c.execute(
                """SELECT id FROM learning_intent_corrections
                   WHERE message_text=? AND IFNULL(predicted_kind,'')=?
                     AND corrected_kind=?
                   ORDER BY id DESC LIMIT 1""",
                (msg[:800], predicted or "", corrected),
            ).fetchone()
            if row:
                return
            c.execute(
                """INSERT INTO learning_intent_corrections
                   (ts, sender, message_text, predicted_kind, corrected_kind, source)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    db.now(),
                    (sender or "")[:80] or None,
                    msg[:800],
                    predicted,
                    corrected,
                    (source or "")[:64],
                ),
            )
    except Exception:  # noqa: BLE001
        log.exception("record_intent_correction failed")


def maybe_append_playbook(task: dict[str, Any], *, action: str | None = None) -> None:
    """After a successful publish, distill a short reusable project rule."""
    if not _enabled():
        return
    project = str(task.get("project") or "").strip()
    instruction = (task.get("instruction") or "").strip()
    if not project or len(instruction) < 8:
        return
    summary = (task.get("summary") or "").strip()
    files = _files_snip(task.get("modified_files"))
    instr = _one_line(instruction, _INSTRUCTION_SNIP)
    summ = _one_line(summary, _SUMMARY_SNIP)
    parts = [f"When asked like: {instr}"]
    if files:
        parts.append(f"files that mattered: {files}")
    if summ:
        parts.append(f"result: {summ}")
    if action:
        parts.append(f"published via {action}")
    rule = " — ".join(parts)
    rule = rule[:_RULE_MAX_CHARS]
    norm = _normalize_rule(rule)
    try:
        with db.DB_LOCK, db.connect() as c:
            ensure_schema(c)
            cap = _playbook_max()
            existing = c.execute(
                """SELECT id, rule_text FROM learning_playbook
                   WHERE project=? AND active=1 ORDER BY id DESC LIMIT ?""",
                (project, cap * 2),
            ).fetchall()
            for row in existing:
                if _normalize_rule(row["rule_text"]) == norm:
                    return
            c.execute(
                """INSERT INTO learning_playbook
                   (ts, project, rule_text, source_task_id, active)
                   VALUES (?, ?, ?, ?, 1)""",
                (db.now(), project, rule, str(task.get("id") or "")[:32] or None),
            )
            # Keep only the newest N active rules per project.
            ids = [
                r["id"]
                for r in c.execute(
                    """SELECT id FROM learning_playbook
                       WHERE project=? AND active=1 ORDER BY id DESC""",
                    (project,),
                ).fetchall()
            ]
            for old_id in ids[cap:]:
                c.execute(
                    "UPDATE learning_playbook SET active=0 WHERE id=?",
                    (old_id,),
                )
    except Exception:  # noqa: BLE001
        log.exception("maybe_append_playbook failed")


def playbook_for_project(project: str, *, limit: int | None = None) -> list[str]:
    if not project or not _enabled():
        return []
    lim = limit if limit is not None else _playbook_max()
    try:
        with db.DB_LOCK, db.connect() as c:
            ensure_schema(c)
            rows = c.execute(
                """SELECT rule_text FROM learning_playbook
                   WHERE project=? AND active=1
                   ORDER BY id DESC LIMIT ?""",
                (project, lim),
            ).fetchall()
        return [str(r["rule_text"]).strip() for r in rows if r["rule_text"]]
    except Exception:  # noqa: BLE001
        return []


def past_successes_for_project(
    project: str,
    *,
    instruction: str = "",
    limit: int | None = None,
) -> list[dict[str, str]]:
    """Recent published/approved outcomes, preferring keyword overlap with instruction."""
    if not project or not _enabled():
        return []
    lim = limit if limit is not None else _past_success_max()
    if lim <= 0:
        return []
    try:
        with db.DB_LOCK, db.connect() as c:
            ensure_schema(c)
            rows = c.execute(
                """SELECT instruction, summary_excerpt, modified_files, decision
                   FROM learning_outcomes
                   WHERE project=? AND decision IN ('published', 'approved')
                   ORDER BY id DESC LIMIT 40""",
                (project,),
            ).fetchall()
    except Exception:  # noqa: BLE001
        return []
    scored: list[tuple[int, dict[str, str]]] = []
    needles = _tokens(instruction)
    for row in rows:
        instr = str(row["instruction"] or "").strip()
        if not instr:
            continue
        score = _overlap(needles, _tokens(instr))
        scored.append(
            (
                score,
                {
                    "instruction": instr[:_INSTRUCTION_SNIP],
                    "summary": str(row["summary_excerpt"] or "")[:_SUMMARY_SNIP],
                    "files": _files_snip(row["modified_files"]),
                },
            )
        )
    scored.sort(key=lambda x: (-x[0],))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, item in scored:
        key = _normalize_rule(item["instruction"])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= lim:
            break
    return out


def intent_fewshots(*, limit: int | None = None) -> list[dict[str, str]]:
    """Recent corrections for Groq system prompt few-shots."""
    if not _enabled():
        return []
    lim = limit if limit is not None else _fewshot_max()
    if lim <= 0:
        return []
    try:
        with db.DB_LOCK, db.connect() as c:
            ensure_schema(c)
            rows = c.execute(
                """SELECT message_text, predicted_kind, corrected_kind
                   FROM learning_intent_corrections
                   ORDER BY id DESC LIMIT ?""",
                (lim * 3,),
            ).fetchall()
    except Exception:  # noqa: BLE001
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        msg = str(row["message_text"] or "").strip()
        corrected = str(row["corrected_kind"] or "").strip()
        if not msg or not corrected:
            continue
        key = _normalize_rule(msg)[:80]
        if key in seen:
            continue
        seen.add(key)
        item = {
            "message": msg[:200],
            "kind": corrected,
        }
        predicted = str(row["predicted_kind"] or "").strip()
        if predicted:
            item["not"] = predicted
        out.append(item)
        if len(out) >= lim:
            break
    return out


def format_playbook_section(project: str, *, instruction: str = "") -> str:
    """Text block for Cursor agent prompt (playbook + similar past successes)."""
    if not project or not _enabled():
        return ""
    rules = playbook_for_project(project)
    past = past_successes_for_project(project, instruction=instruction)
    if not rules and not past:
        return ""
    lines: list[str] = [
        "LEARNED PROJECT MEMORY (from prior approved work — prefer these patterns when relevant):"
    ]
    for i, rule in enumerate(rules, 1):
        lines.append(f"{i}. {rule}")
    if past:
        lines.append("")
        lines.append("SIMILAR PAST SUCCESSES:")
        for i, item in enumerate(past, 1):
            bit = f'{i}. Asked: "{item["instruction"]}"'
            if item.get("files"):
                bit += f" | files: {item['files']}"
            if item.get("summary"):
                bit += f" | outcome: {item['summary']}"
            lines.append(bit)
    return "\n".join(lines)


def format_intent_fewshot_section() -> str:
    shots = intent_fewshots()
    if not shots:
        return ""
    lines = [
        "Learned intent corrections (match these patterns; prefer corrected kind):"
    ]
    for s in shots:
        msg = s["message"].replace("\n", " ")
        if s.get("not"):
            lines.append(f'- "{msg}" → kind "{s["kind"]}" (not "{s["not"]}")')
        else:
            lines.append(f'- "{msg}" → kind "{s["kind"]}"')
    return "\n".join(lines)


def _one_line(text: str, max_len: int) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _files_snip(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, list):
        items = [str(x).strip() for x in raw if str(x).strip()]
    else:
        text = str(raw).strip()
        if not text:
            return ""
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                items = [str(x).strip() for x in parsed if str(x).strip()]
            else:
                items = [p.strip() for p in text.replace(",", "\n").splitlines() if p.strip()]
        except json.JSONDecodeError:
            items = [p.strip() for p in text.replace(",", "\n").splitlines() if p.strip()]
    # Prefer basename for brevity
    short = []
    for p in items[:8]:
        short.append(p.replace("\\", "/").rsplit("/", 1)[-1])
    return ", ".join(short)


def _normalize_rule(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", (text or "").lower()) if t}


def _overlap(a: set[str], b: set[str]) -> int:
    if not a or not b:
        return 0
    return len(a & b)
