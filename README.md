# WhatsApp → Cursor Coding Orchestrator (local-first starter)

A runnable foundation for messaging tasks to a registered local or Git project, executing Cursor CLI in a separate workspace, returning a review report, and requesting explicit approval before pushing an **unmerged branch** or running a preconfigured deployment command.

## Documentation

| Doc | Purpose |
|-----|---------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System topology and components |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Phased plan and acceptance criteria |
| [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) | Controls and residual risks |
| [docs/SETUP_WINDOWS.md](docs/SETUP_WINDOWS.md) | Windows setup (use `python`, not only `py`) |
| [docs/WHATSAPP_INTEGRATION.md](docs/WHATSAPP_INTEGRATION.md) | Meta Cloud API status |
| [docs/TELEGRAM_INTEGRATION.md](docs/TELEGRAM_INTEGRATION.md) | Telegram bot (no Meta billing / tunnel) |
| [docs/WEBCHAT.md](docs/WEBCHAT.md) | Private password-protected web chat at `/chat` |
| [docs/CURSOR_AGENT_INTEGRATION.md](docs/CURSOR_AGENT_INTEGRATION.md) | Cursor CLI flags and isolation |
| [docs/DEPLOYMENT_RUNBOOK.md](docs/DEPLOYMENT_RUNBOOK.md) | Publish/deploy operator guide |
| [docs/TEST_REPORT.md](docs/TEST_REPORT.md) | Historical Phase 1 audit (superseded for current gaps) |
| [docs/PRODUCTION_READINESS_GAP_ANALYSIS.md](docs/PRODUCTION_READINESS_GAP_ANALYSIS.md) | **Current** production-readiness baseline (R0–R8) |
| [docs/CONVERSATIONAL_AGENT_AUDIT.md](docs/CONVERSATIONAL_AGENT_AUDIT.md) | Root causes: chat vs Cursor execution evidence |
| [docs/CONVERSATIONAL_AGENT_VERIFICATION.md](docs/CONVERSATIONAL_AGENT_VERIFICATION.md) | Conversational + execution tracking upgrade verification |

## Status / limitations

Authoritative gap list: [docs/PRODUCTION_READINESS_GAP_ANALYSIS.md](docs/PRODUCTION_READINESS_GAP_ANALYSIS.md). Older architecture and security notes that still say the queue is in-memory, or that `--workspace` / stream-json / job recovery are absent, are historical.

- **Not a production deployment platform.** `allow_deploy` must stay false. There is no target health check or rollback.
- **Single-operator allowlists**, not per-project accounts. Web chat is one shared password (`web:owner`).
- Git tasks use a worktree branch `wa/<id>`. Publishing requires a non-empty review **content digest** and fails closed on mismatch. Push does not force-push and does not merge to the default branch. Pull requests use `gh pr create` when you ask for one (`allow_push` required).
- Local (`type=local`) projects are copied and are **not** copied back automatically.
- Cursor `--sandbox` is **not available on Windows**. The agent still uses `--force`. Prompt text is not a security boundary. Live runs require the Windows isolation boundary (or an explicit break-glass flag).
- `DRY_RUN=true` by default: workspace prep only; agent and publish stay off.
- WhatsApp is text-only (non-text is ignored). Web chat can transcribe a microphone clip via Groq. Telegram is text-only. No screenshot/attachment pipeline and no in-place task revision.
- WhatsApp Cloud API may require billing, a public HTTPS webhook, and the 24-hour session window. There is no template fallback.

## Windows setup (PowerShell)

1. Install Python 3.11+, Git and [Cursor CLI](https://cursor.com/cli). For Windows, Cursor documents:

   ```powershell
   irm 'https://cursor.com/install?win32=true' | iex
   agent login
   agent --version
   ```

2. Extract this folder, open PowerShell inside it:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   Copy-Item .env.example .env
   Copy-Item projects.example.json projects.json
   ```

3. Edit `.env` and `projects.json`. Use **Windows paths** in `projects.json`. Set `AGENT_BIN=agent` or full path to Cursor CLI executable. Use your own WhatsApp number without `+` in `ALLOWED_WHATSAPP_NUMBERS`. For Git projects, ensure `git` is in PATH, the checkout has no uncommitted changes, a remote named `origin` exists, and Git push credentials work. Start with `DRY_RUN=true` and `allow_deploy=false`.

4. Start service:

   ```powershell
   python -m uvicorn app:app --host 127.0.0.1 --port 8000
   ```

5. Provide a secure publicly accessible **HTTPS** endpoint pointing to `http://127.0.0.1:8000`, e.g. a correctly configured Cloudflare Tunnel. Only expose webhook route publicly; protect local machine. In Meta's WhatsApp Cloud API app webhook configuration, use `https://YOUR-DOMAIN/webhook` with the matching `META_VERIFY_TOKEN`, subscribe to WhatsApp `messages`, and configure token, app secret, phone number ID. The Meta test phone number and recipient allowlist can be used for sandbox testing.

6. Message your connected WhatsApp number:

   ```text
   PROJECTS
   TASK demo: Improve the form validation and write tests.
   STATUS <task_id>
   REJECT <task_id>
   APPROVE <task_id> PUSH
   APPROVE <task_id> DEPLOY
   ```

7. Confirm a dry run creates a workspace and delivers review message, **without changing original files**. Set `DRY_RUN=false` only after you can authenticate the CLI and have isolated its privileges. Review files under `data/workspaces/<task_id>` carefully before explicit approval.

## Publishing

- **Git push:** after review, approve push commits the isolated worktree and updates `origin` branch `wa/<id>` only when the remote can fast-forward or the branch is absent. An existing identical remote SHA is treated as already pushed. No force-push and no merge to the default branch.
- **Pull request:** ask to create a pull request. Requires `gh` auth and `allow_push`. This does not deploy.
- **Local project without Git:** no automatic apply-back.
- **Deploy:** keep `allow_deploy=false`. The deploy command path is exit-code only and is not a production deployment.

## Run tests

```powershell
python -m pytest -q
```

## Security and functional next steps before broad rollout

- Run agent in OS-level isolation, restrict filesystem/network access, block access to SSH keys and deployment credentials, define output/diff limits.
- Review prompt injection and webhook abuse risks; add per-project policies, queued job persistence/recovery, per-sender quotas, approval expiration and separate deploy review.
- Replace arbitrary deploy command with explicit CI/CD deployment integrations, with backups, smoke tests and rollback.
- Support inbound media via authenticated Meta media retrieval and transcription; implement task revision threads.
- Avoid including secrets in agent logs and WhatsApp reports; audit and scrub outputs.

## Authoritative references

- Cursor CLI: https://cursor.com/cli and https://prod.cursor.com/docs/cli/using
- WhatsApp Cloud API official Meta Postman collection: https://www.postman.com/meta/whatsapp-business-platform/overview
