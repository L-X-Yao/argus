"""backend/flight_log.py: a recorded tlog summarised, and what it refuses to read."""

import json
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


def position(lat, lon, vx=0, vy=0, seq=0, rel_alt_mm=5000):
    payload = struct.pack("<Iiiiihhhh", 0, int(lat * 1e7), int(lon * 1e7), 15000, rel_alt_mm, vx, vy, 0, 9000)
    return fc_frame(33, payload, seq)


def other_vehicle(lat, lon, seq=0):
    payload = struct.pack("<Iiiiihhhh", 0, int(lat * 1e7), int(lon * 1e7), 0, 0, 0, 0, 0, 0)
    return bm(33, payload, seq, CRC_EXTRA[33], sysid=2, compid=1)


def sys_status(voltage_mv=12000, remaining=50, seq=0, current_ca=-1):
    # SYS_STATUS: present/enabled/health u32, load u16, voltage u16 mV, current i16 cA,
    # drop/errors u16, four counters u16, remaining i8
    payload = struct.pack("<IIIHHhHHHHHHb", 0, 0, 0, 100, voltage_mv, current_ca, 0, 0, 0, 0, 0, 0, remaining)
    return fc_frame(1, payload, seq)


def gps_raw(seq=0, fix=3, sats=9):
    # GPS_RAW_INT in MAVLink 2 wire order (fields sorted by size): time u64, lat/lon/alt i32,
    # eph/epv/vel/cog u16, fix u8, sats u8.
    payload = struct.pack("<QiiiHHHHBB", 0, int(31.2304e7), int(121.4737e7), 15000, 100, 100, 0, 0, fix, sats)
    return fc_frame(24, payload, seq)


def vibration(seq=0, level=1.5):
    payload = struct.pack("<QfffIII", 0, level, 0.5, 0.2, 0, 0, 0)
    return fc_frame(241, payload, seq)


def vfr_hud(speed=5.0, seq=0):
    payload = struct.pack("<ffffHH", 0.0, speed, 0.0, 0.0, 0, 0)
    return fc_frame(74, payload, seq)


def ekf(pos_horiz=0.25, terrain=0.0, seq=0):
    # EKF_STATUS_REPORT in MAVLink 2 wire order: velocity@0, pos_horiz@4,
    # pos_vert@8, compass@12, terrain@16, flags@20.
    payload = bytearray(22)
    struct.pack_into("<f", payload, 4, pos_horiz)
    struct.pack_into("<f", payload, 16, terrain)
    return fc_frame(193, payload, seq)


def mission_item(item_seq=0, seq=0):
    payload = bytearray(37)
    struct.pack_into("<H", payload, 28, item_seq)
    return fc_frame(73, payload, seq)


def mission_current(item_seq=0, seq=0):
    return fc_frame(42, struct.pack("<H", item_seq), seq)


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


def test_ekf_reads_the_horizontal_position_variance(tmp_path):
    # The terrain variance at offset 16 is 0.01; only the field at offset 4 is the metric,
    # and it is kept to four decimals.
    write_tlog(tmp_path / "argus_ekf.tlog", [heartbeat(armed=False, seq=0), ekf(pos_horiz=0.0123, terrain=0.01, seq=1)])
    with mock.patch.object(cfg, "LOG_DIR", tmp_path):
        summary = flight_log.analyze("argus_ekf.tlog")
    assert summary["ekf_max_pos_horiz_variance"] == 0.0123


def test_event_and_mission_lists_are_capped_while_counting(tmp_path):
    frames = [heartbeat(armed=False, seq=0)]
    frames += [statustext(text=f"warning {i}".encode(), seq=i + 1) for i in range(60)]
    frames += [mission_current(item_seq=i, seq=i + 61) for i in range(12)]
    write_tlog(tmp_path / "argus_long.tlog", frames)
    with mock.patch.object(cfg, "LOG_DIR", tmp_path):
        summary = flight_log.analyze("argus_long.tlog")
    assert len(summary["events"]) == flight_log.MAX_EVENTS
    assert summary["events_left_out"] == 10
    assert len(summary["mission"]["current_seqs"]) == 10
    assert summary["mission"]["current_seqs"][-1]["seq"] == 11


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


def test_a_nul_in_a_file_name_is_refused(tmp_path):
    with mock.patch.object(cfg, "LOG_DIR", tmp_path), pytest.raises(flight_log.LogRefused):
        flight_log.path_of("a\x00b.tlog")


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


def test_battery_start_and_end_are_summarised(tmp_path):
    frames = [
        heartbeat(armed=True, seq=0),
        sys_status(voltage_mv=12500, remaining=80, seq=1),
        sys_status(voltage_mv=11000, remaining=30, seq=2),
        heartbeat(armed=False, seq=3),
    ]
    write_tlog(tmp_path / "battery.tlog", frames)
    with mock.patch.object(cfg, "LOG_DIR", tmp_path):
        battery = flight_log.analyze("battery.tlog")["battery"]
    assert battery["start_voltage_v"] == 12.5
    assert battery["end_voltage_v"] == 11.0
    assert battery["min_voltage_v"] == 11.0
    assert battery["start_remaining_pct"] == 80
    assert battery["end_remaining_pct"] == 30
    assert battery["min_remaining_pct"] == 30


def test_mode_periods_are_not_limited_by_the_returned_mode_list(tmp_path):
    frames = [heartbeat(mode=4 if i % 2 == 0 else 5, armed=False, seq=i) for i in range(35)]
    write_tlog(tmp_path / "modes.tlog", frames)
    with mock.patch.object(cfg, "LOG_DIR", tmp_path):
        summary = flight_log.analyze("modes.tlog")
    assert len(summary["modes"]) == flight_log.MAX_MODES
    assert summary["mode_periods"] == 35


def comparison_flights(tmp_path):
    first = [
        heartbeat(mode=4, armed=True, seq=0),
        position(31.2304, 121.4737, seq=1),
        sys_status(voltage_mv=12000, remaining=50, seq=2, current_ca=1000),
        gps_raw(seq=3),
        vibration(seq=4),
        vfr_hud(speed=4.0, seq=5),
        ekf(pos_horiz=0.2, seq=6),
        mission_item(seq=7),
        statustext(text=b"one", seq=8),
        heartbeat(mode=4, armed=False, seq=9),
    ]
    second = [
        heartbeat(mode=4, armed=True, seq=0),
        position(31.2304, 121.4737, vx=100, seq=1, rel_alt_mm=10000),
        sys_status(voltage_mv=13000, remaining=80, seq=2, current_ca=2000),
        gps_raw(seq=3, fix=4, sats=12),
        vibration(seq=4, level=2.5),
        vfr_hud(speed=6.5, seq=5),
        ekf(pos_horiz=0.5, seq=6),
        mission_item(item_seq=0, seq=7),
        mission_item(item_seq=1, seq=8),
        statustext(text=b"one", seq=9),
        statustext(text=b"two", seq=10),
        position(31.2314, 121.4737, vx=100, seq=11, rel_alt_mm=10000),
        sys_status(voltage_mv=11000, remaining=30, seq=12, current_ca=500),
        heartbeat(mode=5, armed=False, seq=13),
    ]
    write_tlog(tmp_path / "first.tlog", first, spacing_usec=1_000_000)
    write_tlog(tmp_path / "second.tlog", second, spacing_usec=1_000_000)


def test_two_flights_are_compared_through_the_same_analysis(tmp_path):
    comparison_flights(tmp_path)
    with mock.patch.object(cfg, "LOG_DIR", tmp_path):
        result = flight_log.compare("first.tlog", "second.tlog")
    assert result["first"] == "first.tlog"
    assert result["second"] == "second.tlog"
    assert result["delta_direction"] == "second - first"
    metrics = result["metrics"]

    def check(name, first, second, delta, group=None):
        values = metrics[group][name] if group else metrics[name]
        assert values == {"first": first, "second": second, "delta": delta}

    check("duration_s", 9.0, 13.0, 4.0)
    check("armed_seconds", 9.0, 13.0, 4.0)
    check("max_altitude_above_home_m", 5.0, 10.0, 5.0)
    check("max_ground_speed_ms", 4.0, 6.5, 2.5)
    check("distance_m", 0, metrics["distance_m"]["second"], metrics["distance_m"]["second"])
    assert metrics["distance_m"]["second"] > 50
    check("min_voltage_v", 12.0, 11.0, -1.0, "battery")
    check("start_voltage_v", 12.0, 13.0, 1.0, "battery")
    check("end_voltage_v", 12.0, 11.0, -1.0, "battery")
    check("max_current_a", 10.0, 20.0, 10.0, "battery")
    check("min_remaining_pct", 50, 30, -20, "battery")
    check("start_remaining_pct", 50, 80, 30, "battery")
    check("end_remaining_pct", 50, 30, -20, "battery")
    check("max_fix", 3, 4, 1, "gps")
    check("max_satellites", 9, 12, 3, "gps")
    check("vibration_max", 1.5, 2.5, 1.0)
    check("ekf_max_pos_horiz_variance", 0.2, 0.5, 0.3)
    check("mode_periods", 1, 2, 1)
    check("event_count", 1, 2, 1)
    check("mission_items_seen", 1, 2, 1)


def test_a_missing_metric_has_no_delta(tmp_path):
    write_tlog(tmp_path / "bare.tlog", [heartbeat(armed=False), heartbeat(armed=False, seq=1)])
    with mock.patch.object(cfg, "LOG_DIR", tmp_path):
        result = flight_log.compare("bare.tlog", "bare.tlog")
    assert result["metrics"]["max_ground_speed_ms"] == {"first": None, "second": None, "delta": None}
    assert result["metrics"]["battery"]["start_voltage_v"] == {"first": None, "second": None, "delta": None}


def test_compare_stops_when_the_first_analysis_is_cancelled():
    cancelled = object()
    with mock.patch.object(flight_log, "analyze", return_value=None) as analyze:
        assert flight_log.compare("first.tlog", "second.tlog", cancelled) is None
    analyze.assert_called_once_with("first.tlog", cancelled)


def test_the_second_log_is_held_to_the_same_size_limit(tmp_path):
    comparison_flights(tmp_path)
    limit = (tmp_path / "first.tlog").stat().st_size
    assert (tmp_path / "second.tlog").stat().st_size > limit
    with (
        mock.patch.object(cfg, "LOG_DIR", tmp_path),
        mock.patch.object(flight_log, "MAX_TLOG_SIZE", limit),
        pytest.raises(flight_log.LogRefused, match="second.tlog.*reads up to"),
    ):
        flight_log.compare("first.tlog", "second.tlog")


def non_finite_flights(tmp_path):
    for name, speed, vibration_y in (("first.tlog", 4.0, 2.0), ("second.tlog", 6.0, 3.0)):
        vibration_frame = fc_frame(
            241,
            struct.pack("<QfffIII", 0, float("inf"), vibration_y, float("nan"), 0, 0, 0),
            3,
        )
        frames = [
            heartbeat(armed=False, seq=0),
            vfr_hud(speed=float("inf"), seq=1),
            vfr_hud(speed=speed, seq=2),
            vibration_frame,
        ]
        write_tlog(tmp_path / name, frames)


def test_non_finite_peaks_are_ignored(tmp_path):
    non_finite_flights(tmp_path)
    with mock.patch.object(cfg, "LOG_DIR", tmp_path):
        summary = flight_log.analyze("first.tlog")
    assert summary["max_ground_speed_ms"] == 4.0
    assert summary["vibration_max"] == 2.0
    json.dumps(summary, allow_nan=False)


def test_non_finite_peaks_remain_json_safe_when_compared(tmp_path):
    non_finite_flights(tmp_path)
    with mock.patch.object(cfg, "LOG_DIR", tmp_path):
        result = flight_log.compare("first.tlog", "second.tlog")
    json.dumps(result, allow_nan=False)
    assert result["metrics"]["max_ground_speed_ms"] == {"first": 4.0, "second": 6.0, "delta": 2.0}
    assert result["metrics"]["vibration_max"] == {"first": 2.0, "second": 3.0, "delta": 1.0}
