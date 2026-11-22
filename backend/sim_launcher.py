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


def _simulator_script() -> Path | None:
    """The bundled script, packaged layout first, then a development checkout."""
    for candidate in (ROOT_DIR / "simulator.py", ROOT_DIR / "scripts" / "simulator.py"):
        if candidate.is_file():
            return candidate
    return None


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
    return subprocess.Popen([sys.executable, str(script), str(SIM_PORT)], **kwargs)  # noqa: S603


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
                    "error": f"simulator exited with code {code}; run {script.name} to see why",
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
