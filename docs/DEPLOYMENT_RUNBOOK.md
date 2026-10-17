# Deployment Runbook

**Warning:** Production deployment automation is **not ready**. Keep `allow_deploy=false`. Do not enable deploy while implementing reliability work (through R6). Health verification and rollback are R8 and are intentionally not in this tree yet.

See [PRODUCTION_READINESS_GAP_ANALYSIS.md](PRODUCTION_READINESS_GAP_ANALYSIS.md).

This runbook documents **current** publish behavior and the **future** controlled deployment process.

## Current publish paths

### A. Git branch push (`APPROVE <task_id> PUSH`)

Preconditions (all required):

1. Task status is `review`.
2. `DRY_RUN=false`.
3. Project `allow_push=true`.
4. Task has a non-empty `branch` (git worktree tasks only).
5. Approving WhatsApp sender matches task `sender`.

Actions performed:

1. Status → `publishing`.
2. `git add -A`
3. Commit with local identity `WhatsApp Cursor Agent <automation@localhost>`
4. `git push origin HEAD:refs/heads/<branch>`
5. Report short SHA; status → `published` or `publish_failed`.

**Does not:** merge to the default branch, force-push, wait for GitHub CI, or deploy. A separate approve action can open a PR via `gh` (`publish.py`). The message names GitHub only when `origin` contains `github.com`. Push is refused when the content digest is missing or mismatched, and when the remote branch has diverged.

Message text currently says “GitHub remote branch” even if `origin` is not GitHub — treat that wording as inaccurate until Phase 5 remote detection lands.

### B. Deploy command (`APPROVE <task_id> DEPLOY`)

Preconditions:

1. Same review / dry-run / sender checks as push.
2. `allow_deploy=true`.
3. Non-empty `deploy_command` in `projects.json` (admin-controlled argv).

Actions:

1. `shlex.split(deploy_command)` and run with cwd = workspace, timeout 600s.
2. Success = exit code 0 only.
3. WhatsApp instructs operator to verify service independently.

**Does not:** confirm environment, backup, health, rollback, or revision pin beyond workspace contents.

### C. Local projects

No automated apply-back. Operators must inspect `data/workspaces/<task_id>` and merge manually.

## Operator procedure (safe today)

1. Keep deploy disabled.
2. Run tasks with `DRY_RUN=true` until workspace creation and WhatsApp reports look correct.
3. Enable agent with isolation; review diffs under the workspace.
4. For git: `APPROVE … PUSH`, then open a PR **manually** in the hosting UI.
5. Merge via normal protected-branch process (human + CI).
6. Deploy via existing project pipeline (GitHub Actions, host panel, etc.) — **outside** this orchestrator until Phase 6.

## Incident responses

| Failure | Immediate action |
|---------|------------------|
| Bad push | Do not APPROVE DEPLOY; delete or abandon remote branch `wa/<id>`; fix locally |
| Agent leaked secret in WA | Rotate secret; set `WEBHOOK_REPLY_ENABLED=false` until scrubbing exists |
| Unexpected deploy ran | Treat host as possibly changed; verify version; roll back via project’s existing process |
| Stuck `publishing` after crash | Inspect workspace + remote; manually set task status after determining outcome (no auto-recovery yet) |

## Phase 6 target procedure (not implemented)

1. Confirm task revision digest + target environment (`dev`/`staging`/`prod`).
2. Validate separate deploy authorization (not the same token as PUSH).
3. Run pre-deploy checks (tests already green, migrations plan, feature flags).
4. Confirm backup / snapshot artifact id.
5. Execute provider-specific deploy (Actions workflow_dispatch, SSH script, etc.).
6. Health verify (HTTP probe / smoke script).
7. Record deployed SHA + environment in audit log.
8. On health failure: run approved rollback only if policy + backup exist.

## Rollback policy (placeholder)

Until implemented: **manual only**. Document each project’s rollback in that project’s ops docs; do not encode irreversible prod commands in `deploy_command`.
