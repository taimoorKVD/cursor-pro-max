# Private Web Chat

A password-protected chat page served by the orchestrator itself at `/chat`. It uses the same commands and job pipeline as WhatsApp/Telegram, with no third-party messaging app or billing.

## How it works

```text
Phone browser → https://<tunnel>/chat → Cloudflare tunnel → FastAPI on the laptop
             → same handle() commands → Cursor Agent → reply stored → page polls every 2s
```

- Single operator; tasks are owned by sender `web:owner`.
- Chat history is stored in SQLite table `web_messages`.

## Setup

1. Set a strong password in `.env` (minimum 12 characters; the page is disabled otherwise):

   ```text
   WEBCHAT_PASSWORD=<long random string>
   WEBCHAT_SESSION_DAYS=7
   ```

2. Keep uvicorn + tunnel always on (once per machine):

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install-autostart.ps1
   ```

   Or restart uvicorn manually if you prefer a foreground window.
3. Get the public URL from `data/logs/cloudflared-public-url.txt` and open `<url>/chat` on your phone. Locally: `http://127.0.0.1:8000/chat`.
4. Hard-refresh the page after deploys (`Ctrl+F5` / pull-to-refresh) so you get the latest UI.
5. Log in. A welcome message and status pill show agent/DRY_RUN health.
6. Commands: `PROJECTS`, `TASKS`, `HELP`, `TASK project: ...`, `STATUS <task_id>`, `APPROVE <id> PUSH`, `REJECT <id>`.

### Install on iPhone (Home Screen app)

**Easiest (QR):** on the laptop browser open:

```text
http://127.0.0.1:8000/chat/qr
```

Scan with iPhone Camera/Safari → log in → Share → **Add to Home Screen**.

Safari on iPhone (must use **https://** tunnel URL, not localhost):

1. Open `<tunnel>/chat` and log in.
2. Tap **Share** → **Add to Home Screen**.
3. Name it `Orchestrator` → **Add**.

It opens full-screen like an app (standalone), with its own icon. The UI is built for iPhone safe areas, notch, and keyboard. The QR page is laptop-only (`Host: 127.0.0.1`) and refreshes when the quick-tunnel URL changes.

Android Chrome: menu → **Install app** / **Add to Home screen**.

### Notifications

Tap the **bell** in the chat header and allow notifications. New replies are tagged:

| Level | When |
|-------|------|
| success | task ready for review, publish done |
| error | task/publish failed |
| warning | blocked / dry-run / missing agent |
| info | progress updates |

Success / error / warning always notify. Info notifies when the tab is in the background. Works best on Android Chrome / desktop; iOS is limited unless the page is added to the Home Screen.

## Security

- Anyone with the password can run Cursor Agent on this machine. Use a long random password and do not share the URL + password together.
- Session cookie is HttpOnly, SameSite=Strict, Secure over HTTPS, HMAC-signed with the password, and expires after `WEBCHAT_SESSION_DAYS`. Changing the password logs out all sessions.
- 5 wrong passwords from one IP → 15-minute lockout.
- Pages send a strict Content-Security-Policy and `X-Frame-Options: DENY`.

## Limitation: changing tunnel URL

Quick tunnels get a new `*.trycloudflare.com` hostname whenever cloudflared restarts (reboot, crash), so a bookmark stops working. For a permanent URL, use a named Cloudflare tunnel with your own domain.

When the URL changes, `scripts/notify-tunnel-url.ps1` emails `TUNNEL_URL_NOTIFY_TO` (via SMTP2GO settings in `.env`) with the new `/chat` link and related details. Set `SMTP_PASSWORD` and keep `TUNNEL_URL_EMAIL_ENABLED=true`.
