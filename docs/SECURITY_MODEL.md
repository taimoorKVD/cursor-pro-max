# Security Model

**Status:** Historical Phase 1 note. **Current baseline:** [PRODUCTION_READINESS_GAP_ANALYSIS.md](PRODUCTION_READINESS_GAP_ANALYSIS.md) (accepted 2026-10-17).

Do not treat this service as safe for untrusted senders or production deployment. `allow_deploy` stays false.

Corrections to the Phase 1 text below:

- The job queue is SQLite-backed (`orchestrator/queue.py`), not only an in-memory `queue.Queue`. Lease renewal and restart policy are part of the R2 work tracked in the gap analysis.
- `--workspace`, `--trust`, and `--output-format stream-json` are used. `--sandbox enabled` is forced **off on Windows**.
- Approval stores `content_digest`. Publish must fail closed when the digest is missing or no longer matches.
- Prompt instructions are not an isolation boundary.

## Security goals

1. Only allowlisted WhatsApp senders can create or control tasks.
2. Coding agents may change code only inside task workspaces.
3. Push, merge, and deploy require separate human authorization.
4. Secrets never appear in source, WhatsApp replies, or agent-facing env unnecessarily.
5. Webhook payloads are authentic (Meta-signed).

## Controls present today

| Control | Implementation | Assessment |
|---------|----------------|------------|
| Webhook signature | HMAC-SHA256 over **raw** body vs `X-Hub-Signature-256` | Correct Meta pattern; missing secret → 403 |
| Verify token | GET `/webhook` uses `hmac.compare_digest` | Correct |
| Sender allowlist | Normalized digits without `+` | Necessary but coarse (no per-project ACL) |
| Message dedup | SQLite primary key on WhatsApp message id | Mitigates Meta retries |
| Dry run default | `DRY_RUN=true` | Blocks agent + publish |
| Publish gating | Status must be `review`; flags `allow_push` / `allow_deploy` | Good baseline |
| No auto-merge | Push to `wa/<task_id>` only | Aligns with principle |
| Deploy argv source | Admin `projects.json` only; not WhatsApp text | Important |
| Local copy ignores | Skips `.env*` and common dep dirs | Reduces secret copy-in for local type |
| Task ownership | Approve/reject/status require matching `sender` | Basic |

## High residual risks

### R1 — Agent is not sandboxed (Critical)

Invocation: `agent -p --force --output-format text <prompt>`.

Official docs state:

- `-p/--print` has access to write and shell tools.
- `-f/--force` **force-allows commands unless explicitly denied**.
- `--sandbox enabled` exists and is **not used** by this codebase.

Prompt text cannot prevent reading `~/.ssh`, env vars, sibling repos, or calling network APIs. Treat agent host credentials as compromised for the duration of a run.

**Required direction:** `--sandbox enabled` (and/or OS user / container / Windows Job Object limits), separate credentials for publish vs agent, deny network by default for coding jobs.

### R2 — In-memory job queue (High)

Queued/running work is lost on process exit; DB status may remain `queued`/`running` forever. Restart recovery and idempotent claim are absent.

### R3 — Approval not bound to revision (High)

`APPROVE <id> PUSH|DEPLOY` authorizes whatever is currently in the workspace, not the exact tree that was reviewed. Post-review mutation (manual edit, second agent run) still publishes.

### R4 — Secrets exposure paths (High)

- Git worktrees include tracked `.env` files if present in the repo.
- Agent stdout is truncated and sent to WhatsApp — can leak tokens from command output.
- App process holds `META_ACCESS_TOKEN`; same process starts the agent.
- Logs use `log.exception` — may capture sensitive stderr.

### R5 — Dynamic SQL in `update()` (Medium)

Column names are interpolated from kwargs. Callers are internal today; any future untrusted key would be SQL injection. Prefer a fixed column allowlist.

### R6 — Deploy trust model (High for production)

`deploy_command` success = process exit 0. No health probe, backup proof, or rollback. `allow_deploy` must remain false until Module I is real.

### R7 — Empty allowlist / misconfig (Medium)

Empty `ALLOWED_WHATSAPP_NUMBERS` silently drops all messages (returns 200). Operators may believe the webhook “works” while nothing is processed.

### R8 — WhatsApp conversation window (Medium operational)

Free-form replies only work inside Meta’s customer service window. Outside it, Graph rejects non-template sends. No template fallback → silent delivery failure (`log.exception` only).

### R9 — Public surface (Medium)

Service is intended behind a tunnel. Entire FastAPI app is exposed if the tunnel points at the process; only webhook routes should be publicly reachable (reverse-proxy path filter recommended).

### R10 — Windows `shlex.split` for deploy/test (Low–Medium)

POSIX shlex on Windows paths with spaces can mis-parse admin commands.

## Explicit non-goals (do not weaken)

- No unofficial WhatsApp Web / session hijacking.
- No undocumented Cursor Desktop automation.
- No bypass of GitHub branch protection or forced pushes to protected defaults.
- No storing long-lived GitHub PATs in WhatsApp-visible config without encryption at rest (future).

## Credential inventory

| Secret | Where | Who needs it |
|--------|-------|--------------|
| `META_APP_SECRET` | `.env` | Webhook verify only |
| `META_VERIFY_TOKEN` | `.env` | Webhook GET verify |
| `META_ACCESS_TOKEN` | `.env` | Outbound + future media download |
| Cursor auth / `CURSOR_API_KEY` | User/agent env | Agent process only |
| Git push credentials | OS credential helper / SSH agent | **Publish worker only** (should not be in agent env) |
| Deploy SSH / cloud tokens | TBD | **Deploy worker only** |

## Threat scenarios (Phase 1)

| Scenario | Current outcome |
|----------|-----------------|
| Forged webhook without valid HMAC | 403 |
| Non-allowlisted sender | Message ignored (200) |
| Duplicate webhook delivery | Second insert ignored |
| Prompt injection via TASK text | Agent may obey; host risk R1 |
| APPROVE while DRY_RUN | Status stays `review`; message explains |
| Double APPROVE | First sets `publishing`; second rejected (“not awaiting”) — soft race remains |
| Malicious `deploy_command` in projects.json | Runs with app user privileges if enabled |

## Phase 2+ control plan (summary)

1. Durable queue with lease/heartbeat; recover `running` on boot.
2. Content digest at review time; approve must match digest.
3. Separate worker identities for agent vs publish.
4. Enable Cursor `--sandbox` / workspace network deny; scrub outbound reports.
5. Structured audit log (who, task, action, digest, result) without secret bodies.
6. Per-project authorized senders and allowed operations.
7. Approval TTL and single-use tokens for PUSH vs DEPLOY vs PR vs APPLY_LOCAL.
