"""Thread safety tests for DroneLink state access."""

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.drone_link import DroneLink


class TestThreadSafety:
    def test_concurrent_read_write(self):
        link = DroneLink()
        errors = []
        stop = threading.Event()

        def writer():
            i = 0
            while not stop.is_set():
                link.lat = float(i)
                link.lon = float(i)
                link.roll = float(i)
                link.voltage = float(i % 100)
                i += 1

        def reader():
            while not stop.is_set():
                try:
                    state = link.get_state()
                    assert isinstance(state, dict)
                    assert "lat" in state
                    assert "voltage" in state
                except Exception as e:
                    errors.append(e)

        w = threading.Thread(target=writer, daemon=True)
        r = threading.Thread(target=reader, daemon=True)
        w.start()
        r.start()
        time.sleep(1)
        stop.set()
        w.join(timeout=2)
        r.join(timeout=2)
        assert errors == [], f"Errors during concurrent access: {errors}"

    def test_get_state_keys_stable(self):
        link = DroneLink()
        state = link.get_state()
        expected = {
            "type",
            "connected",
            "frames",
            "mode",
            "mode_id",
            "armed",
            "roll",
            "pitch",
            "yaw",
            "lat",
            "lon",
            "alt_rel",
            "alt_msl",
            "gs",
            "airspeed",
            "throttle",
            "climb",
            "vz",
            "hdg",
            "dist_home",
            "flight_time",
            "voltage",
            "current",
            "remaining",
            "gps_fix",
            "gps_fix_raw",
            "gps_sats",
            "wp",
            "vtype",
            "vtype_raw",
            "autopilot",
            "mode_btns",
            "link_age",
            "bat_time",
            "home_lat",
            "home_lon",
            "parse_errors",
            "flight_summary",
            "log_active",
            "fw_version",
            "fw_git",
            "board_id",
            "rc",
            "rc_rssi",
            "vibe",
            "vibe_clip",
            "servo",
            "ekf_vel",
            "ekf_pos_h",
            "ekf_pos_v",
            "ekf_compass",
            "ekf_flags",
            "wind_dir",
            "wind_speed",
            "terrain_alt",
            "gimbal_pitch",
            "gimbal_yaw",
            "vehicles",
            "prearm",
            "adsb",
            "cells",
            "param_count",
            "param_total",
            "param_fetching",
        }
        assert state.keys() == expected


class TestBufferCap:
    def test_buf_capped(self):
        link = DroneLink()
        link._buf = b"\x00" * 70000
        link._buf += b"\x01" * 1024
        if len(link._buf) > 65536:
            link._buf = link._buf[-32768:]
            link._parse_errors += 1
        assert len(link._buf) <= 65536
        assert link._parse_errors == 1
