"""Detailed publish/apply completion reports (timeline format)."""
from __future__ import annotations

from orchestrator import progress
from orchestrator.progress import format_completion_report, parse_completion_report


def test_format_and_parse_completion_report_roundtrip():
    text = format_completion_report(
        task_id="3429d8b88fe9",
        title="Commit local changes and apply to project.",
        steps=[
            {
                "title": "Committing local changes",
                "detail": "Found 7 local change(s) on branch master.",
                "status": "completed",
            },
            {
                "title": "Creating backup",
                "detail": "Creating backup bundle before applying changes.",
                "status": "completed",
            },
            {
                "title": "Applying changes",
                "detail": "Applying local changes to project...",
                "status": "in_progress",
            },
            {
                "title": "Finalizing",
                "detail": "Updating project state and confirming success.",
                "status": "ready",
            },
        ],
        status_label="In Progress",
        footnotes=["No production deploy was run."],
    )
    assert text.startswith("=== Task completion ===")
    assert "Task 3429d8b88fe9" in text
    assert "1. [done] Committing local changes" in text
    assert "Found 7 local change(s) on branch master." in text
    assert "3. [live] Applying changes" in text
    parsed = parse_completion_report(text)
    assert parsed is not None
    assert parsed["task_id"] == "3429d8b88fe9"
    assert parsed["status_label"] == "In Progress"
    assert parsed["title"].startswith("Commit local changes")
    assert len(parsed["steps"]) == 4
    assert parsed["steps"][0]["status"] == "completed"
    assert parsed["steps"][2]["status"] == "in_progress"
    assert parsed["steps"][3]["status"] == "ready"
    assert parsed["footnotes"] == ["No production deploy was run."]


def test_parse_rejects_generic_commit_summary():
    assert parse_completion_report("Done for task abc. Committed deadbeef on wa/x.") is None


def test_publish_apply_sends_completion_timeline(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "t.sqlite"))
    monkeypatch.setenv("WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.setenv("DEPLOY_ENABLED", "false")
    from orchestrator import config, db, tasks
    from orchestrator import publish as pub

    config.settings.reload()
    db.initialize()
    replies: list[str] = []
    monkeypatch.setattr(pub, "send_text", lambda s, t, **k: replies.append(t))
    monkeypatch.setattr(
        pub,
        "apply_to_local",
        lambda *a, **k: "Local project fast-forwarded: D:/demo (master ← wa/aabbccddeeff). Backup: D:/bak",
    )
    monkeypatch.setattr(pub, "_commit_workspace", lambda *a, **k: "abc1234")
    monkeypatch.setattr(pub, "_head_sha", lambda *a, **k: "abc1234deadbeef")
    monkeypatch.setattr(pub, "_worktree_clean", lambda *a, **k: True)
    monkeypatch.setattr(
        "orchestrator.workspace.content_digest",
        lambda *a, **k: "digest123",
    )
    monkeypatch.setattr(pub, "_is_orchestrator_checkout", lambda *_a, **_k: False)

    ws = tmp_path / "wt"
    ws.mkdir()
    tasks.create_task("aabbccddeeff", "web:owner", "demo", "tweak")
    tasks.update_task("aabbccddeeff", status="running")
    tasks.update_task(
        "aabbccddeeff",
        status="review",
        workspace=str(ws),
        branch="wa/aabbccddeeff",
        content_digest="digest123",
        approved_sha="abc1234deadbeef",
    )
    assert tasks.claim_publishing("aabbccddeeff")
    task = tasks.get_task("aabbccddeeff")
    assert task
    pub.publish(
        task,
        {
            "path": str(tmp_path / "demo"),
            "type": "git",
            "apply_local": True,
            "allow_push": False,
        },
        "APPLY",
    )
    assert replies
    final = replies[-1]
    assert "=== Task completion ===" in final
    assert "Done for task" not in final
    parsed = parse_completion_report(final)
    assert parsed is not None
    titles = [s["title"] for s in parsed["steps"]]
    assert "Committing approved changes" in titles
    assert "Creating backup" in titles
    assert "Applying changes" in titles
    assert "Finalizing" in titles
    assert not any("restart" in (n or "").lower() for n in (parsed.get("footnotes") or []))
    snap = progress.snapshot(tasks.get_task("aabbccddeeff"))
    assert snap["publish_steps"]
    assert any(s["title"] == "Applying changes" for s in snap["publish_steps"])
