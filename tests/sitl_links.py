#!/usr/bin/env python3
"""Drive the backend against real firmware in SITL, over the links and commands the
other SITL scripts leave out.

Usage: python tests/sitl_links.py commands
Needs the binary and default parameters in ~/sitl (see the sitl-links CI job).
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
    REPO,
    SITL_DIR,
    Session,
    arm,
    boot_backend,
    boot_sitl,
    failure_count,
    record,
    set_mode,
)

COPTER_PARM = str(SITL_DIR / "copter.parm")
GIMBAL_PARM = str(REPO / "tests/e2e/sitl-gimbal.parm")
SYSID_PARM = str(REPO / "tests/e2e/sitl-sysid.parm")
GUIDED, AUTO, RTL = 4, 3, 6


def ws_url() -> str:
    return f"ws://127.0.0.1:{BACKEND_PORT}/ws"


async def connect(s: Session, port: str) -> None:
    await s.send({"type": "connect", "port": port})
    record("connects", await s.until(lambda: s.state.get("connected") is True, 30), port)


async def ready_to_fly(s: Session) -> None:
    ok = await s.until(lambda: s.state.get("gps_fix_raw", 0) >= 3, 120)
    record("gets a GPS fix", ok)
    ok = await s.until(lambda: s.state.get("ekf_flags", 0) & 0x10, 120)
    record("EKF has a position", bool(ok))


def waypoints(s: Session, alt: float = 20) -> list[dict]:
    lat, lon = s.state.get("lat", -35.36), s.state.get("lon", 149.16)
    return [
        {"lat": lat + d, "lon": lon, "alt": alt, "speed": 0, "type": "wp", "drop": False, "delay": 0}
        for d in (0.0005, 0.001, 0.0015)
    ]


async def acked(s: Session, mark: int, command: int, label: str, timeout: float = 10) -> None:
    """The FC's answer, as the backend reports it: event text carries the command id."""

    def answered() -> dict | None:
        for m in s.messages[mark:]:
            if m.get("type") == "event" and m.get("event_type") in ("cmd_ack_ok", "cmd_ack_fail"):
                if str(command) in m.get("text", ""):
                    return m
        return None

    await s.until(lambda: answered() is not None, timeout)
    m = answered() or {}
    record(label, m.get("event_type") == "cmd_ack_ok", m.get("text", "no answer"))


async def take_off(s: Session, alt: float = 20) -> None:
    record("switches to GUIDED", await set_mode(s, GUIDED))
    record("arms", await arm(s))
    await s.command("takeoff", alt=alt)
    ok = await s.until(lambda: s.state.get("alt_rel", 0) > alt * 0.75, 60)
    record("takes off", ok, f"alt_rel={s.state.get('alt_rel')}")


async def land(s: Session) -> None:
    await s.command("rtl")
    record("rtl", await s.until(lambda: s.state.get("mode_id") == RTL, 10))
    record("lands and disarms", await s.until(lambda: s.state.get("armed") is False, 150))


async def comes_back(s: Session, mark: int, label: str) -> None:
    """A reboot closes the link, and the backend has to find the FC again by itself."""

    def happened(event_type: str) -> bool:
        return any(m.get("type") == "event" and m.get("event_type") == event_type for m in s.messages[mark:])

    record(f"{label}: the link drops", await s.until(lambda: happened("link_lost"), 20))
    record(f"{label}: the backend reconnects", await s.until(lambda: happened("reconnected"), 30))
    ok = await s.until(lambda: s.state.get("connected") is True and s.state.get("link_age", 99) < 2, 30)
    record(f"{label}: telemetry is back", ok, f"link_age={s.state.get('link_age')}")


async def commands() -> None:
    """Commands on a vehicle that is not system 1, with a gimbal to act on."""
    async with websockets.connect(ws_url(), max_size=None) as ws:
        s = Session(ws)
        await connect(s, f"tcp:127.0.0.1:{5760 + 10 * INSTANCE}")
        # These ride no stream, so they only arrive if the requests reached system 7.
        ok = await s.until(lambda: s.state.get("vtol_state") == 3, 15)
        record("a vehicle that is not system 1 answers", ok, f"vtol_state={s.state.get('vtol_state')}")
        ok = await s.until(lambda: bool(s.state.get("fw_version")), 15)
        record("reports firmware", ok, str(s.state.get("fw_version")))
        await ready_to_fly(s)

        await s.command("mission_upload", waypoints=waypoints(s))
        ok = await s.until(
            lambda: s.seen(lambda m: m.get("type") == "event" and m.get("event_type") == "mission_ack_ok"), 30
        )
        record("uploads a mission", ok)
        await take_off(s)

        await s.command("mission_start")
        record("mission_start selects AUTO", await s.until(lambda: s.state.get("mode_id") == AUTO, 10))
        await asyncio.sleep(1)
        await s.command("mission_set_current", wp_index=2)
        ok = await s.until(lambda: s.state.get("wp_idx") == 2, 15)
        record("mission_set_current jumps", ok, f"wp={s.state.get('wp')} wp_idx={s.state.get('wp_idx')}")

        mark = len(s.messages)
        await s.command("gimbal_angle", pitch=-10, yaw=0)
        await acked(s, mark, 205, "gimbal_angle is accepted")
        ok = await s.until(lambda: abs(s.state.get("gimbal_pitch", 0) + 10) < 3, 10)
        record("the gimbal reports the new angle", ok, f"pitch={s.state.get('gimbal_pitch')}")

        mark = len(s.messages)
        await s.command("gimbal_pitchyaw", pitch=-20, yaw=10)
        await acked(s, mark, 1000, "gimbal_pitchyaw is accepted")
        ok = await s.until(lambda: abs(s.state.get("gimbal_pitch", 0) + 20) < 3, 10)
        record("the gimbal reports the second angle", ok, f"pitch={s.state.get('gimbal_pitch')}")

        mark = len(s.messages)
        await s.command("camera_trigger")
        await acked(s, mark, 203, "camera_trigger is accepted")

        await land(s)

        mark = len(s.messages)
        await s.command("reboot")
        await acked(s, mark, 246, "reboot is accepted")
        await comes_back(s, mark, "reboot")

        mark = len(s.messages)
        await s.command("reboot_bootloader")
        await acked(s, mark, 246, "reboot_bootloader is accepted")
        await comes_back(s, mark, "reboot_bootloader")

        await s.send({"type": "disconnect"})
        s.reader.cancel()


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in ("commands",):
        raise SystemExit(__doc__)
    print(f"[{name}]", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        sitl = boot_sitl("arducopter", "+", f"{COPTER_PARM},{GIMBAL_PARM},{SYSID_PARM}", Path(tmp))
        backend = boot_backend()
        try:
            asyncio.run(commands())
        finally:
            backend.terminate()
            backend.wait(timeout=10)
            os.killpg(sitl.pid, 15)
    print(f"[{name}] {failure_count()} failed", flush=True)
    return failure_count()


if __name__ == "__main__":
    raise SystemExit(main())
