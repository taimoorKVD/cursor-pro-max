from orchestrator.converse import clear_pending, parse_intent

REGISTRY = {
    "lifeos": {"display_name": "lifeOS", "type": "git"},
    "kv-hrms": {"display_name": "kv-hrms", "type": "git"},
}


def test_parse_natural_task_forms():
    assert parse_intent("on lifeos, add a README note", REGISTRY).kind == "task"
    assert parse_intent("on lifeos, add a README note", REGISTRY).project == "lifeos"
    assert parse_intent("lifeos: fix the login", REGISTRY).instruction.lower().startswith("fix")
    i = parse_intent("please improve login on lifeos", REGISTRY)
    assert i.kind == "task" and i.project == "lifeos"


def test_parse_need_project_then_resolve():
    clear_pending("u1")
    i = parse_intent("please improve the login validation", REGISTRY, sender="u1")
    assert i.kind == "task_need_project"
    # simulate pending set by handler
    from orchestrator import converse

    converse.set_pending("u1", kind="need_project", instruction=i.instruction)
    i2 = parse_intent("lifeos", REGISTRY, sender="u1")
    assert i2.kind == "task"
    assert i2.project == "lifeos"


def test_parse_approve_reject_last():
    assert parse_intent("approve and push", REGISTRY).kind == "approve"
    assert parse_intent("approve and push", REGISTRY).action == "PUSH"
    assert parse_intent("apply locally", REGISTRY).kind == "approve"
    assert parse_intent("apply locally", REGISTRY).action == "APPLY"
    assert parse_intent("apply", REGISTRY).kind == "approve"
    assert parse_intent("apply", REGISTRY).action == "APPLY"
    assert parse_intent("apply it", REGISTRY).action == "APPLY"
    assert parse_intent("approve and apply", REGISTRY).action == "APPLY"
    assert parse_intent("reject that", REGISTRY).kind == "reject"
    assert parse_intent("cancel that task", REGISTRY).kind == "cancel_task"
    assert parse_intent("how is my last task going?", REGISTRY).kind == "status"


def test_resolve_intent_prefers_regex_apply_over_llm_task():
    from orchestrator.converse import Intent, resolve_intent

    llm_task = Intent(kind="task", project="lifeos", instruction="apply", raw="apply")
    resolved = resolve_intent("apply", REGISTRY, llm_intent=llm_task)
    assert resolved.kind == "approve"
    assert resolved.action == "APPLY"

    llm_push = Intent(kind="approve", action="PUSH", raw="apply")
    resolved2 = resolve_intent("apply", REGISTRY, llm_intent=llm_push)
    assert resolved2.action == "APPLY"


def test_parse_create_pull_request():
    i = parse_intent("Create a pull request instead.", REGISTRY)
    assert i.kind == "approve" and i.action == "PR"
    i2 = parse_intent("open a PR for abcdef123456", REGISTRY)
    assert i2.kind == "approve" and i2.action == "PR" and i2.task_id == "abcdef123456"
    i3 = parse_intent("approve and create a pull request", REGISTRY)
    assert i3.kind == "approve" and i3.action == "PR"


def test_offer_project_followup_yes():
    from orchestrator import converse

    clear_pending("u2")
    converse.set_pending("u2", kind="offer_project", project="lifeos")
    i = parse_intent(
        "yes, remove the welcome back text from the login page",
        REGISTRY,
        sender="u2",
    )
    assert i.kind == "task"
    assert i.project == "lifeos"
    assert "welcome back" in (i.instruction or "").lower()


def test_work_request_with_trailing_project_word():
    """'… from the lifeos project' must start a task, not list projects."""
    i = parse_intent(
        "remove the light/dark mode from the login page from the lifeos project",
        REGISTRY,
    )
    assert i.kind == "task"
    assert i.project == "lifeos"
    assert "light/dark" in (i.instruction or "").lower()
    assert "lifeos" not in (i.instruction or "").lower()
    assert not (i.instruction or "").lower().endswith("project")


def test_explicit_projects_list_still_works():
    assert parse_intent("what projects do I have?", REGISTRY).kind == "projects"
    assert parse_intent("PROJECTS", REGISTRY).kind == "projects"
    assert parse_intent("list my projects", REGISTRY).kind == "projects"
    # Casual / imperfect English should still list projects.
    for phrase in (
        "what type of projects we've?",
        "what types of projects do we have",
        "what kind of projects are there",
        "how many projects",
        "show me our projects",
        "got any projects?",
        "which projects can you work on",
        "do we have projects",
    ):
        assert parse_intent(phrase, REGISTRY).kind == "projects", phrase


def test_parse_scan_register_update_remove_projects():
    assert parse_intent("scan projects", REGISTRY).kind == "scan_projects"
    assert parse_intent("find new projects", REGISTRY).kind == "scan_projects"
    assert parse_intent("what folders aren't registered", REGISTRY).kind == "scan_projects"
    from_scan = parse_intent("scan projects from C:/laragon/www", REGISTRY)
    assert from_scan.kind == "scan_projects"
    assert from_scan.instruction and "laragon" in from_scan.instruction.replace("\\", "/")
    set_root = parse_intent("set projects root C:/Users/me/code", REGISTRY)
    assert set_root.kind == "set_projects_root"
    assert set_root.instruction and "Users" in set_root.instruction.replace("\\", "/")
    assert parse_intent("where is the projects root?", REGISTRY).kind == "show_projects_root"

    reg = parse_intent("add project velora", REGISTRY)
    assert reg.kind == "register_project" and reg.project == "velora"
    assert parse_intent("register truck-lts", REGISTRY).kind == "register_project"

    upd = parse_intent("update project lifeos set allow_push true", REGISTRY)
    assert upd.kind == "update_project"
    assert upd.project == "lifeos"
    assert upd.updates == {"allow_push": True}

    rem = parse_intent("remove project velora", REGISTRY)
    assert rem.kind == "remove_project" and rem.project == "velora"

    from orchestrator import converse

    clear_pending("u-rm")
    converse.set_pending("u-rm", kind="confirm_remove_project", project="velora")
    yes = parse_intent("yes", REGISTRY, sender="u-rm")
    assert yes.kind == "remove_project"
    assert yes.action == "CONFIRM"
    assert yes.project == "velora"


def test_retry_uses_remembered_work():
    from orchestrator import converse

    converse.remember_work(
        "u-retry",
        project="lifeos",
        instruction="fix light/dark on login",
        task_id="abcdef123456",
    )
    i = parse_intent("yeah let's do it again", REGISTRY, sender="u-retry")
    assert i.kind == "retry"
    assert i.project == "lifeos"
    assert "light/dark" in (i.instruction or "")
    i2 = parse_intent("the task I gave you earlier", REGISTRY, sender="u-retry")
    assert i2.kind == "retry" and i2.project == "lifeos"
