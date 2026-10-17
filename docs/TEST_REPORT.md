# Test Report & Phase 1 Audit Findings

> **Historical (2026-10-10).** The suite is no longer 3 tests, the queue is not only in-memory, and several “not implemented” rows below were built later. For the current production-readiness baseline and its test evidence, use [PRODUCTION_READINESS_GAP_ANALYSIS.md](PRODUCTION_READINESS_GAP_ANALYSIS.md). Do not operate from the feature matrix in section 5 of this file.

**Date:** 2026-10-10  
**Host:** Windows 10.0.26200, PowerShell  
**Python:** 3.10.6  
**Git:** 2.55.0.windows.5  
**Cursor CLI (`agent`):** not installed / not on PATH  
**Meta live webhook:** not exercised (no credentials configured for this audit)

---

## 1. Automated tests

### Command

```powershell
python -m pip install -r requirements.txt
python -m pytest -q --tb=short
```

### Result

| Test | Result |
|------|--------|
| `test_health` | PASS |
| `test_webhook_signature_and_dedup` | PASS |
| `test_dry_run_approval_cannot_publish` | PASS |

**Phase 1 summary: 3 passed**, 1 Starlette/httpx `TestClient` deprecation warning.

### Phase 2 checkpoint (same day)

```powershell
python -m pytest -q --tb=short
```

**Result: 8 passed** — prior three plus durable queue claim, lease reclaim, project schema rejection, state machine guard, agent argv sandbox flags.

### Phase 2 completion + bootstrap (same day)

- `.env`, `projects.json`, `.venv` created; Cursor CLI installed (`agent` 2026.10.01, **not logged in**).
- Added workspace retention + `audit_events`.
- **pytest: 10 passed**.

### Coverage gaps (not tested today)

- Happy-path TASK enqueue + worker execution
- Git worktree creation / dirty-tree rejection
- Local copytree ignores
- Cursor agent success/failure/timeout
- APPROVE PUSH / DEPLOY when `DRY_RUN=false`
- Unauthorized sender path (silent ignore)
- Non-text message handling
- Publish race / restart recovery
- WhatsApp Graph send failures / retries
- projects.json malformed / missing path

---

## 2. Dependency verification

| Package | Constraint | Installed (audit host) |
|---------|------------|-------------------------|
| fastapi | `>=0.115,<1` | 0.143.0 |
| httpx | `>=0.27,<1` | 0.28.1 |
| python-dotenv | `>=1,<2` | present |
| uvicorn | `>=0.30,<1` | present (via prior install) |
| pytest | `>=8,<10` | present |

**Missing from requirements for future phases:** pydantic (schema), tenacity/backoff (retries), GitHub SDK or explicit `httpx` wrappers, transcription SDK — add only when implementing.

**README mismatch:** docs recommend `py -m venv`; audit host has no `py` launcher. Use `python -m venv` (documented in `SETUP_WINDOWS.md`).

---

## 3. Integration verification (documentation, not live)

### Cursor CLI

Cross-checked against official docs:

- `-p --force --output-format text` is a valid headless pattern for applying changes.
- `--force` also force-allows shell commands unless denied — confirms README risk statement.
- Safer headless pattern available: `--print --trust --sandbox enabled` (not used in code).
- `--workspace`, plan/ask modes, stream-json progress exist and are unused.

**Cannot claim** agent runs succeed on this machine until CLI is installed and authenticated.

### Meta WhatsApp Cloud API

Cross-checked:

- Webhook verify + HMAC raw-body pattern matches Meta guidance.
- Outbound messages API shape is correct for Cloud API.
- 24-hour customer service window / templates: **unhandled** operational risk.
- Media download API exists; **not implemented**.
- Graph version pin `v23.0` is explicit; newer docs may show later versions — upgrade deliberately.

---

## 4. Defects & insecure assumptions (prioritized)

### Critical

1. **No OS/CLI sandbox for agent** while using `--force` — prompt is not isolation.
2. **Approval not bound to content digest** — review report can diverge from published tree.

### High

3. **In-memory `queue.Queue`** — tasks lost on restart; statuses can stick at `queued`/`running`/`publishing`.
4. **Agent/publish share process identity** — deploy/git credentials potentially visible to agent environment.
5. **WhatsApp reports include raw agent stdout** — secret leakage channel.
6. **Deploy = exit code** — insufficient for production claims.
7. **Local projects never apply back** — featured limitation; easy to misunderstand as “done on disk.”

### Medium

8. **`update()` builds SQL from kwargs keys** — unsafe pattern if ever fed external keys.
9. **Non-text inbound messages silently dropped** — no user feedback.
10. **Empty allowlist** processes nothing but returns 200.
11. **Push success message says “GitHub”** without validating remote host.
12. **Single worker thread** — no concurrency control design beyond “one at a time.”
13. **Module import starts worker thread** — test reloads can spawn extra daemons.
14. **Windows `shlex.split`** for test/deploy commands can mis-parse paths.
15. **No webhook path restriction** guidance enforced in code — tunnel may expose `/docs` etc.

### Low

16. Truncation of summaries may hide failures.
17. No retention/cleanup for workspaces.
18. No rate limiting on TASK creation.
19. TestClient deprecation warning (httpx2).

---

## 5. Feature matrix vs required modules

| Module | Requirement theme | Implemented? |
|--------|-------------------|--------------|
| A WhatsApp | Text in/out | Partial |
| A | Voice / image / attachments | No |
| A | Retries / delivery tracking / templates | No |
| B Registry | Rich project metadata / envs / ACLs | Minimal JSON only |
| C Understanding | Clarification / plan | No |
| D Cursor agent | CLI invoke | Yes (unverified live) |
| D | Isolation / cancel / retry | Partial timeout only |
| E Verification | Real diffs / honest success | Weak (`git status --short` / generic local text) |
| F Human review | Approve/reject | Partial (no revise, no digest) |
| G GitHub | PR / API | No (branch push only) |
| H Local | Apply + backup | Snapshot only |
| I Deploy | Health / rollback | No |
| J Reliability | Durable queue / audit / ACL | No |

---

## 6. What works today (factual)

- FastAPI health endpoint.
- Meta-compatible webhook verification and signature rejection.
- Dedup of identical webhook message ids.
- Allowlisted text command handling for the documented verbs.
- SQLite persistence of task rows and message ids.
- Workspace preparation for git (worktree) and local (copy) when paths are valid.
- Dry-run blocks agent and publish (automated test).
- Explicit approval required before push/deploy code paths run.

---

## 7. Phase 1 conclusion

The repository is a **credible local-first starter**, not a production unattended automation platform. Automated unit tests pass for the narrow surface they cover. Cursor CLI and live Meta messaging were **not** validated on the audit host. Highest-priority engineering work is Phase 2 (durable queue, modularization, config validation, sandbox defaults) before expanding WhatsApp media or deployment features.

**Next checkpoint:** Phase 2 implementation per `IMPLEMENTATION_PLAN.md`.

---

## 8. Manual verification checklist (pending operator)

- [ ] Install + `agent login`; `agent -p --force "…"` in a toy repo
- [ ] Configure Meta sandbox; GET verify succeeds
- [ ] Send PROJECTS from allowlisted number
- [ ] TASK with DRY_RUN=true creates workspace; no source mutation
- [ ] Unauthorized number ignored
- [ ] Duplicate webhook does not double-create tasks
- [ ] APPROVE under DRY_RUN refused
- [ ] (Later) DRY_RUN=false agent run + review report quality
- [ ] (Later) PUSH creates remote branch only
- [ ] (Later) Restart mid-queue recovery (after Phase 2)
