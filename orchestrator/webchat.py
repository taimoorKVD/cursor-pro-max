"""Password-protected browser chat channel (single operator, sender id `web:owner`)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import secrets
import struct
import threading
import time
import zlib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from orchestrator import attachments as chat_attachments
from orchestrator import audit, config, db
from orchestrator.webchat_pages import (
    CHAT_HTML,
    FAVICON_LINKS,
    FONT_LINKS,
    LOGIN_HTML,
    QR_HTML,
    QR_PLACEHOLDER,
    STYLESHEET,
)

SENDER = "web:owner"
COOKIE = "orch_session"
MAX_TEXT = 4000
MAX_VOICE_BYTES = 8 * 1024 * 1024
MAX_FAILURES = 5
LOCKOUT_SEC = 900
MIN_PASSWORD_LEN = 12
HISTORY_LIMIT = 200
IMAGE_ONLY_PLACEHOLDER = "[Image attached]"
_VOICE_EXTS = {
    "audio/webm": ".webm",
    "audio/mp4": ".mp4",
    "audio/m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "video/mp4": ".mp4",
}

router = APIRouter()
_failures: dict[str, tuple[int, float]] = {}
_failures_lock = threading.Lock()


def enabled() -> bool:
    return len(config.WEBCHAT_PASSWORD) >= MIN_PASSWORD_LEN


def ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS web_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER NOT NULL,
            direction TEXT NOT NULL,
            text TEXT NOT NULL,
            level TEXT NOT NULL DEFAULT 'info',
            project TEXT
        )"""
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(web_messages)")}
    if "level" not in cols:
        conn.execute("ALTER TABLE web_messages ADD COLUMN level TEXT NOT NULL DEFAULT 'info'")
    if "project" not in cols:
        conn.execute("ALTER TABLE web_messages ADD COLUMN project TEXT")
    if "attachments" not in cols:
        conn.execute("ALTER TABLE web_messages ADD COLUMN attachments TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_web_messages_project ON web_messages(project, id)"
    )
    chat_attachments.ensure_schema(conn)


def _current_project() -> str | None:
    try:
        from orchestrator import session

        proj = (session.get(SENDER).get("active_project") or "").strip()
        return proj or None
    except Exception:  # noqa: BLE001
        return None


def store(
    direction: str,
    text: str,
    *,
    level: str = "info",
    mirror_history: bool = True,
    project: str | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> None:
    from orchestrator.notify import infer_level

    kind = infer_level(text, level if direction == "out" else "info")
    if direction == "in":
        kind = "info"
    if project is None:
        project = _current_project()
    attach_json = (
        chat_attachments.serialize_for_message(attachments) if attachments else None
    )
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        c.execute(
            "INSERT INTO web_messages (ts, direction, text, level, project, attachments) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (db.now(), direction, text, kind, project, attach_json),
        )
    # Keep shared conversation history in sync for Groq / follow-ups.
    if mirror_history:
        try:
            from orchestrator import history

            history_text = text
            if attachments:
                names = ", ".join(
                    str(a.get("filename") or "image") for a in attachments[:5]
                )
                history_text = f"{text}\n[attachments: {names}]".strip()
            history.append(SENDER, direction, history_text, level=kind, project=project)
        except Exception:  # noqa: BLE001
            pass


def _row_message(row) -> dict[str, Any]:
    item = dict(row)
    item["level"] = item.get("level") or "info"
    item["attachments"] = chat_attachments.deserialize_message_attachments(
        item.pop("attachments", None)
    )
    return item


def messages_after(after_id: int, *, project: str | None = None) -> list[dict[str, Any]]:
    """Return messages, optionally scoped to one project thread."""
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        if project:
            if after_id <= 0:
                rows = c.execute(
                    """SELECT id, ts, direction, text, level, project, attachments
                       FROM web_messages
                       WHERE project=? ORDER BY id DESC LIMIT ?""",
                    (project, HISTORY_LIMIT),
                ).fetchall()
                rows = list(reversed(rows))
            else:
                rows = c.execute(
                    """SELECT id, ts, direction, text, level, project, attachments
                       FROM web_messages
                       WHERE project=? AND id > ? ORDER BY id LIMIT ?""",
                    (project, after_id, HISTORY_LIMIT),
                ).fetchall()
        else:
            if after_id <= 0:
                rows = c.execute(
                    """SELECT id, ts, direction, text, level, project, attachments
                       FROM web_messages
                       ORDER BY id DESC LIMIT ?""",
                    (HISTORY_LIMIT,),
                ).fetchall()
                rows = list(reversed(rows))
            else:
                rows = c.execute(
                    """SELECT id, ts, direction, text, level, project, attachments
                       FROM web_messages
                       WHERE id > ? ORDER BY id LIMIT ?""",
                    (after_id, HISTORY_LIMIT),
                ).fetchall()
    return [_row_message(r) for r in rows]


def recent_messages(limit: int = 16, *, project: str | None = None) -> list[dict[str, Any]]:
    """Latest chat turns oldest→newest (for LLM context) — project-scoped when set."""
    limit = max(1, min(int(limit), 40))
    if project is None:
        project = _current_project()
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        if project:
            rows = c.execute(
                """SELECT id, ts, direction, text, level, project, attachments
                   FROM web_messages
                   WHERE project=? ORDER BY id DESC LIMIT ?""",
                (project, limit),
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT id, ts, direction, text, level, project, attachments
                   FROM web_messages ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
    return [_row_message(r) for r in reversed(list(rows))]


def clear_messages(*, project: str | None = None) -> None:
    """Wipe web chat history (operator reset), optionally for one project only."""
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        if project:
            c.execute("DELETE FROM web_messages WHERE project=?", (project,))
        else:
            c.execute("DELETE FROM web_messages")
        c.commit()


def seed_welcome() -> None:
    """Post a short ChatGPT-style greeting into an empty chat."""
    from orchestrator import preflight

    agent_ok, agent_detail = preflight.agent_available()
    if agent_ok:
        text = "Hi - what can I help you with?"
        level = "info"
    else:
        text = (
            "Hi - what can I help you with?\n\n"
            f"(Quick note: the coding agent on this laptop still needs setup — {agent_detail[:80]}.)"
        )
        level = "warning"
    store("out", text, level=level)


def _sign(issued: int) -> str:
    return hmac.new(
        config.WEBCHAT_PASSWORD.encode(), f"webchat:{issued}".encode(), hashlib.sha256
    ).hexdigest()


def _make_session() -> str:
    issued = int(time.time())
    return f"{issued}.{_sign(issued)}"


def _authed(request: Request) -> bool:
    if not enabled():
        return False
    issued_s, _, sig = request.cookies.get(COOKIE, "").partition(".")
    if not issued_s.isdigit() or not sig:
        return False
    issued = int(issued_s)
    if time.time() - issued > config.WEBCHAT_SESSION_DAYS * 86400:
        return False
    return hmac.compare_digest(sig, _sign(issued))


def _client_ip(request: Request) -> str:
    return request.headers.get("cf-connecting-ip") or (
        request.client.host if request.client else "unknown"
    )


def _is_https(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def _locked(ip: str) -> bool:
    with _failures_lock:
        count, last = _failures.get(ip, (0, 0.0))
        if count and time.time() - last >= LOCKOUT_SEC:
            _failures.pop(ip, None)
            return False
        return count >= MAX_FAILURES


def _record_failure(ip: str) -> None:
    with _failures_lock:
        count, _ = _failures.get(ip, (0, 0.0))
        _failures[ip] = (count + 1, time.time())


def _clear_failures(ip: str) -> None:
    with _failures_lock:
        _failures.pop(ip, None)


def _json(data: dict[str, Any], status: int = 200) -> JSONResponse:
    resp = JSONResponse(data, status_code=status)
    resp.headers["Cache-Control"] = "no-store"
    return resp


async def _read_json(request: Request) -> dict[str, Any] | None:
    if not request.headers.get("content-type", "").startswith("application/json"):
        return None
    try:
        data = await request.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _page(html: str, nonce: str, status: int = 200) -> HTMLResponse:
    resp = HTMLResponse(html.replace("__NONCE__", nonce), status_code=status)
    resp.headers["Content-Security-Policy"] = (
        f"default-src 'none'; script-src 'nonce-{nonce}'; "
        f"style-src 'nonce-{nonce}' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com data:; "
        "img-src 'self' data:; connect-src 'self'; "
        "worker-src 'self'; "
        "manifest-src 'self'; form-action 'none'; "
        "frame-ancestors 'none'; base-uri 'none'"
    )
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _is_direct_local(request: Request) -> bool:
    """True only for laptop browser hits (Host: localhost), not the public tunnel."""
    host = (request.headers.get("host") or "").split(":")[0].lower()
    return host in {"127.0.0.1", "localhost"}


def _tunnel_status_hint() -> str:
    """Best-effort reason when the public URL file is missing."""
    err_log = Path(config.BASE) / "data" / "logs" / "cloudflared-session.err.log"
    try:
        text = err_log.read_text(encoding="utf-8", errors="replace")[-4000:]
    except OSError:
        text = ""
    lower = text.lower()
    if "context deadline exceeded" in lower or "timeout exceeded" in lower:
        return (
            "Cloudflare quick tunnel can’t be created right now "
            "(api.trycloudflare.com timed out). Check internet/VPN/firewall, "
            "then wait — this page refreshes automatically."
        )
    if "failed to request quick tunnel" in lower:
        return (
            "Cloudflare rejected the quick tunnel request. "
            "The supervisor keeps retrying — this page refreshes when a URL is ready."
        )
    return (
        "Tunnel URL not found yet. The Cloudflare tunnel is reconnecting — "
        "this page refreshes automatically when it’s ready."
    )


def _tunnel_chat_url() -> tuple[str | None, str]:
    url_file = Path(config.BASE) / "data" / "logs" / "cloudflared-public-url.txt"  # project root
    if not url_file.is_file():
        return None, _tunnel_status_hint()
    raw = url_file.read_text(encoding="utf-8").strip().lstrip("\ufeff")
    if not raw.startswith("https://"):
        return None, "Tunnel URL file is invalid. Waiting for Cloudflare to publish a new URL."
    return raw.rstrip("/") + "/chat", ""


def _render_qr_html(chat_url: str | None, err: str, img: str = "") -> str:
    has_qr = bool(chat_url and img)
    has_url = bool(chat_url)
    return (
        QR_HTML.replace("__QR_IMG__", img if has_qr else QR_PLACEHOLDER)
        .replace("__CHAT_URL__", chat_url or "")
        .replace("__OPEN_HREF__", chat_url or "#")
        .replace("__ERROR__", err)
        .replace("__HAS_ERROR__", "1" if err else "0")
        .replace("__READY__", "1" if has_qr else "0")
        .replace("__BADGE_CLASS__", "" if has_qr else "hidden")
        .replace("__COPY_DISABLED__", "" if has_url else "disabled")
        .replace("__OPEN_DISABLED__", "false" if has_url else "true")
        .replace(
            "__META__",
            "Auto-refreshes if the tunnel URL changes."
            if has_qr
            else "Waiting for Cloudflare tunnel…",
        )
    )


def _qr_img_html(data: str) -> str:
    """PNG QR as <img data URI> — more reliable on-screen for iPhone Camera."""
    import segno

    qr = segno.make(data, error="h")
    buf = io.BytesIO()
    # High contrast + quiet border for phone cameras reading a laptop screen.
    qr.save(buf, kind="png", scale=12, border=4, dark="#000000", light="#ffffff")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return (
        '<img class="block h-auto w-full rounded-lg [image-rendering:pixelated]" '
        f'src="data:image/png;base64,{b64}" width="280" height="280" alt="QR code for {data}">'
    )


@router.get("/chat", response_class=HTMLResponse)
def chat_page(request: Request) -> HTMLResponse:
    nonce = secrets.token_urlsafe(16)
    if not enabled():
        return _page(DISABLED_HTML, nonce, status=503)
    return _page(CHAT_HTML if _authed(request) else LOGIN_HTML, nonce)


@router.get("/chat/qr", response_class=HTMLResponse)
def chat_qr_page(request: Request) -> HTMLResponse:
    """Laptop-only QR page — scan with iPhone Camera / Safari to open /chat."""
    nonce = secrets.token_urlsafe(16)
    if not enabled():
        return _page(DISABLED_HTML, nonce, status=503)
    if not _is_direct_local(request):
        return _page(QR_REMOTE_BLOCKED_HTML, nonce, status=403)
    chat_url, err = _tunnel_chat_url()
    if not chat_url:
        return _page(_render_qr_html(None, err), nonce)
    try:
        img = _qr_img_html(chat_url)
    except Exception as exc:  # noqa: BLE001
        return _page(_render_qr_html(chat_url, f"QR generation failed: {exc}"), nonce)
    return _page(_render_qr_html(chat_url, "", img), nonce)


@router.get("/chat/qr.json")
def chat_qr_json(request: Request) -> JSONResponse:
    """JSON helper for the QR page auto-refresh (local Host only)."""
    if not _is_direct_local(request):
        return _json({"error": "QR is only available on the laptop (127.0.0.1)."}, 403)
    chat_url, err = _tunnel_chat_url()
    if not chat_url:
        return _json({"ok": False, "error": err})
    try:
        img = _qr_img_html(chat_url)
    except Exception as exc:  # noqa: BLE001
        return _json({"ok": False, "error": str(exc), "url": chat_url})
    return _json({"ok": True, "url": chat_url, "img": img})


@router.post("/chat/login")
async def login(request: Request) -> JSONResponse:
    if not enabled():
        return _json({"error": "Web chat disabled"}, 503)
    ip = _client_ip(request)
    if _locked(ip):
        return _json({"error": "Too many attempts. Try again in 15 minutes."}, 429)
    data = await _read_json(request)
    if data is None:
        return _json({"error": "Bad request"}, 400)
    password = str(data.get("password", ""))
    # Hash first so compare_digest never raises on length mismatch.
    if not hmac.compare_digest(
        hashlib.sha256(password.encode()).digest(),
        hashlib.sha256(config.WEBCHAT_PASSWORD.encode()).digest(),
    ):
        _record_failure(ip)
        audit.record("webchat_login_failed", actor=ip, ok=False)
        return _json({"error": "Wrong password"}, 401)
    _clear_failures(ip)
    audit.record("webchat_login", actor=ip)
    if not messages_after(0):
        seed_welcome()
        from orchestrator import preflight

        agent_ok, agent_detail = preflight.agent_available()
        if not agent_ok:
            store("out", f"Heads up - the agent isn't ready yet: {agent_detail}", level="warning")
    remember = bool(data.get("remember", True))
    resp = _json({"ok": True})
    cookie_kw: dict[str, Any] = {
        "httponly": True,
        "samesite": "strict",
        "secure": _is_https(request),
        "path": "/chat",
    }
    if remember:
        cookie_kw["max_age"] = config.WEBCHAT_SESSION_DAYS * 86400
    resp.set_cookie(COOKIE, _make_session(), **cookie_kw)
    return resp


@router.post("/chat/logout")
def logout() -> JSONResponse:
    resp = _json({"ok": True})
    resp.delete_cookie(COOKIE, path="/chat")
    return resp


@router.post("/chat/clear")
def clear_chat(request: Request) -> JSONResponse:
    """Delete chat messages and tear down isolated workspaces for a fresh start."""
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    from orchestrator import history, retention, session
    from orchestrator.converse import clear_conversation_state

    project = _current_project()
    cleanup = retention.cleanup_sender_workspaces(
        SENDER, project=project or None, reason="chat cleared"
    )
    clear_messages(project=project)
    # Drop active task so the next message starts cleanly.
    session.set_active_task(SENDER, None, project=project or None)
    clear_conversation_state(SENDER)
    try:
        history.clear_sender(SENDER, project=project or None)
    except Exception:  # noqa: BLE001
        pass
    seed_welcome()
    audit.record(
        "webchat_cleared",
        actor=_client_ip(request),
        detail={"project": project, **cleanup},
    )
    return _json({"ok": True, "project": project, **cleanup})


@router.post("/chat/clear-activity")
def clear_activity(request: Request) -> JSONResponse:
    """Clear activity history for the active project without wiping chat messages."""
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    from orchestrator import retention, session

    project = _current_project()
    cleanup = retention.cleanup_sender_workspaces(
        SENDER, project=project or None, reason="activity cleared"
    )
    session.set_active_task(SENDER, None, project=project or None)
    audit.record(
        "webchat_activity_cleared",
        actor=_client_ip(request),
        detail={"project": project, **cleanup},
    )
    return _json({"ok": True, "project": project, **cleanup})


@router.post("/chat/send")
async def send(request: Request) -> JSONResponse:
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    data = await _read_json(request)
    if data is None:
        return _json({"error": "Bad request"}, 400)
    text = str(data.get("text", "")).strip()
    cid = str(data.get("cid", ""))[:64]
    attach_ids = chat_attachments.parse_ids(data.get("attachments"))
    metas = chat_attachments.resolve_owned(attach_ids, SENDER) if attach_ids else []
    if attach_ids and len(metas) != len(attach_ids):
        return _json({"error": "One or more attachments are missing or expired"}, 400)
    if not text and not metas:
        return _json({"error": "Empty message"}, 400)
    if not text and metas:
        text = IMAGE_ONLY_PLACEHOLDER
    if len(text) > MAX_TEXT:
        return _json({"error": f"Message too long (max {MAX_TEXT} chars)"}, 413)

    from orchestrator.handlers import handle
    from orchestrator.tasks import seen_message

    if cid and not seen_message(f"web:{cid}"):
        return _json({"ok": True, "duplicate": True})
    store("in", text, attachments=metas or None)
    if metas:
        chat_attachments.set_pending(SENDER, [m["id"] for m in metas])
    await run_in_threadpool(handle, SENDER, text)
    return _json({"ok": True, "attachments": len(metas)})


@router.post("/chat/attach")
async def attach(request: Request) -> JSONResponse:
    """Upload an image for the next chat message (Cursor-style attachment)."""
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    ctype = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" not in ctype:
        return _json({"error": "Expected multipart image upload"}, 400)
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001
        return _json({"error": "Bad upload"}, 400)
    upload = form.get("image") or form.get("file") or form.get("attachment")
    if upload is None:
        return _json({"error": "Missing image"}, 400)
    raw = await upload.read() if hasattr(upload, "read") else b""
    if not raw:
        return _json({"error": "Empty image"}, 400)
    if len(raw) > chat_attachments.MAX_IMAGE_BYTES:
        return _json({"error": "Image too large (max 8 MB)"}, 413)
    raw_ctype = str(getattr(upload, "content_type", "") or "")
    filename = Path(str(getattr(upload, "filename", None) or "image")).name or "image"
    try:
        meta = await run_in_threadpool(
            chat_attachments.save_upload,
            SENDER,
            raw,
            filename=filename,
            content_type=raw_ctype,
        )
    except ValueError as exc:
        return _json({"error": str(exc) or "Invalid image"}, 422)
    except Exception as exc:  # noqa: BLE001
        return _json({"error": f"Upload failed: {exc}"}, 500)
    audit.record(
        "webchat_attach",
        actor=_client_ip(request),
        detail={"id": meta["id"], "bytes": meta["size"], "type": meta["content_type"]},
    )
    return _json({"ok": True, **meta})


@router.get("/chat/attachments/{attach_id}")
def get_attachment_file(request: Request, attach_id: str) -> Response:
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    meta = chat_attachments.get_attachment(attach_id, sender=SENDER)
    if not meta:
        return _json({"error": "Not found"}, 404)
    path = Path(meta["path"])
    return FileResponse(
        path,
        media_type=str(meta.get("content_type") or "application/octet-stream"),
        filename=str(meta.get("filename") or "image"),
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/chat/voice")
async def voice(request: Request) -> JSONResponse:
    """Transcribe a short mic recording (iPhone MediaRecorder → Groq Whisper)."""
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    from orchestrator import llm_chat

    if not llm_chat.voice_enabled():
        return _json(
            {"error": "Voice needs GROQ_API_KEY with GROQ_VOICE_ENABLED=true on the server."},
            503,
        )
    ctype = (request.headers.get("content-type") or "").lower()
    if "multipart/form-data" not in ctype:
        return _json({"error": "Expected multipart audio upload"}, 400)
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001
        return _json({"error": "Bad upload"}, 400)
    upload = form.get("audio")
    if upload is None:
        return _json({"error": "Missing audio"}, 400)
    raw = await upload.read() if hasattr(upload, "read") else b""
    if not raw:
        return _json({"error": "Empty audio"}, 400)
    if len(raw) > MAX_VOICE_BYTES:
        return _json({"error": "Voice clip too large (max 8 MB)"}, 413)
    raw_ctype = str(getattr(upload, "content_type", "") or "")
    media_type = raw_ctype.split(";")[0].strip().lower() or "application/octet-stream"
    filename = Path(str(getattr(upload, "filename", None) or "voice")).name or "voice"
    if "." not in filename:
        filename += _VOICE_EXTS.get(media_type) or _VOICE_EXTS.get(raw_ctype.lower()) or ".webm"
    try:
        text = await run_in_threadpool(
            llm_chat.transcribe,
            raw,
            filename=filename,
            content_type=media_type,
        )
    except ValueError as exc:
        return _json({"error": str(exc) or "No speech detected"}, 422)
    except Exception as exc:  # noqa: BLE001
        return _json({"error": f"Transcription failed: {exc}"}, 502)
    text = (text or "").strip()
    if not text:
        return _json({"error": "No speech detected"}, 422)
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT]
    audit.record("webchat_voice", actor=_client_ip(request), detail={"chars": len(text)})
    return _json({"ok": True, "text": text})


@router.get("/chat/messages")
def messages(request: Request, after: int = 0, project: str = "") -> JSONResponse:
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    proj = (project or "").strip() or None
    return _json(
        {
            "messages": messages_after(after, project=proj),
            "project": proj,
            "active_project": _current_project(),
        }
    )


@router.post("/chat/focus-task")
async def focus_task(request: Request) -> JSONResponse:
    """Bind chat follow-ups (status/approve/cancel) to a selected Activity task."""
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    data = await _read_json(request)
    if data is None:
        return _json({"error": "Bad request"}, 400)
    task_id = str(data.get("task_id") or "").strip().lower()
    if not task_id:
        return _json({"error": "task_id required"}, 400)
    from orchestrator import session
    from orchestrator.tasks import get_task

    task = get_task(task_id)
    if not task or task.get("sender") != SENDER:
        return _json({"error": "Task not found"}, 404)
    session.set_active_task(
        SENDER, task["id"], project=str(task.get("project") or "") or None
    )
    return _json(
        {
            "ok": True,
            "task_id": task["id"],
            "project": task.get("project"),
            "status": task.get("status"),
        }
    )


@router.post("/chat/active-project")
async def set_active_project_api(request: Request) -> JSONResponse:
    """Switch the operator's active project and return a fresh project-scoped thread."""
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    data = await _read_json(request)
    if data is None:
        return _json({"error": "Bad request"}, 400)
    project = str(data.get("project") or "").strip() or None
    from orchestrator import session
    from orchestrator.projects import projects as load_projects

    registry = load_projects()
    if project and project not in registry:
        return _json({"error": f"Unknown project: {project}"}, 404)
    result = session.switch_project(SENDER, project)
    if result["changed"] and project:
        store(
            "out",
            f"Switched to {project}. This chat thread is only for {project} — "
            "earlier conversations on other projects stay in their own threads. "
            "Any agent work already running elsewhere keeps going in the background.",
            level="info",
            project=project,
        )
    elif result["changed"] and not project:
        store(
            "out",
            "Cleared the active project. Showing the combined chat history again.",
            level="info",
            project=None,
        )
    return _json(
        {
            "ok": True,
            "changed": result["changed"],
            "previous": result["previous"],
            "active_project": result["project"],
            "messages": messages_after(0, project=project),
        }
    )


@router.get("/chat/projects")
def list_projects_api(request: Request) -> JSONResponse:
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    from orchestrator.projects import projects as load_projects
    from orchestrator.projects import projects_root_info, serialize_project

    registry = load_projects()
    return _json(
        {
            "ok": True,
            "projects_root": projects_root_info(),
            "projects": [
                serialize_project(name, meta)
                for name, meta in sorted(registry.items(), key=lambda kv: kv[0].lower())
            ],
        }
    )


@router.get("/chat/projects/browse")
def browse_folders_api(request: Request) -> JSONResponse:
    """Folder picker listing for the Manage → Choose folder UI."""
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    from orchestrator.projects import ProjectConfigError, browse_directories

    path = (request.query_params.get("path") or "").strip()
    try:
        listing = browse_directories(path or None)
    except ProjectConfigError as exc:
        return _json({"error": str(exc)}, 400)
    return _json({"ok": True, **listing})


@router.get("/chat/projects/root")
def get_projects_root_api(request: Request) -> JSONResponse:
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    from orchestrator.projects import projects_root_info

    return _json({"ok": True, "projects_root": projects_root_info()})


@router.put("/chat/projects/root")
async def set_projects_root_api(request: Request) -> JSONResponse:
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    data = await _read_json(request)
    if data is None:
        return _json({"error": "Bad request"}, 400)
    path = str(data.get("path") or "").strip()
    if not path:
        return _json({"error": "path is required"}, 400)
    from orchestrator.projects import ProjectConfigError, set_projects_root

    try:
        info = set_projects_root(path, persist=True)
    except ProjectConfigError as exc:
        return _json({"error": str(exc)}, 400)
    audit.record("projects_root_set", actor=SENDER, detail={"path": info.get("path")})
    return _json({"ok": True, "projects_root": info})


@router.delete("/chat/projects/root")
def clear_projects_root_api(request: Request) -> JSONResponse:
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    from orchestrator.projects import ProjectConfigError, clear_projects_root_override

    try:
        info = clear_projects_root_override()
    except ProjectConfigError as exc:
        return _json({"error": str(exc)}, 400)
    audit.record("projects_root_cleared", actor=SENDER, detail={"path": info.get("path")})
    return _json({"ok": True, "projects_root": info})


@router.get("/chat/projects/candidates")
def list_project_candidates_api(request: Request) -> JSONResponse:
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    from orchestrator.projects import ProjectConfigError, discover_candidates, projects_root_info

    root_q = (request.query_params.get("root") or "").strip()
    try:
        candidates = discover_candidates(root=root_q or None)
    except ProjectConfigError as exc:
        return _json({"error": str(exc)}, 400)
    return _json(
        {
            "ok": True,
            "projects_root": projects_root_info(),
            "candidates": candidates,
        }
    )


@router.post("/chat/projects")
async def register_project_api(request: Request) -> JSONResponse:
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    data = await _read_json(request)
    if data is None:
        return _json({"error": "Bad request"}, 400)
    path = str(data.get("path") or "").strip()
    if not path:
        return _json({"error": "path is required"}, 400)
    project_id = str(data.get("id") or data.get("project") or "").strip()
    if not project_id:
        project_id = Path(path).name
    from orchestrator.projects import ProjectConfigError, register_project

    try:
        created = register_project(project_id, path)
    except ProjectConfigError as exc:
        return _json({"error": str(exc)}, 400)
    audit.record(
        "project_registered",
        actor=SENDER,
        detail={"project": created["id"], "path": created.get("path")},
    )
    return _json({"ok": True, "project": created})


@router.patch("/chat/projects/{project_id}")
async def update_project_api(request: Request, project_id: str) -> JSONResponse:
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    data = await _read_json(request)
    if data is None or not isinstance(data, dict):
        return _json({"error": "Bad request"}, 400)
    from orchestrator.projects import UPDATABLE_FIELDS, ProjectConfigError, update_project

    fields = {k: data[k] for k in data if k in UPDATABLE_FIELDS}
    if not fields:
        return _json({"error": "No updatable fields provided"}, 400)
    try:
        updated = update_project(project_id, **fields)
    except ProjectConfigError as exc:
        return _json({"error": str(exc)}, 400)
    audit.record(
        "project_updated",
        actor=SENDER,
        detail={"project": project_id, "fields": sorted(fields)},
    )
    return _json({"ok": True, "project": updated})


@router.delete("/chat/projects/{project_id}")
def delete_project_api(request: Request, project_id: str) -> JSONResponse:
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    from orchestrator import session
    from orchestrator.projects import ProjectConfigError, remove_project

    try:
        removed = remove_project(project_id)
    except ProjectConfigError as exc:
        return _json({"error": str(exc)}, 404 if "Unknown project" in str(exc) else 400)
    ctx = session.get(SENDER)
    if (ctx.get("active_project") or "") == project_id:
        session.switch_project(SENDER, None)
    audit.record("project_removed", actor=SENDER, detail={"project": project_id})
    return _json({"ok": True, "project": removed})


_CHAT_CSS = Path(__file__).resolve().parent / "static" / "app.css"


@router.get("/chat/app.css")
def chat_css() -> Response:
    if not _CHAT_CSS.is_file():
        return Response(status_code=404)
    return Response(
        _CHAT_CSS.read_bytes(),
        media_type="text/css; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/chat/sw.js")
def service_worker() -> Response:
    """Service worker for PWA shell + browser notifications (scope /chat/)."""
    return Response(
        SERVICE_WORKER_JS,
        media_type="application/javascript; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Service-Worker-Allowed": "/chat/",
        },
    )


@router.get("/chat/manifest.webmanifest")
def web_manifest() -> Response:
    """Home-screen / PWA manifest for iPhone & Android."""
    data = {
        "name": "Cursor Orchestrator",
        "short_name": "Orchestrator",
        "description": "Private control chat for your laptop coding agent.",
        "start_url": "/chat",
        "scope": "/chat",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#eef3f0",
        "theme_color": "#0b6e4f",
        "lang": "en",
        "icons": [
            {
                "src": "/chat/icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
            {
                "src": "/chat/apple-touch-icon.png",
                "sizes": "180x180",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "/chat/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    }
    return Response(
        json.dumps(data),
        media_type="application/manifest+json; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/chat/icon.svg")
def icon_svg() -> Response:
    return Response(
        ICON_SVG,
        media_type="image/svg+xml; charset=utf-8",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/chat/apple-touch-icon.png")
def apple_touch_icon() -> Response:
    return Response(
        _png_icon(180),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/chat/icon-512.png")
def icon_512() -> Response:
    return Response(
        _png_icon(512),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


def _png_icon(size: int) -> bytes:
    """Generate a simple brand PNG (no external image deps)."""
    r, g, b = 0x0B, 0x6E, 0x4F
    wr, wg, wb = 0xFF, 0xFF, 0xFF
    cx = cy = size / 2
    mark_r = size * 0.16
    rows = []
    for y in range(size):
        row = bytearray([0])  # filter none
        for x in range(size):
            # rounded-square feel via distance to edge
            edge = min(x, y, size - 1 - x, size - 1 - y)
            if edge < size * 0.06:
                row.extend((0xEE, 0xF3, 0xF0))
                continue
            dx, dy = x - cx, y - cy
            if dx * dx + dy * dy <= mark_r * mark_r:
                row.extend((wr, wg, wb))
            elif abs(dy) < size * 0.03 and abs(dx) < size * 0.28:
                row.extend((wr, wg, wb))
            else:
                row.extend((r, g, b))
        rows.append(bytes(row))
    raw = b"".join(rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


@router.get("/chat/status")
def status(request: Request) -> JSONResponse:
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    from orchestrator import agent as agent_mod
    from orchestrator import llm_chat, preflight, queue, session
    from orchestrator.projects import projects as load_projects
    from orchestrator.projects import projects_root_info
    from orchestrator.tasks import (
        active_task_for_sender,
        get_task,
        inflight_projects_for_sender,
        inflight_tasks_for_sender,
        list_tasks_for_sender,
    )

    agent_ok, agent_detail = preflight.agent_available()
    auth = agent_mod.auth_status()
    recent = list_tasks_for_sender(SENDER, limit=20)
    ctx = session.get(SENDER)
    active_project = ctx.get("active_project") or None
    active = None
    if ctx.get("active_task_id"):
        candidate = get_task(str(ctx["active_task_id"]))
        if candidate and (
            not active_project or candidate.get("project") == active_project
        ):
            active = candidate
    if not active:
        active = active_task_for_sender(SENDER, project=active_project)
    project_inflight = inflight_tasks_for_sender(SENDER, project=active_project)
    return _json(
        {
            "ok": True,
            "dry_run": config.DRY_RUN,
            "agent_ok": agent_ok,
            "agent_detail": agent_detail if agent_ok else agent_detail,
            "groq_chat": llm_chat.enabled(),
            "voice": llm_chat.voice_enabled(),
            "agent_auth": {
                "ok": bool(auth.get("ok")),
                "email": auth.get("email"),
                "mode": auth.get("mode"),
            },
            "projects": len(load_projects()),
            "projects_root": projects_root_info(),
            "project_list": [
                {
                    "id": name,
                    "name": str(meta.get("display_name") or name),
                    "type": str(meta.get("type") or "local"),
                    "path": str(meta.get("path") or ""),
                    "allow_push": bool(meta.get("allow_push", False)),
                    "allow_deploy": bool(meta.get("allow_deploy", False)),
                    "apply_local": bool(meta.get("apply_local", False)),
                }
                for name, meta in sorted(load_projects().items(), key=lambda kv: kv[0].lower())
            ],
            "pending_jobs": queue.pending_count(),
            "worker_count": int(getattr(config, "WORKER_COUNT", 1) or 1),
            "active_project": active_project,
            "inflight_projects": inflight_projects_for_sender(SENDER),
            "inflight_count": len(project_inflight),
            "active_task": (
                {
                    "id": active["id"],
                    "project": active["project"],
                    "status": active["status"],
                    "execution_stage": active.get("execution_stage"),
                }
                if active
                else None
            ),
            "recent_tasks": [
                {
                    "id": t["id"],
                    "project": t["project"],
                    "status": t["status"],
                    "execution_stage": t.get("execution_stage"),
                    "summary": (t.get("summary") or "")[:240],
                    "blocker": (t.get("blocker") or "")[:160],
                }
                for t in recent
                if (t.get("execution_stage") or "") != "canceled"
            ],
        }
    )


@router.get("/chat/task-progress")
def task_progress(request: Request, task_id: str = "", after: int = 0) -> JSONResponse:
    """Evidence-backed task progress for the chat progress panel."""
    if not _authed(request):
        return _json({"error": "Unauthorized"}, 401)
    from orchestrator import progress, session, task_events
    from orchestrator.tasks import active_task_for_sender, get_task

    tid = (task_id or "").strip().lower()
    task = get_task(tid) if tid else None
    if not task:
        ctx = session.get(SENDER)
        active_project = ctx.get("active_project") or None
        if ctx.get("active_task_id"):
            candidate = get_task(str(ctx["active_task_id"]))
            if candidate and (
                not active_project or candidate.get("project") == active_project
            ):
                task = candidate
        if not task:
            task = active_task_for_sender(SENDER, project=active_project)
    if not task or task.get("sender") != SENDER:
        return _json({"ok": True, "task": None, "events": []})
    snap = progress.snapshot(task)
    events = task_events.list_events(task["id"], after_id=after, limit=200)
    return _json({"ok": True, "task": snap, "events": events})


ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img">
  <rect width="512" height="512" rx="112" fill="#0b6e4f"/>
  <g fill="none" stroke="#fff" stroke-width="28" stroke-linecap="round" stroke-linejoin="round">
    <path d="M118 168c0-42 38-74 84-74h108c46 0 84 32 84 74v84c0 42-38 74-84 74h-46l-68 64v-64h-78c-46 0-84-32-84-74z"/>
  </g>
  <circle cx="208" cy="214" r="18" fill="#fff"/>
  <circle cx="280" cy="214" r="18" fill="#fff"/>
  <circle cx="352" cy="214" r="18" fill="#fff"/>
</svg>
"""

QR_REMOTE_BLOCKED_HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>QR</title>
{FAVICON_LINKS}
{FONT_LINKS}
{STYLESHEET}
</head>
<body class="app-bg grid min-h-dvh place-items-center px-6 text-center font-sans text-ink antialiased"><div class="w-full max-w-[440px] rounded-3xl border border-line bg-card p-7 shadow-card">
  <h1 class="mb-2.5 font-display text-2xl">Open this on your laptop</h1>
  <p class="mx-auto max-w-[36ch] leading-normal text-muted">The QR page is only available at <code class="text-accent">http://127.0.0.1:8000/chat/qr</code> so your tunnel URL stays private.</p>
  <p class="mt-4"><a class="font-semibold text-accent no-underline" href="/chat">Back to chat</a></p>
</div></body></html>"""

DISABLED_HTML = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>Orchestrator</title>
{FAVICON_LINKS}
{FONT_LINKS}
{STYLESHEET}
</head>
<body class="app-bg grid min-h-dvh place-items-center px-6 font-sans text-ink antialiased"><main class="w-full max-w-[440px] rounded-3xl border border-line bg-card p-7 text-center shadow-card">
<h2 class="mb-3 font-display text-2xl font-bold">Web chat is disabled</h2>
<p class="leading-normal text-muted">Set <code class="text-accent">WEBCHAT_PASSWORD</code> (at least {MIN_PASSWORD_LEN} characters) in <code class="text-accent">.env</code> and restart the orchestrator.</p>
</main></body></html>"""


SERVICE_WORKER_JS = """
const CACHE = 'orch-chat-shell-v3';
const ASSETS = [
  '/chat/manifest.webmanifest',
  '/chat/icon.svg',
  '/chat/apple-touch-icon.png',
  '/chat/icon-512.png',
];
// CSS changes with UI — always prefer network so Manage drawer styles ship.
const NETWORK_FIRST = ['/chat/app.css'];
self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (NETWORK_FIRST.includes(url.pathname)) {
    event.respondWith(
      fetch(event.request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(event.request, copy));
          return res;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }
  if (!ASSETS.includes(url.pathname)) return;
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
self.addEventListener('message', (event) => {
  const data = event.data || {};
  if (data.type !== 'notify') return;
  const title = data.title || 'Orchestrator';
  const opts = {
    body: data.body || '',
    tag: data.tag || 'orch',
    renotify: !!data.renotify,
    data: data.data || {url: '/chat'},
  };
  event.waitUntil(self.registration.showNotification(title, opts));
});
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/chat';
  event.waitUntil(clients.matchAll({type: 'window', includeUncontrolled: true}).then((list) => {
    for (const c of list) {
      if (c.url.includes('/chat') && 'focus' in c) return c.focus();
    }
    if (clients.openWindow) return clients.openWindow(url);
  }));
});
"""
