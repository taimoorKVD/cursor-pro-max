"""Project registry load, discovery, validation, and persistence."""
from __future__ import annotations

import json
import os
import re
import string
import tempfile
from pathlib import Path
from typing import Any

from orchestrator import config

REQUIRED_KEYS = ("path", "type")
ALLOWED_TYPES = frozenset({"git", "local"})
UPDATABLE_FIELDS = frozenset(
    {
        "path",
        "type",
        "test_command",
        "allow_push",
        "allow_deploy",
        "apply_local",
        "deploy_command",
        "display_name",
        "description",
        "instructions",
        "default_branch",
    }
)
_SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".idea",
        ".vscode",
        "vendor",
        "dist",
        "build",
        "tmp",
        "temp",
    }
)


class ProjectConfigError(ValueError):
    pass


def slugify_project_id(name: str) -> str:
    """Normalize a folder/display name into a valid project id."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(name).strip()).strip("-_").lower()
    slug = re.sub(r"[-_]{2,}", "-", slug)
    if not slug or not slug.replace("_", "").replace("-", "").isalnum():
        raise ProjectConfigError(f"Invalid project id from name {name!r}")
    return slug


def _is_valid_project_id(name: str) -> bool:
    return bool(name) and bool(str(name).replace("_", "").replace("-", "").isalnum())


def _validate_one(name: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProjectConfigError(f"Project {name!r} must be an object")
    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise ProjectConfigError(f"Project {name!r} missing keys: {', '.join(missing)}")
    typ = raw.get("type")
    if typ not in ALLOWED_TYPES:
        raise ProjectConfigError(f"Project {name!r} type must be git or local, got {typ!r}")
    path = Path(str(raw["path"])).expanduser()
    # Existence checked at task time (paths may be offline during startup).
    allow_push = bool(raw.get("allow_push", False))
    allow_deploy = bool(raw.get("allow_deploy", False))
    # Default ON for git: approve updates the Laragon/local checkout the user actually opens.
    if "apply_local" in raw:
        apply_local = bool(raw.get("apply_local"))
    else:
        apply_local = typ == "git"
    if typ == "local" and allow_push:
        raise ProjectConfigError(f"Project {name!r}: local projects cannot allow_push")
    if typ == "local" and apply_local:
        raise ProjectConfigError(f"Project {name!r}: local snapshot projects cannot apply_local")
    deploy_command = str(raw.get("deploy_command") or "")
    if allow_deploy and not deploy_command.strip():
        raise ProjectConfigError(f"Project {name!r}: allow_deploy requires deploy_command")
    return {
        "path": str(path),
        "type": typ,
        "test_command": str(raw.get("test_command") or ""),
        "allow_push": allow_push,
        "allow_deploy": allow_deploy,
        "apply_local": apply_local,
        "deploy_command": deploy_command,
        "display_name": str(raw.get("display_name") or name),
        "description": str(raw.get("description") or ""),
        "instructions": str(raw.get("instructions") or ""),
        "default_branch": str(raw.get("default_branch") or "main"),
    }


def load_projects(path: Path | None = None, *, strict: bool = False) -> dict[str, dict[str, Any]]:
    target = path or config.PROJECTS_FILE
    if not target.exists():
        if strict:
            raise ProjectConfigError(f"Projects file not found: {target}")
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectConfigError(f"Invalid JSON in {target}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProjectConfigError("projects.json root must be an object")
    validated: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for name, raw in data.items():
        if not isinstance(name, str) or not _is_valid_project_id(name):
            errors.append(f"Invalid project id {name!r}")
            continue
        try:
            validated[name] = _validate_one(name, raw)
        except ProjectConfigError as exc:
            errors.append(str(exc))
    if errors and strict:
        raise ProjectConfigError("; ".join(errors))
    if errors and not validated:
        raise ProjectConfigError("; ".join(errors))
    return validated


def projects() -> dict[str, dict[str, Any]]:
    """Runtime loader: validate when file exists; empty dict if absent."""
    if not config.PROJECTS_FILE.exists():
        return {}
    return load_projects(strict=bool(getattr(config, "PROJECTS_STRICT", True)))


def _projects_root_file() -> Path:
    return Path(getattr(config, "PROJECTS_ROOT_FILE", config.BASE / "data" / "projects_root.json"))


def _env_projects_root() -> Path | None:
    root = getattr(config, "PROJECTS_ROOT", None)
    if root is None:
        return None
    text = str(root).strip()
    if not text:
        return None
    return Path(text).expanduser()


def _read_root_override() -> Path | None:
    target = _projects_root_file()
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    text = str(data.get("path") or "").strip()
    if not text:
        return None
    return Path(text).expanduser()


def projects_root() -> Path | None:
    """Effective scan root: runtime override, then PROJECTS_ROOT env, else None."""
    override = _read_root_override()
    if override is not None:
        return override
    return _env_projects_root()


def projects_root_info() -> dict[str, Any]:
    """Describe the effective scan root and where it came from."""
    override = _read_root_override()
    env_root = _env_projects_root()
    if override is not None:
        path = override
        source = "override"
    elif env_root is not None:
        path = env_root
        source = "env"
    else:
        return {"path": None, "source": "none", "exists": False}
    exists = False
    resolved: str | None = None
    try:
        resolved_path = path.expanduser().resolve(strict=True)
        exists = resolved_path.is_dir()
        resolved = str(resolved_path)
    except OSError:
        resolved = str(path.expanduser())
    return {
        "path": str(path.expanduser()),
        "resolved": resolved,
        "source": source,
        "exists": exists,
        "env_default": str(env_root) if env_root is not None else None,
    }


def set_projects_root(path: str | Path, *, persist: bool = True) -> dict[str, Any]:
    """Validate and optionally persist the directory used for folder scans."""
    candidate = Path(str(path).strip().strip("\"'")).expanduser()
    if not str(candidate):
        raise ProjectConfigError("Scan directory path is required")
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ProjectConfigError(f"Scan directory does not exist: {candidate}") from exc
    if not resolved.is_dir():
        raise ProjectConfigError(f"Scan directory is not a directory: {candidate}")

    if persist:
        target = _projects_root_file()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"path": str(resolved)}, indent=2, ensure_ascii=False) + "\n"
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=str(target.parent),
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, target)
        except Exception:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise
    return projects_root_info()


def clear_projects_root_override() -> dict[str, Any]:
    """Remove the runtime override so PROJECTS_ROOT from .env is used again."""
    target = _projects_root_file()
    try:
        target.unlink(missing_ok=True)
    except OSError as exc:
        raise ProjectConfigError(f"Could not clear projects root override: {exc}") from exc
    return projects_root_info()


def list_windows_drives() -> list[dict[str, Any]]:
    """Return available drive roots on Windows (empty on other platforms)."""
    if os.name != "nt":
        return []
    drives: list[dict[str, Any]] = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:/")
        try:
            if root.exists():
                drives.append(
                    {
                        "name": f"{letter}:",
                        "path": str(root.resolve()),
                        "type": "drive",
                    }
                )
        except OSError:
            continue
    return drives


def browse_directories(path: str | Path | None = None) -> dict[str, Any]:
    """List folders for a simple Choose-folder UI (no file contents)."""
    raw = str(path or "").strip().strip("\"'")
    if not raw:
        if os.name == "nt":
            drives = list_windows_drives()
            return {
                "path": None,
                "parent": None,
                "entries": drives,
                "at_root": True,
            }
        home = Path.home()
        return browse_directories(home)

    try:
        current = Path(raw).expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise ProjectConfigError(f"Folder does not exist: {raw}") from exc
    if not current.is_dir():
        raise ProjectConfigError(f"Not a folder: {raw}")

    parent: str | None = None
    try:
        parent_path = current.parent
        if parent_path != current:
            parent = str(parent_path)
        elif os.name == "nt":
            # At drive root (e.g. C:\) — parent navigation returns to drive list.
            parent = ""
    except OSError:
        parent = None

    entries: list[dict[str, Any]] = []
    try:
        children = sorted(current.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        raise ProjectConfigError(f"Cannot read folder: {current} ({exc})") from exc

    for child in children:
        name = child.name
        if name.startswith(".") or name in _SKIP_DIR_NAMES:
            continue
        try:
            if not child.is_dir():
                continue
            # Skip junctions/symlink loops lightly; still allow real dirs.
            resolved = child.resolve(strict=False)
            entries.append(
                {
                    "name": name,
                    "path": str(resolved),
                    "type": "dir",
                }
            )
        except OSError:
            continue

    return {
        "path": str(current),
        "parent": parent,
        "entries": entries,
        "at_root": False,
    }


def _resolve_under_root(path: Path | str, root: Path | None = None) -> Path:
    """Resolve path and require it to live under PROJECTS_ROOT."""
    scan_root = root or projects_root()
    if scan_root is None:
        raise ProjectConfigError(
            "No scan directory is set. Use Manage → set folder path, or say "
            '"set projects root C:/laragon/www".'
        )
    try:
        root_resolved = scan_root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ProjectConfigError(f"PROJECTS_ROOT does not exist: {scan_root}") from exc
    if not root_resolved.is_dir():
        raise ProjectConfigError(f"PROJECTS_ROOT is not a directory: {scan_root}")

    candidate = Path(path).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ProjectConfigError(f"Project path does not exist: {candidate}") from exc
    if not resolved.is_dir():
        raise ProjectConfigError(f"Project path is not a directory: {candidate}")
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ProjectConfigError(
            f"Project path must be under PROJECTS_ROOT ({root_resolved}): got {resolved}"
        ) from exc
    return resolved


def _detect_type(folder: Path) -> str:
    return "git" if (folder / ".git").exists() else "local"


def _registry_paths(registry: dict[str, dict[str, Any]]) -> set[str]:
    paths: set[str] = set()
    for meta in registry.values():
        try:
            paths.add(str(Path(str(meta["path"])).expanduser().resolve()))
        except OSError:
            paths.add(str(Path(str(meta["path"])).expanduser()))
    return paths


def discover_candidates(root: Path | str | None = None) -> list[dict[str, Any]]:
    """List immediate child folders under the effective scan root as register candidates."""
    if root is None or (isinstance(root, str) and not root.strip()):
        scan_root = projects_root()
    else:
        scan_root = Path(root).expanduser()
    if scan_root is None:
        raise ProjectConfigError(
            "No scan directory is set. Use Manage → set folder path, or say "
            '"set projects root C:/laragon/www".'
        )
    try:
        root_resolved = scan_root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ProjectConfigError(f"PROJECTS_ROOT does not exist: {scan_root}") from exc
    if not root_resolved.is_dir():
        raise ProjectConfigError(f"PROJECTS_ROOT is not a directory: {scan_root}")

    registry = load_projects(strict=False)
    registered_paths = _registry_paths(registry)
    registered_ids = {name.lower() for name in registry}

    candidates: list[dict[str, Any]] = []
    for child in sorted(root_resolved.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        name = child.name
        if name.startswith(".") or name in _SKIP_DIR_NAMES:
            continue
        try:
            resolved = child.resolve(strict=True)
        except OSError:
            continue
        try:
            suggested_id = slugify_project_id(name)
        except ProjectConfigError:
            continue
        path_str = str(resolved)
        registered = path_str in registered_paths or suggested_id.lower() in registered_ids
        registered_as = None
        if registered:
            for pid, meta in registry.items():
                try:
                    if str(Path(str(meta["path"])).expanduser().resolve()) == path_str:
                        registered_as = pid
                        break
                except OSError:
                    continue
            if registered_as is None and suggested_id.lower() in registered_ids:
                registered_as = next(n for n in registry if n.lower() == suggested_id.lower())
        candidates.append(
            {
                "id": suggested_id,
                "name": name,
                "path": path_str,
                "type": _detect_type(resolved),
                "registered": registered,
                "registered_as": registered_as,
            }
        )
    return candidates


def save_projects(
    registry: dict[str, dict[str, Any]],
    path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Validate and atomically write the project registry."""
    target = path or config.PROJECTS_FILE
    validated: dict[str, dict[str, Any]] = {}
    for name, raw in registry.items():
        if not isinstance(name, str) or not _is_valid_project_id(name):
            raise ProjectConfigError(f"Invalid project id {name!r}")
        validated[name] = _validate_one(name, raw)

    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(validated, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return validated


def create_project(
    name: str,
    *,
    projects_file: Path | None = None,
    root: Path | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Create a new folder under PROJECTS_ROOT and register it.

    Used for build-from-scratch: pick scan root → choose folder name → mkdir + register.
    """
    display = str(name or "").strip()
    if not display:
        raise ProjectConfigError("Project name is required")
    try:
        pid = slugify_project_id(display) if not _is_valid_project_id(display) else display
    except ProjectConfigError as exc:
        raise ProjectConfigError(f"Invalid project name {name!r}") from exc
    if not _is_valid_project_id(pid):
        raise ProjectConfigError(f"Invalid project name {name!r}")
    if pid.lower() in {s.lower() for s in _SKIP_DIR_NAMES} or pid.startswith("."):
        raise ProjectConfigError(f"Reserved or invalid folder name: {pid}")

    scan_root = root or projects_root()
    if scan_root is None:
        raise ProjectConfigError(
            "No scan directory is set. Use Manage → Choose folder, or say "
            '"set projects root C:/laragon/www".'
        )
    try:
        root_resolved = scan_root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ProjectConfigError(f"PROJECTS_ROOT does not exist: {scan_root}") from exc
    if not root_resolved.is_dir():
        raise ProjectConfigError(f"PROJECTS_ROOT is not a directory: {scan_root}")

    folder = root_resolved / pid
    if folder.exists():
        raise ProjectConfigError(
            f"Folder already exists: {folder}. "
            f'Say "add project {pid}" to register it, or pick another name.'
        )

    registry = load_projects(projects_file, strict=False)
    if pid in registry:
        raise ProjectConfigError(f"Project {pid!r} is already registered")

    try:
        folder.mkdir(parents=False, exist_ok=False)
    except OSError as exc:
        raise ProjectConfigError(f"Could not create folder {folder}: {exc}") from exc

    try:
        extra = {k: v for k, v in fields.items() if k not in {"type", "display_name"}}
        return register_project(
            pid,
            folder,
            projects_file=projects_file,
            root=root_resolved,
            type=str(fields.get("type") or "local"),
            display_name=str(fields.get("display_name") or display),
            **extra,
        )
    except Exception:
        try:
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        except OSError:
            pass
        raise


def register_project(
    project_id: str,
    path: str | Path,
    *,
    projects_file: Path | None = None,
    root: Path | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Register a folder under PROJECTS_ROOT with safe defaults."""
    pid = slugify_project_id(project_id) if not _is_valid_project_id(project_id) else project_id
    if not _is_valid_project_id(pid):
        raise ProjectConfigError(f"Invalid project id {project_id!r}")

    resolved = _resolve_under_root(path, root=root)
    registry = load_projects(projects_file, strict=False)
    if pid in registry:
        raise ProjectConfigError(f"Project {pid!r} is already registered")
    for existing_id, meta in registry.items():
        try:
            existing = str(Path(str(meta["path"])).expanduser().resolve())
        except OSError:
            existing = str(Path(str(meta["path"])).expanduser())
        if existing == str(resolved):
            raise ProjectConfigError(
                f"Path {resolved} is already registered as {existing_id!r}"
            )

    typ = str(fields.get("type") or _detect_type(resolved))
    raw: dict[str, Any] = {
        "path": str(resolved),
        "type": typ,
        "test_command": str(fields.get("test_command") or ""),
        "allow_push": bool(fields.get("allow_push", False)),
        "allow_deploy": bool(fields.get("allow_deploy", False)),
        "deploy_command": str(fields.get("deploy_command") or ""),
        "display_name": str(fields.get("display_name") or resolved.name),
        "description": str(fields.get("description") or ""),
        "instructions": str(fields.get("instructions") or ""),
        "default_branch": str(fields.get("default_branch") or "main"),
    }
    if "apply_local" in fields:
        raw["apply_local"] = bool(fields.get("apply_local"))

    registry[pid] = _validate_one(pid, raw)
    save_projects(registry, projects_file)
    return {"id": pid, **registry[pid]}


def update_project(
    project_id: str,
    *,
    projects_file: Path | None = None,
    root: Path | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Merge fields into an existing project and persist."""
    registry = load_projects(projects_file, strict=False)
    if project_id not in registry:
        raise ProjectConfigError(f"Unknown project: {project_id}")
    unknown = set(fields) - UPDATABLE_FIELDS
    if unknown:
        raise ProjectConfigError(
            f"Unsupported fields for update: {', '.join(sorted(unknown))}"
        )
    merged = dict(registry[project_id])
    for key, value in fields.items():
        if key in {"allow_push", "allow_deploy", "apply_local"}:
            merged[key] = bool(value)
        else:
            merged[key] = value
    if "path" in fields:
        merged["path"] = str(_resolve_under_root(merged["path"], root=root))
    registry[project_id] = _validate_one(project_id, merged)
    save_projects(registry, projects_file)
    return {"id": project_id, **registry[project_id]}


def remove_project(
    project_id: str,
    *,
    projects_file: Path | None = None,
) -> dict[str, Any]:
    """Remove a project from the registry."""
    registry = load_projects(projects_file, strict=False)
    if project_id not in registry:
        raise ProjectConfigError(f"Unknown project: {project_id}")
    removed = registry.pop(project_id)
    save_projects(registry, projects_file)
    return {"id": project_id, **removed}


def serialize_project(project_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    """Stable API/UI shape for a registered project."""
    return {
        "id": project_id,
        "name": str(meta.get("display_name") or project_id),
        "display_name": str(meta.get("display_name") or project_id),
        "type": str(meta.get("type") or "local"),
        "path": str(meta.get("path") or ""),
        "allow_push": bool(meta.get("allow_push", False)),
        "allow_deploy": bool(meta.get("allow_deploy", False)),
        "apply_local": bool(meta.get("apply_local", False)),
        "deploy_command": str(meta.get("deploy_command") or ""),
        "test_command": str(meta.get("test_command") or ""),
        "description": str(meta.get("description") or ""),
        "default_branch": str(meta.get("default_branch") or "main"),
    }
