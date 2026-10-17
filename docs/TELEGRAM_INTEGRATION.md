# Telegram Integration

Telegram fulfills the same product goal as WhatsApp for this orchestrator: send `PROJECTS` / `TASK` / `STATUS` / `APPROVE` / `REJECT` from your phone, run Cursor Agent in an isolated workspace, review, then approve push/deploy.

## Why Telegram here

- No Meta payment / Paid Message Account requirement
- Long polling works on a laptop **without** a public tunnel
- Same command handlers and job queue as WhatsApp

WhatsApp Cloud API remains supported when billing/token access works.

## Setup

1. In Telegram, open [@BotFather](https://t.me/BotFather) → `/newbot` → copy the bot token.
2. Put it in `.env`:

   ```text
   TELEGRAM_BOT_TOKEN=123456:ABC...
   TELEGRAM_POLLING_ENABLED=true
   WEBHOOK_REPLY_ENABLED=true
   ```

3. Start the orchestrator (`uvicorn app:app --host 127.0.0.1 --port 8000`).
4. Message your bot anything. If you are not allowlisted yet, it replies with your **numeric user id**.
5. Set:

   ```text
   ALLOWED_TELEGRAM_USER_IDS=123456789
   ```

6. Restart uvicorn, then send:

   ```text
   PROJECTS
   TASK lifeos: Add a short note to README about orchestrator testing.
   ```

## Sender identity

Telegram actors are stored as `tg:<user_id>` in the task DB (WhatsApp stays as digits). Approvals only work for the same sender that created the task.

## Notes

- Keep the laptop awake with uvicorn running (same local-first model).
- Tunnel is **not** required for Telegram polling.
- Set `DRY_RUN=true` until you trust agent behavior on real projects.
