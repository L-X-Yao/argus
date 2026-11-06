#!/usr/bin/env python3
"""Drive the backend against real Plane, QuadPlane, Rover and Sub firmware in SITL.

tests/sitl_verify.py covers Copter in depth. This covers what differs per vehicle:
how it is recognised, its mode numbers, and that parameters and missions work.
Mode numbers are the trap here. RTL is 6 on Copter, 11 on Plane and Rover, and does
not exist on Sub; 6 on a Rover is FOLLOW. Hold is 12 on a plain plane, but 19 on a
QuadPlane, which heartbeats the same.

Usage: python tests/sitl_vehicles.py plane|quadplane|rover|sub
Needs the binary and default parameters in ~/sitl (see the sitl-vehicles CI job).
Boots SITL and a backend of its own, and exits with the number of failures.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sitl_common import (  # noqa: E402
    BACKEND_PORT,
    INSTANCE,
    SITL_DIR,
    Session,
    arm,
    boot_backend,
    boot_sitl,
    failure_count,
    record,
    set_mode,
)

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
        "hold": 12,
        "land": None,
    },
    "quadplane": {
        "binary": "arduplane",
        "model": "quadplane",
        "parm": "quadplane.parm",
        "vtype_raw": 1,
        "vtol": True,
        "armable": 0,  # MANUAL
        "auto": 10,
        "guided": 15,
        "rtl": 11,
        "hold": 19,
        "land": 20,
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
        "hold": 4,
        "land": None,
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
        "hold": 16,
        "land": 9,
    },
}


async def run(spec: dict) -> None:
    port = 5760 + 10 * INSTANCE
    async with websockets.connect(f"ws://127.0.0.1:{BACKEND_PORT}/ws", max_size=None) as ws:
        s = Session(ws)
        await s.send({"type": "connect", "port": f"tcp:127.0.0.1:{port}"})

        ok = await s.until(lambda: s.state.get("connected") is True, 30)
        record("connects", ok)
        ok = await s.until(lambda: s.state.get("vtype_raw") == spec["vtype_raw"], 15)
        record("recognised", ok, f"vtype_raw={s.state.get('vtype_raw')} vtype={s.state.get('vtype')}")
        ok = await s.until(lambda: bool(s.state.get("vtol_state")) is spec.get("vtol", False), 15)
        record("tells a QuadPlane from a plane", ok, f"vtol_state={s.state.get('vtol_state')}")
        record("offers modes", bool(s.state.get("mode_btns")), str(s.state.get("mode_btns"))[:70])
        ok = await s.until(lambda: bool(s.state.get("fw_version")), 15)
        record("reports firmware", ok, str(s.state.get("fw_version")))

        await s.command("param_request_all")
        ok = await s.until(lambda: s.seen(lambda m: m.get("type") == "params_complete"), 90)
        count = sum(len(m.get("params", [])) for m in s.messages if m.get("type") == "param_batch")
        record("reads parameters", ok and count > 100, f"{count} params")
        names = {p.get("name") for m in s.messages if m.get("type") == "param_batch" for p in m.get("params", [])}
        slot = "MODE1" if spec["binary"] == "ardurover" else "FLTMODE1"
        record("has the mode slots the panel edits", slot in names, slot)

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

        # What the Pause and Land buttons send: see src/lib/vehicleModes.ts.
        record("takes the hold mode", await set_mode(s, spec["hold"]), f"mode_id={s.state.get('mode_id')}")
        if spec["land"] is not None:
            record("takes the land mode", await set_mode(s, spec["land"]), f"mode_id={s.state.get('mode_id')}")

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
        sitl = boot_sitl(spec["binary"], spec["model"], str(SITL_DIR / spec["parm"]), Path(tmp))
        backend = boot_backend()
        try:
            asyncio.run(run(spec))
        finally:
            backend.terminate()
            backend.wait(timeout=10)
            os.killpg(sitl.pid, 15)
    print(f"[{name}] {failure_count()} failed", flush=True)
    return failure_count()


if __name__ == "__main__":
    raise SystemExit(main())
