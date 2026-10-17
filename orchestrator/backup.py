"""SQLite online backup and restore into a separate file.

Restore never replaces the live database path. Callers pass an explicit destination.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from orchestrator import db


def backup_database(dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    with db.DB_LOCK:
        source = db.connect()
        try:
            target = sqlite3.connect(str(dest))
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
    if not verify_database(dest):
        raise RuntimeError(f"Backup failed integrity check: {dest}")
    return dest


def verify_database(path: Path) -> bool:
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        if not row or str(row[0]).lower() != "ok":
            return False
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        return "tasks" in tables
    finally:
        conn.close()


def restore_database(backup: Path, dest: Path) -> Path:
    """Copy a verified backup to ``dest``. Refuses to overwrite the live database file."""
    backup = Path(backup)
    dest = Path(dest)
    if dest.resolve() == config_database().resolve():
        raise RuntimeError("Refusing to restore over the live orchestrator database")
    if not verify_database(backup):
        raise RuntimeError(f"Backup is not a valid orchestrator database: {backup}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    src = sqlite3.connect(str(backup))
    try:
        out = sqlite3.connect(str(dest))
        try:
            src.backup(out)
        finally:
            out.close()
    finally:
        src.close()
    if not verify_database(dest):
        raise RuntimeError(f"Restored database failed integrity check: {dest}")
    return dest


def config_database() -> Path:
    from orchestrator import config

    return Path(config.DATABASE_FILE)
