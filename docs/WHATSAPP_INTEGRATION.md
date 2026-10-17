# WhatsApp Integration

**Scope:** Official Meta WhatsApp Cloud API only. Unofficial WhatsApp Web automation is out of scope and must not be added.

## Implemented (verified in code)

| Capability | Status | Notes |
|------------|--------|-------|
| GET webhook verification | Yes | `hub.mode` / `hub.verify_token` / `hub.challenge` |
| POST webhook receive | Yes | Parses `entry[].changes[].value.messages[]` |
| HMAC signature check | Yes | Raw body + `META_APP_SECRET` → `X-Hub-Signature-256` |
| Sender allowlist | Yes | Digits, strip `+` |
| Dedup by message id | Yes | SQLite `incoming` |
| Text commands | Yes | PROJECTS, TASK, STATUS, APPROVE, REJECT |
| Outbound text | Yes | Graph `POST /{PHONE_NUMBER_ID}/messages` |
| Tunnel URL → Meta sync | Yes | Phone/WABA `override_callback_uri` via `orchestrator.meta_webhook_sync` when quick tunnel URL changes |
| Delivery retries / outbox | No | Single attempt; log on failure |
| Status webhooks (sent/delivered/read) | No | Ignored if present |
| Images / audio / documents | No | Non-text types silently skipped |
| Transcription | No | — |
| Template messages | No | Required outside 24h window |
| Interactive buttons / lists | No | Plain text commands only |
| Typing indicators / mark read | No | — |

## Command protocol (current)

```text
PROJECTS
TASK <project_id>: <requirement (≥5 chars)>
STATUS <task_id>
REJECT <task_id>
APPROVE <task_id> PUSH
APPROVE <task_id> DEPLOY
```

Unknown text receives a help string. Follow-up freeform conversation is **not** associated with tasks.

## Meta compatibility notes (docs-checked 2026-10-10)

### Webhooks

- Meta signs POST bodies with HMAC-SHA256; verify **before** trusting JSON (implemented).
- Failed deliveries (non-200) are retried for up to ~7 days — dedup is mandatory (implemented).
- Subscribe to field `messages` for inbound + status events.

### Sending

- Endpoint shape matches Cloud API: `https://graph.facebook.com/{version}/{phone-number-id}/messages`.
- Payload uses `messaging_product: whatsapp`, `type: text`, `text.body`.
- Body truncated to 3900 chars in code (platform limit is 4096) — safe margin.
- Acceptance by Graph ≠ delivery. Delivery comes via status webhooks (not handled yet).
- Free-form service messages only inside the **customer service window** (~24h after user message). Outside that window, only approved **templates** work. Current code will fail and only log.

### Phone numbers

- Allowlist stores digits without `+`.
- Meta recommends including `+` and country code on **send**; current code sends the allowlisted form as stored. Prefer storing E.164 digits consistently and documenting the format you use with your WABA.

### Media (not implemented; Phase 3)

Official flow:

1. Webhook includes media `id` (and sometimes short-lived `url`).
2. `GET /{media-id}` (with auth) to obtain download URL (URLs expire ~5 minutes).
3. `GET` download URL with `Authorization: Bearer <token>`.
4. Webhook media ids expire ~7 days.

Supported future types for this product: `image`, `audio` (voice notes), `document` (limited).

### Graph version

`.env.example` pins `META_GRAPH_VERSION=v23.0`. Meta documentation examples may reference newer versions (e.g. v26). Keep pin explicit; upgrade after changelog review.

## Tunnel URL sync to Meta

Quick tunnels change hostname on restart. When `META_WEBHOOK_SYNC_ENABLED=true`, `scripts/start-cloudflare-tunnel.ps1` calls `scripts/sync-meta-webhook.ps1`, which runs:

```text
python -m orchestrator.meta_webhook_sync <public-url>
```

That sets Meta’s **override** callback (not the App Dashboard default) using:

- phone override when `META_PHONE_NUMBER_ID` is set: `POST /{PHONE_NUMBER_ID}` with `webhook_configuration.override_callback_uri`
- and/or WABA override when `META_WABA_ID` is set: `POST /{WABA_ID}/subscribed_apps`

Requirements: orchestrator must be reachable at `{public}/webhook` (Meta sends a verify GET), and IDs must not be placeholders. Manual sync:

```powershell
.\scripts\sync-meta-webhook.ps1 -Force
```

Synced URL is recorded in `data/logs/cloudflared-meta-synced-url.txt`.

## Security requirements for operators

1. Never commit `.env`.
2. Rotate `META_ACCESS_TOKEN` if leaked; treat WhatsApp reports as untrusted channels for secrets.
3. Restrict public ingress to `/webhook`.
4. Keep `ALLOWED_WHATSAPP_NUMBERS` minimal.
5. Do not put deploy secrets in messages or agent-visible environment.

## Phase 3 target protocol (draft)

Additive commands (backward compatible):

```text
REPLY <task_id>: <follow-up>
REVISE <task_id>: <change request>
APPROVE <task_id> PR
APPROVE <task_id> APPLY
APPROVE <task_id> DEPLOY <env>
```

Media messages without caption should still create or attach to a task when a project is unambiguous; otherwise ask clarifying questions.
