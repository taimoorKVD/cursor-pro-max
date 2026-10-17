"""
Deep browser investigation of the core product loop:

  select project → assign coding work via chat → Cursor CLI runs →
  stream/progress feedback → review/approve readiness

Runs against the LIVE orchestrator (default http://127.0.0.1:8000).
Produces docs/golive-browser/GOLIVE_BROWSER_INVESTIGATION.md.

Usage:
  $env:ORCH_BROWSER_RUN='1'
  .\\.venv\\Scripts\\python.exe -m pytest tests/browser -m browser_live -q --tb=short
  # optional long agent smoke on a disposable fixture:
  $env:ORCH_BROWSER_LIVE_AGENT='1'
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.browser.investigation_lib import (
    ROOT,
    CheckResult,
    analyze_sqlite_history,
    find_stuck_phrases,
    new_report,
    wait_until,
    write_report,
)

pytestmark = pytest.mark.browser_live


def _login(page: Page, base_url: str, password: str) -> None:
    page.goto(f"{base_url}/chat", wait_until="domcontentloaded")
    # Already authenticated sessions land on the chat shell.
    if page.locator("#txt").count() and page.locator("#txt").is_visible():
        return
    # Cookie login first — survives UI timing glitches after service restart.
    api = page.request.post(
        f"{base_url}/chat/login",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"password": password}),
    )
    if api.status == 429:
        raise AssertionError("Webchat login rate-limited (too many wrong attempts). Wait 15 minutes.")
    if not api.ok:
        # Fall back to form submit for clearer error surface.
        page.wait_for_selector("#pw", timeout=15_000)
        page.locator("#pw").fill(password)
        page.locator("#btn").click()
        page.wait_for_selector("#txt", timeout=25_000)
        return
    page.goto(f"{base_url}/chat", wait_until="domcontentloaded")
    page.wait_for_selector("#txt", timeout=20_000)


def _api_json(page: Page, path: str) -> dict:
    return page.evaluate(
        """async (path) => {
          const r = await fetch(path, {cache: 'no-store'});
          const text = await r.text();
          let body = null;
          try { body = JSON.parse(text); } catch (e) { body = {raw: text.slice(0, 400)}; }
          return {status: r.status, body};
        }""",
        path,
    )


def _send_chat(page: Page, text: str) -> None:
    page.locator("#txt").fill(text)
    page.locator("#send").click()
    # Busy indicator should appear briefly; wait until send re-enabled.
    page.wait_for_function(
        "() => !document.getElementById('send')?.disabled",
        timeout=60_000,
    )


def _out_bubbles(page: Page) -> list[str]:
    """Agent/outbound bubbles use .msg-bubble.agent in webchat_pages.py."""
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('#log .msg-bubble.agent .msg-bubble-text, #log .msg-bubble.agent'))
            .map(el => (el.innerText || el.textContent || '').trim())
            .filter(Boolean)"""
    )


def _all_bubble_texts(page: Page) -> list[str]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('#log .msg-bubble .msg-bubble-text, #log .msg-bubble'))
            .map(el => (el.innerText || el.textContent || '').trim())
            .filter(Boolean)"""
    )


def _select_project(page: Page, project_id: str) -> None:
    """Switch project via API (authoritative) then sync UI; click is best-effort."""
    result = page.evaluate(
        """async (id) => {
          const r = await fetch('/chat/active-project', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({project: id}),
          });
          const body = await r.json().catch(() => ({}));
          return {status: r.status, body};
        }""",
        project_id,
    )
    if result.get("status") != 200:
        raise AssertionError(f"active-project failed: {result}")
    # Best-effort UI sync — sidebar items can sit outside the Playwright viewport.
    menu = page.locator("#menuBtn")
    if menu.count() and menu.is_visible():
        menu.click()
    item = page.locator(f'#projectList button.proj-item[data-id="{project_id}"]')
    if item.count():
        try:
            item.first.scroll_into_view_if_needed(timeout=3_000)
            item.first.click(timeout=5_000, force=True)
        except Exception:  # noqa: BLE001
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector("#txt", timeout=15_000)
    page.wait_for_timeout(500)


def _latest_message_id(page: Page) -> int:
    data = _api_json(page, "/chat/messages?after=0")
    msgs = ((data.get("body") or {}).get("messages")) or []
    return max((int(m.get("id") or 0) for m in msgs), default=0)


def _new_outbound_since(page: Page, after_id: int, timeout_sec: float = 60.0) -> list[str]:
    found: list[str] = []

    def _poll() -> bool:
        nonlocal found
        data = _api_json(page, f"/chat/messages?after={after_id}")
        msgs = ((data.get("body") or {}).get("messages")) or []
        found = [
            str(m.get("text") or "")
            for m in msgs
            if m.get("direction") == "out" and str(m.get("text") or "").strip()
        ]
        return bool(found)

    wait_until(_poll, timeout_sec=timeout_sec, interval=1.0)
    return found


def test_golive_deep_investigation(page: Page, base_url: str, webchat_password: str, report_dir: Path):
    report = new_report(base_url)
    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_requests: list[str] = []

    page.on("console", lambda msg: console_errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on(
        "response",
        lambda resp: failed_requests.append(f"{resp.status} {resp.url}")
        if resp.status >= 400 and "/chat/" in resp.url
        else None,
    )

    # --- 1) Health endpoint ---
    health = page.request.get(f"{base_url}/health")
    report.add(
        CheckResult(
            id="health",
            title="Orchestrator /health responds",
            ok=health.ok and "ok" in health.text().lower(),
            severity="blocker",
            detail=f"status={health.status} body={health.text()[:120]}",
            evidence={"status": health.status},
        )
    )

    # --- 2) Login + shell ---
    _login(page, base_url, webchat_password)
    chat_ready = page.locator("#txt").is_visible() and page.locator("#send").is_visible()
    report.add(
        CheckResult(
            id="login_shell",
            title="Web chat login reaches composer",
            ok=chat_ready,
            severity="blocker",
            detail="Composer #txt/#send visible after login" if chat_ready else "Composer missing after login",
        )
    )
    assert chat_ready, "Chat shell did not load after login"

    # Capture screenshot of ready shell
    page.screenshot(path=str(report_dir / "01-chat-shell.png"), full_page=True)

    # --- 3) /chat/status: agent, dry_run, projects ---
    status = _api_json(page, "/chat/status")
    body = status.get("body") or {}
    agent_ok = bool(body.get("agent_ok"))
    dry_run = bool(body.get("dry_run"))
    auth = body.get("agent_auth") or {}
    projects = body.get("project_list") or []
    project_ids = {p.get("id") for p in projects}

    report.add(
        CheckResult(
            id="status_endpoint",
            title="/chat/status authenticated payload",
            ok=status.get("status") == 200 and body.get("ok") is True,
            severity="blocker",
            detail=f"HTTP {status.get('status')}; dry_run={dry_run}; agent_ok={agent_ok}; projects={len(projects)}",
            evidence={
                "dry_run": dry_run,
                "agent_ok": agent_ok,
                "agent_detail": body.get("agent_detail"),
                "agent_auth": auth,
                "pending_jobs": body.get("pending_jobs"),
                "active_task": body.get("active_task"),
            },
        )
    )
    report.add(
        CheckResult(
            id="live_mode",
            title="DRY_RUN is false (real Cursor runs enabled)",
            ok=not dry_run,
            severity="blocker",
            detail="DRY_RUN=false" if not dry_run else "DRY_RUN=true — coding agent will not run for real",
        )
    )
    report.add(
        CheckResult(
            id="agent_cli",
            title="Cursor agent CLI is available",
            ok=agent_ok,
            severity="blocker",
            detail=str(body.get("agent_detail") or ("ok" if agent_ok else "agent missing")),
        )
    )
    report.add(
        CheckResult(
            id="agent_auth",
            title="Cursor agent authentication is healthy",
            ok=bool(auth.get("ok")),
            severity="blocker",
            detail=f"mode={auth.get('mode')} email={auth.get('email')} ok={auth.get('ok')}",
            evidence=dict(auth),
        )
    )
    report.add(
        CheckResult(
            id="lifeos_registered",
            title="LifeOS project is registered",
            ok="lifeos" in project_ids,
            severity="blocker",
            detail=f"projects={sorted(project_ids)}",
        )
    )

    # Status pill text in UI
    pill = (page.locator("#pillText").inner_text() or "").strip()
    report.add(
        CheckResult(
            id="status_pill",
            title="Header status pill reflects live agent health",
            ok=("LIVE" in pill.upper() or "live" in pill.lower()) and "agent" in pill.lower(),
            severity="major",
            detail=f"pillText={pill!r}",
        )
    )

    # --- 4) Select LifeOS + isolation ---
    # Force a real project change so we exercise switch_project clearing active_task_id
    # (re-selecting the already-active project would skip that path).
    other = next((pid for pid in sorted(project_ids) if pid != "lifeos"), None)
    if other:
        _select_project(page, other)
        page.wait_for_timeout(300)
    _select_project(page, "lifeos")
    after_switch = _api_json(page, "/chat/status")
    active_project = (after_switch.get("body") or {}).get("active_project")
    active_task_after_switch = (after_switch.get("body") or {}).get("active_task")
    report.add(
        CheckResult(
            id="select_lifeos",
            title="Selecting LifeOS sets active_project session",
            ok=active_project == "lifeos",
            severity="blocker",
            detail=f"active_project={active_project!r}; active_task_after_switch={active_task_after_switch!r}",
        )
    )
    page.screenshot(path=str(report_dir / "02-lifeos-selected.png"), full_page=True)

    # --- 5) Conversational status probe (no new coding task) ---
    after_id = _latest_message_id(page)
    _send_chat(
        page,
        "What's the status of my latest LifeOS task? What's remaining, and what files changed?",
    )
    new_outs = _new_outbound_since(page, after_id, timeout_sec=60)
    joined = "\n".join(new_outs[-5:])
    stuck = find_stuck_phrases(new_outs)
    evidence_ish = bool(
        re.search(
            r"review|ready|failed|queued|running|modified|file|stage|progress|task|approve|publish",
            joined,
            re.I,
        )
    )
    invents_fake_progress = bool(
        re.search(r"just a few minutes|almost done|95%|nearly finished", joined, re.I)
    ) and not evidence_ish

    report.add(
        CheckResult(
            id="status_followup",
            title="Status follow-up gets an evidence-shaped reply (not empty/stuck)",
            ok=bool(new_outs) and evidence_ish and not invents_fake_progress,
            severity="major",
            detail=(joined[:400] if joined else "no outbound reply within 60s"),
            evidence={"stuck_phrases": stuck, "new_out_count": len(new_outs)},
        )
    )

    # --- 6) Progress panel + task-progress API ---
    # Product gap probe: switch_project clears active_task_id, so the panel can go idle
    # even when LifeOS still has a reviewable task (matches "is it done?" confusion).
    progress_toggle = page.locator("#progressToggle")
    if progress_toggle.count():
        try:
            progress_toggle.click(timeout=5_000, force=True)
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(500)
    prog = _api_json(page, "/chat/task-progress")
    prog_body = prog.get("body") or {}
    task_snap = prog_body.get("task")
    events = prog_body.get("events") or []
    panel_visible = page.locator("#progressPanel").evaluate(
        "el => el && el.classList.contains('open')"
    )
    status_after = _api_json(page, "/chat/status")
    recent = (status_after.get("body") or {}).get("recent_tasks") or []
    lifeos_recent = next((t for t in recent if t.get("project") == "lifeos"), None)
    # If session lost active task, fetch progress by explicit id (operator still needs this).
    prog_by_id = None
    if not task_snap and lifeos_recent and lifeos_recent.get("id"):
        prog_by_id = _api_json(page, f"/chat/task-progress?task_id={lifeos_recent['id']}")
        task_snap = ((prog_by_id.get("body") or {}).get("task")) or task_snap
        events = ((prog_by_id.get("body") or {}).get("events")) or events

    report.add(
        CheckResult(
            id="task_progress_after_project_switch",
            title="After selecting LifeOS, progress API still surfaces the latest LifeOS task",
            ok=bool(task_snap) or bool(lifeos_recent),
            severity="major",
            detail=(
                "GAP: project switch clears active_task_id — default /chat/task-progress "
                f"returned task={prog_body.get('task')!r}; recent_lifeos={lifeos_recent}; "
                f"recovered_via_task_id={bool(prog_by_id and (prog_by_id.get('body') or {}).get('task'))}"
            ),
            evidence={
                "default_task": prog_body.get("task"),
                "lifeos_recent": lifeos_recent,
                "recovered_task": task_snap,
                "event_count": len(events),
                "panel_openish": panel_visible,
            },
        )
    )
    if prog_body.get("task") is None and lifeos_recent:
        report.gaps.append(
            "[major] Selecting a project clears active_task_id, so the Live progress panel "
            "goes idle even when that project still has a review/running task — operators "
            "cannot tell if work finished without asking in chat."
        )

    report.add(
        CheckResult(
            id="task_progress_api",
            title="/chat/task-progress returns structured snapshot (by id if needed)",
            ok=prog.get("status") == 200 and (prog_body.get("ok") is True) and bool(task_snap),
            severity="major",
            detail=(
                f"task={None if not task_snap else {k: task_snap.get(k) for k in ('task_id','status','execution_stage','current_label','project')}}"
                f"; events={len(events)}; panel_openish={panel_visible}"
            ),
            evidence={"task": task_snap, "event_count": len(events)},
        )
    )

    if task_snap and (task_snap.get("status") in {"queued", "running"}):
        # Mid-run: poll for stream evidence for up to 90s
        saw_stream = False
        stages_seen: list[str] = []
        for _ in range(18):
            snap = _api_json(page, "/chat/task-progress")
            tb = (snap.get("body") or {}).get("task") or {}
            evs = (snap.get("body") or {}).get("events") or []
            stage = tb.get("execution_stage") or ""
            if stage:
                stages_seen.append(stage)
            if any((e.get("event_type") == "agent_stream") for e in evs):
                saw_stream = True
                break
            if tb.get("status") in {"review", "failed", "canceled", "published"}:
                break
            time.sleep(5)
        report.add(
            CheckResult(
                id="midrun_stream",
                title="Active task emits agent_stream events (or finishes quickly)",
                ok=saw_stream or (task_snap.get("status") not in {"queued", "running"}),
                severity="major",
                detail=f"saw_stream={saw_stream}; stages={stages_seen[-8:]}",
            )
        )
        page.screenshot(path=str(report_dir / "03-midrun-progress.png"), full_page=True)

    # --- 7) Historical reliability from SQLite ---
    hist = analyze_sqlite_history()
    latest = hist.get("latest_task") or {}
    buckets = hist.get("failure_buckets") or {}
    auth_failures = int(buckets.get("auth") or 0)
    collision = int(buckets.get("workspace_collision") or 0)
    empty_out = int(buckets.get("empty_output") or 0)
    stream_ok = int(hist.get("stream_ok_tasks_in_sample") or 0)

    report.add(
        CheckResult(
            id="history_sample",
            title="SQLite history shows at least one successful streamed review",
            ok=bool(hist.get("ok")) and (stream_ok >= 1 or hist.get("review_with_files", 0) >= 1),
            severity="major",
            detail=(
                f"status_counts={hist.get('status_counts')}; "
                f"stream_ok_in_sample={stream_ok}; "
                f"review_with_files={hist.get('review_with_files')}; "
                f"failure_buckets={buckets}"
            ),
            evidence={"latest_task": latest, "latest_events": hist.get("latest_events")},
        )
    )

    # Historical buckets stay visible, but go-live major only if the *latest* task
    # failed with a known mode while live agent/auth are unhealthy. Prior auth /
    # collision / empty-output rows are covered by quarantined remove, empty-output
    # retry + stream recovery, and current API-key auth.
    from tests.browser.investigation_lib import KNOWN_FAILURE_BUCKETS

    latest_blob = " ".join(
        str(x or "")
        for x in (
            (latest or {}).get("summary"),
            (latest or {}).get("blocker"),
            (latest or {}).get("status"),
        )
    )
    latest_known_fail = False
    latest_fail_kind = None
    if (latest or {}).get("status") in {"failed", "rejected"}:
        for name, rx in KNOWN_FAILURE_BUCKETS.items():
            if name in {"auth", "workspace_collision", "empty_output", "sandbox"} and rx.search(
                latest_blob
            ):
                latest_known_fail = True
                latest_fail_kind = name
                break

    recurring = []
    if auth_failures:
        recurring.append(f"auth×{auth_failures}")
    if collision:
        recurring.append(f"collision×{collision}")
    if empty_out:
        recurring.append(f"empty×{empty_out}")
    live_ok = agent_ok and bool(auth.get("ok")) and not dry_run
    report.add(
        CheckResult(
            id="recurring_failures",
            title="Latest task is not a known reliability failure (live agent healthy)",
            ok=(not latest_known_fail) and live_ok,
            severity="major" if latest_known_fail or not live_ok else "minor",
            detail=(
                f"latest_id={(latest or {}).get('id')}; latest_status={(latest or {}).get('status')}; "
                f"latest_known_fail={latest_fail_kind}; historical={recurring or ['clean']}; "
                f"live_agent_ok={live_ok}"
            ),
            evidence={"all_time": buckets, "latest": latest},
        )
    )
    if recurring and not latest_known_fail and live_ok:
        report.notes.append(
            "SQLite still has older auth/collision/empty-output failures, but the latest "
            "task is healthy and live agent auth is OK. Mitigations: workspace quarantine, "
            "empty-output retry + stream recovery, CSP worker-src."
        )

    # Remember-me style task specifically (if present)
    remember = None
    if latest and "remember" in str(latest.get("summary") or "").lower():
        remember = latest
    else:
        # Scan sample via API recent_tasks + sqlite already loaded
        for ev_task in [latest]:
            if ev_task and (ev_task.get("status") == "review") and ev_task.get("modified_files"):
                remember = ev_task
                break
    if remember:
        done = remember.get("status") in {"review", "published"} and (
            remember.get("modified_files") or remember.get("execution_stage") == "ready_for_review"
        )
        report.add(
            CheckResult(
                id="latest_coding_outcome",
                title="Latest coding task reached a real reviewable outcome",
                ok=done,
                severity="major",
                detail=(
                    f"id={remember.get('id')} status={remember.get('status')} "
                    f"stage={remember.get('execution_stage')} exit={remember.get('exit_code')} "
                    f"files={str(remember.get('modified_files') or '')[:180]}"
                ),
                evidence={"task": remember},
            )
        )
        report.notes.append(
            "Your recent LifeOS coding run is recorded in SQLite. "
            "If the UI felt 'stuck', compare chat wording vs task status/events — "
            "a finished review task can still look vague if follow-ups don't cite evidence."
        )

    # --- 8) Browser console / network hygiene ---
    chat_console = [e for e in console_errors if "favicon" not in e.lower()]
    chat_net = [u for u in failed_requests if "favicon" not in u.lower()]
    csp_sw = any("sw.js" in e and "Content Security Policy" in e for e in chat_console)
    report.add(
        CheckResult(
            id="browser_console",
            title="No severe page/console errors during investigation",
            ok=not page_errors and (len(chat_console) <= 2 or (csp_sw and len(chat_console) <= 4)),
            severity="minor",
            detail=f"page_errors={page_errors[:5]}; console={chat_console[:8]}; net={chat_net[:8]}",
        )
    )
    report.add(
        CheckResult(
            id="pwa_service_worker_csp",
            title="Service worker registers without CSP block (PWA/notifications)",
            ok=not csp_sw,
            severity="minor",
            detail=(
                "CSP blocks /chat/sw.js worker — install/notifications may be degraded"
                if csp_sw
                else "No CSP worker block observed"
            ),
        )
    )

    # --- 9) Optional live disposable agent smoke ---
    if os.getenv("ORCH_BROWSER_LIVE_AGENT", "").strip() in {"1", "true", "yes"}:
        _run_disposable_agent_smoke(page, report, report_dir)
    else:
        report.notes.append(
            "Skipped live Cursor agent smoke (set ORCH_BROWSER_LIVE_AGENT=1 to run a disposable fixture task)."
        )

    # --- Finalize + persist ---
    # Product gap: user cannot tell done vs stuck from chat alone if replies are thin.
    if not evidence_ish:
        report.gaps.append(
            "[major] Chat status replies are not clearly citing task evidence "
            "(stage/files/exit) — this matches the 'looks busy but unclear' product failure."
        )

    report.finalize()
    json_path, md_path = write_report(report, report_dir)
    page.screenshot(path=str(report_dir / "99-final.png"), full_page=True)

    # Soft assert: blockers must pass for pytest green; majors are reported in the doc.
    blockers = [c for c in report.checks if not c.ok and c.severity == "blocker"]
    assert not blockers, (
        "Go-live blockers failed:\n"
        + "\n".join(f"- {c.title}: {c.detail}" for c in blockers)
        + f"\nSee {md_path}"
    )

    # Always write a machine-readable summary for humans reading pytest output
    print(json.dumps({"go_live_ready": report.go_live_ready, "report": str(md_path), "gaps": report.gaps}, indent=2))


def _run_disposable_agent_smoke(page: Page, report, report_dir: Path) -> None:
    """End-to-end Cursor smoke on an ephemeral uvicorn (does NOT mutate production projects.json)."""
    import json as _json
    import socket
    import subprocess
    import sys
    import tempfile
    import urllib.request

    fixture = Path(tempfile.mkdtemp(prefix="orch-browser-smoke-"))
    work = Path(tempfile.mkdtemp(prefix="orch-browser-work-"))
    data_dir = Path(tempfile.mkdtemp(prefix="orch-browser-data-"))
    (fixture / "hello.txt").write_text("hello\n", encoding="utf-8")
    smoke_id = f"browser_smoke_{uuid.uuid4().hex[:6]}"
    projects_file = data_dir / "projects.json"
    projects_file.write_text(
        _json.dumps(
            {
                smoke_id: {
                    "path": str(fixture).replace("\\", "/"),
                    "type": "local",
                    "test_command": "",
                    "allow_push": False,
                    "allow_deploy": False,
                    "deploy_command": "",
                    "display_name": smoke_id,
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    smoke_url = f"http://127.0.0.1:{port}"
    password = "browser-smoke-password-ok"
    env = {
        **os.environ,
        "DATABASE_FILE": str(data_dir / "smoke.sqlite"),
        "WORK_ROOT": str(work),
        "PROJECTS_FILE": str(projects_file),
        "WEBCHAT_PASSWORD": password,
        "ORCHESTRATOR_WORKER": "true",
        "TELEGRAM_POLLING_ENABLED": "false",
        "META_WEBHOOK_SYNC_ENABLED": "false",
        "REPLY_LOG_ENABLED": "false",
        "DRY_RUN": "false",
        "AGENT_OUTPUT_FORMAT": "stream-json",
        "GROQ_CHAT_ENABLED": "false",
        "GROQ_API_KEY": "",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    smoke_page = None
    try:
        ok_boot = False
        for _ in range(40):
            try:
                with urllib.request.urlopen(f"{smoke_url}/health", timeout=1) as r:
                    if r.status == 200:
                        ok_boot = True
                        break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        if not ok_boot:
            report.add(
                CheckResult(
                    id="live_agent_smoke",
                    title="Disposable project: chat → Cursor → file change → review",
                    ok=False,
                    severity="blocker",
                    detail=f"Ephemeral uvicorn failed to boot on {smoke_url}",
                )
            )
            return

        # Reuse the pytest-playwright browser (nested sync_playwright is forbidden).
        smoke_page = page.context.new_page()
        _login(smoke_page, smoke_url, password)
        _select_project(smoke_page, smoke_id)
        instruction = (
            f"On {smoke_id}, edit hello.txt and append a line exactly: NOTE=browser-smoke-ok. "
            "Do not create other files. When done, summarize the change."
        )
        _send_chat(smoke_page, instruction)
        terminal = {"review", "failed", "canceled", "published", "rejected"}
        final_task = None
        saw_stream = False
        deadline = time.time() + 240
        while time.time() < deadline:
            st = _api_json(smoke_page, "/chat/status")
            active = (st.get("body") or {}).get("active_task")
            prog = _api_json(smoke_page, "/chat/task-progress")
            events = (prog.get("body") or {}).get("events") or []
            if any(e.get("event_type") == "agent_stream" for e in events):
                saw_stream = True
            if active and active.get("status") in terminal:
                final_task = active
                break
            for t in (st.get("body") or {}).get("recent_tasks") or []:
                if t.get("project") == smoke_id and t.get("status") in terminal:
                    final_task = t
                    break
            if final_task:
                break
            time.sleep(5)
        smoke_page.screenshot(path=str(report_dir / "04-agent-smoke.png"), full_page=True)
        # Local projects are edited in an isolated WORK_ROOT copy — not the source fixture.
        # Prove the change via task snapshot + workspace file evidence.
        tid = (final_task or {}).get("id")
        prog_final = _api_json(smoke_page, f"/chat/task-progress?task_id={tid}") if tid else {}
        snap = ((prog_final.get("body") or {}).get("task")) or {}
        modified = snap.get("modified_files") or snap.get("files") or []
        if isinstance(modified, str):
            try:
                modified = _json.loads(modified)
            except Exception:  # noqa: BLE001
                modified = [modified]
        workspace_hello = ""
        ws_candidates = list(work.glob("*/hello.txt"))
        for hp in ws_candidates:
            workspace_hello = hp.read_text(encoding="utf-8")
            if "NOTE=browser-smoke-ok" in workspace_hello:
                break
        source_hello = (fixture / "hello.txt").read_text(encoding="utf-8")
        file_ok = ("NOTE=browser-smoke-ok" in workspace_hello) or any(
            "hello.txt" in str(p) for p in (modified or [])
        )
        status_ok = bool(final_task) and final_task.get("status") == "review"
        report.add(
            CheckResult(
                id="live_agent_smoke",
                title="Disposable project: chat → Cursor → file change → review",
                ok=status_ok and file_ok and saw_stream,
                severity="blocker",
                detail=(
                    f"final={final_task}; saw_stream={saw_stream}; "
                    f"workspace_hello={workspace_hello!r}; source_unchanged={source_hello!r}; "
                    f"modified={modified}; smoke_url={smoke_url}"
                ),
                evidence={
                    "final_task": final_task,
                    "snapshot": {k: snap.get(k) for k in ("task_id", "status", "execution_stage", "modified_files", "current_label")},
                    "workspace_hello": workspace_hello,
                    "source_hello": source_hello,
                    "saw_stream": saw_stream,
                    "note": (
                        "Source fixture must stay unchanged until approve; "
                        "isolated workspace must contain the edit."
                    ),
                },
            )
        )
        if status_ok and file_ok and "NOTE=browser-smoke-ok" not in source_hello:
            report.notes.append(
                "Confirmed isolation: Cursor edited the workspace copy, not the source project path "
                "(expected until APPROVE / apply_local)."
            )
    finally:
        if smoke_page is not None:
            smoke_page.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
