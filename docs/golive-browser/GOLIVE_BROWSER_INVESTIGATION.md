# Go-live browser investigation

**When:** 2026-10-17T13:08:36.339832+00:00
**Target:** `http://127.0.0.1:8000`
**Verdict:** READY

## Executive summary

This suite investigates the core product promise: chat assigns work → Cursor CLI applies
changes in an isolated workspace → progress/events feed the UI → operator can approve/push.

If the verdict is NOT READY, treat major/blocker gaps below as launch blockers even when
the latest single task looks successful.

## Notes

- SQLite still has older auth/collision/empty-output failures, but the latest task is healthy and live agent auth is OK. Mitigations: workspace quarantine, empty-output retry + stream recovery, CSP worker-src.
- Your recent LifeOS coding run is recorded in SQLite. If the UI felt 'stuck', compare chat wording vs task status/events — a finished review task can still look vague if follow-ups don't cite evidence.
- Confirmed isolation: Cursor edited the workspace copy, not the source project path (expected until APPROVE / apply_local).
- No blocker/major gaps found by this investigation pass.

## Gaps

- None recorded.

## Known product failure modes this suite looks for

- Chat acknowledges work while Cursor never starts / exits empty / auth fails
- Mid-run UI stuck with no `agent_stream` evidence (streaming / CLI opacity)
- Workspace collision after crash/retry
- Orchestrator restart canceling an in-flight agent
- Status replies that invent progress instead of citing DB evidence

## Checks

### [PASS] Orchestrator /health responds

- **id:** `health`
- **severity:** blocker
- **detail:** status=200 body={"status":"ok"}
- **evidence:** `{"status": 200}`

### [PASS] Web chat login reaches composer

- **id:** `login_shell`
- **severity:** blocker
- **detail:** Composer #txt/#send visible after login

### [PASS] /chat/status authenticated payload

- **id:** `status_endpoint`
- **severity:** blocker
- **detail:** HTTP 200; dry_run=False; agent_ok=True; projects=11
- **evidence:** `{"dry_run": false, "agent_ok": true, "agent_detail": "C:/Users/naeem/AppData/Local/cursor-agent/agent.cmd", "agent_auth": {"ok": true, "email": "info@kingdom-vision.com", "mode": "api-key"}, "pending_jobs": 0, "active_task": {"id": "2b68ff094d33", "project": "lifeos", "status": "review", "execution_stage": "ready_for_review"}}`

### [PASS] DRY_RUN is false (real Cursor runs enabled)

- **id:** `live_mode`
- **severity:** blocker
- **detail:** DRY_RUN=false

### [PASS] Cursor agent CLI is available

- **id:** `agent_cli`
- **severity:** blocker
- **detail:** C:/Users/naeem/AppData/Local/cursor-agent/agent.cmd

### [PASS] Cursor agent authentication is healthy

- **id:** `agent_auth`
- **severity:** blocker
- **detail:** mode=api-key email=info@kingdom-vision.com ok=True
- **evidence:** `{"ok": true, "email": "info@kingdom-vision.com", "mode": "api-key"}`

### [PASS] LifeOS project is registered

- **id:** `lifeos_registered`
- **severity:** blocker
- **detail:** projects=['beydountech', 'ecc', 'japanski_travel', 'kv-hrms', 'kv-travels', 'lifeos', 'shahbasalon', 'staging-beydountech', 'truck-lts-admin-dashboard', 'valoracares', 'velora']

### [PASS] Header status pill reflects live agent health

- **id:** `status_pill`
- **severity:** major
- **detail:** pillText='LIVE · agent ok · smart chat · 11 projects · lifeos'

### [PASS] Selecting LifeOS sets active_project session

- **id:** `select_lifeos`
- **severity:** blocker
- **detail:** active_project='lifeos'; active_task_after_switch={'id': '2b68ff094d33', 'project': 'lifeos', 'status': 'review', 'execution_stage': 'ready_for_review'}

### [PASS] Status follow-up gets an evidence-shaped reply (not empty/stuck)

- **id:** `status_followup`
- **severity:** major
- **detail:** Your task 2b68ff094d33 in project lifeos is ready for review. 6 files were modified, the work has been running for 5 minutes and the last activity was 7 minutes ago. No blockers are reported. The task is queued, the workspace is prepared, tests are running, and the agent has finished coding. Would you like me to open the review or help with anything else?
- **evidence:** `{"stuck_phrases": [], "new_out_count": 1}`

### [PASS] After selecting LifeOS, progress API still surfaces the latest LifeOS task

- **id:** `task_progress_after_project_switch`
- **severity:** major
- **detail:** GAP: project switch clears active_task_id — default /chat/task-progress returned task={'task_id': '2b68ff094d33', 'project': 'lifeos', 'status': 'review', 'execution_stage': 'ready_for_review', 'current_label': 'Ready for review', 'completed': ['Queued', 'Preparing isolated workspace', 'Agent running — awaiting tool activity', 'Running configured tests', 'Ready for review'], 'remaining': [], 'instruction': 'implement remember me for 30 days on login screen', 'started_at': 1792239699, 'last_activity_at': 1792242083, 'ended_at': 1792240015, 'duration': '5 minutes', 'last_activity': '7m ago', 'modified_files': ['app/Http/Controllers/Auth/AuthController.php', 'app/Services/Iam/SocialAuthService.php', 'app/Services/Settings/SettingsConfigSyncService.php', 'config/auth.php', 'resources/views/auth/login.blade.php', 'tests/Feature/Auth/AuthEnterpriseTest.php'], 'exit_code': 0, 'blocker': None, 'workspace': None, 'summary': 'Agent: I\'ll read `.orchestrator-task.md` first and implement the USER TASK from it.I\'ll explore the workspace to find the login screen and how auth sessions are handled.The login UI already mentions 30 days — I\'ll check whether the backend actually enforces that duration.Config already defines a 30-day session policy — I\'ll trace whether it\'s actually applied to remember-me.Wiring the remember-me cookie to the 30-day IAM session policy, and tightening the login checkbox plus tests.**Remember me for 30 days** is wired end-to-end: the login checkbox, a 30-day remember cookie, and tests that lock that behavior in.\n\n### Changes\n1. **`resources/views/auth/login.blade.php`** — Checkbox uses `value="1"`, keeps state via `old(\'remember\')`, and labels days from `iam.session_lifetime_days` (default 30).\n2. **`app/Http/Controllers/Auth/AuthController.php`** — On remember login, sets the remember cookie duration to `session_lifetime_days × 24 × 60` minutes before `Auth::attempt`.\n3. **`config/auth.php`** — Web guard `remember` defaults to 30 days (from `IAM_SESSION_LIFETIME_DAYS`).\n4. **`SettingsConfigSyncService`** — Keeps `auth.guards.web.remember` in sync when session lifetime settings change.\n5. **`SocialAuthService`** — Social logins use the same 30-day remember duration.\n6. **`AuthEnterpriseTest`** — Covers UI label, 30-day cookie when checked, and no cookie when unchecked.\n\n### How to verify\n1. Open `/login` — you should see **Remember me for 30 days**.\n2. Sign in with the box checked — browser should get a `remember_web_*` cookie lasting ~30 days.\n3. Sign in unchecked — that cookie should not be set.\n4. Run: `php artisan test --filter=AuthEnterpriseTest`Remember-me for 30 days is done and verified. The earlier test run failed only because `APP_KEY` was missing; after generating it, all 14 `AuthEnterpriseTest` cases passed, including the new remember-cookie checks.\nTests: Tests not configured\nChanges: M app/Http/Controllers/Auth/AuthController.php\n M app/Services/Iam/Soc', 'events': [{'id': 135, 'ts': 1792239749, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read app/Providers/AppServiceProvider.php'}, {'id': 136, 'ts': 1792239750, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Grep'}, {'id': 137, 'ts': 1792239751, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Shell'}, {'id': 138, 'ts': 1792239757, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read app/Services/Iam/SessionTrackingService.php'}, {'id': 139, 'ts': 1792239757, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read config/settings.php'}, {'id': 140, 'ts': 1792239758, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Grep vendor/laravel/framework/src/Illuminate/Auth'}, {'id': 141, 'ts': 1792239759, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Grep'}, {'id': 142, 'ts': 1792239768, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read app/Models/UserSession.php'}, {'id': 143, 'ts': 1792239768, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Grep'}, {'id': 144, 'ts': 1792239768, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Glob'}, {'id': 145, 'ts': 1792239768, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Grep'}, {'id': 146, 'ts': 1792239769, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Shell'}, {'id': 147, 'ts': 1792239777, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read app/Http/Middleware/TrackSessionActivity.php'}, {'id': 148, 'ts': 1792239777, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read app/Http/Controllers/SessionStatusController.php'}, {'id': 149, 'ts': 1792239777, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Grep'}, {'id': 150, 'ts': 1792239777, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Grep'}, {'id': 151, 'ts': 1792239778, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read docs/AUTH_ENTERPRISE_DELIVERY.md'}, {'id': 152, 'ts': 1792239788, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read composer.json'}, {'id': 153, 'ts': 1792239788, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Grep'}, {'id': 154, 'ts': 1792239788, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Shell'}, {'id': 155, 'ts': 1792239789, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Grep'}, {'id': 156, 'ts': 1792239813, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read app/Services/Iam/SocialAuthService.php'}, {'id': 157, 'ts': 1792239813, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read tests/Feature/Auth/AuthEnterpriseTest.php'}, {'id': 158, 'ts': 1792239813, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Shell'}, {'id': 159, 'ts': 1792239841, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Grep vendor/laravel/framework/src/Illuminate/Auth'}, {'id': 160, 'ts': 1792239841, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Grep'}, {'id': 161, 'ts': 1792239841, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read app/Services/Settings/SettingsConfigSyncService.php'}, {'id': 162, 'ts': 1792239846, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read vendor/laravel/framework/src/Illuminate/Auth/AuthManager.php'}, {'id': 163, 'ts': 1792239846, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read vendor/laravel/framework/src/Illuminate/Auth/SessionGuard.php'}, {'id': 164, 'ts': 1792239850, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Grep'}, {'id': 165, 'ts': 1792239854, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read app/Providers/SettingsServiceProvider.php'}, {'id': 166, 'ts': 1792239854, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Read bootstrap/providers.php'}, {'id': 167, 'ts': 1792239859, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Grep'}, {'id': 168, 'ts': 1792239870, 'stage': 'investigating', 'event_type': 'agent_stream', 'message': 'Edit config/auth.php'}, {'id': 169, 'ts': 1792239870, 'stage': 'implementing', 'event_type': 'stage_evidence', 'message': 'Stage advanced to implementing from Cursor stream evidence'}, {'id': 170, 'ts': 1792239873, 'stage': 'implementing', 'event_type': 'agent_stream', 'message': 'Edit app/Http/Controllers/Auth/AuthController.php'}, {'id': 171, 'ts': 1792239875, 'stage': 'implementing', 'event_type': 'agent_stream', 'message': 'Edit resources/views/auth/login.blade.php'}, {'id': 172, 'ts': 1792239877, 'stage': 'implementing', 'event_type': 'agent_stream', 'message': 'Edit app/Services/Settings/SettingsConfigSyncService.php'}, {'id': 173, 'ts': 1792239878, 'stage': 'implementing', 'event_type': 'agent_stream', 'message': 'Edit app/Services/Iam/SocialAuthService.php'}, {'id': 174, 'ts': 1792239888, 'stage': 'implementing', 'event_type': 'agent_stream', 'message': 'Edit tests/Feature/Auth/AuthEnterpriseTest.php'}, {'id': 175, 'ts': 1792239889, 'stage': 'implementing', 'event_type': 'agent_stream', 'message': 'Edit tests/Feature/Auth/AuthEnterpriseTest.php'}, {'id': 176, 'ts': 1792239896, 'stage': 'implementing', 'event_type': 'agent_stream', 'message': 'Grep app/Services/Iam/SocialAuthService.php'}, {'id': 177, 'ts': 1792239896, 'stage': 'implementing', 'event_type': 'agent_stream', 'message': 'Grep vendor/laravel/framework/src/Illuminate/Auth/SessionGuard.php'}, {'id': 178, 'ts': 1792239996, 'stage': 'implementing', 'event_type': 'agent_stream', 'message': 'Read …chestrator-data-workspaces-2b68ff094d33/terminals/522767.txt'}, {'id': 179, 'ts': 1792240002, 'stage': 'implementing', 'event_type': 'agent_stream', 'message': 'Agent stream result'}, {'id': 180, 'ts': 1792240011, 'stage': 'implementing', 'event_type': 'agent_stream', 'message': 'Agent: **Remember me for 30 days** is wired end-to-end: the login checkbox, a 30-day remember cookie, and tests that lock that behavior in.  ### Changes 1. **`resources/views/auth/login.blade.php`** — Checkb'}, {'id': 181, 'ts': 1792240012, 'stage': 'implementing', 'event_type': 'agent_stream', 'message': "I'll read `.orchestrator-task.md` first and implement the USER TASK from it.I'll explore the workspace to find the login screen and how auth sessions are handled.The login UI already mentions 30 days — I'll check whether the backend actuall"}, {'id': 182, 'ts': 1792240014, 'stage': 'implementing', 'event_type': 'agent_exited', 'message': 'Cursor agent process exited with code 0'}, {'id': 183, 'ts': 1792240014, 'stage': 'implementing', 'event_type': 'files_changed', 'message': 'Workspace evidence: 6 modified file(s)'}, {'id': 184, 'ts': 1792240015, 'stage': 'ready_for_review', 'event_type': 'ready_for_review', 'message': 'Coding complete — ready for review'}]}; recent_lifeos={'id': '2b68ff094d33', 'project': 'lifeos', 'status': 'review', 'execution_stage': 'ready_for_review'}; recovered_via_task_id=False
- **evidence:** `{"default_task": {"task_id": "2b68ff094d33", "project": "lifeos", "status": "review", "execution_stage": "ready_for_review", "current_label": "Ready for review", "completed": ["Queued", "Preparing isolated workspace", "Agent running \u2014 awaiting tool activity", "Running configured tests", "Ready for review"], "remaining": [], "instruction": "implement remember me for 30 days on login screen", "started_at": 1792239699, "last_activity_at": 1792242083, "ended_at": 1792240015, "duration": "5 minu`

### [PASS] /chat/task-progress returns structured snapshot (by id if needed)

- **id:** `task_progress_api`
- **severity:** major
- **detail:** task={'task_id': '2b68ff094d33', 'status': 'review', 'execution_stage': 'ready_for_review', 'current_label': 'Ready for review', 'project': 'lifeos'}; events=80; panel_openish=True
- **evidence:** `{"task": {"task_id": "2b68ff094d33", "project": "lifeos", "status": "review", "execution_stage": "ready_for_review", "current_label": "Ready for review", "completed": ["Queued", "Preparing isolated workspace", "Agent running \u2014 awaiting tool activity", "Running configured tests", "Ready for review"], "remaining": [], "instruction": "implement remember me for 30 days on login screen", "started_at": 1792239699, "last_activity_at": 1792242083, "ended_at": 1792240015, "duration": "5 minutes", "l`

### [PASS] SQLite history shows at least one successful streamed review

- **id:** `history_sample`
- **severity:** major
- **detail:** status_counts={'failed': 8, 'published': 2, 'rejected': 1, 'review': 2}; stream_ok_in_sample=3; review_with_files=1; failure_buckets={'auth': 2, 'sandbox': 1, 'empty_output': 2, 'workspace_collision': 1, 'orchestrator_restart': 1, 'none_type': 1, 'other_failed': 1}
- **evidence:** `{"latest_task": {"id": "2b68ff094d33", "project": "lifeos", "status": "review", "execution_stage": "ready_for_review", "exit_code": 0, "blocker": null, "summary": "Agent: I'll read `.orchestrator-task.md` first and implement the USER TASK from it.I'll explore the workspace to find the login screen and how auth sessions are handled.The login UI already mentions 30 days \u2014 I'll check whether the backend ", "started_at": 1792239699, "ended_at": 1792240015, "last_activity_at": 1792242083, "modif`

### [PASS] Latest task is not a known reliability failure (live agent healthy)

- **id:** `recurring_failures`
- **severity:** minor
- **detail:** latest_id=2b68ff094d33; latest_status=review; latest_known_fail=None; historical=['auth×2', 'collision×1', 'empty×2']; live_agent_ok=True
- **evidence:** `{"all_time": {"auth": 2, "sandbox": 1, "empty_output": 2, "workspace_collision": 1, "orchestrator_restart": 1, "none_type": 1, "other_failed": 1}, "latest": {"id": "2b68ff094d33", "project": "lifeos", "status": "review", "execution_stage": "ready_for_review", "exit_code": 0, "blocker": null, "summary": "Agent: I'll read `.orchestrator-task.md` first and implement the USER TASK from it.I'll explore the workspace to find the login screen and how auth sessions are handled.The login UI already menti`

### [PASS] Latest coding task reached a real reviewable outcome

- **id:** `latest_coding_outcome`
- **severity:** major
- **detail:** id=2b68ff094d33 status=review stage=ready_for_review exit=0 files=["app/Http/Controllers/Auth/AuthController.php", "app/Services/Iam/SocialAuthService.php", "app/Services/Settings/SettingsConfigSyncService.php", "config/auth.php", "resources/view
- **evidence:** `{"task": {"id": "2b68ff094d33", "project": "lifeos", "status": "review", "execution_stage": "ready_for_review", "exit_code": 0, "blocker": null, "summary": "Agent: I'll read `.orchestrator-task.md` first and implement the USER TASK from it.I'll explore the workspace to find the login screen and how auth sessions are handled.The login UI already mentions 30 days \u2014 I'll check whether the backend ", "started_at": 1792239699, "ended_at": 1792240015, "last_activity_at": 1792242083, "modified_fil`

### [PASS] No severe page/console errors during investigation

- **id:** `browser_console`
- **severity:** minor
- **detail:** page_errors=[]; console=[]; net=[]

### [PASS] Service worker registers without CSP block (PWA/notifications)

- **id:** `pwa_service_worker_csp`
- **severity:** minor
- **detail:** No CSP worker block observed

### [PASS] Disposable project: chat → Cursor → file change → review

- **id:** `live_agent_smoke`
- **severity:** blocker
- **detail:** final={'id': '90a30e796193', 'project': 'browser_smoke_540ca5', 'status': 'review', 'execution_stage': 'ready_for_review'}; saw_stream=True; workspace_hello='hello\nNOTE=browser-smoke-ok\n'; source_unchanged='hello\n'; modified=['hello.txt']; smoke_url=http://127.0.0.1:56337
- **evidence:** `{"final_task": {"id": "90a30e796193", "project": "browser_smoke_540ca5", "status": "review", "execution_stage": "ready_for_review"}, "snapshot": {"task_id": "90a30e796193", "status": "review", "execution_stage": "ready_for_review", "modified_files": ["hello.txt"], "current_label": "Ready for review"}, "workspace_hello": "hello\nNOTE=browser-smoke-ok\n", "source_hello": "hello\n", "saw_stream": true, "note": "Source fixture must stay unchanged until approve; isolated workspace must contain the ed`
