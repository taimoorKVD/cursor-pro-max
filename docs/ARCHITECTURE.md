# Architecture

**Status:** Historical Phase 2 sketch. **Current behavior and gaps:** [PRODUCTION_READINESS_GAP_ANALYSIS.md](PRODUCTION_READINESS_GAP_ANALYSIS.md).

**Entrypoint:** `app.py` re-exports `orchestrator.api:app` for `uvicorn app:app`.

The diagram and tables below are not fully current. In particular: jobs are stored in SQLite; the agent argv includes `--workspace`, `--trust`, and `stream-json`; WhatsApp, Telegram, and `/chat` share `handlers.handle`; publish can push, open a GitHub PR via `gh`, or merge a git worktree locally. Production deploy health and rollback are not implemented. Keep `allow_deploy=false`.

## Purpose

Local-first orchestrator that accepts WhatsApp Cloud API webhooks, maps text commands to registered projects, runs Cursor Agent CLI in an isolated workspace, reports results for human review, and performs push/deploy only after an explicit second authorization.

## Current topology

```text
WhatsApp user
    │  HTTPS (Meta → public tunnel → localhost)
    ▼
FastAPI (orchestrator/api.py)
    ├── GET  /health
    ├── GET  /webhook   (Meta subscription verify)
    └── POST /webhook   (HMAC verify → dedupe → handle)
            │
            ├── SQLite (tasks, incoming, jobs)
            ├── Durable job queue + lease reclaim + worker thread
            ├── projects.json registry (validated)
            ├── Cursor CLI (agent -p --force --trust --workspace [--sandbox])
            ├── Git worktree / shutil.copytree workspaces + content_digest
            └── Meta Graph API outbound text (httpx)
```

## Package layout

```text
orchestrator/
  api.py          # routes + lifespan
  handlers.py     # WhatsApp commands
  queue.py        # durable jobs
  worker.py       # claim/execute loop
  execute.py      # agent + tests + review
  publish.py      # push/deploy + digest check
  agent.py        # CLI argv adapter
  workspace.py    # isolation + digests
  projects.py     # registry validation
  state.py        # task transitions
  tasks.py / db.py / config.py / whatsapp.py / scrub.py
app.py            # compatibility entrypoint
```

## Components (as implemented)

| Component | Location | Role | Maturity |
|-----------|----------|------|----------|
| HTTP API | `app.py` FastAPI routes | Health + webhook | Working (unit-tested) |
| AuthZ (sender) | `ALLOWED_WHATSAPP_NUMBERS` | Allowlist only | Minimal |
| Webhook crypto | HMAC-SHA256 `X-Hub-Signature-256` | Reject unsigned bodies | Correct pattern |
| Dedup | `incoming` table | `INSERT OR IGNORE` on message id | Working |
| Command parser | `handle()` regex | PROJECTS / TASK / STATUS / APPROVE / REJECT | Text-only |
| Task store | SQLite `tasks` | Status + summary blobs | Durable rows; queue not durable |
| Worker | daemon thread + `queue.Queue` | Serial task execution | Lost on restart |
| Workspace | `workspace_setup()` | Git worktree or local copy | Functional |
| Agent | `execute_task()` | `AGENT_BIN -p --force --output-format text` | Untested on this host (CLI absent) |
| Publish | `publish()` | Git commit+push or deploy_command | Gated by DRY_RUN + flags |
| Outbound WA | `send()` | Graph `/{phone-number-id}/messages` | Fire-and-forget |

## Data model

### `tasks`

| Column | Notes |
|--------|--------|
| `id` | 12-char hex UUID slice |
| `sender` | WhatsApp id (digits, no `+`) |
| `project` | Key in `projects.json` |
| `instruction` | Raw task text |
| `status` | See state machine |
| `workspace` | Absolute path under `WORK_ROOT` |
| `branch` | `wa/<task_id>` for git; empty for local |
| `summary` | Truncated report / error |
| `created_at` / `updated_at` | Unix seconds |

### `incoming`

| Column | Notes |
|--------|--------|
| `message_id` | WhatsApp message id (primary key) |

### Project registry (`projects.json`)

Minimal schema today: `path`, `type` (`git`|`local`), `test_command`, `allow_push`, `allow_deploy`, `deploy_command`.  
No validation, environments, ACLs, stack metadata, or instructions fields yet.

## Task state machine (de facto)

```text
queued → running → review → publishing → published
                 ↘ failed              ↘ publish_failed
                         review → rejected
```

Gaps vs Module F/J requirements:

- No `planning` / `clarifying` / `revising` states
- Approval is not bound to a content hash / revision id
- Restart leaves `queued`/`running`/`publishing` orphaned (queue is memory-only)
- No cancellation or timeout states

## Isolation model (current)

1. **Git projects:** `git worktree add -b wa/<id>`; requires clean source tree.
2. **Local projects:** `copytree` with ignores for `.git`, `node_modules`, `.venv`, `vendor`, `.env*`, `data`.
3. **Agent:** subprocess cwd = workspace; prompt asks not to leave workspace — **not enforceable**.
4. **CLI flags:** `-p --force` (documented: apply writes; force-allow shell unless denied). **`--sandbox` is not used.**

## Trust boundaries

| Boundary | Enforcement today |
|----------|-------------------|
| Internet → webhook | HMAC + allowlist |
| WhatsApp text → shell | Commands are fixed verbs; deploy argv comes only from admin `projects.json` |
| Agent → host FS/network | Prompt only; shares process user credentials |
| Review → publish | Explicit APPROVE + DRY_RUN + project flags |
| Push → merge/main | Not performed (branch push only) |
| Deploy → health | Exit code only |

## Intentionally out of current architecture

- n8n or other external workflow engines
- Unofficial WhatsApp Web automation
- Controlling Cursor Desktop UI
- Automatic merge to default branch
- Applying local-project diffs back to the source tree

## Target modular layout (Phase 2+)

Preserve behavior; split `app.py` into packages without changing the WhatsApp command surface until Phase 3:

```text
orchestrator/
  api/           # FastAPI routes
  whatsapp/      # verify, send, media, templates
  registry/      # projects schema + load/validate
  tasks/         # state machine + repository
  queue/         # durable jobs + workers
  agent/         # Cursor CLI adapter + sandbox options
  workspace/     # git worktree + local snapshot
  publish/       # push, PR, local apply, deploy
  audit/         # structured logs
```

## References verified

- Cursor CLI: https://cursor.com/docs/cli/overview , https://cursor.com/docs/cli/headless , https://cursor.com/docs/cli/reference/parameters
- Meta webhooks / messages: https://developers.facebook.com/docs/whatsapp/cloud-api/guides/set-up-webhooks/ , https://developers.facebook.com/docs/whatsapp/cloud-api/guides/send-messages
