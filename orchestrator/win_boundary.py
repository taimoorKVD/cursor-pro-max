"""Windows AppContainer boundary for the coding agent.

Cursor's ``--sandbox`` does not exist on Windows. This module starts a child
in an AppContainer that can write the task workspace and read the runtime it
needs, and cannot read the rest of the user profile (``.env``, ``.ssh``).

Non-Windows callers should not import this module.
"""
from __future__ import annotations

import ctypes
import msvcrt
import os
import subprocess
from ctypes import wintypes
from pathlib import Path
from typing import Any

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
userenv = ctypes.WinDLL("userenv", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

kernel32.InitializeProcThreadAttributeList.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
kernel32.UpdateProcThreadAttribute.argtypes = [
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_size_t,
    ctypes.c_void_p,
    ctypes.c_size_t,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_size_t),
]
kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
kernel32.DeleteProcThreadAttributeList.restype = None
kernel32.CreateProcessW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPWSTR,
    ctypes.c_void_p,
    ctypes.c_void_p,
    wintypes.BOOL,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.LPCWSTR,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
kernel32.CreateProcessW.restype = wintypes.BOOL
kernel32.LocalFree.argtypes = [ctypes.c_void_p]
kernel32.LocalFree.restype = ctypes.c_void_p
advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL

CONTAINER_NAME = "OrchCursorAgentNet"
_PROFILE_EXISTS = 0x800700B7
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
CREATE_NEW_PROCESS_GROUP = 0x00000200
STARTF_USESTDHANDLES = 0x00000100
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0
PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
SE_GROUP_ENABLED = 0x00000004
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
STILL_ACTIVE = 259

_sid: int | None = None
_sid_text: str | None = None
_granted: set[tuple] = set()


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [
        ("AppContainerSid", ctypes.c_void_p),
        ("Capabilities", ctypes.POINTER(SID_AND_ATTRIBUTES)),
        ("CapabilityCount", wintypes.DWORD),
        ("Reserved", wintypes.DWORD),
    ]


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def _check(ok: bool, what: str) -> None:
    if ok:
        return
    err = ctypes.get_last_error()
    raise OSError(err, f"{what} failed: WinError {err}")


def _sid_to_text(sid: int) -> str:
    out = ctypes.c_wchar_p()
    if not advapi32.ConvertSidToStringSidW(ctypes.c_void_p(sid), ctypes.byref(out)):
        raise OSError(ctypes.get_last_error(), "ConvertSidToStringSidW failed")
    try:
        return str(out.value)
    finally:
        kernel32.LocalFree(out)


def _internet_client_sid() -> int:
    sid = ctypes.c_void_p()
    if not advapi32.ConvertStringSidToSidW("S-1-15-3-1", ctypes.byref(sid)):
        raise OSError(ctypes.get_last_error(), "internetClient SID failed")
    return int(sid.value or 0)


def appcontainer_sid() -> tuple[int, str]:
    """Create or open the orchestrator AppContainer and return (sid, SDDL)."""
    global _sid, _sid_text
    if _sid and _sid_text:
        return _sid, _sid_text
    userenv.CreateAppContainerProfile.restype = ctypes.HRESULT
    userenv.DeleteAppContainerProfile.restype = ctypes.HRESULT
    userenv.DeleteAppContainerProfile.argtypes = [wintypes.LPCWSTR]
    userenv.DeriveAppContainerSidFromAppContainerName.restype = ctypes.HRESULT
    userenv.DeriveAppContainerSidFromAppContainerName.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    cap_sid = _internet_client_sid()
    cap = SID_AND_ATTRIBUTES(cap_sid, SE_GROUP_ENABLED)
    sid_ptr = ctypes.c_void_p()
    try:
        hr = int(
            userenv.CreateAppContainerProfile(
                CONTAINER_NAME,
                "Orchestrator Cursor Agent",
                "Least-privilege container for Cursor agent runs",
                ctypes.byref(cap),
                1,
                ctypes.byref(sid_ptr),
            )
        )
    except OSError as exc:
        # Profile already created by a previous run (HRESULT 0x800700B7).
        winerror = getattr(exc, "winerror", None)
        if winerror not in {-2147024713, 183}:
            raise
        hr = -1
        sid_ptr = ctypes.c_void_p()
    if not sid_ptr.value:
        hr = int(
            userenv.DeriveAppContainerSidFromAppContainerName(
                CONTAINER_NAME, ctypes.byref(sid_ptr)
            )
        )
        if hr < 0:
            raise OSError(
                f"DeriveAppContainerSidFromAppContainerName HRESULT {hr & 0xFFFFFFFF:#x}"
            )
    if not sid_ptr.value:
        raise OSError("AppContainer SID is null")
    _sid = int(sid_ptr.value)
    _sid_text = _sid_to_text(_sid)
    return _sid, _sid_text


def grant(path: Path, rights: str, *, recursive: bool = True) -> None:
    """Grant the container SID rights on a path the child must use.

    Set ``recursive=False`` for ancestor directories (drive roots / parents).
    Applying ``/T`` to ``C:\\`` would walk the whole volume.
    """
    _sid_i, sid_text = appcontainer_sid()
    target = str(Path(path))
    token = (target.lower(), rights, bool(recursive))
    if token in _granted:
        return
    cmd = ["icacls", target, "/grant", f"*{sid_text}:{rights}"]
    if recursive:
        cmd.append("/T")
    cmd.extend(["/Q", "/C"])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    detail = f"{result.stdout or ''}\n{result.stderr or ''}".strip()
    lower = detail.lower()
    # icacls often returns 0 with /C even when every target failed ("Access is denied").
    if (
        result.returncode != 0
        or "access is denied" in lower
        or "successfully processed 0 files" in lower
    ):
        raise OSError(f"icacls grant failed for {target}: {detail[:300]}")
    _granted.add(token)


def grant_ancestors(path: Path) -> None:
    """Allow traverse/list on parents so Node ``realpath`` can walk from the drive root.

    AppContainers often get ``EPERM`` on ``lstat('C:\\\\')`` when resolving a
    runtime installed under ``C:\\\\Users\\\\...\\\\cursor-agent``.
    """
    current = Path(path).resolve()
    chain: list[Path] = []
    while True:
        parent = current.parent
        if parent == current:
            # Drive roots (C:\, D:\) refuse AppContainer ACL edits without
            # elevation. Node boots with --preserve-symlinks-main instead.
            break
        chain.append(parent)
        current = parent
    for ancestor in reversed(chain):
        try:
            grant(ancestor, "(RX)", recursive=False)
        except OSError:
            # Protected directories may refuse ACL edits; keep going.
            continue


def _pipe() -> tuple[int, int]:
    read = wintypes.HANDLE()
    write = wintypes.HANDLE()
    attrs = SECURITY_ATTRIBUTES()
    attrs.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
    attrs.bInheritHandle = True
    _check(
        bool(kernel32.CreatePipe(ctypes.byref(read), ctypes.byref(write), ctypes.byref(attrs), 0)),
        "CreatePipe",
    )
    # Parent must not leak the read end into the child.
    _check(bool(kernel32.SetHandleInformation(read, 1, 0)), "SetHandleInformation")
    return int(read.value or 0), int(write.value or 0)


def _env_block(env: dict[str, str]) -> ctypes.Array[ctypes.c_wchar]:
    """Double-null-terminated UTF-16 environment. Must not stop at the first null."""
    chars: list[str] = []
    for key in sorted(env):
        if key == "__ORCH_MERGE__" or env[key] is None:
            continue
        value = str(env[key]).replace("\0", "")
        chars.extend(f"{key}={value}")
        chars.append("\0")
    chars.append("\0")
    buf = (ctypes.c_wchar * len(chars))()
    for index, char in enumerate(chars):
        buf[index] = char
    return buf


class ContainedProcess:
    """Small Popen-shaped handle for an AppContainer process."""

    def __init__(self, pid: int, process_handle: int, stdout: Any, stderr: Any) -> None:
        self.pid = pid
        self._handle = process_handle
        self.stdout = stdout
        self.stderr = stderr
        self.returncode: int | None = None

    def poll(self) -> int | None:
        if self.returncode is not None:
            return self.returncode
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(self._handle, ctypes.byref(code)):
            return None
        if int(code.value) == STILL_ACTIVE:
            return None
        self.returncode = int(code.value)
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        ms = 0xFFFFFFFF if timeout is None else max(0, int(timeout * 1000))
        waited = kernel32.WaitForSingleObject(self._handle, ms)
        if waited != 0:
            raise subprocess.TimeoutExpired(["contained"], timeout or 0)
        self.poll()
        return int(self.returncode if self.returncode is not None else -1)


def popen(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    read_paths: list[Path],
    write_paths: list[Path],
) -> ContainedProcess:
    """Start ``argv`` inside the AppContainer. ``cwd`` must be a write path."""
    sid, _text = appcontainer_sid()
    for path in read_paths:
        resolved = Path(path)
        if resolved.exists():
            grant_ancestors(resolved)
            grant(resolved, "(OI)(CI)(RX)")
    for path in write_paths:
        resolved = Path(path)
        resolved.mkdir(parents=True, exist_ok=True)
        grant_ancestors(resolved)
        grant(resolved, "(OI)(CI)(M)")

    out_r, out_w = _pipe()
    err_r, err_w = _pipe()
    nul_attrs = SECURITY_ATTRIBUTES()
    nul_attrs.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
    nul_attrs.bInheritHandle = True
    nul = kernel32.CreateFileW(
        "NUL",
        0x80000000,
        1,
        ctypes.byref(nul_attrs),
        3,
        0,
        None,
    )

    size = ctypes.c_size_t(0)
    kernel32.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
    attr = ctypes.create_string_buffer(size.value)
    _check(
        bool(kernel32.InitializeProcThreadAttributeList(attr, 2, 0, ctypes.byref(size))),
        "InitializeProcThreadAttributeList",
    )
    caps = SECURITY_CAPABILITIES()
    caps.AppContainerSid = sid
    net = SID_AND_ATTRIBUTES(_internet_client_sid(), SE_GROUP_ENABLED)
    caps.Capabilities = ctypes.pointer(net)
    caps.CapabilityCount = 1
    caps.Reserved = 0
    _check(
        bool(
            kernel32.UpdateProcThreadAttribute(
                attr,
                0,
                PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                ctypes.byref(caps),
                ctypes.sizeof(caps),
                None,
                None,
            )
        ),
        "UpdateProcThreadAttribute",
    )
    inherited = (wintypes.HANDLE * 3)(nul, out_w, err_w)
    _check(
        bool(
            kernel32.UpdateProcThreadAttribute(
                attr,
                0,
                PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                inherited,
                ctypes.sizeof(inherited),
                None,
                None,
            )
        ),
        "UpdateProcThreadAttribute(handle list)",
    )

    si = STARTUPINFOEXW()
    si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
    si.StartupInfo.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW
    si.StartupInfo.wShowWindow = SW_HIDE
    si.StartupInfo.hStdInput = nul
    si.StartupInfo.hStdOutput = out_w
    si.StartupInfo.hStdError = err_w
    si.lpAttributeList = ctypes.cast(attr, ctypes.c_void_p)

    # AppContainer CreateProcess returns ERROR_ENVVAR_NOT_FOUND unless the
    # profile variables exist, even when the caller wanted a tiny env.
    home = str(cwd)
    merged = dict(env)
    for key, value in {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
        "LOCALAPPDATA": home,
        "APPDATA": home,
        "USERPROFILE": home,
        "TEMP": home,
        "TMP": home,
    }.items():
        merged.setdefault(key, value)
    env = merged
    cmdline = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
    # Keep the wchar block alive for the duration of CreateProcess. Casting a
    # temporary drops the buffer and CreateProcessW returns ERROR_ENVVAR_NOT_FOUND.
    env_block = _env_block(env) if env else None
    env_buf = ctypes.cast(env_block, ctypes.c_void_p) if env_block is not None else None
    pi = PROCESS_INFORMATION()
    flags = EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT | CREATE_NEW_PROCESS_GROUP
    ok = kernel32.CreateProcessW(
        None,
        cmdline,
        None,
        None,
        True,
        flags,
        env_buf,
        str(cwd),
        ctypes.byref(si),
        ctypes.byref(pi),
    )
    kernel32.DeleteProcThreadAttributeList(attr)
    kernel32.CloseHandle(out_w)
    kernel32.CloseHandle(err_w)
    if nul:
        kernel32.CloseHandle(nul)
    if not ok:
        err = ctypes.get_last_error()
        kernel32.CloseHandle(out_r)
        kernel32.CloseHandle(err_r)
        raise OSError(err, f"CreateProcessW (AppContainer) failed: WinError {err}")

    def _text(handle: int):
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        return os.fdopen(fd, "r", encoding="utf-8", errors="replace", closefd=True)

    return ContainedProcess(int(pi.dwProcessId), int(pi.hProcess or 0), _text(out_r), _text(err_r))


def probe(secret: Path, workspace: Path) -> str:
    """Return ``denied``, ``read``, or ``unavailable``.

    ``denied`` means a container process could read a file inside ``workspace``
    and was refused when reading ``secret``. Uses ``cmd.exe`` so the check does
    not depend on granting the container access to a Python install.
    """
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    inside = workspace / "_orch_inside.txt"
    inside.write_text("inside-ok", encoding="utf-8")
    secret = Path(secret)
    secret.parent.mkdir(parents=True, exist_ok=True)
    if not secret.exists():
        secret.write_text("secret-marker", encoding="utf-8")
    cmd = os.environ.get("COMSPEC") or r"C:\Windows\System32\cmd.exe"
    env = {"PATH": str(Path(cmd).parent), "COMSPEC": cmd}

    def _run(target: Path) -> tuple[int, str, str]:
        proc = popen(
            [cmd, "/c", "type", str(target)],
            cwd=workspace,
            env=env,
            read_paths=[],
            write_paths=[workspace],
        )
        code = proc.wait(timeout=20)
        out = proc.stdout.read() if proc.stdout else ""
        err = proc.stderr.read() if proc.stderr else ""
        return code, out, err

    try:
        in_code, in_out, _in_err = _run(inside)
        sec_code, sec_out, sec_err = _run(secret)
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    if in_code != 0 or "inside-ok" not in in_out:
        return "unavailable"
    if "secret-marker" in sec_out:
        return "read"
    if sec_code != 0 and "denied" in sec_err.lower():
        return "denied"
    return "unavailable"
