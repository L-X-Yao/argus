"""Start the bundled simulator for the SIM button.

The simulator is a separate process: in the Windows package ``simulator.py`` sits
beside the backend, in a development checkout it is under ``scripts/``. The page
cannot start a local program itself and the backend had no route for it, so the
SIM button failed with "connection refused" unless the user had already run
``启动仿真器.bat``. This module starts that fixed, bundled script with a fixed
argument; no path, argument or environment from the request is ever used.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from .config import ROOT_DIR

SIM_HOST = "127.0.0.1"
SIM_PORT = 5770
START_TIMEOUT = 10.0
PROBE_INTERVAL = 0.1

_lock = threading.Lock()
_proc: subprocess.Popen | None = None
_job_handle = None
_kernel32 = None


def _ensure_job():
    """A Windows job whose last handle closes when this backend dies.

    Closing the packaged launcher's console window does not run FastAPI's
    lifespan, so ``stop_simulator`` never runs. The job kills the hidden
    simulator with its parent even then (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE).
    """
    global _job_handle, _kernel32
    if sys.platform != "win32" or _job_handle is not None:
        return _job_handle
    try:
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_ulonglong),
                ("WriteOperationCount", ctypes.c_ulonglong),
                ("OtherOperationCount", ctypes.c_ulonglong),
                ("ReadTransferCount", ctypes.c_ulonglong),
                ("WriteTransferCount", ctypes.c_ulonglong),
                ("OtherTransferCount", ctypes.c_ulonglong),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return None
        info = ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            handle,
            9,
            ctypes.byref(info),
            ctypes.sizeof(info),  # JobObjectExtendedLimitInformation
        ):
            kernel32.CloseHandle(handle)
            return None
        _kernel32, _job_handle = kernel32, handle
    except (ImportError, OSError, AttributeError):
        return None
    return _job_handle


def _put_in_job(proc: subprocess.Popen) -> None:
    if sys.platform != "win32":
        return
    handle = _ensure_job()
    if handle is None:
        return
    try:
        _kernel32.AssignProcessToJobObject(handle, int(proc._handle))  # type: ignore[union-attr]
    except (OSError, AttributeError):
        # The simulator still runs; only the belt-and-braces cleanup is lost.
        pass


def _simulator_script() -> Path | None:
    """The bundled script, packaged layout first, then a development checkout."""
    for candidate in (ROOT_DIR / "simulator.py", ROOT_DIR / "scripts" / "simulator.py"):
        if candidate.is_file():
            return candidate
    return None


def _manual_hint(script: Path) -> str:
    if script == ROOT_DIR / "simulator.py":
        return "run 启动仿真器.bat to see why"
    return "run python scripts/simulator.py to see why"


def _port_open(port: int = SIM_PORT, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((SIM_HOST, port), timeout=timeout):
            return True
    except OSError:
        return False


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def _spawn(script: Path) -> subprocess.Popen:
    kwargs: dict = {
        "cwd": str(ROOT_DIR),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        # No console window when the page starts it; the manual .bat still
        # exists for anyone who wants to see the simulator's output.
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen([sys.executable, str(script), str(SIM_PORT)], **kwargs)  # noqa: S603
    _put_in_job(proc)
    return proc


def start_simulator() -> dict:
    """Return ``{"ok": True, "started": bool}`` once port 5770 accepts, or an error.

    Blocking; the route runs it in the default executor.
    """
    global _proc
    if _port_open():
        return {"ok": True, "started": False}
    script = _simulator_script()
    if script is None:
        return {
            "ok": False,
            "error": "simulator.py not found beside the program; run 启动仿真器.bat",
        }
    with _lock:
        # Another click may have started it while this one waited for the lock.
        if _port_open():
            return {"ok": True, "started": False}
        try:
            proc = _spawn(script)
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        _proc = proc
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if _port_open(timeout=PROBE_INTERVAL):
                return {"ok": True, "started": True}
            code = proc.poll()
            if code is not None:
                _proc = None
                return {
                    "ok": False,
                    "error": f"simulator exited with code {code}; {_manual_hint(script)}",
                }
            time.sleep(PROBE_INTERVAL)
        _terminate(proc)
        _proc = None
        return {
            "ok": False,
            "error": f"simulator did not open {SIM_HOST}:{SIM_PORT} within {START_TIMEOUT:.0f} s",
        }


def stop_simulator() -> None:
    """Stop a simulator this backend started; one started by hand is left alone."""
    global _proc
    with _lock:
        proc, _proc = _proc, None
    if proc is None:
        return
    _terminate(proc)
