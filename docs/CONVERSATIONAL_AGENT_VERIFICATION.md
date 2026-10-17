# Conversational Agent — Verification Report

**Date:** 2026-10-16 (updated)  
**Baseline:** `docs/CONVERSATIONAL_AGENT_AUDIT.md` (accepted)

## Architectural change summary

Two AI capabilities remain separate and share durable SQLite state:

| Capability | Modules | Role |
|------------|---------|------|
| Conversational AI | `history`, `session`, `converse`, `llm_chat`, `handlers`, `progress` | Context, follow-ups, evidence-based answers |
| Cursor coding agent | `agent`, `process`, `execute`, `worker` | Isolated workspace edits; process PID/exit/cancel |

### Honest execution stages (critical fix)

Mid-run Cursor activity is **not** labeled `investigating` / `implementing` merely because a subprocess is alive.

| Stage | When recorded |
|-------|----------------|
| `queued` | Task created |
| `preparing_workspace` | Workspace setup started/finished |
| `agent_running` | Cursor process started; label = **Agent running — detailed activity unavailable** |
| `testing` | Configured `test_command` actually runs |
| `ready_for_review` | Agent (+ optional tests) finished with review package |
| `failed` / `canceled` / `timeout` | Evidenced terminal outcomes |

Process monitoring: PID registry, heartbeats (touch `last_activity_at`), exit codes, cancel via `process.cancel_tracked`.

### Shared conversation history (all channels)

New table `conversation_turns` (`orchestrator/history.py`), keyed by **sender**:

- `web:owner`
- `tg:<id>`
- WhatsApp digits

Inbound turns are appended in channel adapters (webchat / Telegram / WhatsApp webhook).  
Outbound turns are appended in `notify.send_text` for every channel.  
Groq (`llm_chat._chat_history`) reads this shared layer — not web-only memory.

Active project/task context remains in `chat_sessions` (`session.py`) — also sender-keyed and restart-safe.

Isolation and approval gates are unchanged: isolated workspaces, no push/deploy without explicit approve.

---

## Database migration details

Applied automatically on `db.initialize()` via `CREATE TABLE IF NOT EXISTS` / `_ensure_column`:

### `tasks` (new columns)

| Column | Type | Purpose |
|--------|------|---------|
| `execution_stage` | TEXT | Evidence-backed stage |
| `started_at` | INTEGER | Unix start |
| `ended_at` | INTEGER | Unix end |
| `last_activity_at` | INTEGER | Heartbeat / updates |
| `agent_pid` | INTEGER | Last known Cursor PID |
| `exit_code` | INTEGER | Process exit |
| `modified_files` | TEXT | JSON list of paths |
| `blocker` | TEXT | Failure reason |
| `revision` | INTEGER | Task revision |

### New tables

**`task_events`** — append-only execution log (`task_id`, `ts`, `stage`, `event_type`, `message`, `detail_json`)

**`chat_sessions`** — `sender` PK → `active_project`, `active_task_id`

**`conversation_turns`** — shared chat history (`sender`, `ts`, `direction`, `text`, `level`, `channel`)

No destructive migration; existing rows keep working with NULL new columns until next writes.

---

## Automated test results

```text
python -m pytest -q --tb=line
67 passed
```

Critical coverage:

| Test module | Behavior |
|-------------|----------|
| `test_lifeos_conversation.py` | Original LifeOS dialogue: remaining / done / taking so long / changes; no inferred investigating |
| `test_execute_events.py` | Dry-run stage/events |
| `test_history_shared.py` | Sender isolation + Groq history from shared layer (incl. Telegram sender) |
| `test_progress_intents.py` | Follow-up intents + `agent_running` wording |
| Existing handlers / converse / webchat / agent suites | Regression |

---

## Actual Cursor integration test results

**Environment (this host):**

| Check | Result |
|-------|--------|
| `agent --version` | `2026.10.14-941492e` |
| `preflight.agent_available` | True (`agent.cmd`) |
| `agent.auth_status` | ok, mode=`api-key`, email=`info@kingdom-vision.com` |
| `.env` | `DRY_RUN=false`, `CURSOR_API_KEY` set |

**Disposable live smoke (not production LifeOS):**

- Temp local project with `hello.txt`
- Instruction: add `NOTE=ok`
- Elapsed ~23s
- **Status:** `review`
- **Stage:** `ready_for_review`
- **Exit code:** `0`
- **Events:** `workspace_preparing` → `workspace_ready` → `agent_started` → `agent_pid` → `agent_exited` → `ready_for_review`
- **Inferred stages:** `HAS_INVESTIGATING=False`, `HAS_IMPLEMENTING=False`
- Agent summary confirmed file edit

**Not run against production LifeOS checkout in this verification** (avoids dirtying the registered git worktree). Lifecycle + follow-ups were verified via automated LifeOS conversation reproduction + live disposable agent smoke.

---

## Remaining limitations and security concerns

1. **No mid-run Cursor tool stream** — while `agent_running`, detailed file/tool steps are unavailable by design until process exit.
2. **Local project file list** uses mtime-after-start evidence (less precise than `git status`).
3. **Cancel** signals the tracked process; orphaned grandchildren of the agent are not guaranteed.
4. **Groq** is optional; when enabled it may phrase replies but must not invent progress (server still builds status from DB facts).
5. **WhatsApp/Telegram** history is now durable per sender, but there is still no multi-user ACL beyond allowlists.
6. **Agent `--force`** remains powerful — isolation of credentials/OS user is still required for production hardening.
7. **Auto push/deploy** remains gated; never automatic.

---

## Modified files (this remediation pass)

- `orchestrator/history.py` (new)
- `orchestrator/task_events.py`, `execute.py`, `process.py`, `agent.py`, `progress.py`
- `orchestrator/notify.py`, `webchat.py`, `llm_chat.py`, `api.py`, `telegram.py`, `db.py`, `converse.py`
- Tests: `test_lifeos_conversation.py`, `test_history_shared.py`, updated progress/lifeos mocks
- Docs: this file + audit baseline
