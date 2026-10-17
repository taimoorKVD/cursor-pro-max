"""Parse Cursor CLI ``--output-format stream-json`` NDJSON into evidence events.

Cursor emits tool events shaped like::

    {"type":"tool_call","subtype":"started","tool_call":{"readToolCall":{"args":{"path":"..."}}}}

Only high-signal activity advances stages (tool reads → investigating, writes → implementing).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class StreamEvidence:
    """Accumulated evidence from an agent stream."""

    tool_calls: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    text_chunks: list[str] = field(default_factory=list)
    result_text: str = ""
    session_id: str = ""
    raw_events: int = 0
    saw_tool: bool = False
    saw_write: bool = False
    saw_read: bool = False


# Cursor CLI keys: readToolCall, writeToolCall, editToolCall, grepToolCall, …
_TOOL_CALL_KEY = re.compile(r"^([A-Za-z0-9]+)ToolCall$")
_WRITE_KINDS = frozenset(
    {"write", "edit", "delete", "searchreplace", "applypatch", "createfile", "strreplace"}
)
_READ_KINDS = frozenset(
    {
        "read",
        "grep",
        "glob",
        "ls",
        "listdir",
        "semanticsearch",
        "search",
        "readdir",
        "shell",  # shell alone is ambiguous — treat as activity, not write
    }
)
_WRITE_HINT = re.compile(
    r"\b(write|edit|delete|search_replace|apply_patch|create_file|StrReplace|Write)\b",
    re.I,
)
_READ_HINT = re.compile(
    r"\b(read|grep|glob|search|list_dir|ls|SemanticSearch|shell)\b",
    re.I,
)


def _human_tool_name(raw: str) -> str:
    """readToolCall → Read, writeToolCall → Write, Grep → Grep."""
    m = _TOOL_CALL_KEY.match(raw)
    if m:
        return m.group(1)[0].upper() + m.group(1)[1:]
    return raw.strip()[:80] or "tool"


def _kind_bucket(name: str) -> str:
    """Return 'write', 'read', or 'other' from a tool display/key name."""
    key = name.strip()
    m = _TOOL_CALL_KEY.match(key)
    base = (m.group(1) if m else key).lower().replace("_", "")
    if base in _WRITE_KINDS or _WRITE_HINT.search(key):
        return "write"
    if base in _READ_KINDS or _READ_HINT.search(key):
        return "read"
    return "other"


def _extract_cursor_tool(data: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    """From a stream event, return (tool_name, args_dict).

    Handles:
    - tool_call: { readToolCall: { args: {...} } }
    - tool_call: { function: { name, arguments } }
    - flat name / tool fields (legacy / tests)
    """
    tc = data.get("tool_call")
    if isinstance(tc, dict) and tc:
        # Preferred Cursor shape: single *ToolCall key
        for key, body in tc.items():
            if key == "function" and isinstance(body, dict):
                name = body.get("name")
                args = body.get("arguments") or body.get("args") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                if isinstance(name, str) and name.strip():
                    return name.strip(), args if isinstance(args, dict) else {}
                continue
            if _TOOL_CALL_KEY.match(key) or key.endswith("ToolCall"):
                body_dict = body if isinstance(body, dict) else {}
                args = body_dict.get("args") or body_dict.get("arguments") or {}
                if not isinstance(args, dict):
                    args = {}
                return _human_tool_name(key), args
            # Unknown nested key — still treat as a tool if it has args
            if isinstance(body, dict) and ("args" in body or "arguments" in body):
                args = body.get("args") or body.get("arguments") or {}
                if not isinstance(args, dict):
                    args = {}
                return _human_tool_name(key), args

        # Legacy: tool_call.name
        name = tc.get("name")
        if isinstance(name, str) and name.strip():
            args = tc.get("arguments") or tc.get("args") or tc.get("input") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            return name.strip(), args if isinstance(args, dict) else {}

    for key in ("tool", "name", "toolName"):
        val = data.get(key)
        if isinstance(val, str) and val.strip() and val.strip().lower() not in {"tool_call", "tool"}:
            args = data.get("arguments") or data.get("args") or data.get("input") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            return val.strip(), args if isinstance(args, dict) else {}
    return None, None


def _short_path(path: str) -> str:
    """Prefer a short relative path for progress UI (drop .../workspaces/<id>/)."""
    norm = path.replace("\\", "/")
    marker = "/workspaces/"
    if marker in norm:
        rest = norm.split(marker, 1)[1]
        if "/" in rest:
            return rest.split("/", 1)[1] or rest
    # Drop drive-rooted noise when it is clearly a repo file
    for tip in ("/app/", "/resources/", "/tests/", "/config/", "/public/", "/src/"):
        idx = norm.lower().find(tip)
        if idx >= 0:
            return norm[idx + 1 :]
    if len(norm) > 72:
        return "…" + norm[-60:]
    return norm


def _path_from_args(args: dict[str, Any] | None, data: dict[str, Any]) -> str | None:
    if isinstance(args, dict):
        for key in ("path", "file", "file_path", "filePath", "target_file", "filename", "uri"):
            val = args.get(key)
            if isinstance(val, str) and val.strip() and len(val) < 400:
                return val.strip().replace("\\", "/")
    return _extract_path(data)


def parse_line(line: str, evidence: StreamEvidence) -> dict[str, Any] | None:
    """Parse one NDJSON line. Returns a compact event dict for logging, or None."""
    text = (line or "").strip()
    if not text:
        return None
    if not (text.startswith("{") and text.endswith("}")):
        if len(text) > 8:
            evidence.text_chunks.append(text[:500])
            return {"kind": "text_line", "message": text[:240]}
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    evidence.raw_events += 1

    sid = data.get("session_id") or data.get("chat_id") or data.get("chatId")
    if isinstance(sid, str) and sid.strip():
        evidence.session_id = sid.strip()

    etype = str(
        data.get("type") or data.get("event") or data.get("kind") or data.get("role") or ""
    ).lower()
    subtype = str(data.get("subtype") or "").lower()

    # --- Cursor tool_call events (readToolCall / writeToolCall / …) ---
    if etype == "tool_call" or "tool" in etype or "function" in etype:
        # Prefer started; still accept events without subtype. Skip completed duplicates
        # unless we have not yet seen this tool (keeps UI quieter).
        tool_name, args = _extract_cursor_tool(data)
        if not tool_name:
            # type is tool_call but shape unrecognized — count as opaque tool activity
            evidence.saw_tool = True
            if subtype == "completed":
                return None
            return {
                "kind": "tool",
                "tool": "tool_call",
                "write": False,
                "message": "Tool activity (unparsed)",
            }

        bucket = _kind_bucket(tool_name)
        path = _path_from_args(args, data)
        evidence.saw_tool = True
        evidence.tool_calls.append(tool_name[:80])
        if bucket == "write":
            evidence.saw_write = True
        elif bucket == "read":
            evidence.saw_read = True
        if path:
            evidence.files_touched.append(path)
            if bucket == "write" or _WRITE_HINT.search(path):
                evidence.saw_write = True

        if subtype == "completed":
            # Don't spam progress with completion echoes; stage already updated on start.
            return None

        short = _short_path(path) if path else None
        if short:
            msg = f"{tool_name} {short}"
        else:
            msg = tool_name
        return {
            "kind": "tool",
            "tool": tool_name[:80],
            "path": path,
            "write": bucket == "write",
            "message": msg[:400],
        }

    # --- Assistant message (complete segment between tools) ---
    if etype == "assistant":
        msg_obj = data.get("message")
        chunks: list[str] = []
        if isinstance(msg_obj, dict):
            content = msg_obj.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        t = str(block.get("text") or "").strip()
                        if t:
                            chunks.append(t)
            elif isinstance(content, str) and content.strip():
                chunks.append(content.strip())
        content_flat = data.get("content") or data.get("text")
        if isinstance(content_flat, str) and content_flat.strip():
            chunks.append(content_flat.strip())
        if chunks:
            joined = " ".join(chunks).strip()
            evidence.text_chunks.append(joined[:800])
            # Skip duplicate partial flushes when stream-partial-output is on
            if data.get("model_call_id") and data.get("timestamp_ms"):
                return None
            preview = joined[:200].replace("\n", " ")
            if len(preview) > 12:
                return {"kind": "assistant", "message": f"Agent: {preview}"}
        return None

    # --- Terminal result ---
    if etype in {"result", "done", "completed"} or data.get("status") in {"completed", "success"}:
        result = data.get("result")
        if isinstance(result, str) and result.strip():
            evidence.result_text = result.strip()[-2200:]
        msg = str(data.get("message") or result or "Agent stream result")[:240]
        if isinstance(msg, str):
            return {"kind": "result", "message": msg}
        return {"kind": "result", "message": "Agent stream result"}

    # --- Generic content fallback ---
    content = data.get("content") or data.get("text") or data.get("result")
    if isinstance(content, str) and content.strip():
        evidence.text_chunks.append(content.strip()[:800])
        if etype in {"result", "final", "completed"} or data.get("subtype") == "success":
            evidence.result_text = content.strip()[-2200:]
        return None
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = str(block.get("text") or "")
                if t:
                    evidence.text_chunks.append(t[:800])
            if isinstance(block, dict) and block.get("type") in {"tool_use", "tool_call"}:
                evidence.saw_tool = True
                name = str(block.get("name") or "tool")[:80]
                evidence.tool_calls.append(name)
                bucket = _kind_bucket(name)
                if bucket == "write":
                    evidence.saw_write = True
                elif bucket == "read":
                    evidence.saw_read = True
                return {
                    "kind": "tool",
                    "tool": name,
                    "write": bucket == "write",
                    "message": f"Tool: {name}",
                }

    return None


def _extract_path(data: dict[str, Any]) -> str | None:
    for key in ("path", "file", "filePath", "filename", "uri"):
        val = data.get(key)
        if isinstance(val, str) and val.strip() and len(val) < 400:
            return val.strip().replace("\\", "/")
    args = data.get("arguments") or data.get("input") or data.get("args")
    if isinstance(args, dict):
        for key in ("path", "file_path", "filePath", "target_file", "file"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip().replace("\\", "/")
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            if isinstance(parsed, dict):
                return _extract_path(parsed)
        except json.JSONDecodeError:
            pass
    return None


def stage_from_evidence(evidence: StreamEvidence) -> str | None:
    """Return an evidence-backed stage upgrade, or None to keep agent_running."""
    if evidence.saw_write:
        return "implementing"
    if evidence.saw_read or (
        evidence.saw_tool and any(_READ_HINT.search(t) for t in evidence.tool_calls)
    ):
        return "investigating"
    if evidence.saw_tool:
        # Generic tool use without read/write classification — stay opaque.
        return None
    return None


def make_line_handler(
    evidence: StreamEvidence,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> Callable[[str], None]:
    def _handle(line: str) -> None:
        ev = parse_line(line, evidence)
        if ev and on_event:
            on_event(ev)

    return _handle
