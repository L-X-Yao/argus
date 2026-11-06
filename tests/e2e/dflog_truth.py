"""What an independent reader makes of a dataflash log: the oracle for panels-sitl-tools.spec.ts.

Usage: dflog_truth.py <file.BIN>. Prints JSON with pymavlink's count of every message type
and, per the first instance of a type, min/max/mean of the fields the log viewer plots.
"""

from __future__ import annotations

import json
import sys

from pymavlink import mavutil

FIELDS = {"ATT": "DesRoll", "BAT": "Volt", "BARO": "Alt", "GPS": "Status", "VIBE": "VibeX"}
INSTANCE = {"BAT": "Inst", "BARO": "I", "GPS": "I", "VIBE": "IMU"}


def main() -> None:
    log = mavutil.mavlink_connection(sys.argv[1], robust_parsing=False)
    counts: dict[str, int] = {}
    series: dict[str, list[float]] = {name: [] for name in FIELDS}
    roi: list[list[int]] = []
    while True:
        msg = log.recv_msg()
        if msg is None:
            break
        name = msg.get_type()
        counts[name] = counts.get(name, 0) + 1
        if name in FIELDS and getattr(msg, INSTANCE.get(name, ""), 0) == 0:
            series[name].append(float(getattr(msg, FIELDS[name])))
        if name == "MAVC" and msg.Cmd == 201:
            roi.append([msg.X, msg.Y, msg.Res])

    stats = {
        f"{name}.{FIELDS[name]}": {"min": min(v), "max": max(v), "avg": sum(v) / len(v), "n": len(v)}
        for name, v in series.items()
        if v
    }
    print(json.dumps({"counts": counts, "stats": stats, "roi": roi}))


if __name__ == "__main__":
    main()
