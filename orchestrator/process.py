"""Subprocess helpers: tracked runs, streaming stdout, process-tree cancel."""
from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

_LOCK = threading.Lock()
_TRACKED: dict[str, dict[str, Any]] = {}


def run(
    argv: list[str],
    cwd: str | Path | None = None,
    timeout: int = 600,
    *,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = None
    if env is not None:
        merged_env = {**os.environ, **env} if env.get("__ORCH_MERGE__", "1") != "0" else dict(env)
        merged_env.pop("__ORCH_MERGE__", None)
    result = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        shell=False,
        env=merged_env,
    )
    if result.stdout is None:
        result.stdout = ""
    if result.stderr is None:
        result.stderr = ""
    return result


def run_tracked(
    task_id: str,
    argv: list[str],
    cwd: str | Path | None = None,
    timeout: int = 600,
    *,
    env: dict[str, str] | None = None,
    on_pid: Callable[[int], None] | None = None,
    on_heartbeat: Callable[[dict[str, Any]], None] | None = None,
    on_stdout_line: Callable[[str], None] | None = None,
    heartbeat_sec: float = 15.0,
    contained: bool = False,
    read_paths: list[Path] | None = None,
    write_paths: list[Path] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a long-lived process with cancel + optional line streaming + heartbeats."""
    if env is not None and env.get("__ORCH_MERGE__", "1") == "0":
        merged_env = {k: v for k, v in env.items() if k != "__ORCH_MERGE__"}
    elif env is not None:
        merged_env = {**os.environ, **{k: v for k, v in env.items() if k != "__ORCH_MERGE__"}}
    else:
        merged_env = None

    creationflags = 0
    if os.name == "nt":
        # New process group so we can signal the tree more reliably.
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    if contained and os.name == "nt":
        from orchestrator.win_boundary import popen as contained_popen

        proc = contained_popen(
            argv,
            cwd=Path(cwd) if cwd else Path("."),
            env=merged_env or {},
            read_paths=list(read_paths or []),
            write_paths=list(write_paths or ([Path(cwd)] if cwd else [])),
        )
    else:
        proc = subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=merged_env,
            creationflags=creationflags,
            bufsize=1,
        )
    started = time.time()
    with _LOCK:
        _TRACKED[task_id] = {
            "proc": proc,
            "argv": list(argv),
            "started": started,
            "alive": True,
        }
    if on_pid:
        try:
            on_pid(proc.pid)
        except Exception:  # noqa: BLE001
            pass

    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    stop_hb = threading.Event()
    reader_done = threading.Event()

    def _read_stdout() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                stdout_chunks.append(line)
                if on_stdout_line:
                    try:
                        on_stdout_line(line.rstrip("\n"))
                    except Exception:  # noqa: BLE001
                        pass
        finally:
            reader_done.set()

    def _read_stderr() -> None:
        try:
            assert proc.stderr is not None
            for line in proc.stderr:
                stderr_chunks.append(line)
        except Exception:  # noqa: BLE001
            pass

    def _heartbeat_loop() -> None:
        while not stop_hb.wait(heartbeat_sec):
            with _LOCK:
                item = _TRACKED.get(task_id)
            if not item or item.get("proc") is not proc:
                return
            code = proc.poll()
            info = {
                "pid": proc.pid,
                "elapsed_sec": int(time.time() - started),
                "alive": code is None,
                "poll": code,
            }
            if on_heartbeat:
                try:
                    on_heartbeat(info)
                except Exception:  # noqa: BLE001
                    pass
            if code is not None:
                return

    t_out = threading.Thread(target=_read_stdout, name=f"agent-out-{task_id}", daemon=True)
    t_err = threading.Thread(target=_read_stderr, name=f"agent-err-{task_id}", daemon=True)
    t_out.start()
    t_err.start()
    hb_thread: threading.Thread | None = None
    if on_heartbeat and heartbeat_sec > 0:
        hb_thread = threading.Thread(
            target=_heartbeat_loop, name=f"agent-hb-{task_id}", daemon=True
        )
        hb_thread.start()

    timed_out = False
    try:
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_process_tree(proc.pid)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                pass
        # Drain readers briefly
        reader_done.wait(timeout=5)
        t_out.join(timeout=2)
        t_err.join(timeout=2)
        code = proc.returncode if proc.returncode is not None else (-9 if timed_out else -1)
        stderr = "".join(stderr_chunks)
        if timed_out:
            stderr = (stderr + "\nTIMEOUT").strip()
        return subprocess.CompletedProcess(
            argv,
            returncode=code,
            stdout="".join(stdout_chunks),
            stderr=stderr,
        )
    finally:
        stop_hb.set()
        with _LOCK:
            current = _TRACKED.get(task_id)
            if current and current.get("proc") is proc:
                _TRACKED.pop(task_id, None)


def cancel_tracked(task_id: str) -> bool:
    """Kill the tracked process tree for task_id."""
    with _LOCK:
        item = _TRACKED.get(task_id)
    if not item:
        return False
    proc = item.get("proc")
    if not proc:
        return False
    kill_process_tree(proc.pid)
    return True


def tracked_info(task_id: str) -> dict[str, Any] | None:
    with _LOCK:
        item = _TRACKED.get(task_id)
        if not item:
            return None
        proc = item.get("proc")
        if not proc:
            return None
        code = proc.poll()
        return {
            "pid": proc.pid,
            "alive": code is None,
            "poll": code,
            "started": item.get("started"),
            "elapsed_sec": int(time.time() - float(item.get("started") or time.time())),
        }


def tracked_pid(task_id: str) -> int | None:
    info = tracked_info(task_id)
    return int(info["pid"]) if info else None


def kill_process_tree(pid: int | None) -> None:
    """Terminate a process and its children (Windows taskkill /T, POSIX killpg when possible)."""
    if not pid:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            return
        try:
            os.killpg(pid, 15)
            time.sleep(1)
            os.killpg(pid, 9)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, 15)
                time.sleep(1)
                os.kill(pid, 9)
            except (ProcessLookupError, PermissionError, OSError):
                pass
    except Exception:  # noqa: BLE001
        pass
