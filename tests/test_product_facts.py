"""Grounded product Q&A — no invented Cursor REST / GitHub-only / self-train claims."""
from __future__ import annotations

from orchestrator import product_facts
from orchestrator.converse import Intent, parse_intent, resolve_intent


REGISTRY = {"lifeos": {"display_name": "lifeOS", "type": "git"}}


def test_faq_cursor_api_key():
    ans = product_facts.try_answer(
        "when we are using cursor API Key, then don't we directly communicate to cursor?"
    )
    assert ans
    assert "CLI" in ans
    assert "REST" not in ans or "not a separate" in ans.lower() or "not" in ans.lower()


def test_faq_github_bypass():
    ans = product_facts.try_answer(
        "is there any possibility we could bypass the local server project and "
        "directly read the project from github?"
    )
    assert ans
    assert "GitHub-only" in ans or "local" in ans.lower()


def test_faq_self_train():
    ans = product_facts.try_answer(
        "are you able to train yourself based on every action and request?"
    )
    assert ans
    lowered = ans.lower()
    assert "fine-tune" in lowered or "don't" in lowered
    assert "playbook" in lowered or "not weight" in lowered or "sqlite" in lowered


def test_how_it_works_intent():
    i = parse_intent("do you work just like cursor?", REGISTRY)
    assert i.kind == "how_it_works"
    i2 = parse_intent("how does this work?", REGISTRY)
    assert i2.kind == "how_it_works"


def test_resolve_intent_keeps_local_git_over_llm_approve():
    llm = Intent(kind="approve", action="PUSH", raw="commit local and apply")
    resolved = resolve_intent(
        "commit local and apply",
        REGISTRY,
        llm_intent=llm,
    )
    assert resolved.kind == "local_git"
    assert resolved.action == "COMMIT_APPLY"


def test_resolve_intent_keeps_how_it_works_over_llm_chat():
    llm = Intent(kind="chat", raw="is it safe?")
    resolved = resolve_intent("is it safe to push to github?", REGISTRY, llm_intent=llm)
    assert resolved.kind == "how_it_works"
