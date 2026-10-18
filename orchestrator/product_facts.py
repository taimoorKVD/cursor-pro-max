"""Grounded product / architecture facts for chat (never invent how the system works)."""
from __future__ import annotations

import re

# Injected into the Groq system prompt so meta-questions stay truthful.
ARCHITECTURE_FACTS = """
How this orchestrator actually works (facts — do not invent alternatives):
- Coding work runs via the Cursor CLI agent in an isolated git worktree on this laptop.
  CURSOR_API_KEY (or `agent login`) authenticates that CLI. There is no separate
  "Cursor REST chat API" proxy in the middle of ordinary coding tasks.
- Groq (GROQ_API_KEY) is optional and only classifies chat + drafts soft replies.
  Groq is NOT the coding agent and does not edit your repos.
- Projects are folders registered on this machine (local path and/or git). Work never
  mutates your real project folder until you explicitly approve (apply / push / PR).
- "Approve and apply" merges the review branch into your local project. "Approve and
  push" also needs a git remote named origin (e.g. GitHub). No origin → use apply only
  or add a remote first.
- Image attachments in web chat are staged into the task workspace and listed in the
  agent prompt as workspace-relative paths (Cursor-style), not uploaded to a cloud vision API by default.
- Chat history and last-work memory can survive restarts (SQLite). The model itself is
  not fine-tuned from your chats; durable memory + session/history are how continuity works.
- Closed-loop learning (when enabled): approve/reject/thumbs outcomes update a per-project
  playbook and intent few-shots injected into the next agent/classifier run — still not
  weight fine-tuning.
- Self-improve means registering this orchestrator repo as a project, letting the agent
  change an isolated copy, then approving apply — not automatic model training.
- Status / remaining / done / changes answers must come from task evidence on the server
  (reply=null for those kinds). Never invent progress, timings, or test results.
""".strip()


_FAQ: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(cursor\s+api\s*key|api\s*key).{0,80}\b(direct|communicate|talk|call)|"
            r"\b(directly\s+communicate|talk\s+to\s+cursor|use\s+cursor\s+api)\b|"
            r"\bhow\s+do\s+you\s+(talk|connect|call).{0,40}\bcursor\b",
            re.I,
        ),
        "When CURSOR_API_KEY (or `agent login`) is set, coding tasks run the Cursor CLI "
        "agent against an isolated worktree on this laptop. That key authenticates the CLI — "
        "it is not a separate chat proxy, and Groq (if enabled) only helps understand your "
        "messages, not write the code.",
    ),
    (
        re.compile(
            r"\b(bypass|skip).{0,40}\b(local|laptop|server).{0,40}\b(github|git)|"
            r"\b(directly|only).{0,40}\b(from|on)\s+github\b|"
            r"\bread\s+the\s+project\s+from\s+github\b|"
            r"\bwithout\s+(a\s+)?local\b",
            re.I,
        ),
        "Today every coding run still uses a local checkout: either your registered project "
        "folder or a clone/worktree under the orchestrator work root. There is no "
        "GitHub-only mode that edits remote files without a local workspace. After review "
        "you can push to origin if the project has allow_push and a remote named origin.",
    ),
    (
        re.compile(
            r"\bis\s+it\s+safe\b|"
            r"\b(safe|security).{0,40}\b(push|github|apply|approve)\b",
            re.I,
        ),
        "The safe path is: work stays in an isolated copy until you approve; apply can "
        "update your local folder; push needs origin + allow_push. Use least-privilege "
        "credentials, review the diff before approving, and keep secrets out of commits "
        "(.env stays gitignored).",
    ),
    (
        re.compile(
            r"\b(train|learn|improv)\s+(yourself|itself|from)\b|"
            r"\bself[- ]?(train|learn|improv)\b|"
            r"\bremember\s+(every|each|past)\b|"
            r"\b(fine[- ]?tun|retrain)\b",
            re.I,
        ),
        "I don't fine-tune a model from your chats. Continuity comes from durable chat "
        "history, session (active project/task), and last-work memory in SQLite. "
        "Approve/reject and thumbs also feed a project playbook and intent corrections "
        "into later runs — still not weight training. Improving the product code itself "
        "means running coding tasks on this orchestrator repo and approving apply.",
    ),
    (
        re.compile(
            r"\b(do you|are you).{0,20}\b(work\s+)?(just\s+)?like\s+cursor\b|"
            r"\b(same\s+as|similar\s+to)\s+cursor\b|"
            r"\bhow\s+do\s+you\s+work\b|"
            r"\bhow\s+does\s+(this|the)\s+(system|orchestrator|chat)\s+work\b",
            re.I,
        ),
        "I'm the orchestrator chat layer: I understand requests, track tasks, and answer "
        "from real execution evidence. Heavy coding is done by the Cursor CLI agent in an "
        "isolated workspace — similar spirit to Cursor, but you approve before your real "
        "project folder (or remote) is updated.",
    ),
    (
        re.compile(
            r"\b(remember|persist|keep).{0,40}\b(past|previous|prior)\s+"
            r"(conversation|chat|messages|context)\b|"
            r"\bconversation\s+memory\b",
            re.I,
        ),
        "Yes for product state: web/Telegram/WhatsApp turns are stored, your active "
        "project/task session is durable, and last-work / pending clarifications persist "
        "across orchestrator restarts. Clearing chat wipes that sender's conversational "
        "state. The underlying LLM is not permanently trained on those turns.",
    ),
]


def architecture_blurb() -> str:
    """Short grounded overview for help / how_it_works."""
    return (
        "I run coding work through the Cursor CLI in an isolated copy of your registered "
        "laptop project, then wait for your approval before applying locally or pushing to "
        "origin. Optional Groq only helps understand chat — it does not edit code. "
        "Status answers come from real task events, not guesses."
    )


def try_answer(text: str) -> str | None:
    """Return a grounded FAQ answer when the message is clearly about the product."""
    raw = (text or "").strip()
    if not raw or len(raw) > 500:
        return None
    for pattern, answer in _FAQ:
        if pattern.search(raw):
            return answer
    return None


def looks_like_product_question(text: str) -> bool:
    return try_answer(text) is not None
