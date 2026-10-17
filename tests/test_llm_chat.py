from orchestrator.llm_chat import LlmResult, _parse_payload, understand
from orchestrator.converse import Intent

REGISTRY = {
    "lifeos": {"display_name": "lifeOS", "type": "git"},
    "kv-hrms": {"type": "git"},
}


def test_parse_projects_payload():
    result = _parse_payload(
        {
            "kind": "projects",
            "project": None,
            "reply": "You've got lifeos on GitHub plus kv-hrms - want me to dig into one?",
        },
        REGISTRY,
        "what type of projects we've?",
    )
    assert result is not None
    assert result.intent.kind == "projects"
    assert result.reply and "lifeos" in result.reply.lower()


def test_parse_projects_reply_dropped_if_invented():
    result = _parse_payload(
        {"kind": "projects", "reply": "You only have madeup-app available."},
        REGISTRY,
        "what projects?",
    )
    assert result is not None
    assert result.intent.kind == "projects"
    assert result.reply is None


def test_parse_task_and_chat_reply():
    task = _parse_payload(
        {
            "kind": "task",
            "project": "lifeOS",
            "instruction": "fix the login page",
            "reply": "ignored",
        },
        REGISTRY,
        "on lifeos fix login",
    )
    assert task is not None
    assert task.intent.kind == "task"
    assert task.intent.project == "lifeos"
    assert task.reply is None

    chat = _parse_payload(
        {"kind": "chat", "reply": "Happy to help with your coding work."},
        REGISTRY,
        "how's your day?",
    )
    assert chat is not None
    assert chat.intent.kind == "chat"
    assert "Happy to help" in (chat.reply or "")


def test_unknown_project_becomes_need_project():
    result = _parse_payload(
        {"kind": "task", "project": "not-real", "instruction": "add a button"},
        REGISTRY,
        "on not-real add a button",
    )
    assert result is not None
    assert result.intent.kind == "task_need_project"


def test_parse_registry_management_kinds():
    scan = _parse_payload({"kind": "scan_projects", "reply": "ignored"}, REGISTRY, "scan projects")
    assert scan is not None
    assert scan.intent.kind == "scan_projects"
    assert scan.reply is None

    set_root = _parse_payload(
        {
            "kind": "set_projects_root",
            "instruction": "C:/laragon/www",
        },
        REGISTRY,
        "set projects root C:/laragon/www",
    )
    assert set_root is not None
    assert set_root.intent.kind == "set_projects_root"
    assert "laragon" in (set_root.intent.instruction or "")

    show_root = _parse_payload(
        {"kind": "show_projects_root"},
        REGISTRY,
        "where is the projects root?",
    )
    assert show_root is not None
    assert show_root.intent.kind == "show_projects_root"

    reg = _parse_payload(
        {"kind": "register_project", "project": "velora"},
        REGISTRY,
        "add project velora",
    )
    assert reg is not None
    assert reg.intent.kind == "register_project"
    assert reg.intent.project == "velora"

    upd = _parse_payload(
        {
            "kind": "update_project",
            "project": "lifeos",
            "updates": {"allow_push": True},
        },
        REGISTRY,
        "update project lifeos set allow_push true",
    )
    assert upd is not None
    assert upd.intent.kind == "update_project"
    assert upd.intent.updates == {"allow_push": True}

    rem = _parse_payload(
        {"kind": "remove_project", "project": "lifeos"},
        REGISTRY,
        "remove project lifeos",
    )
    assert rem is not None
    assert rem.intent.kind == "remove_project"
    assert rem.intent.project == "lifeos"


def test_understand_disabled_without_key(monkeypatch):
    from orchestrator import config

    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "")
    monkeypatch.setattr(config.settings, "GROQ_CHAT_ENABLED", True)
    assert understand("what projects?", REGISTRY) is None


def test_understand_uses_groq_when_enabled(monkeypatch):
    from orchestrator import config, llm_chat

    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(config.settings, "GROQ_CHAT_ENABLED", True)

    def fake_completion(
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        history=None,
    ):
        assert "lifeos" in system
        assert "what type" in user.lower()
        return {
            "kind": "projects",
            "project": None,
            "reply": "You've got lifeos and kv-hrms ready - which should we open?",
        }

    monkeypatch.setattr(llm_chat, "_chat_completion", fake_completion)
    result = understand("what type of projects we've?", REGISTRY)
    assert isinstance(result, LlmResult)
    assert result.intent.kind == "projects"


def test_handler_prefers_llm_intent(monkeypatch, tmp_path):
    from orchestrator import config, db, handlers, llm_chat

    monkeypatch.setattr(config.settings, "DATABASE_FILE", tmp_path / "t.sqlite")
    monkeypatch.setattr(config.settings, "WORK_ROOT", tmp_path / "w")
    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(config.settings, "GROQ_CHAT_ENABLED", True)
    db.initialize()

    sent: list[str] = []

    def capture(sender: str, text: str, *, level: str | None = None) -> None:
        sent.append(text)

    monkeypatch.setattr("orchestrator.handlers.send_text", capture)
    monkeypatch.setattr(
        "orchestrator.handlers.projects.projects",
        lambda: REGISTRY,
    )
    monkeypatch.setattr(
        llm_chat,
        "understand",
        lambda text, registry, sender="": LlmResult(
            intent=Intent(kind="projects", raw=text),
            reply=None,
        ),
    )

    monkeypatch.setattr(
        llm_chat,
        "phrase",
        lambda *a, **k: None,
    )

    handlers.handle("web:test", "what type of projects we've?")
    assert sent
    assert "lifeos" in sent[0].lower() or "projects" in sent[0].lower()
