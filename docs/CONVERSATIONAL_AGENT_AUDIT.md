# Conversational Agent Audit

**Date:** 2026-10-16  
**Scope:** Trace the LifeOS-style conversation through the real execution path and identify verified root causes (not UI wording alone).

## Executive summary

The orchestrator already has three pieces that look like a conversational coding assistant:

1. **Channel layer** — WhatsApp / Telegram / web chat → `handlers.handle`
2. **Conversational AI** — optional Groq classifier (`llm_chat`) + regex fallback (`converse`)
3. **Cursor coding agent** — CLI via `agent.run_agent` inside a durable job worker

The product failure in the reported conversation is **not** primarily that Cursor never ran. It is that **chat answers are decoupled from execution evidence**: status replies use coarse status labels (`running` → “In progress”), task creation always acknowledges with a template (“Got it - working on …”), follow-ups like “what’s remaining?” / “how long?” are not first-class intents without Groq, and the execution pipeline records almost no intermediate stages or events the assistant can cite.

Two AI roles must stay separate and share durable task state:

| Role | Existing module(s) | Job |
|------|--------------------|-----|
| Conversational AI | `llm_chat`, `converse`, `handlers` | Understand messages, maintain context, answer questions, orchestrate tasks |
| Cursor coding agent | `agent`, `execute`, `worker` | Investigate/edit code in an isolated workspace |

---

## 1. Message path (verified)

```text
User message
  → webchat.store("in") / WhatsApp / Telegram
  → handlers.handle(sender, body)
      → llm_chat.understand(...)   # if GROQ_API_KEY + GROQ_CHAT_ENABLED
      → else converse.parse_intent(...)
      → kind-specific branch (task / status / approve / …)
  → tasks.create_task + queue.enqueue("execute")
  → worker.process_job → execute.execute_task
      → workspace.setup
      → agent.run_agent (blocking subprocess)
      → optional test_command
      → tasks.update_task(status="review", summary=…)
      → notify.send_text (review / failure)
```

**Persistent chat history (remediated):** shared `conversation_turns` keyed by sender for web / Telegram / WhatsApp (`orchestrator/history.py`). Groq reads this shared layer. Web UI still uses `web_messages` for rendering.

**Project context (remediated):** durable `chat_sessions` (`active_project` / `active_task_id`) plus short-lived in-memory `_pending` clarifications.

**Active task context for follow-ups:** `_resolve_task` uses an explicit hex id or the newest task for the sender. Status replies do **not** read execution stages or events (those columns/events did not exist at audit time).

---

## 2. Reproduction of the reported conversation

| User | Observed / likely path | Why it fails the product bar |
|------|------------------------|------------------------------|
| “Let’s work on lifeos.” | Regex: no `_WORK_VERBS` match for “work”; often `unknown` or Groq → `ask_instruction`. Reply: “Okay - I'll use lifeos. What should I change?” | Acceptable project selection, but context is only in-memory pending. |
| “Fix light/dark mode on login/register…” | `task` → `_start_task` → template “Got it - working on lifeos…” | Acknowledgement invents confidence; does not say investigation stage or cite workspace prep. |
| “How long will it take?” | Regex: **not** matched as status/estimate → `unknown` or Groq `chat`. Often a hedged soft reply or “Just a few minutes”-style LLM invention. | Estimates are not grounded in scope/evidence. |
| “What’s remaining?” | Regex status patterns require `status|progress|what happened` — **“remaining” is absent**. Falls through unless Groq maps to `status`. | Status reply then: “Your work on lifeos is: In progress.” + repeats instruction. |
| Repeated “in progress” | `_STATUS_PLAIN["running"] = "In progress"`; no stage/events | No completed steps, current stage, or blockers from evidence. |

**Important:** Template replies do **not** prove the Cursor process failed. At audit time, `execute_task` sets `status=running`, prepares a workspace, then blocks on `agent.run_agent`. While that subprocess runs, chat has **no** intermediate events to report — so “In progress” is the only durable fact, even if the agent is actively editing files.

---

## 3. Root causes (verified)

### RC1 — Status answers are templates over coarse status

`handlers._status_reply` maps `queued|running|review|…` to plain English and always re-states the original instruction. It never lists completed pipeline steps, current execution stage, modified files, exit codes, or blockers.

### RC2 — No durable execution lifecycle beyond status enum

`tasks` stores `status`, `summary`, workspace/branch. There is no `execution_stage`, event log, `started_at` / `last_activity_at`, modified-file list, or exit code. Suggested stages (`preparing_workspace` → `investigating` → `implementing` → `testing` → `ready_for_review`) are not represented.

### RC3 — Follow-up intents missing from regex brain

`converse.parse_intent` lacks first-class kinds for remaining / estimate / changes / stuck / done / continue. Without Groq, those messages become `unknown` and get a generic help dump.

### RC4 — Conversational context is ephemeral

`_pending` and `_memory` live in process memory. Restart clears “we’re working on LifeOS” and “last work request.” Web message history helps Groq only for `web:` senders.

### RC5 — Cursor execution is opaque to chat

`process.run` is a blocking `subprocess.run` with captured stdout/stderr only at the end. No PID registry for cancel, no streaming events, no mid-run file snapshots. Cancel marks the task `failed` but does not reliably stop the agent process.

### RC6 — Milestone notifications are sparse and not event-driven

Handler acknowledges once; execute notifies mainly on review/failure. Quiet-by-design comment in `execute.py` suppresses mid-run updates. Users who ask for progress only see the coarse status template.

### RC7 — Dual-brain coupling is incomplete

Groq is used to *classify* and *phrase* informational replies, but status/approve paths deliberately null out LLM replies and rebuild from templates. That is correct for not inventing facts — but the factual payload fed into those replies is too thin.

---

## 4. What already works (preserve)

- Durable job queue + worker lease (`queue`, `worker`)
- Isolated workspaces (`workspace.setup`) — does not mutate the user’s active checkout until approve
- Cursor CLI adapter with Windows-safe task file (`agent.py`)
- Auth recovery / API key path
- Approval gates for push / apply / PR / deploy
- Optional Groq classifier with JSON schema + project allowlist
- Web chat history + polling UI

---

## 5. Remediation map (this upgrade)

| Capability | Approach |
|------------|----------|
| Conversational intelligence | Durable `chat_sessions` (active project/task); expand intents; enrich Groq system prompt with session + task evidence |
| Real agent integration | Keep CLI; record stages/events around workspace/agent/tests; track process for cancel |
| Durable task tracking | New task columns + `task_events` table |
| Context-aware status | `progress.py` builds replies only from DB evidence |
| Event-driven updates | Milestone chat notices on stage transitions; `/chat/task-progress` for the UI panel |
| Regression | Automated tests for intents, progress text, session, events |

---

## 6. Non-goals / constraints honored

- Do not rebuild the app; extend existing modules.
- Never invent file changes, timings, or test results.
- Never treat an LLM sentence as proof of execution.
- Never auto-deploy/push without explicit approval.
- Groq is optional; regex + evidence replies must work when `GROQ_API_KEY` is empty.
