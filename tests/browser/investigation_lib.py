"""Shared helpers for go-live browser investigation (UI + API + SQLite evidence)."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

# Phrases that historically meant "looks busy but isn't reliable"
STUCK_PATTERNS = [
    r"streaming\s+issue",
    r"stream(?:ing)?\s+(?:error|failed|broke|stuck)",
    r"cli\s+(?:is\s+)?not\s+working",
    r"agent\s+(?:missing|unavailable|failed|not\s+found)",
    r"authentication\s+required",
    r"empty\s+output",
    r"workspace\s+collision",
    r"sandbox\s+mode\s+is\s+enabled",
    r"detailed\s+activity\s+unavailable",
]

KNOWN_FAILURE_BUCKETS = {
    "auth": re.compile(r"auth|login|CURSOR_API_KEY|invalid", re.I),
    "sandbox": re.compile(r"sandbox", re.I),
    "empty_output": re.compile(r"empty output", re.I),
    "workspace_collision": re.compile(r"workspace collision", re.I),
    "orchestrator_restart": re.compile(r"restart|interrupted|reload", re.I),
    "none_type": re.compile(r"NoneType", re.I),
}


@dataclass
class CheckResult:
    id: str
    title: str
    ok: bool
    severity: str  # blocker | major | minor | info
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class InvestigationReport:
    started_at: str
    base_url: str
    checks: list[CheckResult] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    go_live_ready: bool = False
    notes: list[str] = field(default_factory=list)

    def add(self, check: CheckResult) -> None:
        self.checks.append(check)
        if not check.ok and check.severity in {"blocker", "major"}:
            self.gaps.append(f"[{check.severity}] {check.title}: {check.detail}")

    def finalize(self) -> None:
        blockers = [c for c in self.checks if not c.ok and c.severity == "blocker"]
        majors = [c for c in self.checks if not c.ok and c.severity == "major"]
        self.go_live_ready = not blockers and not majors
        if self.go_live_ready:
            self.notes.append("No blocker/major gaps found by this investigation pass.")
        else:
            self.notes.append(
                f"Not go-live ready: {len(blockers)} blocker(s), {len(majors)} major gap(s)."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "base_url": self.base_url,
            "go_live_ready": self.go_live_ready,
            "notes": self.notes,
            "gaps": self.gaps,
            "checks": [asdict(c) for c in self.checks],
        }


def new_report(base_url: str) -> InvestigationReport:
    return InvestigationReport(
        started_at=datetime.now(timezone.utc).isoformat(),
        base_url=base_url,
    )


def write_report(report: InvestigationReport, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"investigation-{stamp}.json"
    md_path = out_dir / "GOLIVE_BROWSER_INVESTIGATION.md"
    latest_json = out_dir / "latest.json"

    data = report.to_dict()
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    latest_json.write_text(json.dumps(data, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(report), encoding="utf-8")
    return json_path, md_path


def _render_markdown(report: InvestigationReport) -> str:
    lines = [
        "# Go-live browser investigation",
        "",
        f"**When:** {report.started_at}",
        f"**Target:** `{report.base_url}`",
        f"**Verdict:** {'READY' if report.go_live_ready else 'NOT READY'}",
        "",
        "## Executive summary",
        "",
        "This suite investigates the core product promise: chat assigns work → Cursor CLI applies",
        "changes in an isolated workspace → progress/events feed the UI → operator can approve/push.",
        "",
        "If the verdict is NOT READY, treat major/blocker gaps below as launch blockers even when",
        "the latest single task looks successful.",
        "",
        "## Notes",
        "",
    ]
    for n in report.notes:
        lines.append(f"- {n}")
    lines.extend(["", "## Gaps", ""])
    if not report.gaps:
        lines.append("- None recorded.")
    else:
        for g in report.gaps:
            lines.append(f"- {g}")
    lines.extend(
        [
            "",
            "## Known product failure modes this suite looks for",
            "",
            "- Chat acknowledges work while Cursor never starts / exits empty / auth fails",
            "- Mid-run UI stuck with no `agent_stream` evidence (streaming / CLI opacity)",
            "- Workspace collision after crash/retry",
            "- Orchestrator restart canceling an in-flight agent",
            "- Status replies that invent progress instead of citing DB evidence",
            "",
            "## Checks",
            "",
        ]
    )
    for c in report.checks:
        mark = "PASS" if c.ok else "FAIL"
        lines.append(f"### [{mark}] {c.title}")
        lines.append("")
        lines.append(f"- **id:** `{c.id}`")
        lines.append(f"- **severity:** {c.severity}")
        lines.append(f"- **detail:** {c.detail}")
        if c.evidence:
            lines.append(f"- **evidence:** `{json.dumps(c.evidence)[:500]}`")
        lines.append("")
    return "\n".join(lines)


def analyze_sqlite_history(db_path: Path | None = None) -> dict[str, Any]:
    path = db_path or (ROOT / "data" / "orchestrator.sqlite")
    if not path.exists():
        return {"ok": False, "error": f"missing db: {path}"}
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    rows = [
        dict(r)
        for r in con.execute(
            """
            SELECT id, project, status, execution_stage, exit_code, blocker,
                   substr(COALESCE(summary,''),1,240) AS summary,
                   started_at, ended_at, last_activity_at,
                   substr(COALESCE(modified_files,''),1,240) AS modified_files
            FROM tasks
            ORDER BY rowid DESC
            LIMIT 40
            """
        ).fetchall()
    ]
    buckets: dict[str, int] = {k: 0 for k in KNOWN_FAILURE_BUCKETS}
    buckets["other_failed"] = 0
    review_with_files = 0
    review_without_files = 0
    stream_ok_tasks = 0
    for r in rows:
        status = (r.get("status") or "").lower()
        blob = " ".join(
            str(x or "") for x in (r.get("summary"), r.get("blocker"), r.get("execution_stage"))
        )
        if status in {"failed", "rejected"}:
            matched = False
            for name, rx in KNOWN_FAILURE_BUCKETS.items():
                if rx.search(blob):
                    buckets[name] += 1
                    matched = True
                    break
            if not matched:
                buckets["other_failed"] += 1
        if status == "review":
            if r.get("modified_files"):
                review_with_files += 1
            else:
                review_without_files += 1
        tid = r["id"]
        n_stream = con.execute(
            "SELECT COUNT(*) FROM task_events WHERE task_id=? AND event_type='agent_stream'",
            (tid,),
        ).fetchone()[0]
        if n_stream >= 3:
            stream_ok_tasks += 1

    status_counts: dict[str, int] = {}
    for r in con.execute("SELECT status, COUNT(*) c FROM tasks GROUP BY status").fetchall():
        status_counts[str(r[0])] = int(r[1])

    latest = rows[0] if rows else None
    latest_events = []
    if latest:
        latest_events = [
            dict(e)
            for e in con.execute(
                """
                SELECT event_type, stage, substr(message,1,140) AS message
                FROM task_events WHERE task_id=? ORDER BY id DESC LIMIT 15
                """,
                (latest["id"],),
            ).fetchall()
        ]
    con.close()
    return {
        "ok": True,
        "db": str(path),
        "task_count_sample": len(rows),
        "status_counts": status_counts,
        "failure_buckets": buckets,
        "review_with_files": review_with_files,
        "review_without_files": review_without_files,
        "stream_ok_tasks_in_sample": stream_ok_tasks,
        "latest_task": latest,
        "latest_events": latest_events,
    }


def find_stuck_phrases(texts: list[str]) -> list[str]:
    hits: list[str] = []
    for text in texts:
        for pat in STUCK_PATTERNS:
            if re.search(pat, text or "", re.I):
                hits.append(f"{pat} ← {(text or '')[:160]}")
    return hits


def wait_until(predicate, timeout_sec: float = 30.0, interval: float = 0.5) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False
