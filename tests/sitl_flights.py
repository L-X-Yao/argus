#!/usr/bin/env python3
"""Fly a whole mission on Plane, QuadPlane, Rover and Sub in SITL, through the backend.

tests/sitl_vehicles.py checks what each vehicle answers on the ground. This goes on:
take off or set off, pass every waypoint, come back and stop, and read it all from the
telemetry the backend reports.

Usage: python tests/sitl_flights.py plane|quadplane|rover|sub
Needs the binary and default parameters in ~/sitl (see the sitl-vehicles CI job).
Boots SITL and a backend of its own, and exits with the number of failures.
"""

import asyncio
import math
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
from sitl_vehicles import VEHICLES  # noqa: E402

# The sim's water surface is at sea level, so a Sub needs a home there, as
# Tools/autotest/ardusub.py has. The speed is real time because Sub answers a missing
# GCS heartbeat by disarming, and the backend's heartbeat runs on the wall clock.
SUB_SITL = {"home": "33.810313,-118.393867,0,185", "speedup": "1"}


def events(s: Session, event_type: str, mark: int = 0) -> int:
    return sum(1 for m in s.messages[mark:] if m.get("type") == "event" and m.get("event_type") == event_type)


def square(s: Session, side_deg: float, alt: float) -> list[dict]:
    lat, lon = s.state["lat"], s.state["lon"]
    corners = [(side_deg, 0), (side_deg, side_deg), (0, side_deg)]
    return [
        {"lat": lat + a, "lon": lon + b, "alt": alt, "speed": 0, "type": "wp", "drop": False, "delay": 0}
        for a, b in corners
    ]


async def upload(s: Session, wps: list[dict], takeoff_alt: float) -> None:
    mark = len(s.messages)
    await s.command("mission_upload", waypoints=wps, takeoff_alt=takeoff_alt)
    ok = await s.until(lambda: events(s, "mission_ack_ok", mark) > 0, 30)
    record("uploads the mission", ok, s.recent_text() if not ok else "")


async def passes_every_waypoint(s: Session, count: int, timeout: float) -> None:
    ok = await s.until(lambda: events(s, "wp_reached") >= count, timeout)
    record("passes every waypoint", ok, f"{events(s, 'wp_reached')} of {count}, {s.recent_text()}")


async def fly_plane(s: Session, spec: dict) -> None:
    await upload(s, square(s, 0.006, 80), 60)
    record("switches to a manual mode", await set_mode(s, spec["armable"]))
    record("arms", await arm(s))
    await s.command("mission_start")
    record("starts the mission", await s.until(lambda: s.state.get("mode_id") == spec["auto"], 10))
    ok = await s.until(lambda: s.state.get("alt_rel", 0) > 40, 120)
    record("takes off", ok, f"alt_rel={s.state.get('alt_rel')} {s.recent_text()}")
    await passes_every_waypoint(s, 3, 240)
    await s.command("rtl")
    record("rtl selects RTL", await s.until(lambda: s.state.get("mode_id") == spec["rtl"], 10))
    ok = await s.until(lambda: 0 < s.state.get("dist_home", 1e9) < 200, 180)
    record("comes back", ok, f"dist_home={s.state.get('dist_home')}")
    await s.command("force_disarm")
    record("disarms", await s.until(lambda: s.state.get("armed") is False, 15))


async def fly_quadplane(s: Session, spec: dict) -> None:
    await upload(s, square(s, 0.006, 80), 60)
    record("switches to GUIDED", await set_mode(s, spec["guided"]))
    record("arms", await arm(s))
    await s.command("takeoff", alt=40)
    ok = await s.until(lambda: s.state.get("alt_rel", 0) > 30, 90)
    record("rises like a copter", ok, f"alt_rel={s.state.get('alt_rel')} {s.recent_text()}")
    record(
        "hovering, it reports VTOL flight", s.state.get("vtol_state") == 3, f"vtol_state={s.state.get('vtol_state')}"
    )
    await s.command("mission_start")
    record("starts the mission", await s.until(lambda: s.state.get("mode_id") == spec["auto"], 10))
    ok = await s.until(lambda: s.state.get("vtol_state") == 4, 90)
    record("goes over to wing-borne flight", ok, f"vtol_state={s.state.get('vtol_state')} {s.recent_text()}")
    await passes_every_waypoint(s, 3, 240)
    await s.command("rtl")
    record("rtl selects RTL", await s.until(lambda: s.state.get("mode_id") == spec["rtl"], 10))
    ok = await s.until(lambda: 0 < s.state.get("dist_home", 1e9) < 300, 180)
    record("comes back", ok, f"dist_home={s.state.get('dist_home')}")
    record("switches to the land mode", await set_mode(s, spec["land"]), f"mode_id={s.state.get('mode_id')}")
    ok = await s.until(lambda: s.state.get("armed") is False, 240)
    record("lands like a copter and disarms", ok, f"alt_rel={s.state.get('alt_rel')} {s.recent_text()}")


async def fly_rover(s: Session, spec: dict) -> None:
    await upload(s, square(s, 0.0004, 0), 0)
    record("switches to a manual mode", await set_mode(s, spec["armable"]))
    record("arms", await arm(s))
    await s.command("mission_start")
    record("starts the mission", await s.until(lambda: s.state.get("mode_id") == spec["auto"], 10))
    ok = await s.until(lambda: s.state.get("gs", 0) > 1, 30)
    record("drives off", ok, f"gs={s.state.get('gs')}")
    await passes_every_waypoint(s, 3, 180)
    await s.command("rtl")
    record("rtl selects RTL", await s.until(lambda: s.state.get("mode_id") == spec["rtl"], 10))
    ok = await s.until(lambda: 0 < s.state.get("dist_home", 1e9) < 10, 120)
    record("comes back", ok, f"dist_home={s.state.get('dist_home')}")
    await s.command("disarm")
    record("disarms", await s.until(lambda: s.state.get("armed") is False, 15))


async def fly_sub(s: Session, spec: dict) -> None:
    await upload(s, square(s, 0.0002, -5), -5)
    record("switches to a manual mode", await set_mode(s, spec["armable"]))
    record("arms", await arm(s))
    await s.command("mission_start")
    record("starts the mission", await s.until(lambda: s.state.get("mode_id") == spec["auto"], 10))
    ok = await s.until(lambda: s.state.get("alt_rel", 0) < -2, 60)
    record("dives", ok, f"alt_rel={s.state.get('alt_rel')} {s.recent_text()}")
    await passes_every_waypoint(s, 3, 240)
    await asyncio.sleep(5)
    refused = s.seen(lambda m: m.get("type") == "event" and "Bad alt frame" in m.get("text", ""))
    record("the firmware takes every item", not refused, s.recent_text())
    record("stays armed at the end of the mission", s.state.get("armed") is True)
    record("switches to the surface mode", await set_mode(s, spec["land"]), f"mode_id={s.state.get('mode_id')}")
    ok = await s.until(lambda: s.state.get("alt_rel", -99) > -1, 90)
    record("surfaces", ok, f"alt_rel={s.state.get('alt_rel')}")
    await s.command("disarm")
    record("disarms", await s.until(lambda: s.state.get("armed") is False, 15))


FLIGHTS = {"plane": fly_plane, "quadplane": fly_quadplane, "rover": fly_rover, "sub": fly_sub}


async def run(name: str, spec: dict) -> None:
    port = 5760 + 10 * INSTANCE
    async with websockets.connect(f"ws://127.0.0.1:{BACKEND_PORT}/ws", max_size=None) as ws:
        s = Session(ws)
        await s.send({"type": "connect", "port": f"tcp:127.0.0.1:{port}"})
        record("connects", await s.until(lambda: s.state.get("connected") is True, 30))
        record("gets a GPS fix", await s.until(lambda: s.state.get("gps_fix_raw", 0) >= 3, 120))
        ok = await s.until(lambda: s.state.get("ekf_flags", 0) & 0x10, 120)
        record("EKF has a position", bool(ok), f"flags=0x{s.state.get('ekf_flags', 0):x}")
        ok = await s.until(lambda: not math.isclose(s.state.get("home_lat", 0), 0), 60)
        record("knows its home", ok)

        await FLIGHTS[name](s, spec)

        await s.send({"type": "disconnect"})
        s.reader.cancel()


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in VEHICLES:
        raise SystemExit(__doc__)
    spec = VEHICLES[name]
    print(f"[{name}]", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        extra = SUB_SITL if name == "sub" else {}
        sitl = boot_sitl(spec["binary"], spec["model"], str(SITL_DIR / spec["parm"]), Path(tmp), **extra)
        backend = boot_backend()
        try:
            asyncio.run(run(name, spec))
        finally:
            backend.terminate()
            backend.wait(timeout=10)
            os.killpg(sitl.pid, 15)
    print(f"[{name}] {failure_count()} failed", flush=True)
    return failure_count()


if __name__ == "__main__":
    raise SystemExit(main())
