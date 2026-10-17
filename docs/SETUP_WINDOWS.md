# Setup (Windows)

Verified during Phase 1 audit on Windows 10 (build 26200), PowerShell, Python **3.10.6**, Git **2.55.0**.

## Prerequisites

| Tool | Required | Audit host status |
|------|----------|-------------------|
| Python 3.11+ recommended (3.10 works) | Yes | 3.10.6 via Laragon `python` |
| `py` launcher | Documented in README; optional | **Not installed** — use `python` |
| Git | Yes for `type: git` projects | Installed |
| Cursor CLI (`agent`) | Yes when `DRY_RUN=false` | **Not on PATH** |
| HTTPS tunnel (e.g. Cloudflare Tunnel) | Yes for Meta webhooks | Not verified in audit |
| Meta WhatsApp Cloud API app | Yes for live messaging | Not configured in audit |

## Install Cursor CLI

Official Windows install (from Cursor docs):

```powershell
irm 'https://cursor.com/install?win32=true' | iex
agent login
agent --version
agent status
```

Set `AGENT_BIN` in `.env` to `agent` or the full path of the executable if PATH is unreliable.

Optional for scripts: `CURSOR_API_KEY` (see Cursor headless docs). Prefer interactive `agent login` for a paid desktop/CLI account when possible.

## Project bootstrap

```powershell
cd d:\taimoorKVD\my-automation-project\whatsapp-cursor-orchestrator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
Copy-Item projects.example.json projects.json
```

Edit `.env`:

- `META_*` values from Meta Developer Console (leave placeholders until ready).
- `ALLOWED_WHATSAPP_NUMBERS` — your number **without** `+` (example: `923001234567`).
- Keep `DRY_RUN=true` until agent isolation is understood.
- `WEBHOOK_REPLY_ENABLED=true` only when you want outbound Graph calls.

Edit `projects.json` with real Windows paths, e.g. `C:/Users/YOU/projects/demo`.

## Run service

Manual (foreground):

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

### Autostart (recommended)

Keep the orchestrator + Cloudflare tunnel running whenever you log into Windows, with auto-restart on crash:

```powershell
cd d:\taimoorKVD\my-automation-project\whatsapp-cursor-orchestrator
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-autostart.ps1
```

This registers two per-user Scheduled Tasks:

| Task | Starts |
|------|--------|
| `WhatsAppOrchestratorService` | uvicorn on `127.0.0.1:8000` |
| `WhatsAppOrchestratorCloudflareTunnel` | Cloudflare quick tunnel → that port |

They start at logon and do not require admin. Each script is a supervisor: uvicorn restarts on crash/`.env` change; the tunnel recycles itself on dead quick-tunnels, Cloudflare API timeouts, or failed public `/health` checks (with backoff). Task Scheduler also restarts a supervisor within ~1 minute if it exits. Laptop must be awake/online (sleep pauses them). Public URL: `data/logs/cloudflared-public-url.txt` (emailed on change). Chat: `http://127.0.0.1:8000/chat` or `https://<tunnel>/chat`.

The orchestrator supervisor **auto-restarts uvicorn when `.env` or `projects.json` changes** (so a new `WEBCHAT_PASSWORD` applies within a couple of seconds). Check `data/logs/orchestrator-control.log` for `config-change` lines.

Health check: `http://127.0.0.1:8000/health` → `{"status":"ok"}`.

## Expose webhook securely

1. Point a tunnel **only** to path `/webhook` if the reverse proxy allows path filtering.
2. In Meta App → WhatsApp → Configuration: Callback URL `https://YOUR-DOMAIN/webhook`, Verify Token = `META_VERIFY_TOKEN`.
3. Subscribe to `messages`.
4. Use App Secret as `META_APP_SECRET`.
5. Phone number ID → `META_PHONE_NUMBER_ID`; permanent/system user token → `META_ACCESS_TOKEN`.
6. Pin Graph version (`META_GRAPH_VERSION`); starter defaults to `v23.0`. Meta examples may show newer versions — bump deliberately after reading changelog.

## Git project checklist

- Working tree clean before tasks (`git status` empty).
- Remote named `origin` exists.
- Push credentials work for non-protected feature branches.
- `allow_push=true` only when ready; never enable force-push workflows.

## Local project checklist

- `type: local`; `allow_push` must stay false.
- Changes land under `data/workspaces/<task_id>` only — **not** auto-applied to source.
- Ensure source path exists and is readable.

## Tests

```powershell
python -m pytest -q
```

Phase 1 result: 3 passed (see `TEST_REPORT.md`).

## Common Windows issues

| Symptom | Likely cause |
|---------|----------------|
| `py` not recognized | Use `python` instead |
| `agent` not recognized | Install CLI; set `AGENT_BIN` full path |
| `shlex` breaks deploy/test | Avoid complex quoting; use `.cmd` wrappers |
| Worktree fails | Uncommitted changes in source repo |
| Meta 403 on webhook | Wrong app secret or body not raw-HMAC’d |
| Outbound send fails hours later | Customer service window closed — need templates (Phase 3) |
