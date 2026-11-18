"""backend/flight_log.py: a recorded tlog summarised, and what it refuses to read."""

import os
import struct
from unittest import mock

import pytest
from frame_builders import fc_frame, write_tlog

from backend import flight_log
from backend.config import cfg
from backend.crc_extras import CRC_EXTRA
from backend.mavlink_frame import bm


def heartbeat(mode=4, armed=True, seq=0, vtype=2, autopilot=3):
    # base_mode 0x01 = MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 0x10 = STABILIZE, 0x80 = armed.
    base_mode = 0x01 | 0x10 | (0x80 if armed else 0)
    return fc_frame(0, struct.pack("<IBBBBB", mode, vtype, autopilot, base_mode, 4, 3), seq)


def position(lat, lon, vx=0, vy=0, seq=0):
    payload = struct.pack("<Iiiiihhhh", 0, int(lat * 1e7), int(lon * 1e7), 15000, 5000, vx, vy, 0, 9000)
    return fc_frame(33, payload, seq)


def other_vehicle(lat, lon, seq=0):
    payload = struct.pack("<Iiiiihhhh", 0, int(lat * 1e7), int(lon * 1e7), 0, 0, 0, 0, 0, 0)
    return bm(33, payload, seq, CRC_EXTRA[33], sysid=2, compid=1)


def sys_status(voltage_mv=12000, remaining=50, seq=0):
    # SYS_STATUS: present/enabled/health u32, load u16, voltage u16 mV, current i16 cA,
    # drop/errors u16, four counters u16, remaining i8
    payload = struct.pack("<IIIHHhHHHHHHb", 0, 0, 0, 100, voltage_mv, -1, 0, 0, 0, 0, 0, 0, remaining)
    return fc_frame(1, payload, seq)


def gps_raw(seq=0):
    # GPS_RAW_INT in MAVLink 2 wire order (fields sorted by size): time u64, lat/lon/alt i32,
    # eph/epv/vel/cog u16, fix u8, sats u8.
    payload = struct.pack("<QiiiHHHHBB", 0, int(31.2304e7), int(121.4737e7), 15000, 100, 100, 0, 0, 3, 9)
    return fc_frame(24, payload, seq)


def vibration(seq=0):
    payload = struct.pack("<QfffIII", 0, 1.5, 0.5, 0.2, 0, 0, 0)
    return fc_frame(241, payload, seq)


def statustext(text=b"Failsafe", severity=4, seq=0):
    return fc_frame(253, struct.pack("<B50s", severity, text), seq)


def a_flight():
    return [
        heartbeat(vtype=26, autopilot=8, armed=False, seq=0),  # gimbal: the FC forwards it
        heartbeat(mode=4, armed=True, seq=1),  # GUIDED on a copter
        position(31.2304, 121.4737, vx=100, seq=2),
        sys_status(seq=3),
        gps_raw(seq=4),
        vibration(seq=5),
        position(31.2314, 121.4737, vx=100, seq=6),
        statustext(seq=7),
        heartbeat(mode=4, armed=False, seq=8),
        other_vehicle(32.0, 122.0, seq=9),  # another aircraft on the same link
    ]


def test_a_flight_is_summarised(tmp_path):
    write_tlog(tmp_path / "argus_x.tlog", a_flight(), spacing_usec=1_000_000)
    with mock.patch.object(cfg, "LOG_DIR", tmp_path):
        summary = flight_log.analyze("argus_x.tlog")
    assert summary["file"] == "argus_x.tlog"
    assert summary["messages"] == 8  # the gimbal and the other aircraft are not the vehicle
    assert summary["duration_s"] == 7.0
    assert summary["vehicle"] == {
        "type": "quadrotor",
        "type_id": 2,
        "autopilot": "ardupilot",
        "autopilot_id": 3,
        "family": "copter",
    }
    assert summary["armed_seconds"] == 7.0
    assert summary["modes"] == [{"t": 0.0, "mode": "Guided"}]
    assert summary["max_altitude_above_home_m"] == 5.0
    assert summary["battery"]["min_voltage_v"] == 12.0
    assert summary["battery"]["min_remaining_pct"] == 50
    assert summary["gps"]["max_fix"] == 3 and summary["gps"]["max_satellites"] == 9
    assert summary["vibration_max"] == 1.5
    assert summary["events"] == [{"t": 6.0, "severity": 4, "text": "Failsafe"}]
    assert summary["distance_m"] > 50
    assert summary["messages_by_type"]["HEARTBEAT"] == 2


def test_the_newest_log_with_content_is_used(tmp_path):
    empty, older = tmp_path / "argus_empty.tlog", tmp_path / "argus_flight.tlog"
    empty.write_bytes(b"")
    write_tlog(older, a_flight())
    os.utime(empty, (2, 2))
    with mock.patch.object(cfg, "LOG_DIR", tmp_path):
        assert flight_log.path_of(None) == older.resolve()


def test_a_link_out_of_the_logs_folder_is_not_read(tmp_path):
    outside = tmp_path / "outside" / "secret.tlog"
    outside.parent.mkdir()
    write_tlog(outside, a_flight())
    logs = tmp_path / "logs"
    logs.mkdir()
    os.symlink(outside, logs / "link.tlog")
    with mock.patch.object(cfg, "LOG_DIR", logs), pytest.raises(flight_log.LogRefused, match="No .tlog"):
        flight_log.path_of(None)


def test_a_still_vehicle_does_not_clock_up_distance(tmp_path):
    # 0.000002 degrees of latitude is about 0.2 m: the EKF moving under a parked vehicle.
    frames = [
        heartbeat(armed=True, seq=0),
        position(31.2304, 121.4737, seq=1),
        position(31.230402, 121.4737, seq=2),
        heartbeat(armed=False, seq=3),
    ]
    write_tlog(tmp_path / "argus_x.tlog", frames, spacing_usec=1_000_000)
    with mock.patch.object(cfg, "LOG_DIR", tmp_path):
        summary = flight_log.analyze("argus_x.tlog")
    assert summary["distance_m"] == 0


@pytest.mark.parametrize("name", ["../x.tlog", "sub/x.tlog", "x.bin", ""])
def test_only_a_file_name_in_the_logs_folder_is_taken(tmp_path, name):
    with mock.patch.object(cfg, "LOG_DIR", tmp_path), pytest.raises(flight_log.LogRefused):
        flight_log.path_of(name)


def test_an_empty_logs_folder_is_refused(tmp_path):
    with mock.patch.object(cfg, "LOG_DIR", tmp_path), pytest.raises(flight_log.LogRefused, match="No .tlog"):
        flight_log.path_of(None)


def test_a_log_past_the_limit_is_refused(tmp_path):
    (tmp_path / "big.tlog").write_bytes(b"x")
    with (
        mock.patch.object(cfg, "LOG_DIR", tmp_path),
        mock.patch.object(flight_log, "MAX_TLOG_SIZE", 0),
        pytest.raises(flight_log.LogRefused, match="reads up to"),
    ):
        flight_log.path_of("big.tlog")


def test_a_log_with_no_messages_is_refused(tmp_path):
    (tmp_path / "empty.tlog").write_bytes(b"")
    with mock.patch.object(cfg, "LOG_DIR", tmp_path), pytest.raises(flight_log.LogRefused, match="no vehicle MAVLink"):
        flight_log.analyze("empty.tlog")
