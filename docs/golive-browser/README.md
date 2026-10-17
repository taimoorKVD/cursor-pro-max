# Go-live browser investigation

Playwright suite that drives the real `/chat` UI against the running orchestrator and writes an evidence report.

## What it checks

1. `/health` + login → composer shell
2. `/chat/status`: `DRY_RUN=false`, Cursor CLI present, agent auth OK, LifeOS registered
3. Select **lifeos** and confirm `active_project`
4. Ask a status follow-up and judge whether the reply cites real task evidence
5. Open progress UI + `/chat/task-progress`
6. SQLite history: streamed reviews vs known failure buckets (auth, workspace collision, empty output, …)
7. Console/network errors during the pass
8. Optional: disposable local project end-to-end Cursor smoke (`ORCH_BROWSER_LIVE_AGENT=1`)

## Run

Prerequisites: orchestrator on `http://127.0.0.1:8000`, `WEBCHAT_PASSWORD` in `.env`, Chromium installed for Playwright.

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
$env:ORCH_BROWSER_RUN='1'
.\.venv\Scripts\python.exe -m pytest tests/browser -m browser_live --tb=short
```

Optional live agent smoke (mutates a temp fixture project, not LifeOS):

```powershell
$env:ORCH_BROWSER_RUN='1'
$env:ORCH_BROWSER_LIVE_AGENT='1'
.\.venv\Scripts\python.exe -m pytest tests/browser -m browser_live --tb=short
```

## Outputs

- `docs/golive-browser/GOLIVE_BROWSER_INVESTIGATION.md` — human report
- `docs/golive-browser/latest.json` — machine-readable
- `docs/golive-browser/*.png` — screenshots
