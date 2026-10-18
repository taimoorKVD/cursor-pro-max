"""Persist and summarize Cursor/agent token spend for the webchat sidebar."""
from __future__ import annotations

from typing import Any

from orchestrator import db


def ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS token_spend (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            kind TEXT NOT NULL,
            task_id TEXT,
            sender TEXT,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            cache_read_tokens INTEGER NOT NULL DEFAULT 0,
            cache_write_tokens INTEGER NOT NULL DEFAULT 0,
            session_id TEXT,
            request_id TEXT
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_token_spend_ts ON token_spend(ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_token_spend_kind_ts ON token_spend(kind, ts)")


def _day_start() -> int:
    now = db.now()
    return now - (now % 86400)


def _as_int(value: Any) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        try:
            return max(0, int(float(value)))
        except (TypeError, ValueError):
            return 0


def record(
    *,
    kind: str = "cursor_agent",
    task_id: str | None = None,
    sender: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    session_id: str | None = None,
    request_id: str | None = None,
) -> None:
    """Store one agent-turn spend row. No-op when all counts are zero."""
    inp = _as_int(input_tokens)
    out = _as_int(output_tokens)
    cache_r = _as_int(cache_read_tokens)
    cache_w = _as_int(cache_write_tokens)
    if inp + out + cache_r + cache_w <= 0:
        return
    kind_s = (kind or "cursor_agent").strip() or "cursor_agent"
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        c.execute(
            """INSERT INTO token_spend (
                ts, kind, task_id, sender,
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                session_id, request_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                db.now(),
                kind_s,
                (task_id or None),
                sender,
                inp,
                out,
                cache_r,
                cache_w,
                (session_id or None),
                (request_id or None),
            ),
        )


def record_from_usage(
    usage: dict[str, Any] | None,
    *,
    kind: str = "cursor_agent",
    task_id: str | None = None,
    sender: str | None = None,
    session_id: str | None = None,
    request_id: str | None = None,
) -> None:
    if not isinstance(usage, dict):
        return
    record(
        kind=kind,
        task_id=task_id,
        sender=sender,
        input_tokens=_as_int(
            usage.get("input_tokens")
            if usage.get("input_tokens") is not None
            else usage.get("inputTokens")
        ),
        output_tokens=_as_int(
            usage.get("output_tokens")
            if usage.get("output_tokens") is not None
            else usage.get("outputTokens")
        ),
        cache_read_tokens=_as_int(
            usage.get("cache_read_tokens")
            if usage.get("cache_read_tokens") is not None
            else usage.get("cacheReadTokens")
        ),
        cache_write_tokens=_as_int(
            usage.get("cache_write_tokens")
            if usage.get("cache_write_tokens") is not None
            else usage.get("cacheWriteTokens")
        ),
        session_id=session_id,
        request_id=request_id,
    )


def _empty_bucket() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "total_tokens": 0,
        "runs": 0,
    }


def _sum_rows(rows: list[Any]) -> dict[str, int]:
    bucket = _empty_bucket()
    for row in rows:
        inp = _as_int(row["input_tokens"])
        out = _as_int(row["output_tokens"])
        cache_r = _as_int(row["cache_read_tokens"])
        cache_w = _as_int(row["cache_write_tokens"])
        bucket["input_tokens"] += inp
        bucket["output_tokens"] += out
        bucket["cache_read_tokens"] += cache_r
        bucket["cache_write_tokens"] += cache_w
        bucket["runs"] += 1
    bucket["total_tokens"] = bucket["input_tokens"] + bucket["output_tokens"]
    return bucket


def summary() -> dict[str, Any]:
    """Return today / all-time spend plus the most recent turn."""
    day = _day_start()
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        today_rows = c.execute(
            """SELECT input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
               FROM token_spend WHERE ts>=?""",
            (day,),
        ).fetchall()
        all_rows = c.execute(
            """SELECT input_tokens, output_tokens, cache_read_tokens, cache_write_tokens
               FROM token_spend"""
        ).fetchall()
        last = c.execute(
            """SELECT ts, kind, task_id, input_tokens, output_tokens,
                      cache_read_tokens, cache_write_tokens, session_id
               FROM token_spend ORDER BY id DESC LIMIT 1"""
        ).fetchone()
    today = _sum_rows(today_rows)
    all_time = _sum_rows(all_rows)
    last_payload = None
    if last:
        last_payload = {
            "ts": int(last["ts"] or 0),
            "kind": str(last["kind"] or "cursor_agent"),
            "task_id": last["task_id"],
            "input_tokens": _as_int(last["input_tokens"]),
            "output_tokens": _as_int(last["output_tokens"]),
            "cache_read_tokens": _as_int(last["cache_read_tokens"]),
            "cache_write_tokens": _as_int(last["cache_write_tokens"]),
            "total_tokens": _as_int(last["input_tokens"]) + _as_int(last["output_tokens"]),
            "session_id": last["session_id"],
        }
    return {
        "today": today,
        "all_time": all_time,
        "last": last_payload,
    }
