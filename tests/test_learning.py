"""Closed-loop learning: outcomes, playbook, intent corrections, feedback."""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator import config, learning
from orchestrator.agent import build_prompt


@pytest.fixture()
def learning_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_FILE", str(tmp_path / "learn.sqlite"))
    monkeypatch.setenv("LEARNING_ENABLED", "true")
    config.settings.reload()
    from orchestrator import db

    db.initialize()
    return tmp_path


def test_outcome_and_playbook_roundtrip(learning_db):
    task = {
        "id": "abc123def456",
        "sender": "web:owner",
        "project": "lifeos",
        "instruction": "Fix light/dark mode toggle on the login page",
        "summary": "Updated login.blade.php theme classes and added a test.",
        "modified_files": '["resources/views/auth/login.blade.php"]',
    }
    learning.record_outcome(decision="approved", task=task, action="APPLY")
    learning.record_outcome(decision="published", task=task, action="APPLY")
    learning.maybe_append_playbook(task, action="APPLY")

    rules = learning.playbook_for_project("lifeos")
    assert rules
    assert "light/dark" in rules[0].lower() or "login" in rules[0].lower()

    # Duplicate should not grow the playbook.
    learning.maybe_append_playbook(task, action="APPLY")
    assert len(learning.playbook_for_project("lifeos")) == 1

    past = learning.past_successes_for_project(
        "lifeos", instruction="dark mode on login"
    )
    assert past
    assert "login" in past[0]["instruction"].lower()

    section = learning.format_playbook_section(
        "lifeos", instruction="fix dark mode login"
    )
    assert "LEARNED PROJECT MEMORY" in section
    assert "SIMILAR PAST SUCCESSES" in section


def test_intent_correction_fewshots(learning_db):
    learning.record_intent_correction(
        message_text="approve and apply",
        predicted_kind="task",
        corrected_kind="approve",
        sender="web:owner",
    )
    learning.record_intent_correction(
        message_text="approve and apply",
        predicted_kind="task",
        corrected_kind="approve",
        sender="web:owner",
    )  # dedup
    shots = learning.intent_fewshots()
    assert len(shots) == 1
    assert shots[0]["kind"] == "approve"
    assert shots[0].get("not") == "task"
    block = learning.format_intent_fewshot_section()
    assert "approve and apply" in block
    assert 'kind "approve"' in block


def test_feedback_thumbs(learning_db):
    ok = learning.record_feedback(
        rating="up",
        sender="web:owner",
        message_id=42,
        message_text="Done for task abc.",
        project="lifeos",
        task_id="abc123def456",
    )
    assert ok
    assert learning.record_feedback(rating="maybe", sender="web:owner") is False


def test_build_prompt_includes_learned_memory():
    prompt = build_prompt(
        "fix the spacing on the submit button",
        project_instructions="Use Tailwind utilities.",
        learned_memory="LEARNED PROJECT MEMORY:\n1. Prefer existing button classes.",
    )
    assert "PROJECT NOTES:" in prompt
    assert "Tailwind" in prompt
    assert "LEARNED PROJECT MEMORY" in prompt
    assert "Prefer existing button classes" in prompt


def test_learning_disabled(learning_db, monkeypatch):
    monkeypatch.setenv("LEARNING_ENABLED", "false")
    config.settings.reload()
    learning.record_outcome(
        decision="published",
        project="lifeos",
        instruction="should not store",
    )
    learning.maybe_append_playbook(
        {
            "project": "lifeos",
            "instruction": "should not store either",
            "summary": "noop",
        }
    )
    assert learning.playbook_for_project("lifeos") == []
    assert learning.format_playbook_section("lifeos") == ""
