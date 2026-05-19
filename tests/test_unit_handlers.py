"""Unit tests: MAVLink message handlers."""
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.drone_link import DroneLink


def make_link():
    link = DroneLink()
    return link


class TestHeartbeat:
    def test_sets_connected(self):
        from backend.mavlink_handlers import handle_heartbeat
        link = make_link()
        p = struct.pack('<IBBBBB', 5, 2, 3, 0, 0, 3)
        handle_heartbeat(p, len(p), link)
        assert link.connected
        assert link.mode == 5
        assert link.vtype_raw == 2

    def test_armed_flag(self):
        from backend.mavlink_handlers import handle_heartbeat
        link = make_link()
        p = struct.pack('<IBBBBB', 5, 2, 3, 0x80, 0, 3)
        handle_heartbeat(p, len(p), link)
        assert link.armed

    def test_disarm_generates_summary(self):
        from backend.mavlink_handlers import handle_heartbeat
        link = make_link()
        p_arm = struct.pack('<IBBBBB', 5, 2, 3, 0x80, 0, 3)
        handle_heartbeat(p_arm, len(p_arm), link)
        assert link.armed
        p_disarm = struct.pack('<IBBBBB', 5, 2, 3, 0, 0, 3)
        handle_heartbeat(p_disarm, len(p_disarm), link)
        assert not link.armed
        assert link.flight_summary is not None
        assert 'duration' in link.flight_summary


class TestAttitude:
    def test_parses_attitude(self):
        from backend.mavlink_handlers import handle_attitude
        link = make_link()
        roll_rad = math.radians(10.5)
        pitch_rad = math.radians(-5.2)
        yaw_rad = math.radians(180.0)
        p = struct.pack('<Iffffff', 1000, roll_rad, pitch_rad, yaw_rad, 0, 0, 0)
        handle_attitude(p, len(p), link)
        assert abs(link.roll - 10.5) < 0.1
        assert abs(link.pitch - (-5.2)) < 0.1
        assert abs(link.yaw - 180.0) < 0.1

    def test_negative_yaw_wrapped(self):
        from backend.mavlink_handlers import handle_attitude
        link = make_link()
        yaw_rad = math.radians(-90.0)
        p = struct.pack('<Iffffff', 1000, 0, 0, yaw_rad, 0, 0, 0)
        handle_attitude(p, len(p), link)
        assert link.yaw > 0


class TestGlobalPosition:
    def test_parses_position(self):
        from backend.mavlink_handlers import handle_global_position_int
        link = make_link()
        lat7 = int(34.258 * 1e7)
        lon7 = int(108.942 * 1e7)
        alt_msl = 400 * 1000
        alt_rel = 30 * 1000
        p = struct.pack('<IiiiihhhH', 1000, lat7, lon7, alt_msl, alt_rel,
                        500, 300, -100, 4500)
        handle_global_position_int(p, len(p), link)
        assert abs(link.lat - 34.258) < 0.001
        assert abs(link.lon - 108.942) < 0.001
        assert abs(link.alt_rel - 30.0) < 0.5
        assert abs(link.alt_msl - 400.0) < 0.5
        assert link.gs > 0

    def test_sets_home(self):
        from backend.mavlink_handlers import handle_global_position_int
        link = make_link()
        lat7 = int(34.258 * 1e7)
        lon7 = int(108.942 * 1e7)
        p = struct.pack('<IiiiihhhH', 1000, lat7, lon7, 400000, 30000,
                        0, 0, 0, 0)
        handle_global_position_int(p, len(p), link)
        assert link.home_lat != 0


class TestSysStatus:
    def test_parses_battery(self):
        from backend.mavlink_handlers import handle_sys_status
        link = make_link()
        v_mv = 25200
        c_ca = 1200
        rem = 85
        p = struct.pack('<IIIHHhHHHHHHb',
                        0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF,
                        500, v_mv, c_ca,
                        0, 0, 0, 0, 0, 0, rem)
        handle_sys_status(p, len(p), link)
        assert abs(link.voltage - 25.2) < 0.1
        assert abs(link.current - 12.0) < 0.1
        assert link.remaining == 85


class TestGpsRaw:
    def test_parses_gps(self):
        from backend.mavlink_handlers import handle_gps_raw_int
        link = make_link()
        p = struct.pack('<QiiiHHHHBB', 1000000,
                        int(34.258 * 1e7), int(108.942 * 1e7), 400000,
                        150, 200, 500, 4500,
                        3, 14)
        handle_gps_raw_int(p, len(p), link)
        assert link.gps_fix == 3
        assert link.gps_sats == 14


class TestStatustext:
    def test_filters_and_adds_event(self):
        from backend.mavlink_handlers import handle_statustext
        link = make_link()
        text = b'PreArm: Need 3D Fix'
        p = struct.pack('<B', 6) + text + bytes(50 - len(text))
        handle_statustext(p, len(p), link)
        assert len(link.events) == 1
        assert 'PreArm' not in link.events[0]['text']


class TestCommandAck:
    def test_adds_event(self):
        from backend.mavlink_handlers import handle_command_ack
        link = make_link()
        p = struct.pack('<HBB', 400, 0, 0)
        handle_command_ack(p, len(p), link)
        assert len(link.events) == 1
        assert '成功' in link.events[0]['text']

    def test_failure(self):
        from backend.mavlink_handlers import handle_command_ack
        link = make_link()
        # command_ack: bytes[0:2]=cmd(H), byte[2]=result
        p = struct.pack('<HB', 400, 4)
        handle_command_ack(p, len(p), link)
        assert '失败' in link.events[0]['text']
