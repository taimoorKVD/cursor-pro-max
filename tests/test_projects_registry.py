"""Unit tests for dynamic project registry (scan + explicit register)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator import config
from orchestrator.projects import (
    ProjectConfigError,
    browse_directories,
    clear_projects_root_override,
    discover_candidates,
    load_projects,
    projects_root,
    projects_root_info,
    register_project,
    remove_project,
    save_projects,
    set_projects_root,
    slugify_project_id,
    update_project,
)


def _setup_root(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    root = tmp_path / "www"
    root.mkdir()
    projects_file = tmp_path / "projects.json"
    root_file = tmp_path / "projects_root.json"
    monkeypatch.setenv("PROJECTS_FILE", str(projects_file))
    monkeypatch.setenv("PROJECTS_ROOT", str(root))
    monkeypatch.setenv("PROJECTS_ROOT_FILE", str(root_file))
    config.settings.reload()
    return root, projects_file


def test_slugify_project_id():
    assert slugify_project_id("My App") == "my-app"
    assert slugify_project_id("kv_hrms") == "kv_hrms"
    with pytest.raises(ProjectConfigError):
        slugify_project_id("???")


def test_discover_candidates_classifies_and_skips(tmp_path, monkeypatch):
    root, projects_file = _setup_root(tmp_path, monkeypatch)
    (root / "alpha").mkdir()
    (root / "beta").mkdir()
    (root / "beta" / ".git").mkdir()
    (root / "node_modules").mkdir()
    (root / ".hidden").mkdir()
    (root / "readme.txt").write_text("x", encoding="utf-8")

    save_projects(
        {
            "alpha": {
                "path": str(root / "alpha"),
                "type": "local",
                "allow_push": False,
                "allow_deploy": False,
            }
        },
        projects_file,
    )

    found = discover_candidates()
    by_id = {c["id"]: c for c in found}
    assert "alpha" in by_id and by_id["alpha"]["registered"] is True
    assert "beta" in by_id
    assert by_id["beta"]["type"] == "git"
    assert by_id["beta"]["registered"] is False
    assert "node_modules" not in by_id
    assert all(not c["id"].startswith(".") for c in found)


def test_register_update_remove_round_trip(tmp_path, monkeypatch):
    root, projects_file = _setup_root(tmp_path, monkeypatch)
    folder = root / "velora"
    folder.mkdir()

    created = register_project("velora", folder)
    assert created["id"] == "velora"
    assert created["type"] == "local"
    assert created["allow_push"] is False
    assert created["allow_deploy"] is False
    assert projects_file.exists()
    loaded = load_projects(projects_file, strict=True)
    assert "velora" in loaded

    updated = update_project("velora", display_name="Velora App", description="demo")
    assert updated["display_name"] == "Velora App"
    assert updated["description"] == "demo"

    removed = remove_project("velora")
    assert removed["id"] == "velora"
    assert load_projects(projects_file, strict=True) == {}


def test_register_rejects_path_outside_root(tmp_path, monkeypatch):
    root, _projects_file = _setup_root(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ProjectConfigError, match="under PROJECTS_ROOT"):
        register_project("evil", outside)


def test_register_rejects_duplicate_id_and_path(tmp_path, monkeypatch):
    root, _projects_file = _setup_root(tmp_path, monkeypatch)
    a = root / "a"
    a.mkdir()
    register_project("a", a)
    with pytest.raises(ProjectConfigError, match="already registered"):
        register_project("a", a)
    b = root / "b"
    b.mkdir()
    # Same path under a different id
    with pytest.raises(ProjectConfigError, match="already registered"):
        register_project("alias", a)


def test_update_rejects_local_allow_push(tmp_path, monkeypatch):
    root, _projects_file = _setup_root(tmp_path, monkeypatch)
    folder = root / "snap"
    folder.mkdir()
    register_project("snap", folder, type="local")
    with pytest.raises(ProjectConfigError, match="allow_push"):
        update_project("snap", allow_push=True)


def test_save_projects_atomic_valid_json(tmp_path, monkeypatch):
    root, projects_file = _setup_root(tmp_path, monkeypatch)
    folder = root / "demo"
    folder.mkdir()
    save_projects(
        {
            "demo": {
                "path": str(folder),
                "type": "local",
                "allow_push": False,
                "allow_deploy": False,
            }
        },
        projects_file,
    )
    data = json.loads(projects_file.read_text(encoding="utf-8"))
    assert "demo" in data
    assert data["demo"]["path"]


def test_discover_requires_projects_root(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECTS_FILE", str(tmp_path / "projects.json"))
    monkeypatch.setenv("PROJECTS_ROOT", "")
    monkeypatch.setenv("PROJECTS_ROOT_FILE", str(tmp_path / "projects_root.json"))
    config.settings.reload()
    with pytest.raises(ProjectConfigError, match="scan directory"):
        discover_candidates()


def test_git_project_defaults_apply_local(tmp_path, monkeypatch):
    root, _projects_file = _setup_root(tmp_path, monkeypatch)
    folder = root / "repo"
    folder.mkdir()
    (folder / ".git").mkdir()
    created = register_project("repo", folder)
    assert created["type"] == "git"
    assert created["apply_local"] is True


def test_set_projects_root_persists_and_overrides_env(tmp_path, monkeypatch):
    root, _projects_file = _setup_root(tmp_path, monkeypatch)
    other = tmp_path / "other"
    other.mkdir()
    (other / "fresh").mkdir()

    info = set_projects_root(other, persist=True)
    assert info["source"] == "override"
    assert Path(info["path"]).resolve() == other.resolve()
    assert projects_root().resolve() == other.resolve()

    found = discover_candidates()
    assert any(c["id"] == "fresh" and not c["registered"] for c in found)

    cleared = clear_projects_root_override()
    assert cleared["source"] == "env"
    assert Path(cleared["path"]).resolve() == root.resolve()
    assert projects_root_info()["source"] == "env"


def test_set_projects_root_rejects_missing(tmp_path, monkeypatch):
    _setup_root(tmp_path, monkeypatch)
    with pytest.raises(ProjectConfigError, match="does not exist"):
        set_projects_root(tmp_path / "missing-dir")


def test_browse_directories_lists_children(tmp_path, monkeypatch):
    root, _projects_file = _setup_root(tmp_path, monkeypatch)
    (root / "alpha").mkdir()
    (root / "beta").mkdir()
    (root / "readme.txt").write_text("x", encoding="utf-8")
    (root / "node_modules").mkdir()

    listing = browse_directories(root)
    names = {e["name"] for e in listing["entries"]}
    assert names == {"alpha", "beta"}
    assert listing["path"]
    assert listing["at_root"] is False


def test_browse_directories_missing(tmp_path, monkeypatch):
    _setup_root(tmp_path, monkeypatch)
    with pytest.raises(ProjectConfigError, match="does not exist"):
        browse_directories(tmp_path / "nope")
