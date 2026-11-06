"""What the scripts that drive the backend against real firmware in SITL share."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parent.parent
SITL_DIR = Path(os.environ.get("SITL_DIR", Path.home() / "sitl"))
INSTANCE = int(os.environ.get("SITL_INSTANCE", "0"))
SPEEDUP = os.environ.get("SITL_SPEEDUP", "5")
BACKEND_PORT = int(os.environ.get("SITL_BACKEND_PORT", "8197"))
HOME = "-35.363261,149.165230,584,353"

_failures = 0

# A timeout's SIGTERM has to unwind through the callers' finally blocks, or SITL stays up.
signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))


def record(name: str, ok: bool, detail: str = "") -> None:
    global _failures
    _failures += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}", flush=True)


def failure_count() -> int:
    return _failures


def boot_sitl(
    binary: str,
    model: str,
    defaults: str,
    run_dir: Path,
    instance: int = INSTANCE,
    serial0: str = "tcp:0",
    home: str = HOME,
    speedup: str = SPEEDUP,
) -> subprocess.Popen:
    """Starts SITL in run_dir. defaults may list several comma-separated files."""
    log = run_dir / "sitl.log"
    # --serial0 tcp:0: boot must not gate on the first client
    # (libraries/AP_HAL_SITL/UARTDriver.cpp:117). The bash parent keeps SITL alive on
    # hosted runners: see sitl-smoke in .github/workflows/ci.yml.
    cmd = (
        f"'{SITL_DIR / binary}' --model {model} --speedup {speedup} -w -I {instance} "
        f"--serial0 {serial0} --defaults '{defaults}' --home {home} >> sitl.log 2>&1; "
        'echo "=== SITL exited with status $?" >> sitl.log'
    )
    # Output to /dev/null too: a parent holding the caller's pipe keeps `| tail` waiting.
    proc = subprocess.Popen(
        ["bash", "-c", cmd],
        cwd=run_dir,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if log.exists() and "SERIAL2 on TCP port" in log.read_text(errors="replace"):
            time.sleep(3)
            return proc
        time.sleep(0.5)
    print(log.read_text(errors="replace")[-2000:] if log.exists() else "no SITL log")
    raise SystemExit("SITL never opened its serial ports")


def boot_backend() -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
        cwd=REPO,
        env={**os.environ, "ARGUS_NO_BROWSER": "1"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"http://127.0.0.1:{BACKEND_PORT}/health", timeout=1).status_code == 200:
                return proc
        except httpx.HTTPError:
            time.sleep(0.3)
    raise SystemExit("backend never became healthy")


class Session:
    """Keeps the latest state and everything else the backend sends."""

    def __init__(self, ws):
        self.ws = ws
        self.state: dict = {}
        self.messages: list[dict] = []
        self.reader = asyncio.create_task(self._read())

    async def _read(self):
        async for raw in self.ws:
            msg = json.loads(raw)
            if msg.get("type") == "state":
                self.state.update(msg)
            self.messages.append(msg)

    async def send(self, msg: dict):
        await self.ws.send(json.dumps(msg))

    async def command(self, cmd: str, param=None, **data):
        await self.send({"type": "command", "cmd": cmd, "param": param, **data})

    async def until(self, predicate, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            await asyncio.sleep(0.1)
        return predicate()

    def seen(self, predicate) -> bool:
        return any(predicate(m) for m in self.messages)

    def recent_text(self) -> str:
        texts = [m.get("text", "") for m in self.messages if m.get("type") == "event"]
        return " | ".join(texts[-5:])


async def set_mode(s: Session, mode: int) -> bool:
    await s.command("mode", mode)
    return await s.until(lambda: s.state.get("mode_id") == mode, 10)


async def arm(s: Session, timeout: float = 90) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        await s.command("arm")
        if await s.until(lambda: s.state.get("armed") is True, 3):
            return True
    return False
