# Cursor Agent Integration

**Principle:** Use the official Cursor CLI (`agent`). Do not automate the Cursor Desktop GUI via undocumented UI hooks.

**Current source of truth:** `orchestrator/agent.py` and [PRODUCTION_READINESS_GAP_ANALYSIS.md](PRODUCTION_READINESS_GAP_ANALYSIS.md). The 2026-10-10 notes below are historical. A later live smoke is recorded in [CONVERSATIONAL_AGENT_VERIFICATION.md](CONVERSATIONAL_AGENT_VERIFICATION.md).

## Current invocation

When `DRY_RUN=false` and the isolation boundary allows it:

```text
{resolved agent entry} -p --force --trust --workspace <workspace> --output-format stream-json <short pointer>
```

- The full task is written to `.orchestrator-task.md` in the workspace. The API key is passed in the environment, not printed in logs.
- `cwd` = task workspace. Timeout = `AGENT_TIMEOUT_SEC` (default 1200).
- On Windows, `--sandbox enabled` is forced to `disabled` because Cursor’s sandbox is not available there. A separate Windows isolation boundary is required for live runs.
- `DRY_RUN=true` (default): workspace is prepared; the agent is not invoked.

## Official CLI capabilities (docs-verified)

Sources: [CLI overview](https://cursor.com/docs/cli/overview), [Headless](https://cursor.com/docs/cli/headless), [Parameters](https://cursor.com/docs/cli/reference/parameters).

| Feature | Relevance | Used today? |
|---------|-----------|-------------|
| `agent -p / --print` | Non-interactive automation | Yes |
| `--force` / `--yolo` | Apply file changes; **force-allow shell unless denied** | Yes |
| `--output-format text\|json\|stream-json` | Parsing / progress | Default `stream-json` |
| `--workspace <dir>` | Explicit workspace root | Yes |
| `--sandbox enabled\|disabled` | Command sandboxing | Forced `disabled` on Windows |
| `--trust` | Headless trust workspace | Yes |
| `--mode plan` / `--mode ask` | Plan-first / read-only | No |
| `--worktree` | CLI-managed git worktree under `~/.cursor/worktrees` | No (app manages its own worktrees) |
| `--resume` / `--continue` | Multi-turn agent sessions | No |
| `CURSOR_API_KEY` / `agent login` | Auth | Operator responsibility |
| Image paths in prompts | Screenshot analysis | No (no media pipeline yet) |
| Rules / `AGENTS.md` / `.cursor/rules` | Project guidance | Not injected by orchestrator (CLI may auto-load if present in workspace) |

### Important doc facts

- Without `--force` in print mode, file changes may be proposed but not applied (headless docs).
- With `--force`, commands are force-allowed unless explicitly denied — this is **not** a security boundary.
- Forum/docs guidance for autonomous headless runs: prefer `--print --trust --sandbox enabled` so unallowlisted commands fail closed instead of prompting.
- Agent can run shell and use network depending on sandbox policy.

## Workspace strategy (orchestrator-owned)

| Project type | Mechanism | Notes |
|--------------|-----------|-------|
| `git` | `git worktree add -b wa/<task_id>` | Requires clean source tree |
| `local` | `shutil.copytree` with ignores | No apply-back |

Do **not** assume Cursor `--worktree` replaces orchestrator isolation; either approach is valid, but mixing both without care creates duplicate worktrees.

## Prompt policy (current)

Hard-coded English instructions: stay in workspace, no credentials/production/deploy/`git push`, summarize changes. This is advisory only.

## Recommended integration changes (Phase 2/4)

1. Prefer explicit `--workspace <target>` and `--trust` for headless.
2. Default non-dry-run to `--sandbox enabled` (allow override in `.env` for debugging).
3. Consider plan step: `agent -p --mode plan` then implement after user OK (optional config).
4. Use `--output-format stream-json` for progress messages to WhatsApp (rate-limited).
5. For revisions: `agent --resume <chatId>` **or** same workspace with new prompt — pick one and document; resume needs persisted chat id.
6. Never pass Meta/GitHub/deploy tokens in the agent environment.
7. Scrub agent output before WhatsApp (token regexes, `.pem`, `AKIA…`, etc.).
8. Resource limits: enforce subprocess timeout (done) + OS-level CPU/memory (not done).

## Authentication checklist

```powershell
agent login
agent status
agent about
agent models   # optional: confirm paid-plan models
```

For CI-like hosts, set `CURSOR_API_KEY` per Cursor headless documentation.

## What we will not do

- Drive Cursor IDE via accessibility/UI automation.
- Claim Cloud Agent / `agent worker` integration until explicitly designed (separate product surface).
- Run with `--force` and sandbox disabled on a machine holding production SSH keys.
