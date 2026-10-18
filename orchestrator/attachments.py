"""Image attachments for web chat → Cursor agent context.

Uploads land under WORK_ROOT/_attachments (staging). When a task runs, files are
copied into the isolated workspace as `.orchestrator-attachments/<name>` and
those relative paths are injected into the agent prompt (Cursor CLI image paths).
"""
from __future__ import annotations

import json
import re
import secrets
import shutil
import threading
from pathlib import Path
from typing import Any

from orchestrator import config, db

ATTACH_DIR_NAME = ".orchestrator-attachments"
STAGING_DIR_NAME = "_attachments"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_ATTACHMENTS_PER_MESSAGE = 5
ALLOWED_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
    (b"RIFF", "image/webp", ".webp"),  # need WEBP at offset 8
)

_pending: dict[str, list[str]] = {}
_pending_lock = threading.Lock()


def staging_root() -> Path:
    root = config.WORK_ROOT / STAGING_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS chat_attachments (
            id TEXT PRIMARY KEY,
            sender TEXT NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL,
            size INTEGER NOT NULL,
            path TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_attachments_sender "
        "ON chat_attachments(sender, created_at)"
    )


def _detect_image(raw: bytes, content_type: str, filename: str) -> tuple[str, str]:
    """Return (content_type, extension) or raise ValueError."""
    if not raw or len(raw) < 12:
        raise ValueError("File is empty or too small to be an image")
    detected_ct = ""
    detected_ext = ""
    for magic, ct, ext in _MAGIC:
        if raw.startswith(magic):
            if magic == b"RIFF":
                if raw[8:12] != b"WEBP":
                    continue
            detected_ct, detected_ext = ct, ext
            break
    if not detected_ct:
        raise ValueError("Only PNG, JPEG, WebP, and GIF images are allowed")

    declared = (content_type or "").split(";")[0].strip().lower()
    if declared and declared not in ALLOWED_CONTENT_TYPES and declared != "application/octet-stream":
        raise ValueError(f"Unsupported image type: {declared}")
    # Prefer sniffed type over client-declared.
    return detected_ct, detected_ext


def _safe_filename(name: str, ext: str) -> str:
    base = Path(name or "image").name
    base = re.sub(r"[^\w.\-]+", "_", base, flags=re.A).strip("._") or "image"
    if len(base) > 80:
        base = base[:80]
    stem = Path(base).stem or "image"
    return f"{stem}{ext}"


def save_upload(
    sender: str,
    raw: bytes,
    *,
    filename: str = "image",
    content_type: str = "",
) -> dict[str, Any]:
    """Validate and stage an image. Returns public metadata (no absolute path)."""
    if not sender:
        raise ValueError("Missing sender")
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image too large (max {MAX_IMAGE_BYTES // (1024 * 1024)} MB)")
    ct, ext = _detect_image(raw, content_type, filename)
    attach_id = secrets.token_hex(12)
    safe_name = _safe_filename(filename, ext)
    dest_dir = staging_root() / attach_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_name
    dest.write_bytes(raw)
    now = db.now()
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        c.execute(
            """INSERT INTO chat_attachments
               (id, sender, filename, content_type, size, path, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (attach_id, sender, safe_name, ct, len(raw), str(dest.resolve()), now),
        )
    return {
        "id": attach_id,
        "filename": safe_name,
        "content_type": ct,
        "size": len(raw),
        "url": f"/chat/attachments/{attach_id}",
    }


def get_attachment(attach_id: str, *, sender: str | None = None) -> dict[str, Any] | None:
    aid = (attach_id or "").strip()
    if not aid or not re.fullmatch(r"[0-9a-f]{24}", aid):
        return None
    with db.DB_LOCK, db.connect() as c:
        ensure_schema(c)
        row = c.execute(
            "SELECT id, sender, filename, content_type, size, path, created_at "
            "FROM chat_attachments WHERE id=?",
            (aid,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    if sender is not None and item.get("sender") != sender:
        return None
    path = Path(str(item["path"]))
    if not _path_under_staging(path) or not path.is_file():
        return None
    item["path"] = str(path.resolve())
    return item


def _path_under_staging(path: Path) -> bool:
    try:
        path.resolve().relative_to(staging_root().resolve())
        return True
    except ValueError:
        return False


def resolve_owned(ids: list[str], sender: str) -> list[dict[str, Any]]:
    """Resolve attachment ids owned by sender; drop unknown/foreign ids."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_id in ids:
        aid = str(raw_id or "").strip()
        if not aid or aid in seen:
            continue
        seen.add(aid)
        meta = get_attachment(aid, sender=sender)
        if meta:
            out.append(meta)
        if len(out) >= MAX_ATTACHMENTS_PER_MESSAGE:
            break
    return out


def set_pending(sender: str, ids: list[str]) -> None:
    cleaned = [str(i).strip() for i in ids if str(i).strip()][:MAX_ATTACHMENTS_PER_MESSAGE]
    with _pending_lock:
        if cleaned:
            _pending[sender] = cleaned
        else:
            _pending.pop(sender, None)


def take_pending(sender: str) -> list[str]:
    with _pending_lock:
        return list(_pending.pop(sender, []))


def clear_pending(sender: str) -> None:
    with _pending_lock:
        _pending.pop(sender, None)


def parse_ids(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            aid = str(item.get("id") or "").strip()
        else:
            aid = str(item or "").strip()
        if aid and aid not in out:
            out.append(aid)
        if len(out) >= MAX_ATTACHMENTS_PER_MESSAGE:
            break
    return out


def serialize_for_message(metas: list[dict[str, Any]]) -> str:
    payload = [
        {
            "id": m["id"],
            "filename": m.get("filename") or "image",
            "content_type": m.get("content_type") or "image/png",
            "size": int(m.get("size") or 0),
            "url": m.get("url") or f"/chat/attachments/{m['id']}",
        }
        for m in metas
    ]
    return json.dumps(payload, ensure_ascii=False)


def deserialize_message_attachments(raw: Any) -> list[dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, list):
        data = raw
    else:
        try:
            data = json.loads(str(raw))
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        aid = str(item.get("id") or "").strip()
        if not aid:
            continue
        out.append(
            {
                "id": aid,
                "filename": str(item.get("filename") or "image"),
                "content_type": str(item.get("content_type") or "image/png"),
                "size": int(item.get("size") or 0),
                "url": str(item.get("url") or f"/chat/attachments/{aid}"),
            }
        )
    return out


def materialize_into_workspace(workspace: Path, attach_ids: list[str] | str | None) -> list[str]:
    """Copy staged attachments into workspace. Returns workspace-relative POSIX paths.

    Rejects any staged path that escapes the staging root (path-traversal fixture).
    """
    ids = parse_ids(attach_ids) if not isinstance(attach_ids, list) else [
        str(x).strip() for x in attach_ids if str(x).strip()
    ]
    if not ids:
        return []
    workspace = Path(workspace).resolve()
    if not workspace.is_dir():
        raise ValueError(f"Workspace does not exist: {workspace}")
    dest_root = workspace / ATTACH_DIR_NAME
    dest_root.mkdir(parents=True, exist_ok=True)
    rel_paths: list[str] = []
    used_names: set[str] = set()
    for aid in ids[:MAX_ATTACHMENTS_PER_MESSAGE]:
        meta = get_attachment(aid)
        if not meta:
            continue
        src = Path(meta["path"]).resolve()
        if not _path_under_staging(src) or not src.is_file():
            continue
        name = _safe_filename(str(meta.get("filename") or "image"), src.suffix or ".png")
        if name in used_names:
            stem, ext = Path(name).stem, Path(name).suffix
            name = f"{stem}_{aid[:6]}{ext}"
        used_names.add(name)
        dest = dest_root / name
        shutil.copy2(src, dest)
        rel = f"{ATTACH_DIR_NAME}/{name}"
        # Defense: ensure final file is inside workspace.
        try:
            dest.resolve().relative_to(workspace)
        except ValueError as exc:
            dest.unlink(missing_ok=True)
            raise ValueError("Attachment path escaped workspace") from exc
        rel_paths.append(rel)
    _exclude_from_git(workspace)
    return rel_paths


def _exclude_from_git(workspace: Path) -> None:
    exclude = workspace / ".git" / "info" / "exclude"
    try:
        if not (workspace / ".git").exists():
            return
        exclude.parent.mkdir(parents=True, exist_ok=True)
        existing = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
        lines = existing.splitlines()
        if ATTACH_DIR_NAME not in lines and f"{ATTACH_DIR_NAME}/" not in lines:
            with exclude.open("a", encoding="utf-8") as fh:
                fh.write(f"\n{ATTACH_DIR_NAME}/\n")
    except OSError:
        pass


def prompt_section(rel_paths: list[str]) -> str:
    if not rel_paths:
        return ""
    lines = [
        "ATTACHED IMAGES (user screenshots / reference images in this workspace — "
        "open and inspect these files like Cursor chat image attachments):",
    ]
    for rel in rel_paths:
        lines.append(f"- {rel}")
    return "\n".join(lines)
