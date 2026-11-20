"""A .tlog Argus recorded, summarised for the AI assistant.

Read-only. The file is the newest `*.tlog` with content in the Argus logs folder unless one is
named; only a bare file name is taken, and the resolved path must stay in that folder. The
frames are read by the project's own reader (`backend/replay.py`), so this runs in the Windows
package too, where pymavlink is not installed.

Only the vehicle's own frames count: `read_tlog` drops Argus's (sysid 255), and the rest are
kept once the flight controller's heartbeat has named the system. A gimbal's or companion
computer's heartbeat is skipped as `backend/mavlink_handlers.handle_heartbeat` skips it.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

from .config import cfg
from .constants import (
    COPTER_MODES_EN,
    NON_VEHICLE_MAV_TYPES,
    PLANE_MODES_EN,
    ROVER_MODES_EN,
    SUB_MODES_EN,
)
from .replay import MAX_TLOG_SIZE, read_tlog

MAX_EVENTS = 50
MAX_MODES = 30
# MAV_SEVERITY_WARNING: what the controller says is a problem, not a note.
WARNING = 4
PLANE_TYPES = (1, 19, 20, 21, 22, 23, 24, 25)
ROVER_TYPES = (10, 11)
MAV_TYPE_NAMES = {
    1: "fixed_wing",
    2: "quadrotor",
    3: "coaxial",
    4: "helicopter",
    10: "ground_rover",
    11: "surface_boat",
    12: "submarine",
    13: "hexarotor",
    14: "octorotor",
    15: "tricopter",
    19: "vtol_durotar",
    20: "vtol_quadrotor",
    21: "vtol_tiltrotor",
    22: "vtol_reserved",
    23: "vtol_tailsitter",
    24: "vtol_durotar",
    25: "vtol_tiltwing",
}
AUTOPILOT_NAMES = {0: "generic", 3: "ardupilot", 12: "px4"}
MESSAGE_NAMES = {
    0: "HEARTBEAT",
    1: "SYS_STATUS",
    22: "PARAM_VALUE",
    24: "GPS_RAW_INT",
    33: "GLOBAL_POSITION_INT",
    38: "MISSION_ITEM",
    42: "MISSION_CURRENT",
    73: "MISSION_ITEM_INT",
    74: "VFR_HUD",
    193: "EKF_STATUS_REPORT",
    241: "VIBRATION",
    253: "STATUSTEXT",
}


class LogRefused(Exception):
    """Not one of Argus's logs, or one this tool will not read."""


def _family(vtype: int) -> str:
    if vtype in PLANE_TYPES:
        return "plane"
    if vtype in ROVER_TYPES:
        return "rover"
    if vtype == 12:
        return "sub"
    if vtype > 0:
        return "copter"
    return "unknown"


def _mode_table(family: str) -> dict[int, str]:
    return {"plane": PLANE_MODES_EN, "rover": ROVER_MODES_EN, "sub": SUB_MODES_EN}.get(family, COPTER_MODES_EN)


def _newest(folder: Path) -> Path:
    """The newest log with content, resolved inside the folder: a link out of it is not one."""
    root = folder.resolve()
    logs = []
    for candidate in folder.glob("*.tlog"):
        try:
            if not candidate.is_file() or candidate.stat().st_size == 0:
                continue
            path = candidate.resolve()
        except OSError:
            continue
        if path.parent == root:
            logs.append(path)
    if not logs:
        raise LogRefused(f"No .tlog with content in {folder}. Argus writes one for every connection.")
    return max(logs, key=lambda p: p.stat().st_mtime)


def path_of(name: str | None) -> Path:
    """The log to read, or LogRefused. A name is a file name in the logs folder, never a path."""
    folder = cfg.LOG_DIR
    if name is None:
        chosen = _newest(folder)
    else:
        if not isinstance(name, str) or not name or "/" in name or "\\" in name:
            raise LogRefused("file: a .tlog file name in the Argus logs folder, not a path.")
        if not name.lower().endswith(".tlog"):
            raise LogRefused("file: a .tlog file name.")
        chosen = (folder / name).resolve()
        if chosen.parent != folder.resolve():
            raise LogRefused("file: a .tlog file name in the Argus logs folder, not a path.")
        if not chosen.is_file():
            raise LogRefused(f"No {name} in the Argus logs folder.")
    size = chosen.stat().st_size
    if size > MAX_TLOG_SIZE:
        raise LogRefused(f"{chosen.name} is {size} bytes; this tool reads up to {MAX_TLOG_SIZE}.")
    return chosen


def _metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(min(1.0, math.sqrt(h)))


def _pad(payload: bytes, size: int) -> bytes:
    """MAVLink 2 drops trailing zero bytes: a short payload reads as zeros after its last one."""
    return payload.ljust(size, b"\x00")


def analyze(name: str | None = None, cancelled=None) -> dict | None:
    """The summary dict, or None when cancelled. Raises LogRefused for a file this tool will not read."""
    path = path_of(name)
    try:
        records = read_tlog(str(path), include_gcs=False)
    except (ValueError, OSError) as exc:
        raise LogRefused(f"{path.name} is not a readable tlog: {exc}") from exc

    counts: dict[int, int] = {}
    events: list[dict] = []
    modes: list[dict] = []
    current_seqs: list[dict] = []
    mission_seqs: set[int] = set()
    parameters = 0
    total = 0
    first: float | None = None
    last: float | None = None
    sysid: int | None = None
    vehicle: dict | None = None
    table: dict[int, str] = COPTER_MODES_EN
    armed_since: float | None = None
    armed_s = 0.0
    mode_now: str | None = None
    mode_periods = 0
    max_alt: float | None = None
    max_speed = 0.0
    min_voltage: float | None = None
    start_voltage: float | None = None
    end_voltage: float | None = None
    max_current = 0.0
    min_remaining: int | None = None
    start_remaining: int | None = None
    end_remaining: int | None = None
    max_fix = 0
    max_sats = 0
    max_vibration = 0.0
    max_ekf = 0.0
    last_pos: tuple[float, float] | None = None
    distance = 0.0

    for usec, frame in records:
        if cancelled is not None and total % 2000 == 0 and cancelled.is_set():
            return None
        mid = frame[7] | (frame[8] << 8) | (frame[9] << 16)
        payload = frame[10 : 10 + frame[1]]
        src = frame[5]
        stamp = usec / 1e6

        if mid == 0:  # HEARTBEAT
            p = _pad(payload, 9)
            mode_number = int.from_bytes(p[0:4], "little")
            vtype, autopilot, base_mode = p[4], p[5], p[6]
            if autopilot == 8 or vtype in NON_VEHICLE_MAV_TYPES:
                continue  # a gimbal, a companion computer, another GCS
            if sysid is not None and src != sysid:
                continue
            if sysid is None:
                sysid = src
                family = _family(vtype)
                table = _mode_table(family)
                vehicle = {
                    "type": MAV_TYPE_NAMES.get(vtype, f"mav_type_{vtype}"),
                    "type_id": vtype,
                    "autopilot": AUTOPILOT_NAMES.get(autopilot, f"mav_autopilot_{autopilot}"),
                    "autopilot_id": autopilot,
                    "family": family,
                }
        elif sysid is None or src != sysid:
            continue

        total += 1
        counts[mid] = counts.get(mid, 0) + 1
        if first is None:
            first = stamp
        last = stamp
        t = round(stamp - first, 1)

        if mid == 0:
            mode = table.get(mode_number, f"MODE{mode_number}")
            if mode != mode_now:
                mode_now = mode
                mode_periods += 1
                if len(modes) < MAX_MODES:
                    modes.append({"t": t, "mode": mode})
            armed = bool(base_mode & 0x80)
            if armed and armed_since is None:
                armed_since = stamp
            elif not armed and armed_since is not None:
                armed_s += stamp - armed_since
                armed_since = None

        elif mid == 33:  # GLOBAL_POSITION_INT
            p = _pad(payload, 28)
            lat = struct.unpack_from("<i", p, 4)[0]
            lon = struct.unpack_from("<i", p, 8)[0]
            rel_alt = struct.unpack_from("<i", p, 16)[0]
            vx, vy = struct.unpack_from("<hh", p, 20)
            alt = rel_alt / 1000.0
            max_alt = alt if max_alt is None else max(max_alt, alt)
            if lat != 0 or lon != 0:
                pos = (lat / 1e7, lon / 1e7)
                if armed_since is not None and last_pos is not None:
                    step = _metres(last_pos, pos)
                    # EKF jitter is not flight: the reported ground speed decides, and a
                    # full metre between fixes counts even when a vehicle reports no speed.
                    if 0.2 < step < 2000 and (math.hypot(vx, vy) / 100.0 >= 0.5 or step >= 1.0):
                        distance += step
                last_pos = pos

        elif mid == 74:  # VFR_HUD
            p = _pad(payload, 20)
            speed = struct.unpack_from("<f", p, 4)[0]
            if math.isfinite(speed):
                max_speed = max(max_speed, speed)

        elif mid == 1:  # SYS_STATUS
            p = _pad(payload, 31)
            voltage = struct.unpack_from("<H", p, 14)[0]
            current = struct.unpack_from("<h", p, 16)[0]
            remaining = struct.unpack_from("<b", p, 30)[0]
            if 0 < voltage < 65535:
                volts = voltage / 1000.0
                min_voltage = volts if min_voltage is None else min(min_voltage, volts)
                if start_voltage is None:
                    start_voltage = volts
                end_voltage = volts
            if 0 < current < 32767:
                max_current = max(max_current, current / 100.0)
            if 0 <= remaining <= 100:
                min_remaining = remaining if min_remaining is None else min(min_remaining, remaining)
                if start_remaining is None:
                    start_remaining = remaining
                end_remaining = remaining

        elif mid == 24:  # GPS_RAW_INT
            p = _pad(payload, 30)
            max_fix = max(max_fix, p[28])
            max_sats = max(max_sats, p[29])

        elif mid == 241:  # VIBRATION
            p = _pad(payload, 32)
            for value in struct.unpack_from("<fff", p, 8):
                if math.isfinite(value):
                    max_vibration = max(max_vibration, value)

        elif mid == 193:  # EKF_STATUS_REPORT
            p = _pad(payload, 34)
            variance = struct.unpack_from("<f", p, 16)[0]
            if math.isfinite(variance):
                max_ekf = max(max_ekf, variance)

        elif mid == 253:  # STATUSTEXT
            p = _pad(payload, 51)
            if p[0] <= WARNING:
                text = p[1:51].split(b"\x00")[0].decode("utf-8", "replace").strip()
                events.append({"t": t, "severity": p[0], "text": text})

        elif mid in (38, 73):  # MISSION_ITEM, MISSION_ITEM_INT
            p = _pad(payload, 37)
            mission_seqs.add(struct.unpack_from("<H", p, 28)[0])

        elif mid == 42:  # MISSION_CURRENT
            p = _pad(payload, 2)
            seq = struct.unpack_from("<H", p, 0)[0]
            if not current_seqs or current_seqs[-1]["seq"] != seq:
                current_seqs.append({"t": t, "seq": seq})

        elif mid == 22:  # PARAM_VALUE
            parameters += 1

    if total == 0:
        raise LogRefused(f"{path.name} holds no vehicle MAVLink messages.")
    if armed_since is not None and last is not None:
        armed_s += last - armed_since

    return {
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "messages": total,
        "duration_s": None if first is None or last is None else round(last - first, 1),
        "vehicle": vehicle,
        "armed_seconds": round(armed_s, 1),
        "modes": modes,
        "mode_periods": mode_periods,
        "max_altitude_above_home_m": None if max_alt is None else (0.0 if max_alt == 0 else round(max_alt, 1)),
        "max_ground_speed_ms": round(max_speed, 1) if max_speed else None,
        "distance_m": round(distance),
        "battery": {
            "min_voltage_v": None if min_voltage is None else round(min_voltage, 2),
            "start_voltage_v": None if start_voltage is None else round(start_voltage, 2),
            "end_voltage_v": None if end_voltage is None else round(end_voltage, 2),
            "max_current_a": round(max_current, 1) if max_current else None,
            "min_remaining_pct": min_remaining,
            "start_remaining_pct": start_remaining,
            "end_remaining_pct": end_remaining,
        },
        "gps": {"max_fix": max_fix or None, "max_satellites": max_sats or None},
        "vibration_max": round(max_vibration, 2) if max_vibration else None,
        "ekf_max_pos_horiz_variance": round(max_ekf, 2) if max_ekf else None,
        "mission": {"items_seen": len(mission_seqs), "current_seqs": current_seqs[-10:]},
        "parameters_read": parameters,
        "events": events[:MAX_EVENTS],
        "events_left_out": max(0, len(events) - MAX_EVENTS),
        "messages_by_type": {
            MESSAGE_NAMES.get(mid, f"MSG_{mid}"): count
            for mid, count in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
        },
        "notes": [
            "distance is summed between consecutive positions while armed, above the EKF's jitter",
            "events are the controller's warnings and worse, in log order",
            "a tlog holds what Argus saw on the link, not the flight controller's own DataFlash log",
        ],
    }


def _values(first: float | int | None, second: float | int | None) -> dict:
    """One comparison row. A value missing from either log cannot give a meaningful delta."""
    delta = round(second - first, 6) if first is not None and second is not None else None
    return {"first": first, "second": second, "delta": delta}


def compare(first_name: str, second_name: str, cancelled=None) -> dict | None:
    """Compare two logs through analyze(), with every delta being second minus first."""
    first = analyze(first_name, cancelled)
    if first is None:
        return None
    second = analyze(second_name, cancelled)
    if second is None:
        return None

    def field(name: str) -> dict:
        return _values(first[name], second[name])

    def battery(name: str) -> dict:
        return _values(first["battery"][name], second["battery"][name])

    def gps(name: str) -> dict:
        return _values(first["gps"][name], second["gps"][name])

    first_events = len(first["events"]) + first["events_left_out"]
    second_events = len(second["events"]) + second["events_left_out"]
    return {
        "first": first["file"],
        "second": second["file"],
        "delta_direction": "second - first",
        "metrics": {
            "duration_s": field("duration_s"),
            "armed_seconds": field("armed_seconds"),
            "max_altitude_above_home_m": field("max_altitude_above_home_m"),
            "max_ground_speed_ms": field("max_ground_speed_ms"),
            "distance_m": field("distance_m"),
            "battery": {
                name: battery(name)
                for name in (
                    "min_voltage_v",
                    "start_voltage_v",
                    "end_voltage_v",
                    "max_current_a",
                    "min_remaining_pct",
                    "start_remaining_pct",
                    "end_remaining_pct",
                )
            },
            "gps": {name: gps(name) for name in ("max_fix", "max_satellites")},
            "vibration_max": field("vibration_max"),
            "ekf_max_pos_horiz_variance": field("ekf_max_pos_horiz_variance"),
            "mode_periods": field("mode_periods"),
            "event_count": _values(first_events, second_events),
            "mission_items_seen": _values(first["mission"]["items_seen"], second["mission"]["items_seen"]),
        },
    }
