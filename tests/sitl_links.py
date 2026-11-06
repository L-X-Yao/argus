#!/usr/bin/env python3
"""Drive the backend against real firmware in SITL, over the links and commands the
other SITL scripts leave out.

  commands  gimbal, camera, mission jump and reboots, on a vehicle that is not system 1
  udp       a whole session over UDP
  tty       a whole session through a real tty, which reads differently from a socket
  radio     a whole session over a telemetry radio: 57600 baud, delay, lost frames
  fleet     two vehicles on one link, flown one after the other

Usage: python tests/sitl_links.py commands|udp|tty|radio|fleet
Needs the binary and default parameters in ~/sitl (see the sitl-links CI job), and
socat for tty. Boots SITL and a backend of its own, and exits with the number of failures.
"""

import asyncio
import contextlib
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
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
RADIO_PARM = str(REPO / "tests/e2e/sitl-radio.parm")
GUIDED, AUTO, RTL = 4, 3, 6
SECOND_HOME = -35.353261  # 1.1 km north of the first


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


def waypoints(s: Session, alt: float = 20, count: int = 3) -> list[dict]:
    lat, lon = s.state.get("lat", -35.36), s.state.get("lon", 149.16)
    return [
        {"lat": lat + 0.0005 * (i + 1), "lon": lon, "alt": alt, "speed": 0, "type": "wp", "drop": False, "delay": 0}
        for i in range(count)
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


async def whole_session(s: Session, port: str, read_timeout: float = 90, mission_size: int = 3) -> None:
    """Connect, read every parameter, move a mission both ways, fly and land."""
    await connect(s, port)
    await ready_to_fly(s)

    await s.command("param_request_all")
    ok = await s.until(lambda: s.seen(lambda m: m.get("type") == "params_complete"), read_timeout)
    done = next((m for m in s.messages if m.get("type") == "params_complete"), {})
    count = sum(len(m.get("params", [])) for m in s.messages if m.get("type") == "param_batch")
    record("reads every parameter", ok and count > 500 and count >= done.get("total", 0), f"{count} of {done}")

    wps = waypoints(s, count=mission_size)
    await s.command("mission_upload", waypoints=wps)
    ok = await s.until(
        lambda: s.seen(lambda m: m.get("type") == "event" and m.get("event_type") == "mission_ack_ok"), 60
    )
    record("uploads a mission", ok, "" if ok else s.recent_text())
    await s.command("mission_download")
    ok = await s.until(lambda: s.seen(lambda m: m.get("type") == "mission_downloaded"), 60)
    got = next((m for m in s.messages if m.get("type") == "mission_downloaded"), {})
    same = [round(w["lat"], 5) for w in got.get("waypoints", [])] == [round(w["lat"], 5) for w in wps]
    record("downloads the same mission", ok and same, str(len(got.get("waypoints", []))))

    await take_off(s)
    await land(s)
    lost = s.seen(lambda m: m.get("type") == "event" and m.get("event_type") == "link_lost")
    record("never reports the link lost", not lost)

    await s.send({"type": "disconnect"})
    s.reader.cancel()


async def over(port: str, read_timeout: float = 90, mission_size: int = 3) -> None:
    async with websockets.connect(ws_url(), max_size=None) as ws:
        await whole_session(Session(ws), port, read_timeout, mission_size)


class Radio:
    """A telemetry radio between the backend and SITL: limited bytes per second each way,
    a delay, and whole frames lost or corrupted, as noise does."""

    def __init__(self, listen_port: int, fc_port: int, baud: int = 57600, loss: float = 0.03, delay: float = 0.03):
        self.listen_port, self.fc_port = listen_port, fc_port
        self.rate, self.loss, self.delay = baud / 10, loss, delay
        seed = int(os.environ.get("RADIO_SEED", time.time()))
        print(f"  RADIO_SEED={seed}", flush=True)
        self.rng = random.Random(seed)
        self.lost = self.corrupted = self.overflowed = 0

    async def serve(self) -> asyncio.AbstractServer:
        return await asyncio.start_server(self._client, "127.0.0.1", self.listen_port)

    async def _client(self, reader, writer):
        fc_reader, fc_writer = await asyncio.open_connection("127.0.0.1", self.fc_port)
        await asyncio.gather(self._pump(reader, fc_writer), self._pump(fc_reader, writer), return_exceptions=True)
        for w in (writer, fc_writer):
            w.close()

    def _frames(self, buf: bytearray) -> list[bytes]:
        """Cuts whole MAVLink 2 frames off the front of buf."""
        out = []
        while len(buf) >= 12:
            if buf[0] != 0xFD:
                nxt = buf.find(0xFD, 1)
                del buf[: nxt if nxt > 0 else len(buf)]
                continue
            size = 12 + buf[1] + (13 if buf[2] & 1 else 0)
            if len(buf) < size:
                break
            out.append(bytes(buf[:size]))
            del buf[:size]
        return out

    async def _deliver(self, queue: asyncio.Queue, writer) -> None:
        while True:
            at, frame = await queue.get()
            wait = at - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            writer.write(frame)
            await writer.drain()

    async def _pump(self, reader, writer):
        queue: asyncio.Queue = asyncio.Queue()
        deliver = asyncio.create_task(self._deliver(queue, writer))
        buf = bytearray()
        sent_until = time.monotonic()
        while data := await reader.read(4096):
            buf += data
            for frame in self._frames(buf):
                roll = self.rng.random()
                if roll < self.loss:
                    self.lost += 1
                    continue
                if roll < self.loss * 1.5:
                    self.corrupted += 1
                    frame = bytearray(frame)
                    frame[self.rng.randrange(10, len(frame))] ^= 0x55
                    frame = bytes(frame)
                now = time.monotonic()
                if sent_until - now > 1:  # its buffer is full, and what does not fit is gone
                    self.overflowed += 1
                    continue
                sent_until = max(sent_until, now) + len(frame) / self.rate
                queue.put_nowait((sent_until + self.delay, frame))
        deliver.cancel()


async def over_radio(fc_port: int) -> None:
    radio = Radio(fc_port + 100, fc_port)
    server = await radio.serve()
    try:
        # 30 waypoints: about 70 frames each way, so a transfer is sure to lose some.
        await over(f"tcp:127.0.0.1:{radio.listen_port}", read_timeout=240, mission_size=30)
    finally:
        server.close()
    print(f"  radio lost {radio.lost}, corrupted {radio.corrupted}, overflowed {radio.overflowed}", flush=True)
    record("the radio really lost frames", radio.lost > 20)


class Hub:
    """Joins several FCs on one TCP port, as a router or a shared radio does."""

    def __init__(self, listen_port: int, fc_ports: list[int]):
        self.listen_port, self.fc_ports = listen_port, fc_ports

    async def serve(self) -> asyncio.AbstractServer:
        return await asyncio.start_server(self._client, "127.0.0.1", self.listen_port)

    async def _client(self, reader, writer):
        fcs = [await asyncio.open_connection("127.0.0.1", port) for port in self.fc_ports]

        async def to_fcs():
            while data := await reader.read(4096):
                for _, fc_writer in fcs:
                    fc_writer.write(data)

        async def from_fc(fc_reader):
            while data := await fc_reader.read(4096):
                writer.write(data)

        await asyncio.gather(to_fcs(), *(from_fc(r) for r, _ in fcs), return_exceptions=True)


async def fleet(hub_port: int, homes: dict[int, float]) -> None:
    async with websockets.connect(ws_url(), max_size=None) as ws:
        s = Session(ws)
        await connect(s, f"tcp:127.0.0.1:{hub_port}")
        await ready_to_fly(s)

        def others() -> list[dict]:
            return s.state.get("vehicles") or []

        ok = await s.until(lambda: len(others()) == 1 and others()[0].get("lat", 0) != 0, 120)
        record("the other vehicle is on the list, with a position", ok, str(others())[:120])
        if not ok:
            return
        second = others()[0]["sysid"]
        first = next(sid for sid in homes if sid != second)

        def at_home_of(sysid: int) -> bool:
            return abs(s.state.get("lat", 0) - homes[sysid]) < 0.002

        steady = []
        for _ in range(30):
            steady.append(at_home_of(first))
            await asyncio.sleep(0.2)
        record("the state stays on one vehicle", all(steady), f"{sum(steady)} of {len(steady)} samples")

        await take_off(s, 15)
        record("the other vehicle stays on the ground", others() and others()[0].get("armed") is False)

        mark = len(s.messages)
        await s.command("switch_vehicle", second)
        ok = await s.until(lambda: s.state.get("connected") is True and at_home_of(second), 15)
        record("switching shows the other vehicle", ok, f"lat={s.state.get('lat')}")
        record("it reads as on the ground", await s.until(lambda: s.state.get("armed") is False, 5))
        await asyncio.sleep(2)
        wrote = any(m.get("type") == "event" and m.get("event_type") == "disarmed" for m in s.messages[mark:])
        record("switching is not taken for a landing", not wrote and not s.state.get("flight_summary"))
        ok = await s.until(lambda: len(others()) == 1 and others()[0]["sysid"] == first, 10)
        record("the first vehicle moves to the list, still armed", ok and others()[0].get("armed") is True)

        await take_off(s, 10)
        await land(s)
        record("the first vehicle is still in the air", others()[0].get("armed") is True, str(others())[:120])

        await s.command("switch_vehicle", first)
        ok = await s.until(lambda: s.state.get("connected") is True and at_home_of(first), 15)
        record("switching back shows the first vehicle", ok)
        record("it reads as armed", await s.until(lambda: s.state.get("armed") is True, 5))
        await land(s)

        await s.send({"type": "disconnect"})
        s.reader.cancel()


@contextlib.contextmanager
def tty_for(fc_port: int, run_dir: Path):
    """Puts a real tty in front of SITL's TCP port."""
    link = run_dir / "fc-tty"
    socat = subprocess.Popen(
        ["socat", f"PTY,link={link},rawer,echo=0", f"TCP:127.0.0.1:{fc_port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(50):
            if link.exists():
                break
            time.sleep(0.1)
        yield str(link)
    finally:
        socat.terminate()


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in ("commands", "udp", "tty", "radio", "fleet"):
        raise SystemExit(__doc__)
    if name == "tty" and not shutil.which("socat"):
        raise SystemExit("socat is not installed")
    print(f"[{name}]", flush=True)
    fc_port = 5760 + 10 * INSTANCE
    udp_port = 14700 + INSTANCE
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        defaults = {
            "commands": f"{COPTER_PARM},{GIMBAL_PARM},{SYSID_PARM}",
            "radio": f"{COPTER_PARM},{RADIO_PARM}",
        }.get(name, COPTER_PARM)
        serial0 = f"udpclient:127.0.0.1:{udp_port}" if name == "udp" else "tcp:0"
        # At real speed for the radio, or the FC sends more per second than any radio carries.
        speedup = {"speedup": "1"} if name == "radio" else {}
        sitl = boot_sitl("arducopter", "+", defaults, run_dir, serial0=serial0, **speedup)
        others = []
        if name == "fleet":
            second_dir = run_dir / "second"
            second_dir.mkdir()
            home = f"{SECOND_HOME},149.165230,584,353"
            others.append(
                boot_sitl(
                    "arducopter", "+", f"{COPTER_PARM},{SYSID_PARM}", second_dir, instance=INSTANCE + 1, home=home
                )
            )
        backend = boot_backend()
        try:
            if name == "fleet":

                async def run_fleet():
                    server = await Hub(fc_port + 100, [fc_port, fc_port + 10]).serve()
                    await fleet(fc_port + 100, {1: -35.363261, 7: SECOND_HOME})
                    server.close()

                asyncio.run(run_fleet())
            elif name == "commands":
                asyncio.run(commands())
            elif name == "udp":
                asyncio.run(over(f"udp:127.0.0.1:{udp_port}"))
            elif name == "tty":
                with tty_for(fc_port, run_dir) as port:
                    asyncio.run(over(port))
            else:
                asyncio.run(over_radio(fc_port))
        finally:
            backend.terminate()
            backend.wait(timeout=10)
            for proc in (sitl, *others):
                os.killpg(proc.pid, 15)
    print(f"[{name}] {failure_count()} failed", flush=True)
    return failure_count()


if __name__ == "__main__":
    raise SystemExit(main())
