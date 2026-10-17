# Production Readiness Gap Analysis

**Date:** 2026-10-17  
**Scope:** Cursor Orchestrator in this repository (`orchestrator/`, `tests/`, `docs/`, `scripts/`).  
**Method:** Static reading of current modules and tests, plus one local unit-test run. No production configuration was changed, no deployment was executed, and no GitHub publish or pull request was created.

## Evidence baseline

| Source | How it was used |
|--------|-----------------|
| Current package `orchestrator/` | Primary evidence. A function existing is not treated as production-ready. |
| `tests/*.py` excluding `tests/browser` | Automated coverage. Fresh run on 2026-10-17: **exit code 0**, pytest progress **72 + 15 = 87** tests, one Starlette/`httpx` `TestClient` deprecation warning. Browser suite was not run. |
| `docs/CONVERSATIONAL_AGENT_VERIFICATION.md` (2026-10-16) | Last recorded live Cursor smoke: disposable local project, status `review`, stage `ready_for_review`, events were process lifecycle only (`workspace_*`, `agent_started`, `agent_pid`, `agent_exited`). That smoke did **not** show tool-level stream events. |
| `docs/SECURITY_MODEL.md`, `docs/ARCHITECTURE.md`, `docs/TEST_REPORT.md`, `docs/CURSOR_AGENT_INTEGRATION.md`, `docs/DEPLOYMENT_RUNBOOK.md`, `README.md` | Historical. Several still describe an in-memory queue, unused `--sandbox` / `--workspace`, and “no job recovery.” Those statements are **stale** relative to the code audited here. This report does not inherit their “done” or “not done” labels without re-checking code. |

**Verdict:** usable as a **single-operator, local-first review tool** with dry-run and approval gates. **Not production-ready** for untrusted users, unattended GitHub publishing, or staging/production deployment. Highest gaps are process isolation on Windows, queue restart semantics, approval binding, and the absence of deploy health/rollback, backups, quotas, and CI.

## Status legend

| Status | Meaning in this report |
|--------|------------------------|
| **IMPLEMENTED** | Behavior is in code and covered by an automated test that exercises the claim. Live/production proof is noted separately when it was not repeated. |
| **PARTIAL** | A real control or path exists, but a required safety, recovery, or evidence property is missing or untested. |
| **MISSING** | No implementation that meets the requirement. |
| **BLOCKED** | The control cannot be made effective on the current platform even though related code exists. |

---

## 1. Agent sandboxing and credential isolation

**Area status: PARTIAL.** Workspace copies are real. Host isolation is not.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Isolated git worktree (`wa/<task_id>`) and local `copytree` | **IMPLEMENTED** | `workspace.setup` refuses a dirty git source, deletes a stale workspace under `WORK_ROOT`, ignores `.git`, `node_modules`, `.venv`, `.env`, `.env.*`, `data` on local copies. Tests: `tests/test_workspace_cleanup.py`. |
| Refuse deleting paths outside `WORK_ROOT` | **IMPLEMENTED** | `workspace.remove` / `_under_work_root`. No dedicated negative test found. |
| Strip orchestrator and cloud secrets from the agent environment | **IMPLEMENTED** (narrow) | `agent._agent_env` drops `META_`, `SMTP_`, `WEBCHAT_`, `TELEGRAM_`, `GROQ_`, `GITHUB_TOKEN`, `GH_TOKEN`, and similar prefixes, and sets `__ORCH_MERGE__=0` so `process.run` does not re-merge `os.environ`. Test: `test_agent_env_strips_orchestrator_secrets`. |
| Cursor CLI sandbox | **BLOCKED** on this Windows host | `config.py` defaults `AGENT_SANDBOX` to `disabled` when `os.name == "nt"`. `agent._effective_sandbox` **forces** `disabled` if the operator sets `enabled` on Windows. `.env.example` sets `AGENT_SANDBOX=disabled`. Test `test_agent_argv_includes_sandbox` asserts Windows gets `disabled`. Cursor’s `--sandbox` is macOS/Linux-only in this codebase’s own comment. |
| Filesystem / network / credential boundary around `--force` | **MISSING** | `build_argv` always passes `-p --force --trust`. Prompt text in `build_prompt` says not to read credentials or push; that is not enforced. The agent process still runs as the orchestrator OS user, so SSH agent, Git credential helper, and profile files remain reachable. No Windows Job Object, restricted token, container, or separate publish user exists. |
| Cursor API key handling | **PARTIAL** | Key is passed as both `CURSOR_API_KEY` and `--api-key` on the argv (`agent.build_argv`). Argv is visible to local process observers. `auth_status` returns `ok` whenever the key is non-empty, without calling Cursor (`test_auth_status_uses_api_key`). |
| Separate credentials for agent vs git push vs deploy | **MISSING** | `publish._push_branch`, `gh pr create`, and `deploy_command` use `process.run` with the default environment (full `os.environ`). The same user that runs the agent can push and deploy. |

**Residual risk:** on this host, a prompt-injected agent with `--force` and sandbox disabled can use the operator’s credentials. Do not treat worktree isolation as a security sandbox.

---

## 2. Task queue reliability, concurrency, cancellation, and restart recovery

**Area status: PARTIAL.** Jobs are durable. Recovery can re-run or skip work incorrectly, and concurrency is one thread inside one process.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Durable SQLite jobs with claim | **IMPLEMENTED** | `queue.enqueue` / `claim_next` insert and claim `pending` rows. Test: `test_durable_queue_enqueue_and_claim`. |
| Lease reclaim | **IMPLEMENTED** (mechanism only) | `reclaim_expired_leases` returns expired `running` jobs to `pending` and increments attempts on the next claim. Test: `test_lease_reclaim`. |
| Lease renewal while a job is actually running | **MISSING** | Heartbeats call `tasks.touch` (`execute._on_heartbeat`) and do **not** extend `jobs.leased_until`. Defaults: `AGENT_TIMEOUT_SEC=1200`, `JOB_LEASE_SEC=1800`. A run longer than the lease, or a crash, leaves a `running` job that another claim will execute again. |
| Single in-process worker | **IMPLEMENTED** as a limit, not a concurrency design | `worker.start_worker` starts one daemon thread. `DB_LOCK` is an in-process `RLock`. A second OS process (second uvicorn worker) would not share that lock. There is no per-project mutex or fair multi-tenant scheduler. |
| Cancellation | **PARTIAL** | `handlers` `cancel_task` calls `process.cancel_tracked` (`taskkill /T /F` on Windows) and sets status `failed` / stage `canceled`. `execute_task` polls `_cancelled`. Publish uses `process.run`, which is **not** tracked, so cancel during push/deploy does not signal that process. `test_kill_process_tree_noop_safe` only checks pid 0/None. No test kills a live agent. Grandchild processes outside the tree are not guaranteed (called out in the 2026-10-16 verification). |
| Restart recovery | **PARTIAL** | `api._requeue_orphaned_tasks` on startup: if status is `running` **and** a workspace path is set **and** no open execute job exists, it raw-SQL marks the task `failed`. If no workspace yet, it re-queues. If a job row is still `running`, it does nothing until the lease expires, then `claim_next` runs `execute_task` again. `workspace.setup` **deletes** an existing workspace and starts over. Tasks stuck in `publishing` are not recovered. The raw SQL update bypasses `state.assert_transition`. **No test covers `_requeue_orphaned_tasks`.** |
| Idempotent execution | **MISSING** | Reclaim and re-queue both call `execute_task` again. There is no job token, fencing token, or “already reached review” guard inside `execute_task` before it sets `running`. |
| Retry with backoff | **MISSING** | `queue.fail(..., retry=False)` is what the worker uses. The only automatic re-entry is lease reclaim, which is a full re-execution, not a bounded retry. |

---

## 3. Multi-user authentication, authorization, and project isolation

**Area status: PARTIAL.** One operator per channel allowlist. Project “isolation” is conversation scoping, not authorization.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| WhatsApp sender allowlist | **IMPLEMENTED** | `api.webhook` ignores senders not in `ALLOWED_WHATSAPP_NUMBERS`. Empty allowlist drops everyone and still returns 200. Test: `test_webhook_signature_and_dedup` (allowlisted path). No automated test asserts the unauthorized sender is ignored. |
| Telegram allowlist | **IMPLEMENTED** | `telegram._allowed` denies when the set is empty. Non-members get one “Unauthorized” reply. Test: `test_allowed_telegram_ids`, `test_handle_update_allowlisted`. |
| Web chat password session | **IMPLEMENTED** for a single operator | `webchat`: password minimum 12 chars or the UI is disabled; SHA-256 compare; HMAC cookie; `httponly`, `samesite=strict`, `secure` when HTTPS; 5 failures / 15 minutes lockout **in memory** (cleared on process restart). Sender is the constant `web:owner`. Tests: `test_disabled_without_strong_password`, `test_requires_login`, `test_wrong_password_locks_out`. |
| Task ownership on approve / reject / cancel | **IMPLEMENTED** | `_resolve_task` requires `task["sender"] == sender` (explicit id, session, or that sender’s active task). |
| Per-user accounts, roles, session revocation | **MISSING** | One shared web password. Cookie is `issued.hmac(password)`; any copy works until expiry. No user table, no logout-all, no role. |
| Per-project authorization | **MISSING** | `projects.json` has no ACL. Any allowlisted sender can name any registered project. `load_projects(..., strict=False)` **drops invalid projects and keeps the rest** at runtime (`projects()`), so a bad entry can disappear without failing startup. |
| Chat/project thread isolation | **IMPLEMENTED** (privacy of history, not authz) | `conversation_turns` and `web_messages` are filtered by sender and active project. Tests: `test_history_isolated_by_sender`, `test_project_chat_isolation.py`, `test_history_and_llm_context_scoped_after_switch`. |
| Approval expiration / single-use publish token | **MISSING** | The status change `review` → `publishing` is the only single-use gate. Two overlapping requests can both observe `review` before either update. No TTL. |

---

## 4. Cursor CLI structured event streaming and activity monitoring

**Area status: PARTIAL.** The parser and event log are real and unit-tested with synthetic NDJSON. A live tool stream was not demonstrated in the last verification, and this audit did not start an agent.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| `stream-json` invocation | **IMPLEMENTED** in argv | Default `AGENT_OUTPUT_FORMAT=stream-json` (`config.py`, `.env.example`). `build_argv` passes `--output-format`. `run_agent` attaches `agent_stream.make_line_handler` only for that format. Also passes `--workspace` and `--trust`. |
| Parse Cursor tool events into stages | **IMPLEMENTED** for fixtures | `agent_stream.parse_line` / `stage_from_evidence`: reads → `investigating`, writes → `implementing`, otherwise stay opaque. Tests in `test_hardening.py` cover read/write/edit shapes, silent `completed` events, and “no stage without tool evidence.” |
| Persist activity | **IMPLEMENTED** | `execute._on_stream_event` writes `task_events` (capped: first 60, plus writes, paths, assistant lines, result). PID and 15s heartbeats update `agent_pid` and `last_activity_at`. Dry-run stages: `test_execute_events.py`. |
| Honest “no detail yet” label | **IMPLEMENTED** | Until a tool event arrives, stage stays `agent_running` and the label is `AGENT_UNAVAILABLE_DETAIL` (`task_events.py`). Chat progress is built from DB facts (`progress.py`). Tests: `test_progress_intents.py`, `test_lifeos_conversation.py`. |
| Live stream from the installed CLI | **Not proven** | 2026-10-16 smoke recorded process lifecycle events only, and explicitly reported no investigating/implementing inference. This audit did not repeat a live agent run. |
| Operator activity API | **PARTIAL** | `GET /chat/task-progress` exists behind the web session (`webchat.task_progress`). No external monitoring system consumes it. |
| Resume / multi-turn agent session | **MISSING** | No stored Cursor chat id. `continue_work` starts a **new** task (`handlers` retry path), it does not `agent --resume`. |

---

## 5. GitHub push, PR, and approval integrity

**Area status: PARTIAL.** Branch push and `gh pr create` exist and are partly tested. Approval is not a complete integrity control.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Push only an orchestrator branch, no force-push, no merge to default | **IMPLEMENTED** | `publish._push_branch`: `git push origin HEAD:refs/heads/<branch>` with no `--force`. No merge-to-default function. Remote host is labeled `GitHub` only when `origin` contains `github.com`. |
| Pull request via GitHub CLI | **IMPLEMENTED** (mocked) | `_create_pull_request` runs `gh pr create` with base `default_branch`, head `wa/<id>`, and a body from the task. Tests: `test_publish_pr.py` (URL parsed, `gh` argv asserted, `publish(..., "PR")` with `apply_local: False`). Requires `gh` auth on the same OS user. Not exercised against GitHub in this audit. |
| Content digest at review | **PARTIAL** | `execute_task` stores `workspace.content_digest` (git diff + porcelain, or local file hashes). `publish` compares it **only when non-empty**. `test_publish_pr_action` sets `content_digest: ""`, so the mismatch path is skipped. **No test asserts mismatch rejection.** |
| Digest meaning after commit | **PARTIAL** | Publish commits first, then **overwrites** `content_digest` with the post-commit digest (`publish` lines that call `content_digest` again). The value the human approved is replaced. A later PR retry would see a different digest. |
| Approve is per sender and blocked in dry-run | **IMPLEMENTED** | `handlers` approve path and `test_dry_run_approval_cannot_publish`. |
| PR retry after `published` | **PARTIAL / broken** | Handler treats `published` + action `PR` as retryable, then `update_task(..., status="publishing")`. `state.ALLOWED_TRANSITIONS["published"]` is empty, so `assert_transition` raises. `publish_failed` → `publishing` is allowed. No test covers this retry. |
| PUSH / PR side effects | **PARTIAL** | `PR` pushes then opens a PR, and also applies locally when `apply_local` is true (the git default). `PUSH` with `allow_push` false still applies locally. Failure of one side can be a warning while status becomes `published` (`publish` error aggregation). |
| Branch protection, required reviews, CI status | **MISSING** inside the orchestrator | Safety depends entirely on GitHub settings. The app never queries protection rules or check runs. |
| Commit identity | **PARTIAL** | Commits use `user.name=WhatsApp Cursor Agent` and `user.email=automation@localhost` for that command only. |

---

## 6. Local-only project changes and safe application

**Area status: PARTIAL.** Changes stay in a copy until an explicit git apply. Apply is not safe in the sense of backup and rollback.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Do not edit the operator checkout during execution | **IMPLEMENTED** | Git: worktree. Local: `copytree` into `WORK_ROOT/<task_id>`. Review copy says the project folder is unchanged until approval (`execute.py`). |
| Local (`type=local`) apply-back | **MISSING** by schema | `projects._validate_one` rejects `allow_push` and `apply_local` for `local`. Handler tells the user to inspect the workspace manually. Test: `test_project_schema_rejects_local_push`. |
| Apply a git task branch onto the local checkout | **IMPLEMENTED** (happy path) | `apply_to_local` refuses a dirty source tree, then `git merge --ff-only`, and on failure `git merge --no-edit`. Test: `test_apply_to_local_fast_forwards` (same repo, fast-forward). |
| Backup before apply | **MISSING** | No snapshot of the destination checkout before merge. |
| Conflict safety | **PARTIAL** | Dirty tree is rejected (untested). A conflicted `git merge` returns non-zero and the function raises, but a failed merge can leave the destination in a merging state. No automatic `merge --abort` and no test for that case. |
| Change evidence for review | **IMPLEMENTED** | Git: `git status --short`. Local: SHA-256 snapshot diff (`file_snapshot` / `diff_snapshots`). Test: `test_local_snapshot_diff_detects_content_change`. |

---

## 7. Staging / production deployment, health verification, and rollback

**Area status: MISSING** as a deployment system. A gated shell command exists and must stay off.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Environment model (dev / staging / prod) | **MISSING** | `projects._validate_one` has no environment, health URL, backup hook, or rollback command. |
| Deploy execution | **PARTIAL** and unsafe if enabled | `allow_deploy` requires a non-empty `deploy_command`. `publish` runs `shlex.split(deploy_command)` with cwd = workspace, timeout 600s, success = exit code 0. The user-facing text says to verify the service independently. Windows `shlex` can mis-parse paths. |
| Post-deploy health check | **MISSING** | `GET /health` returns `{"status":"ok"}` for **this** process only (`test_health`). It does not probe the deployed application. |
| Backup proof before prod | **MISSING** | No hook. |
| Rollback | **MISSING** | `docs/DEPLOYMENT_RUNBOOK.md` still says manual only. No code path rolls back. |
| Keep deploy disabled | **IMPLEMENTED** as policy | Default flags are false unless `projects.json` sets them. Dry-run blocks approve. This audit did not read or modify the live `projects.json` beyond confirming it is gitignored. |

Do not set `allow_deploy=true` on the basis of the current runner.

---

## 8. WhatsApp, Telegram, and web chat integration

**Area status: PARTIAL.** All three can drive the same `handlers.handle` for text. Delivery guarantees and public-surface hardening are not production-grade.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| WhatsApp webhook verify + HMAC on raw body | **IMPLEMENTED** | `api.verify`, `api.webhook`. Missing secret or bad signature → 403. Test: `test_webhook_signature_and_dedup`. |
| WhatsApp text in/out + dedup | **IMPLEMENTED** | Non-text messages are skipped with no reply. Outbound is one `httpx` POST, log on failure, no outbox. `whatsapp.send_text`. |
| WhatsApp templates, delivery receipts, 24h window | **MISSING** | No template payload. Status webhooks are not stored. Graph errors are only logged. |
| Meta callback URL sync | **PARTIAL** | `orchestrator/meta_webhook_sync.py` + `scripts/sync-meta-webhook.ps1`. Tests cover URL normalization and “requires ids,” not a live Graph call. |
| Telegram long polling + text | **IMPLEMENTED** | `telegram.py` getUpdates loop, allowlist, `seen_message` on `update_id`. Tests: `test_telegram_notify.py`. Offset is **in memory**; a restart can re-fetch updates (dedup mitigates double tasks). No webhook mode, no media. |
| Web chat UI + commands | **IMPLEMENTED** | Password gate, project switch, polling, shared history. Tests: `test_webchat.py`, `test_project_chat_isolation.py`. |
| Channel routing | **IMPLEMENTED** | `notify.send_text`: `web:` → SQLite, `tg:` → Telegram, otherwise WhatsApp. Test: `test_notify_routes_telegram`. |
| Public exposure | **PARTIAL** | App is a single FastAPI process. Docs, health, chat, and webhook share it. Tunnel scripts expose the process; nothing in code restricts the public path to `/webhook`. FastAPI’s default `/docs` is not disabled. |
| Reply bodies in logs | **PARTIAL** | `REPLY_LOG_ENABLED` defaults true and logs the first 500 characters of every reply (`notify.send_text`). |

`.env.example` notes Telegram as the practical channel while WhatsApp Cloud API billing is unavailable. That is an operator constraint, not a code defect. Text WhatsApp code is still present and unit-tested with a fake signature.

---

## 9. Voice messages, screenshots, attachments, and revisions

**Area status: MISSING** for WhatsApp/Telegram media and for in-place revisions. Web voice transcription is a narrow exception.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Web microphone → text | **PARTIAL** | `POST /chat/voice` requires the web session, Groq voice enabled, and ≤ 8 MB audio. `llm_chat.transcribe` posts to Groq Whisper. Test `test_voice_requires_auth_and_groq` checks the gate, not a successful transcription. Transcript is then ordinary chat text; it is not attached to a workspace. |
| WhatsApp voice / image / document | **MISSING** | `api.webhook` continues when `type != "text"`. No media download. |
| Telegram voice / photo / document | **MISSING** | `_handle_update` returns when `message.text` is absent. |
| Screenshots as agent context | **MISSING** | No image upload route, no image path injected by `build_prompt`. |
| Task revision on the same workspace | **MISSING** | Column `tasks.revision` is inserted as `1` and never incremented. “Continue working” creates a new task id (`converse` kind `continue_work` → `_start_task`). There is no `REVISE` that reuses the worktree and recomputes a digest. |

---

## 10. Security logging, monitoring, alerting, and backups

**Area status: PARTIAL** for an audit table. **MISSING** for operations.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Structured audit rows | **IMPLEMENTED** | `audit_events` (`ts`, `actor`, `task_id`, `action`, `detail` JSON truncated to 2000, `ok`). Test: `test_audit_record`. Written on execute, approve, publish, cancel, web voice. |
| Secret scrubbing of review text | **PARTIAL** | `scrub.scrub` redacts some key assignments, `AKIA…`, PEM blocks, and JWTs before the review summary. **No unit test.** Audit `detail` and reply logs are not passed through `scrub`. Exceptions can still land in `log.exception`. |
| Metrics, dashboards, alerting | **MISSING** | No Prometheus, health beyond `{"status":"ok"}`, or pager. Tunnel URL email (`scripts/notify-tunnel-url.ps1`, SMTP settings in `.env.example`) notifies an operator that a quick-tunnel hostname changed. That is not failure alerting. |
| SQLite and workspace backups | **MISSING** | Database is `data/orchestrator.sqlite` with WAL. Nothing copies it off the laptop. `retention.cleanup_workspaces` **deletes** old workspaces (`test_workspace_retention_cleanup`); it is not a backup. |
| Log retention / tamper evidence | **MISSING** | `logging.basicConfig(level=INFO)` only. Audit rows live in the same SQLite file as tasks. |

---

## 11. CI/CD, configuration management, and operational documentation

**Area status: PARTIAL.** Local setup docs and schema checks exist. This repository has no CI pipeline, and several operator docs contradict the code.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Dependency pin file | **PARTIAL** | `requirements.txt` uses ranges, not a lockfile. Includes pytest and Playwright. |
| Project registry validation | **IMPLEMENTED** when `strict=True` | `projects._validate_one`. Runtime `projects()` uses `strict=False` and can silently skip bad entries if at least one project validates. Test: `test_project_schema_rejects_local_push`. |
| Environment template | **IMPLEMENTED** | `.env.example` matches current settings (sandbox, stream-json, Groq, Telegram, web password, lease). `.env` and `projects.json` are gitignored. |
| CI for this repo | **MISSING** | No `.github/workflows` at the repository root. Workflows under `data/workspaces/` belong to a **task workspace copy of another product**, not this orchestrator. |
| Autostart / tunnel scripts | **PARTIAL** | `scripts/start-orchestrator.ps1`, `install-autostart.ps1`, Cloudflare tunnel scripts. They are operator conveniences, not a reviewed deploy pipeline. This audit did not execute them. |
| Operational docs accuracy | **PARTIAL** | `docs/SETUP_WINDOWS.md`, `docs/WEBCHAT.md`, `docs/TELEGRAM_INTEGRATION.md`, `docs/WHATSAPP_INTEGRATION.md` are closer to the code. `docs/ARCHITECTURE.md`, `docs/SECURITY_MODEL.md`, `docs/TEST_REPORT.md`, `docs/CURSOR_AGENT_INTEGRATION.md`, `docs/DEPLOYMENT_RUNBOOK.md`, and the limitations list in `README.md` still describe Phase 1/2 gaps that the code has since changed (durable queue, digest field, `--workspace`, stream-json, PR, web voice, restart helper). An operator following those files will misjudge both risk and capability. |
| State machine | **IMPLEMENTED** | `state.py` illegal transitions raise. Test: `test_state_machine_rejects_illegal_transition`. Startup recovery bypasses it with raw SQL (see §2). |

---

## 12. API usage, rate limits, execution quotas, and cost controls

**Area status: MISSING** for cost and abuse control. A few hard caps exist.

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Agent runtime cap | **IMPLEMENTED** | `AGENT_TIMEOUT_SEC` (default 1200) in `run_tracked`; timeout kills the process tree and marks the task failed/timeout. Not covered by a test that expires a real process. |
| Test command cap | **PARTIAL** | 300s timeout in `execute_task`. No quota on how many tasks run tests. |
| Web input caps | **IMPLEMENTED** | Chat text 4000 chars, voice 8 MB. |
| Web login lockout | **PARTIAL** | In-memory, per process, IP from `cf-connecting-ip` or the socket. Not shared across restarts. |
| Per-sender task / job quota | **MISSING** | Any allowlisted sender can enqueue without a daily or concurrent cap. The single worker serializes execution but does not limit queue depth. |
| Cursor spend cap | **MISSING** | No max tokens, no max runs per day, no stop when `CURSOR_API_KEY` usage is high. Timeout is the only brake. |
| Groq spend cap | **MISSING** | Classifier and Whisper run whenever keys and flags are on. No budget counter. |
| Meta / Telegram rate-limit handling | **MISSING** | Single attempt, no `Retry-After`, no outbox. |
| Stream event volume | **PARTIAL** | At most ~60 general stream rows plus selected extras per task. This limits SQLite growth, not API cost. |

---

## What is safe to rely on today

These are the controls the current tests actually lock in:

- Webhook HMAC rejection and message-id dedup.
- Dry-run blocks publishing.
- SQLite job claim and lease reclaim **as database operations**.
- Project schema rejects `allow_push` on `local` projects.
- Illegal task status transitions raised by `update_task`.
- Agent argv includes `--workspace`, `--trust`, and a sandbox flag that is **disabled on Windows**.
- Agent env strips the tested secret prefixes.
- Synthetic stream-json lines advance investigating/implementing only with tool evidence.
- Sender- and project-scoped chat history.
- Web chat refuses a short password and locks out repeated bad passwords in-process.
- GitHub PR creation **against a fake `gh`**.
- Fast-forward apply onto a clean local git checkout in a temp repo.
- Workspace retention deletes an old rejected workspace under `WORK_ROOT`.

## What must stay disabled

- `allow_deploy=true` until health checks, backup, and rollback exist (§7).
- Treating Windows `--force` runs as sandboxed (§1, **BLOCKED**).
- Unattended production pushes for any remote that is not already protected by GitHub branch rules outside this app (§5).
- Exposing the tunnel to anyone who is not the single operator. There is no multi-user ACL (§3).

---

## Dependency-ordered roadmap

Security and reliable execution come before media, UI, and extra model features. Each phase’s acceptance criteria must be automated tests unless marked “manual live check.” Do not start a later phase by weakening an earlier control.

```text
R0 docs truth
  → R1 credential boundary (Windows-realistic)
    → R2 queue correctness (renew, recover, cancel)
      → R3 approval integrity
        → R4 safe local apply
          → R5 backups + audit hygiene + quotas
            → R6 CI and doc sync
              → R7 channel media and revisions
                → R8 deploy health and rollback   (last; keep allow_deploy false until exit)
```

### R0 — Make operator docs match the code

**Depends on:** nothing.  
**Why first:** current `SECURITY_MODEL.md` / `ARCHITECTURE.md` / `README.md` limitations will cause unsafe or false operating decisions.

**Acceptance criteria**

- `README.md`, `SECURITY_MODEL.md`, `ARCHITECTURE.md`, `CURSOR_AGENT_INTEGRATION.md`, `DEPLOYMENT_RUNBOOK.md`, and `TEST_REPORT.md` either match this gap analysis or point at it and drop contradicted claims (in-memory queue, “sandbox unused,” “voice not implemented,” “no PR”).
- Deploy runbook still says `allow_deploy` stays false.
- No production config, tunnel, or GitHub change is required to close R0.

### R1 — Credential and process boundary

**Depends on:** R0 (so the new boundary is what operators read).  
**Windows sandbox stays BLOCKED** until the worker runs on Linux/macOS or Cursor supports a Windows sandbox. Do not pretend `--sandbox enabled` works here.

**Acceptance criteria**

- Agent subprocess environment test proves GitHub tokens, Meta tokens, web password, SMTP password, and deploy-related variables are absent, including names not covered by the current prefix list if they exist in `.env.example`.
- `CURSOR_API_KEY` is passed only via environment, not `--api-key` argv, or the test shows argv is redacted from any log line.
- Publish and deploy run with an explicit env allowlist (git/gh only), not the full orchestrator environment. Test uses a fake `PATH` and asserts `META_ACCESS_TOKEN` is absent.
- On Windows, a documented non-Cursor control is in place: separate OS account **or** a tested restriction that prevents the agent from reading the orchestrator `.env` and the user `.ssh` directory. If that cannot be done, the service must refuse `DRY_RUN=false` unless an operator sets an explicit break-glass flag, and the refusal is tested.
- Prompt text is not cited as the control.

### R2 — Queue correctness

**Depends on:** R1 (so a reclaimed job cannot run with a wider env than a fresh job).

**Acceptance criteria**

- While `execute_task` is in progress, a test advances time or calls the renewal hook and shows `leased_until` stays in the future. Reclaim does not create a second attempt for a live job.
- Startup recovery test matrix:
  - `queued` + pending job → not duplicated.
  - `running` + workspace + live lease → not deleted and not re-executed.
  - `running` + expired lease → either a single fenced retry **or** a terminal `failed` with the workspace preserved. The test must show it does not delete the workspace and start a second agent without that policy.
  - `publishing` + crash → task does not stay `publishing` forever; outcome is `publish_failed` or a resumed publish that is still digest-checked.
- Recovery updates go through `assert_transition` or an explicit recovery transition table tested for illegal jumps.
- Cancel test: a tracked subprocess is killed, the job row ends `done` or `failed` with `retry=false`, and a late `execute_task` completion cannot set `review`.
- Document and test “one worker process.” A second `claim_next` in the same process must not steal a running job whose lease was renewed.

### R3 — Approval integrity

**Depends on:** R2 (publish jobs must not double-apply).

**Acceptance criteria**

- Publish with an empty `content_digest` fails closed. Test covers that.
- If the workspace digest differs from the stored review digest, status becomes `publish_failed` (or stays `review`) and no `git push` / `gh` / merge runs. Test spies on `run`.
- Approve uses a compare-and-swap (`UPDATE ... WHERE status='review'`) so two concurrent approves enqueue one publish job. Test simulates the race.
- `published` → `publishing` is rejected, or PR retry is an explicit tested transition that re-checks digest and does not re-merge local files unexpectedly.
- Approval older than a configured TTL is rejected. Test uses a frozen timestamp.
- Audit row stores action, actor, task id, digest prefix, and result, and the test shows a fake token in `detail` is scrubbed.

### R4 — Safe application to the local checkout

**Depends on:** R3 (only a digest-matched tree may be applied).

**Acceptance criteria**

- Before `apply_to_local`, the destination HEAD is recorded and a stash or bundle backup path is created under `WORK_ROOT` (not inside the user’s project). Test asserts the backup exists.
- Dirty destination still refuses apply (add the missing test).
- Conflicted merge aborts (`git merge --abort` or equivalent) and the test shows the destination file bytes match the pre-apply content.
- `type=local` stays apply-disabled **or** gains an explicit copy-back that uses the same backup rule and refuses on destination files newer than the snapshot. Pick one and test it. Do not silently copy over the source tree.
- Default `apply_local` on `PR` is opt-in. A PR test proves local files do not change unless `apply_local` is true.

### R5 — Backups, audit hygiene, and quotas

**Depends on:** R2 and R3 (so backups are of a queue that will not double-run, and audit rows match real publish decisions).

**Acceptance criteria**

- A script or command copies SQLite online (`VACUUM INTO` or the SQLite backup API) to a configurable directory and is tested against a temp database. It does not run against production in CI.
- Retention cleanup refuses to delete a workspace that has no successful backup pointer, or retention stays opt-in and the test shows the default does not delete when backup is required. Choose one policy and test it.
- `scrub` has unit tests for the patterns it claims, and `audit.record` / reply logs use it. A test reply containing `token=supersecret` does not appear raw in the log helper output.
- Per-sender caps: max queued tasks and max agent starts per UTC day, both tested (the N+1st task is refused with a clear message and no job row).
- Optional Groq and Cursor calls increment a counter; when a configured ceiling is hit, new agent and Whisper calls fail closed. Test with a fake ceiling of 1.

### R6 — CI and configuration

**Depends on:** R1–R5 tests existing so CI can enforce them.

**Acceptance criteria**

- A workflow in **this** repo (not a task workspace) runs `python -m pytest --ignore=tests/browser` on push and fails on red.
- `projects()` in production mode fails startup on any invalid project (`strict=True`), with a test.
- Secrets are not committed. CI does not print `.env`.
- `GET /docs` is disabled outside an explicit dev flag, with a test that `/docs` is 404 in the default app.
- Browser tests stay optional and are not required to claim R6.

### R7 — Media and revisions (after the gates above)

**Depends on:** R1 (downloaded files must land only in the task workspace), R3 (a revision produces a new digest), R5 (media bytes count against quotas).

**Acceptance criteria**

- WhatsApp image and audio and Telegram photo and voice are either rejected with a user-visible reply or stored under the task workspace with size and type allowlists. Tests use fixture bytes, not live Meta.
- A screenshot path is included in the task file only when the file is inside the workspace. A path traversal fixture is rejected.
- `REVISE` reuses the same workspace and branch, increments `revision`, runs the agent again, and stores a **new** digest. Previous approval cannot publish the new tree. Test covers the digest change.
- Voice transcription failure does not create a task.

### R8 — Staging and production deployment

**Depends on:** R1 (deploy credentials not visible to the agent), R3 (digest), R4 (local apply is not confused with prod), R5 (backup).

**Acceptance criteria**

- Registry requires `environment`, `health_check`, and `rollback_command` before `allow_deploy` can be true. Test: prod + missing health URL fails validation.
- A fake deploy exits 0 and a fake health URL returns 500 → task `publish_failed` (or `deploy_failed`) and the rollback command is invoked once. Test with stubs.
- Health success records the deployed SHA and environment in `audit_events`.
- No workflow in this phase enables deploy in the operator’s real `projects.json`. That remains a manual change after the tests pass.

---

## Suggested implementation order (one line each)

1. R0 correct the stale docs.  
2. R1 stop the agent from inheriting publish and chat secrets; accept that Windows CLI sandbox is **BLOCKED**.  
3. R2 renew leases and make restart recovery non-destructive and tested.  
4. R3 fail closed on digest, single-flight approve, TTL.  
5. R4 backup and abort around local merge; do not apply on PR unless asked.  
6. R5 SQLite backup, scrub tests, per-sender and API ceilings.  
7. R6 CI and strict config.  
8. R7 media and real revisions.  
9. R8 health-checked deploy with rollback. Leave `allow_deploy` false until R8’s tests pass.

## Audit limits

- Unit tests were executed locally. The Playwright browser suite was not.  
- No live Cursor agent, Meta Graph, Telegram, Groq, `gh`, or deploy command was invoked for this report.  
- The 2026-10-16 live smoke remains the latest agent evidence and did not prove tool-level streaming.  
- `projects.json` and `.env` were not modified and their secret values were not copied into this document.
