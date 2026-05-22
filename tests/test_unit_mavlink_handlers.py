"""Tests for MAVLink message handlers — parsing, state updates, edge cases."""
from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.drone_link import DroneLink
from backend.mavlink_handlers import (
    handle_attitude,
    handle_battery_status,
    handle_command_ack,
    handle_global_position_int,
    handle_gps_raw_int,
    handle_heartbeat,
    handle_home_position,
    handle_mission_current,
    handle_mission_item_reached,
    handle_rc_channels,
    handle_servo_output,
    handle_statustext,
    handle_sys_status,
    handle_terrain_report,
    handle_vibration,
    handle_wind,
)


def _make_link() -> DroneLink:
    link = DroneLink()
    link.locale = 'en'
    return link


class TestHandleHeartbeat:
    def test_sets_armed(self):
        link = _make_link()
        p = bytearray(9)
        p[6] = 0x80  # armed bit
        handle_heartbeat(p, len(p), link)
        assert link.vehicle.armed is True

    def test_disarm(self):
        link = _make_link()
        link.vehicle.armed = True
        link.vehicle.armed_time = time.time() - 60
        p = bytearray(9)
        p[6] = 0x00
        handle_heartbeat(p, len(p), link)
        assert link.vehicle.armed is False
        assert link.vehicle.flight_summary is not None

    def test_sets_connected(self):
        link = _make_link()
        link._raw_sysid = 1
        p = bytearray(9)
        handle_heartbeat(p, len(p), link)
        assert link.connected is True

    def test_too_short_payload_ignored(self):
        link = _make_link()
        p = bytearray(5)
        handle_heartbeat(p, len(p), link)
        assert link.connected is False

    def test_vehicle_type_detected(self):
        link = _make_link()
        link._raw_sysid = 1
        p = bytearray(9)
        p[4] = 2  # quadrotor
        handle_heartbeat(p, len(p), link)
        assert link.vehicle.vtype_raw == 2

    def test_arm_resets_flight_stats(self):
        link = _make_link()
        link.vehicle.max_alt = 100
        link.vehicle.max_speed = 50
        link._raw_sysid = 1
        p = bytearray(9)
        p[6] = 0x80
        handle_heartbeat(p, len(p), link)
        assert link.vehicle.max_alt == 0
        assert link.vehicle.max_speed == 0


class TestHandleAttitude:
    def test_parses_attitude(self):
        link = _make_link()
        p = bytearray(20)
        struct.pack_into('<f', p, 4, 0.1)   # roll
        struct.pack_into('<f', p, 8, -0.2)  # pitch
        struct.pack_into('<f', p, 12, 1.5)  # yaw
        handle_attitude(p, len(p), link)
        assert abs(link.attitude.roll - 5.73) < 0.1
        assert abs(link.attitude.pitch - (-11.46)) < 0.1

    def test_yaw_wraps_positive(self):
        link = _make_link()
        p = bytearray(20)
        struct.pack_into('<f', p, 12, -1.0)  # negative yaw
        handle_attitude(p, len(p), link)
        assert link.attitude.yaw > 0

    def test_short_payload_ignored(self):
        link = _make_link()
        p = bytearray(10)
        handle_attitude(p, len(p), link)
        assert link.attitude.roll == 0


class TestHandleGlobalPositionInt:
    def test_parses_position(self):
        link = _make_link()
        p = bytearray(30)
        struct.pack_into('<i', p, 4, int(39.9 * 1e7))   # lat
        struct.pack_into('<i', p, 8, int(116.4 * 1e7))  # lon
        struct.pack_into('<i', p, 12, 500_000)           # alt_msl (500m)
        struct.pack_into('<i', p, 16, 100_000)           # alt_rel (100m)
        handle_global_position_int(p, len(p), link)
        assert abs(link.attitude.lat - 39.9) < 0.001
        assert abs(link.attitude.lon - 116.4) < 0.001
        assert abs(link.attitude.alt_msl - 500) < 1
        assert abs(link.attitude.alt_rel - 100) < 1

    def test_auto_sets_home(self):
        link = _make_link()
        p = bytearray(30)
        struct.pack_into('<i', p, 4, int(30.0 * 1e7))
        struct.pack_into('<i', p, 8, int(120.0 * 1e7))
        struct.pack_into('<i', p, 12, 0)
        struct.pack_into('<i', p, 16, 0)
        handle_global_position_int(p, len(p), link)
        assert abs(link.attitude.home_lat - 30.0) < 0.001

    def test_updates_max_alt_when_armed(self):
        link = _make_link()
        link.vehicle.armed = True
        p = bytearray(30)
        struct.pack_into('<i', p, 4, int(30.0 * 1e7))
        struct.pack_into('<i', p, 8, int(120.0 * 1e7))
        struct.pack_into('<i', p, 12, 0)
        struct.pack_into('<i', p, 16, 200_000)  # 200m
        handle_global_position_int(p, len(p), link)
        assert link.vehicle.max_alt == 200.0


class TestHandleSysStatus:
    def test_parses_voltage(self):
        link = _make_link()
        p = bytearray(35)
        struct.pack_into('<H', p, 14, 12600)  # 12.6V
        handle_sys_status(p, len(p), link)
        assert abs(link.battery.voltage - 12.6) < 0.01

    def test_parses_current(self):
        link = _make_link()
        p = bytearray(35)
        struct.pack_into('<H', p, 14, 12000)
        struct.pack_into('<h', p, 16, 1550)  # 15.5A
        handle_sys_status(p, len(p), link)
        assert abs(link.battery.current - 15.5) < 0.1

    def test_parses_remaining(self):
        link = _make_link()
        p = bytearray(35)
        struct.pack_into('<H', p, 14, 12000)
        struct.pack_into('<b', p, 30, 75)
        handle_sys_status(p, len(p), link)
        assert link.battery.remaining == 75


class TestHandleGpsRawInt:
    def test_parses_fix_and_sats(self):
        link = _make_link()
        p = bytearray(31)
        p[28] = 3  # 3D fix
        p[29] = 12
        handle_gps_raw_int(p, len(p), link)
        assert link.gps.gps_fix == 3
        assert link.gps.gps_sats == 12

    def test_short_payload(self):
        link = _make_link()
        p = bytearray(20)
        handle_gps_raw_int(p, len(p), link)
        assert link.gps.gps_fix == 0


class TestHandleMissionCurrent:
    def test_parses_sequence(self):
        link = _make_link()
        p = bytearray(4)
        struct.pack_into('<H', p, 0, 5)
        handle_mission_current(p, len(p), link)
        assert link.mission.wp_seq == 5


class TestHandleHomePosition:
    def test_sets_home(self):
        link = _make_link()
        p = bytearray(24)
        struct.pack_into('<i', p, 0, int(40.0 * 1e7))
        struct.pack_into('<i', p, 4, int(116.0 * 1e7))
        handle_home_position(p, len(p), link)
        assert abs(link.attitude.home_lat - 40.0) < 0.001

    def test_ignores_zero_home(self):
        link = _make_link()
        p = bytearray(24)
        struct.pack_into('<i', p, 0, 0)
        struct.pack_into('<i', p, 4, 0)
        handle_home_position(p, len(p), link)
        assert link.attitude.home_lat == 0


class TestHandleCommandAck:
    def test_success_ack(self):
        link = _make_link()
        p = bytearray(4)
        struct.pack_into('<H', p, 0, 400)  # arm/disarm
        p[2] = 0  # success
        handle_command_ack(p, len(p), link)
        assert any('Arm/Disarm' in e['text'] and 'success' in e['text'] for e in link.events)

    def test_in_progress_ignored(self):
        link = _make_link()
        p = bytearray(4)
        struct.pack_into('<H', p, 0, 400)
        p[2] = 4  # in progress
        handle_command_ack(p, len(p), link)
        assert len(link.events) == 0

    def test_failure_ack(self):
        link = _make_link()
        p = bytearray(4)
        struct.pack_into('<H', p, 0, 176)  # mode
        p[2] = 2  # denied
        handle_command_ack(p, len(p), link)
        assert any(e['event_type'] == 'cmd_ack_fail' for e in link.events)


class TestHandleStatustext:
    def test_parses_message(self):
        link = _make_link()
        msg = b'\x06' + b'GPS: 3D Fix\x00' + b'\x00' * 40
        handle_statustext(msg, len(msg), link)
        assert any('3D Fix' in e['text'] for e in link.events)

    def test_prearm_message_stored(self):
        link = _make_link()
        msg = b'\x06' + b'PreArm: compass not calibrated\x00' + b'\x00' * 20
        handle_statustext(msg, len(msg), link)
        assert any('compass not calibrated' in m for m in link._prearm_messages)

    def test_prearm_list_capped(self):
        link = _make_link()
        for i in range(25):
            msg = b'\x06' + f'PreArm: error {i}'.encode().ljust(50, b'\x00')
            handle_statustext(msg, len(msg), link)
        assert len(link._prearm_messages) <= 20


class TestHandleServoOutput:
    def test_parses_8_channels(self):
        link = _make_link()
        p = bytearray(21)
        for i in range(8):
            struct.pack_into('<H', p, 4 + i * 2, 1500 + i * 10)
        handle_servo_output(p, len(p), link)
        assert link.rc_servo.servo_out[0] == 1500
        assert link.rc_servo.servo_out[7] == 1570


class TestHandleRcChannels:
    def test_parses_16_channels(self):
        link = _make_link()
        p = bytearray(45)
        for i in range(16):
            struct.pack_into('<H', p, 5 + i * 2, 1000 + i * 50)
        p[41] = 200  # rssi
        handle_rc_channels(p, len(p), link)
        assert link.rc_servo.rc_channels[0] == 1000
        assert link.rc_servo.rc_rssi == 200


class TestHandleVibration:
    def test_parses_vibration(self):
        link = _make_link()
        p = bytearray(36)
        struct.pack_into('<f', p, 8, 15.5)
        struct.pack_into('<f', p, 12, 20.3)
        struct.pack_into('<f', p, 16, 10.1)
        struct.pack_into('<I', p, 20, 5)
        struct.pack_into('<I', p, 24, 10)
        struct.pack_into('<I', p, 28, 3)
        handle_vibration(p, len(p), link)
        assert abs(link.diagnostic.vibe_x - 15.5) < 0.1
        assert link.diagnostic.vibe_clip0 == 5


class TestHandleWind:
    def test_parses_wind(self):
        link = _make_link()
        p = bytearray(16)
        struct.pack_into('<f', p, 0, 270.0)  # direction
        struct.pack_into('<f', p, 4, 5.5)    # speed
        handle_wind(p, len(p), link)
        assert link.diagnostic.wind_dir == 270.0
        assert abs(link.diagnostic.wind_speed - 5.5) < 0.1


class TestHandleTerrainReport:
    def test_parses_terrain_alt(self):
        link = _make_link()
        p = bytearray(20)
        struct.pack_into('<f', p, 12, 150.5)
        handle_terrain_report(p, len(p), link)
        assert abs(link.diagnostic.terrain_alt - 150.5) < 0.1


class TestHandleBatteryStatus:
    def test_parses_cells(self):
        link = _make_link()
        p = bytearray(40)
        struct.pack_into('<H', p, 10, 4200)
        struct.pack_into('<H', p, 12, 4150)
        struct.pack_into('<H', p, 14, 4180)
        struct.pack_into('<H', p, 16, 0xFFFF)
        handle_battery_status(p, len(p), link)
        assert len(link.battery.battery_cells) == 3
        assert abs(link.battery.battery_cells[0] - 4.2) < 0.01

    def test_no_cells(self):
        link = _make_link()
        p = bytearray(40)
        struct.pack_into('<H', p, 10, 0xFFFF)
        handle_battery_status(p, len(p), link)
        assert len(link.battery.battery_cells) == 0


class TestHandleMissionItemReached:
    def test_fires_event(self):
        link = _make_link()
        p = bytearray(4)
        struct.pack_into('<H', p, 0, 3)
        handle_mission_item_reached(p, len(p), link)
        assert any('3' in e['text'] for e in link.events)
