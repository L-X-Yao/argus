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
        assert any(e['event_type'] == 'connected' for e in link.events)

    def test_armed_flag(self):
        from backend.mavlink_handlers import handle_heartbeat
        link = make_link()
        p = struct.pack('<IBBBBB', 5, 2, 3, 0x80, 0, 3)
        handle_heartbeat(p, len(p), link)
        assert link.armed
        assert any(e['event_type'] == 'armed' for e in link.events)

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
        assert link.events[0]['event_type'] == 'cmd_ack_ok'

    def test_failure(self):
        from backend.mavlink_handlers import handle_command_ack
        link = make_link()
        p = struct.pack('<HB', 400, 2)
        handle_command_ack(p, len(p), link)
        assert '拒绝' in link.events[0]['text']
        assert link.events[0]['event_type'] == 'cmd_ack_fail'

    def test_en_locale(self):
        from backend.mavlink_handlers import handle_command_ack
        link = make_link()
        link.locale = 'en'
        p = struct.pack('<HBB', 400, 0, 0)
        handle_command_ack(p, len(p), link)
        assert 'success' in link.events[0]['text']
        assert 'Arm/Disarm' in link.events[0]['text']


class TestMavlinkFrameParser:
    def test_parse_valid_frame(self):
        link = make_link()
        link._protocol = 'standard'
        payload = struct.pack('<IBBBBB', 5, 2, 3, 0, 0, 3)
        header = bytes([len(payload), 0, 0, 1, 255, 1, 0, 0, 0])
        frame = b'\xfd' + header + payload + b'\x00\x00'
        link._buf = frame
        result, consumed = link._parse_mavlink_frame()
        assert result is not None
        assert consumed == len(frame)
        assert result[0] == 0xFD

    def test_parse_incomplete(self):
        link = make_link()
        link._buf = b'\xfd\x09\x00'
        result, consumed = link._parse_mavlink_frame()
        assert result is None
        assert consumed == 0

    def test_skip_garbage(self):
        link = make_link()
        link._buf = b'\x00\x00\x00\xfd\x09' + b'\x00' * 20
        result, consumed = link._parse_mavlink_frame()
        assert result is None
        assert consumed == 3

    def test_no_magic(self):
        link = make_link()
        link._buf = b'\x00\x01\x02\x03'
        result, consumed = link._parse_mavlink_frame()
        assert result is None
        assert consumed == 4

    def test_auto_detect_pllink(self):
        link = make_link()
        link._protocol = 'auto'
        link._buf = b'\x50\x4c\x05\x00'
        link._next_frame()
        assert link._protocol == 'pllink'

    def test_auto_detect_mavlink(self):
        link = make_link()
        link._protocol = 'auto'
        link._buf = b'\xfd\x09\x00\x00\x01\x01\x01\x00\x00\x00'
        link._next_frame()
        assert link._protocol == 'standard'


class TestVehicleTypes:
    def test_copter(self):
        link = make_link()
        link.vtype_raw = 2
        _, btns, vn = link._get_vehicle_info()
        assert vn == '多旋翼'

    def test_plane(self):
        link = make_link()
        link.vtype_raw = 1
        _, btns, vn = link._get_vehicle_info()
        assert vn == '固定翼'

    def test_rover(self):
        link = make_link()
        link.vtype_raw = 10
        _, btns, vn = link._get_vehicle_info()
        assert vn == '地面车'

    def test_sub(self):
        link = make_link()
        link.vtype_raw = 12
        _, btns, vn = link._get_vehicle_info()
        assert vn == '水下机器人'

    def test_multi_vehicle_tracking(self):
        from pllink_proto import bm as _bm
        link = make_link()
        link._protocol = 'standard'
        hb = _bm(0, struct.pack('<IBBBBB', 5, 2, 3, 0, 0, 3), 0, 50, sysid=1)
        link._buf = hb
        payload, consumed = link._parse_mavlink_frame()
        assert payload is not None
        link._buf = link._buf[consumed:]
        link._process(payload)
        assert link.connected
        gps = _bm(33, struct.pack('<IiiiihhhH', 1000,
            int(34.258 * 1e7), int(108.942 * 1e7), 430000, 30000,
            500, 300, -100, 4500), 1, 104, sysid=1)
        link._buf = gps
        payload, consumed = link._parse_mavlink_frame()
        link._buf = link._buf[consumed:]
        link._process(payload)
        assert 1 in link._vehicles
        assert abs(link._vehicles[1]['lat'] - 34.258) < 0.001

    def test_get_state_vehicles_field(self):
        import time
        link = make_link()
        link.connected = True
        link.sysid = 1
        link._vehicles[2] = {'sysid': 2, 'lat': 35.0, 'lon': 109.0, 'alt': 50, 'hdg': 90, 't': time.time()}
        link._vehicles[1] = {'sysid': 1, 'lat': 34.0, 'lon': 108.0, 'alt': 30, 'hdg': 45, 't': time.time()}
        state = link.get_state()
        assert 'vehicles' in state
        assert len(state['vehicles']) == 1
        assert state['vehicles'][0]['sysid'] == 2

    def test_force_plane(self):
        link = make_link()
        link.vtype_raw = 2
        link.force_plane = True
        _, _, vn = link._get_vehicle_info()
        assert vn == '固定翼'


class TestServoOutput:
    def test_parses_8_servos(self):
        from backend.mavlink_handlers import handle_servo_output
        link = make_link()
        # offset 0: time_usec (I), then 8 x uint16 starting at offset 4
        # total = 4 + 16 = 20 bytes, handler needs pl >= 21 so pad 1 byte
        vals = [1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800]
        p = struct.pack('<I', 1000) + struct.pack('<8H', *vals) + b'\x00'
        handle_servo_output(p, len(p), link)
        assert link.servo_out[:8] == vals
        assert link.servo_out[8:] == [0] * 8

    def test_parses_16_servos(self):
        from backend.mavlink_handlers import handle_servo_output
        link = make_link()
        vals_lo = [1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800]
        vals_hi = [1900, 2000, 2100, 2200, 900, 950, 1000, 1050]
        # 4 bytes time + 8*2 lo servos + 1 port byte = 21 bytes, then 8*2 hi = 16 => 37 total
        p = struct.pack('<I', 1000) + struct.pack('<8H', *vals_lo) + struct.pack('<B', 0) + struct.pack('<8H', *vals_hi)
        handle_servo_output(p, len(p), link)
        assert link.servo_out[:8] == vals_lo
        assert link.servo_out[8:] == vals_hi


class TestRcChannels:
    def test_parses_channels_and_rssi(self):
        from backend.mavlink_handlers import handle_rc_channels
        link = make_link()
        # layout: time_boot_ms(I) + chancount(B) + 16 x uint16 + rssi(B) = 4+1+32+5(padding to 42)
        # handler reads channels from offset 5 (16 x H) and rssi at byte 41
        vals = [1000 + i * 50 for i in range(16)]
        p = struct.pack('<IB', 1000, 16) + struct.pack('<16H', *vals)
        # pad to 42 bytes: current = 4+1+32 = 37, need 42 => 5 more bytes, byte 41 is rssi
        p += b'\x00' * 4 + struct.pack('<B', 220)
        handle_rc_channels(p, len(p), link)
        assert link.rc_channels == vals
        assert link.rc_rssi == 220


class TestVibration:
    def test_parses_vibration(self):
        from backend.mavlink_handlers import handle_vibration
        link = make_link()
        # layout: time_usec(Q,8) + vibe_x(f,offset 8) + vibe_y(f,12) + vibe_z(f,16) + clip0(I,20) + clip1(I,24) + clip2(I,28)
        p = struct.pack('<Q', 1000) + struct.pack('<fff', 1.5, 2.5, 3.5) + struct.pack('<III', 10, 20, 30)
        handle_vibration(p, len(p), link)
        assert abs(link.vibe_x - 1.5) < 0.01
        assert abs(link.vibe_y - 2.5) < 0.01
        assert abs(link.vibe_z - 3.5) < 0.01
        assert link.vibe_clip0 == 10
        assert link.vibe_clip1 == 20
        assert link.vibe_clip2 == 30


class TestEkfStatus:
    def test_parses_ekf(self):
        from backend.mavlink_handlers import handle_ekf_status
        link = make_link()
        # layout: vel(f) + pos_h(f) + pos_v(f) + compass(f) + terrain(f) + flags(H)
        p = struct.pack('<fffffH', 0.1, 0.2, 0.3, 0.4, 0.5, 0x01FF)
        handle_ekf_status(p, len(p), link)
        assert abs(link.ekf_vel_var - 0.1) < 0.001
        assert abs(link.ekf_pos_h_var - 0.2) < 0.001
        assert abs(link.ekf_pos_v_var - 0.3) < 0.001
        assert abs(link.ekf_compass_var - 0.4) < 0.001
        assert link.ekf_flags == 0x01FF


class TestTerrainReport:
    def test_parses_terrain_alt(self):
        from backend.mavlink_handlers import handle_terrain_report
        link = make_link()
        # layout: lat(i,0) + lon(i,4) + spacing(H,8) + padding(H,10) + terrain_height(f,12)
        p = struct.pack('<iiHHf', int(34.0 * 1e7), int(108.0 * 1e7), 100, 0, 456.78)
        handle_terrain_report(p, len(p), link)
        assert abs(link.terrain_alt - 456.78) < 0.01


class TestWind:
    def test_parses_wind(self):
        from backend.mavlink_handlers import handle_wind
        link = make_link()
        # layout: direction(f) + speed(f) + speed_z(f)
        p = struct.pack('<fff', 270.0, 5.5, 1.0)
        handle_wind(p, len(p), link)
        assert abs(link.wind_dir - 270.0) < 0.01
        assert abs(link.wind_speed - 5.5) < 0.01

    def test_wind_dir_wraps(self):
        from backend.mavlink_handlers import handle_wind
        link = make_link()
        p = struct.pack('<fff', 370.0, 3.0, 0.0)
        handle_wind(p, len(p), link)
        assert abs(link.wind_dir - 10.0) < 0.01


class TestAutopilotVersion:
    def test_parses_version(self):
        from backend.mavlink_handlers import handle_autopilot_version
        link = make_link()
        # layout: capabilities(Q,0-7) + fw_version(I,8-11) + mw_version(I,12-15)
        #         os_version(I,16-19) + board_version(I,20-23) + git_hash(8 bytes,24-31)
        #         ... need at least 36 bytes total
        major, minor, patch = 4, 5, 3
        fw_ver = (major << 24) | (minor << 16) | (patch << 8) | 0
        board = 56
        git_hash = b'\xab\xcd\xef\x12\x34\x56\x78\x00'
        p = struct.pack('<Q', 0)  # capabilities (8 bytes)
        p += struct.pack('<I', fw_ver)  # fw_version at offset 8
        p += struct.pack('<I', 0)  # middleware_version at offset 12
        p += struct.pack('<I', 0)  # os_version at offset 16
        p += struct.pack('<I', board)  # board_version at offset 20
        p += git_hash  # git hash at offset 24-31
        p += struct.pack('<I', 0)  # padding to reach 36 bytes
        handle_autopilot_version(p, len(p), link)
        assert link.fw_version == 'v4.5.3'
        assert link.board_id == 56
        assert link.fw_git == 'abcdef12'


class TestMissionCurrent:
    def test_parses_wp_seq(self):
        from backend.mavlink_handlers import handle_mission_current
        link = make_link()
        p = struct.pack('<H', 7)
        handle_mission_current(p, len(p), link)
        assert link.wp_seq == 7


class TestHomePosition:
    def test_parses_home(self):
        from backend.mavlink_handlers import handle_home_position
        link = make_link()
        # layout: lat(i,0) + lon(i,4) + alt(i,8) + ... need at least 20 bytes
        hlat = int(34.258 * 1e7)
        hlon = int(108.942 * 1e7)
        p = struct.pack('<iii', hlat, hlon, 400000)
        p += b'\x00' * (20 - len(p))
        handle_home_position(p, len(p), link)
        assert abs(link.home_lat - 34.258) < 0.001
        assert abs(link.home_lon - 108.942) < 0.001

    def test_ignores_zero_lat(self):
        from backend.mavlink_handlers import handle_home_position
        link = make_link()
        p = struct.pack('<iii', 0, 0, 0)
        p += b'\x00' * (20 - len(p))
        handle_home_position(p, len(p), link)
        assert link.home_lat == 0.0


class TestMissionItemReached:
    def test_adds_event(self):
        from backend.mavlink_handlers import handle_mission_item_reached
        link = make_link()
        p = struct.pack('<H', 5)
        handle_mission_item_reached(p, len(p), link)
        assert len(link.events) == 1
        assert '5' in link.events[0]['text']
        assert '到达' in link.events[0]['text']


class TestMissionCount:
    def test_sets_dl_total(self):
        from backend.mavlink_handlers import handle_mission_count
        link = make_link()
        link._dl_pending = True
        # Stub send to prevent actual I/O
        link.send = lambda frame: None
        p = struct.pack('<HBB', 10, link.sysid, 1)
        handle_mission_count(p, len(p), link)
        assert link._dl_total == 10
        assert len(link._dl_items) == 10

    def test_zero_count(self):
        from backend.mavlink_handlers import handle_mission_count
        link = make_link()
        link._dl_pending = True
        p = struct.pack('<HBB', 0, link.sysid, 1)
        handle_mission_count(p, len(p), link)
        assert link._dl_total == 0
        assert link._dl_pending is False

    def test_ignored_when_not_pending(self):
        from backend.mavlink_handlers import handle_mission_count
        link = make_link()
        assert link._dl_pending is False
        p = struct.pack('<HBB', 5, link.sysid, 1)
        handle_mission_count(p, len(p), link)
        assert link._dl_total == 0


class TestMissionAck:
    def test_success(self):
        from backend.mavlink_handlers import handle_mission_ack
        link = make_link()
        link._mission_pending = True
        # layout: target_sys(B) + target_comp(B) + type(B) + mission_type(B)
        p = struct.pack('<BBBB', link.sysid, 1, 0, 0)
        handle_mission_ack(p, len(p), link)
        assert link._mission_pending is False
        assert len(link.events) == 1
        assert '成功' in link.events[0]['text']

    def test_failure(self):
        from backend.mavlink_handlers import handle_mission_ack
        link = make_link()
        link._mission_pending = True
        p = struct.pack('<BBBB', link.sysid, 1, 3, 0)
        handle_mission_ack(p, len(p), link)
        assert link._mission_pending is False
        assert '失败' in link.events[0]['text']

    def test_fence_ack(self):
        from backend.mavlink_handlers import handle_mission_ack
        link = make_link()
        link._fence_pending = True
        # mission_type=1 means fence
        p = struct.pack('<BBBB', link.sysid, 1, 0, 1)
        handle_mission_ack(p, len(p), link)
        assert link._fence_pending is False
        assert '围栏' in link.events[0]['text']


class TestLogEntry:
    def test_appends_to_log_list(self):
        from backend.mavlink_handlers import handle_log_entry
        link = make_link()
        # layout: time_utc(I) + size(I) + id(H) + num_logs(H) + last_log_num(H) = 14 bytes
        p = struct.pack('<IIHHH', 1700000000, 524288, 3, 5, 5)
        handle_log_entry(p, len(p), link)
        assert len(link._log_list) == 1
        assert link._log_list[0]['id'] == 3
        assert link._log_list[0]['size'] == 524288

    def test_last_log_triggers_message(self):
        from backend.mavlink_handlers import handle_log_entry
        link = make_link()
        # Two entries, second one has id == last_log_num
        p1 = struct.pack('<IIHHH', 1700000000, 100000, 1, 2, 2)
        handle_log_entry(p1, len(p1), link)
        assert len(link._log_messages) == 0
        p2 = struct.pack('<IIHHH', 1700000001, 200000, 2, 2, 2)
        handle_log_entry(p2, len(p2), link)
        assert len(link._log_messages) == 1
        assert link._log_messages[0]['type'] == 'log_list'


class TestLogData:
    def test_writes_data(self):
        from backend.mavlink_handlers import handle_log_data
        link = make_link()
        link._log_download_id = 5
        link._log_download_size = 20
        link._log_download_data = bytearray(20)
        link._log_download_ofs = 0
        # Stub send to prevent actual I/O
        link.send = lambda frame: None
        # layout: ofs(I) + id(H) + count(B) + data(...)
        data_chunk = bytes(range(10))
        p = struct.pack('<IHB', 0, 5, 10) + data_chunk
        handle_log_data(p, len(p), link)
        assert link._log_download_data[:10] == data_chunk
        assert link._log_download_ofs == 10

    def test_ignores_wrong_id(self):
        from backend.mavlink_handlers import handle_log_data
        link = make_link()
        link._log_download_id = 5
        link._log_download_size = 20
        link._log_download_data = bytearray(20)
        p = struct.pack('<IHB', 0, 99, 10) + bytes(10)
        handle_log_data(p, len(p), link)
        assert link._log_download_ofs == 0

    def test_complete_download(self):
        from backend.mavlink_handlers import handle_log_data
        link = make_link()
        link._log_download_id = 3
        link._log_download_size = 8
        link._log_download_data = bytearray(8)
        link.send = lambda frame: None
        data_chunk = b'\xAA\xBB\xCC\xDD\xEE\xFF\x11\x22'
        p = struct.pack('<IHB', 0, 3, 8) + data_chunk
        handle_log_data(p, len(p), link)
        assert link._log_download_id == -1
        assert any(m['type'] == 'log_complete' for m in link._log_messages)


class TestMissionItemInt:
    def test_stores_item(self):
        from backend.mavlink_handlers import handle_mission_item_int
        link = make_link()
        link._dl_pending = True
        link._dl_total = 3
        link._dl_items = [None] * 3
        link.send = lambda frame: None
        # layout: p1(f,0) + p2(f,4) + p3(f,8) + p4(f,12) + lat(i,16) + lon(i,20) + alt(f,24) + seq(H,28) + cmd(H,30)
        #         + target_sys(B,32) + target_comp(B,33) + frame(B,34) + current(B,35) + autocontinue(B,36) = 37 bytes
        lat = int(34.258 * 1e7)
        lon = int(108.942 * 1e7)
        p = struct.pack('<ffff', 0.0, 15.0, 0.0, 0.0)  # p1, p2, p3, p4
        p += struct.pack('<ii', lat, lon)
        p += struct.pack('<f', 100.0)  # alt
        p += struct.pack('<HH', 1, 16)  # seq=1, cmd=16 (waypoint)
        p += struct.pack('<BBBB', 1, 1, 3, 0)  # target_sys, target_comp, frame, current
        p += struct.pack('<B', 1)  # autocontinue
        handle_mission_item_int(p, len(p), link)
        assert link._dl_items[1] is not None
        assert link._dl_items[1]['seq'] == 1
        assert link._dl_items[1]['cmd'] == 16
        assert abs(link._dl_items[1]['lat'] - 34.258) < 0.001

    def test_last_item_completes_download(self):
        from backend.mavlink_handlers import handle_mission_item_int
        link = make_link()
        link._dl_pending = True
        link._dl_total = 1
        link._dl_items = [None]
        link.send = lambda frame: None
        lat = int(34.258 * 1e7)
        lon = int(108.942 * 1e7)
        p = struct.pack('<ffff', 0.0, 0.0, 0.0, 0.0)
        p += struct.pack('<ii', lat, lon)
        p += struct.pack('<f', 50.0)
        p += struct.pack('<HH', 0, 16)  # seq=0, cmd=16
        p += struct.pack('<BBBBB', 1, 1, 3, 0, 1)
        handle_mission_item_int(p, len(p), link)
        assert link._dl_pending is False


class TestMissionRequest:
    def test_no_crash_with_items(self):
        from backend.mavlink_handlers import handle_mission_request
        link = make_link()
        link._mission_pending = True
        link._mission_items = [
            {'seq': 0, 'frame': 3, 'cmd': 16, 'current': 0, 'autocontinue': 1,
             'p1': 0, 'p2': 0, 'p3': 0, 'p4': 0, 'lat': 34.258, 'lon': 108.942, 'alt': 100},
        ]
        link.send = lambda frame: None
        # layout: seq(B) + seq_hi(B) + target_sys(B) + target_comp(B) + mission_type(B)
        p = struct.pack('<BBBBB', 0, 0, 1, 1, 0)
        handle_mission_request(p, len(p), link)
        # No exception means success; mission_pending should still be True (ack clears it)
        assert link._mission_pending is True

    def test_no_crash_out_of_range(self):
        from backend.mavlink_handlers import handle_mission_request
        link = make_link()
        link._mission_pending = True
        link._mission_items = []
        link.send = lambda frame: None
        p = struct.pack('<BBBBB', 5, 0, 1, 1, 0)
        handle_mission_request(p, len(p), link)
        # Should not crash even if seq is out of range
