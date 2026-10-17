# Implementation Plan

**Phase 1 complete:** codebase audit, test run, Cursor/Meta doc verification (2026-10-10).  
This plan is prioritized by dependency and risk. Do not skip Phase 2 foundations for feature work.

## Phase gate rules

- Each phase ends with: automated tests green, docs updated, remaining limitations listed in `TEST_REPORT.md`.
- No production deploy enablement before Phase 6 acceptance criteria pass.
- Preserve WhatsApp command compatibility unless a phase explicitly versions the protocol.

---

## Phase 1 — Existing Codebase Audit ✅

**Done**

- Read all source files (`app.py`, tests, config samples, README).
- Ran pytest: **3 passed** (see `TEST_REPORT.md`).
- Verified Cursor CLI flags against official docs; CLI **not installed** on audit host.
- Verified Meta webhook HMAC + messaging window / media API behaviors against developer docs.
- Produced architecture, security, setup, integration, and this plan docs.

**Acceptance:** Factual report exists; no unverified “works” claims for live Meta/Cursor.

---

## Phase 2 — Reliable Core Architecture

**Status:** Checkpoint complete (2026-10-10) — package split, SQLite job queue with leases, project schema validation, task state machine, approval `content_digest`, agent `--sandbox`/`--workspace`/`--trust` defaults, output scrubbing, workspace retention cleanup, structured `audit_events` table. Remaining before Phase 3: full process-identity separation for publish vs agent (OS-level), optional lifespan polish.

**Goal:** Maintainable modules + durable jobs + formal state machine + config validation + structured logging.

| Work item | Depends on | Acceptance criteria | Tests |
|-----------|------------|---------------------|-------|
| Split `app.py` into packages; keep behavior | — | Import path `uvicorn orchestrator.api:app` or re-export `app:app`; existing tests adapted | Port existing 3 tests |
| Validate `projects.json` schema (pydantic/jsonschema) | Split | Invalid config fails startup with clear errors | Schema unit tests |
| Formal task state machine + transitions | Split | Illegal transitions rejected; revision/approval fields reserved | State machine unit tests |
| Durable job queue (SQLite-backed initially) | State machine | Restart recovers `queued`; `running` reclaimed after lease expiry | Restart simulation test |
| Structured logging (task_id, status, duration) | Split | No secrets in log format helpers | Logger scrub unit test |
| Agent adapter: `--workspace`, optional `--sandbox`, timeouts | Split | Flags configurable; default remains conservative | Adapter unit tests with mocked subprocess |
| Workspace cleanup policy (retention days) | Durable queue | Configurable; dry-run safe | Cleanup unit test |

**Out of scope for Phase 2:** media, voice, PRs, real deploy verification.

**Checkpoint:** `DRY_RUN` path still creates workspaces; approve still blocked when dry-run.

---

## Phase 3 — Complete WhatsApp Integration

**Goal:** Real Meta credentials path + media + transcription hooks + conversational association + reliable delivery.

| Work item | Depends on | Acceptance criteria | Tests |
|-----------|------------|---------------------|-------|
| Outbound retry / outbox table | Phase 2 queue | Failed Graph calls retry with backoff; honor 24h window errors | Outbox unit + mocked httpx |
| Message status webhooks | Outbox | Persist delivered/failed/read when subscribed | Payload fixture tests |
| Media download (image/audio/document) | Meta token | Authenticated GET media URL; store under task workspace | Mocked media API tests |
| Image → agent context (file path in prompt) | Media | Image tasks create TASK with attachment paths | Integration-style unit |
| Voice transcription (pluggable provider) | Media | Audio → text → same task pipeline; provider key not in WA | Transcription adapter mock |
| Follow-ups bind to active task | State machine | `REPLY <id> …` or single active-task heuristic documented | Conversation unit tests |
| Template messages for closed window | Outbox | Configurable template name; fallback when service window closed | Window-error handling test |

**Manual verification:** sandbox Meta app, Cloudflare Tunnel, allowlisted phone.

---

## Phase 4 — AI Development Lifecycle

**Goal:** Understand → plan → implement → verify → accurate report; revisions.

| Work item | Depends on | Acceptance criteria | Tests |
|-----------|------------|---------------------|-------|
| Project context pack (README, stack, instructions from registry) | Registry schema | Prompt includes registered instructions only | Prompt builder unit |
| Optional plan-first (`--mode plan` or two-step) | Agent adapter | Configurable; plan sent to WA before implement when enabled | Adapter flag test |
| Clarification questions state | Conversational WA | Ambiguous tasks pause in `awaiting_clarification` | State transition test |
| Diff generation (git diff / file diff for local) | Workspace | Review summary includes real file list + patch excerpt | Diff helper unit |
| Test/lint/build commands from registry | Schema | Failures mark task not “success”; status `review` with FAIL evidence | Fake failing test_command |
| REVISE command | Follow-ups | New agent run on same workspace/branch; new review digest | Revision flow test |
| Completion honesty | Diff+tests | Exit 0 alone ≠ success if tests fail or no file changes when changes expected | Policy unit test |

---

## Phase 5 — Git and Local Publishing

**Goal:** Safe GitHub PR path + local apply-back with backups.

| Work item | Depends on | Acceptance criteria | Tests |
|-----------|------------|---------------------|-------|
| Detect remote host (GitHub vs other) | Publish module | Messages say “origin” unless GitHub confirmed | Remote parse unit |
| `APPROVE id PR` via GitHub API | Push | Creates PR from task branch; reports URL/SHA | Mocked gh/API tests |
| Approval digest binding | Phase 2 | Changed tree invalidates prior approval | Digest mismatch test |
| Branch protection compatibility | PR | No force-push; no admin bypass | Doc + negative tests |
| Local `APPROVE id APPLY` | Local workspace | Backup snapshot; conflict detect if source newer; apply copy | Apply/conflict tests |
| Audit trail rows | Logging | Every publish action recorded | Audit query test |

---

## Phase 6 — Controlled Deployment

**Goal:** Environment-scoped auth + verify + rollback policy. **Keep `allow_deploy=false` until done.**

| Work item | Depends on | Acceptance criteria | Tests |
|-----------|------------|---------------------|-------|
| Environments in registry (dev/stage/prod) | Schema | APPROVE requires environment name | Parser + authz tests |
| Pre-deploy checks + backup hook | Env config | Missing backup hook blocks prod | Policy tests |
| Post-deploy health URL/command | Deploy runner | Unhealthy → `deploy_failed` + optional rollback | Health mock tests |
| CI/CD trigger option (GitHub Actions) | GitHub token | Workflow dispatch with task SHA | Mocked Actions API |
| SSH deploy option | Separate credentials | Agent cannot read deploy key | Process env isolation test |

---

## Phase 7 — End-to-End Quality Assurance

Automate and document every scenario listed in the handoff §7 (unauthorized sender, duplicate webhook, agent timeout, restart mid-task, etc.). Expand `TEST_REPORT.md` with pass/fail matrix and manual checklist for Meta/Cursor live runs.

---

## Cross-cutting priorities (all phases)

1. **Security before convenience** — never widen agent privileges to unblock features.
2. **Official APIs only** — Meta Graph, Cursor CLI, GitHub API/`gh`.
3. **Incremental tests** — each PR/checkpoint adds tests for new behavior.
4. **Windows-first docs** — use `python` not only `py` (audit host has no `py` launcher).
5. **Honest messaging** — WhatsApp text must not claim “GitHub” or “deployed healthy” without verification.

## Suggested near-term sequence (after Phase 1)

1. Phase 2 package split + durable queue + schema validation.  
2. Agent adapter with `--sandbox enabled` default for non-dry-run (configurable).  
3. Phase 3 outbox + media stubs.  
4. Phase 4 diffs + revise.  
5. Phase 5 PR + local APPLY.  
6. Phase 6 only with explicit operator sign-off.

## Dependency graph (simplified)

```text
Phase1 ──► Phase2 ──► Phase3 ──► Phase4
              │                      │
              └──────────► Phase5 ◄──┘
                              │
                              ▼
                           Phase6 ──► Phase7
```
