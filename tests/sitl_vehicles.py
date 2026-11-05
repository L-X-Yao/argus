#!/usr/bin/env python3
"""Drive the backend against real Plane, Rover and Sub firmware in SITL.

tests/sitl_verify.py covers Copter in depth. This covers what differs per vehicle:
how it is recognised, its mode numbers, and that parameters and missions work.
Mode numbers are the trap here. RTL is 6 on Copter, 11 on Plane and Rover, and does
not exist on Sub; 6 on a Rover is FOLLOW.

Usage: python tests/sitl_vehicles.py plane|rover|sub
Needs the binary and default parameters in ~/sitl (see the sitl-vehicles CI job).
Boots SITL and a backend of its own, and exits with the number of failures.
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websockets

REPO = Path(__file__).resolve().parent.parent
SITL_DIR = Path(os.environ.get("SITL_DIR", Path.home() / "sitl"))
INSTANCE = int(os.environ.get("SITL_INSTANCE", "0"))
SPEEDUP = os.environ.get("SITL_SPEEDUP", "5")
BACKEND_PORT = 8197
HOME = "-35.363261,149.165230,584,353"

VEHICLES = {
    "plane": {
        "binary": "arduplane",
        "model": "plane",
        "parm": "plane.parm",
        "vtype_raw": 1,
        "armable": 0,  # MANUAL
        "auto": 10,
        "guided": 15,
        "rtl": 11,
    },
    "rover": {
        "binary": "ardurover",
        "model": "rover",
        "parm": "rover.parm",
        "vtype_raw": 10,
        "armable": 0,  # MANUAL
        "auto": 10,
        "guided": 15,
        "rtl": 11,
    },
    "sub": {
        "binary": "ardusub",
        "model": "vectored",
        "parm": "sub.parm",
        "vtype_raw": 12,
        "armable": 19,  # MANUAL
        "auto": 3,
        "guided": 4,
        "rtl": None,
    },
}

failures = 0


def record(name: str, ok: bool, detail: str = "") -> None:
    global failures
    failures += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}", flush=True)


def boot_sitl(spec: dict, run_dir: Path) -> subprocess.Popen:
    log = run_dir / "sitl.log"
    # --serial0 tcp:0: boot must not gate on the first client
    # (libraries/AP_HAL_SITL/UARTDriver.cpp:117). The bash parent keeps SITL alive on
    # hosted runners: see sitl-smoke in .github/workflows/ci.yml.
    cmd = (
        f"'{SITL_DIR / spec['binary']}' --model {spec['model']} --speedup {SPEEDUP} -w -I {INSTANCE} "
        f"--serial0 tcp:0 --defaults '{SITL_DIR / spec['parm']}' --home {HOME} >> sitl.log 2>&1; "
        'echo "=== SITL exited with status $?" >> sitl.log'
    )
    proc = subprocess.Popen(["bash", "-c", cmd], cwd=run_dir, stdin=subprocess.DEVNULL, start_new_session=True)
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


async def run(spec: dict) -> None:
    port = 5760 + 10 * INSTANCE
    async with websockets.connect(f"ws://127.0.0.1:{BACKEND_PORT}/ws", max_size=None) as ws:
        s = Session(ws)
        await s.send({"type": "connect", "port": f"tcp:127.0.0.1:{port}"})

        ok = await s.until(lambda: s.state.get("connected") is True, 30)
        record("connects", ok)
        ok = await s.until(lambda: s.state.get("vtype_raw") == spec["vtype_raw"], 15)
        record("recognised", ok, f"vtype_raw={s.state.get('vtype_raw')} vtype={s.state.get('vtype')}")
        record("offers modes", bool(s.state.get("mode_btns")), str(s.state.get("mode_btns"))[:70])
        ok = await s.until(lambda: bool(s.state.get("fw_version")), 15)
        record("reports firmware", ok, str(s.state.get("fw_version")))

        await s.command("param_request_all")
        ok = await s.until(lambda: s.seen(lambda m: m.get("type") == "params_complete"), 90)
        count = sum(len(m.get("params", [])) for m in s.messages if m.get("type") == "param_batch")
        record("reads parameters", ok and count > 100, f"{count} params")

        ok = await s.until(lambda: s.state.get("gps_fix_raw", 0) >= 3, 120)
        record("gets a GPS fix", ok)
        # AUTO and GUIDED need an absolute position, which comes later than the fix.
        ok = await s.until(lambda: s.state.get("ekf_flags", 0) & 0x10, 120)
        record("EKF has a position", bool(ok), f"flags=0x{s.state.get('ekf_flags', 0):x}")

        home = (s.state.get("lat", -35.36), s.state.get("lon", 149.16))
        wps = [
            {"lat": home[0] + d, "lon": home[1] + d, "alt": 30, "speed": 0, "type": "wp", "drop": False, "delay": 0}
            for d in (0.001, 0.002, 0.003)
        ]
        await s.command("mission_upload", waypoints=wps)
        ok = await s.until(
            lambda: s.seen(lambda m: m.get("type") == "event" and m.get("event_type") == "mission_ack_ok"), 30
        )
        record("uploads a mission", ok)
        await s.command("mission_download")
        ok = await s.until(lambda: s.seen(lambda m: m.get("type") == "mission_downloaded"), 30)
        got = next((m for m in s.messages if m.get("type") == "mission_downloaded"), {})
        record(
            "downloads the mission",
            ok and len(got.get("waypoints", [])) == len(wps),
            str(len(got.get("waypoints", []))),
        )

        record("switches to a manual mode", await set_mode(s, spec["armable"]))
        record("arms", await arm(s))

        await s.command("mission_start")
        ok = await s.until(lambda: s.state.get("mode_id") == spec["auto"], 10)
        record("mission_start selects AUTO", ok, f"mode_id={s.state.get('mode_id')} {'' if ok else s.recent_text()}")

        # mission_start sends MAV_CMD_MISSION_START 0.3 s after the mode change, and
        # that would pull the vehicle back into AUTO.
        await asyncio.sleep(1)
        await s.command("guided_goto", lat=home[0] + 0.001, lon=home[1], alt=30)
        ok = await s.until(lambda: s.state.get("mode_id") == spec["guided"], 10)
        record("guided_goto selects GUIDED", ok, f"mode_id={s.state.get('mode_id')} {'' if ok else s.recent_text()}")

        mark = len(s.messages)
        await s.command("rtl")
        if spec["rtl"] is None:
            ok = await s.until(
                lambda: any(m.get("type") == "cmd_result" and m.get("ok") is False for m in s.messages[mark:]), 5
            )
            record("rtl is refused: this vehicle has no RTL", ok)
        else:
            ok = await s.until(lambda: s.state.get("mode_id") == spec["rtl"], 10)
            record("rtl selects RTL", ok, f"mode_id={s.state.get('mode_id')}")

        await s.command("force_disarm")
        ok = await s.until(lambda: s.state.get("armed") is False, 15)
        record("disarms", ok)

        await s.send({"type": "disconnect"})
        s.reader.cancel()


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in VEHICLES:
        raise SystemExit(__doc__)
    spec = VEHICLES[name]
    print(f"[{name}]", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        sitl = boot_sitl(spec, Path(tmp))
        backend = boot_backend()
        try:
            asyncio.run(run(spec))
        finally:
            backend.terminate()
            backend.wait(timeout=10)
            os.killpg(sitl.pid, 15)
    print(f"[{name}] {failures} failed", flush=True)
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
