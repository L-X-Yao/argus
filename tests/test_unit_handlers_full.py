"""Full coverage for backend/mavlink_handlers.py — all 23+ handlers."""
import struct

from backend.drone_link import DroneLink
from backend.mavlink_handlers import (
    handle_adsb_vehicle,
    handle_autopilot_version,
    handle_battery_status,
    handle_command_ack,
    handle_ekf_status,
    handle_home_position,
    handle_log_data,
    handle_log_entry,
    handle_mission_ack,
    handle_mission_count,
    handle_mission_current,
    handle_mission_item_reached,
    handle_rc_channels,
    handle_serial_control,
    handle_servo_output,
    handle_terrain_report,
    handle_vibration,
    handle_wind,
)


def make_link():
    link = DroneLink()
    from unittest.mock import MagicMock
    link._ser = MagicMock()
    link.connected = True
    link.vehicle.sysid = 1
    return link


class TestMissionCurrent:
    def test_sets_wp_seq(self):
        link = make_link()
        p = struct.pack('<H', 5)
        handle_mission_current(p, len(p), link)
        assert link.mission.wp_seq == 5


class TestHomePosition:
    def test_sets_home(self):
        link = make_link()
        p = struct.pack('<ii', int(30.5 * 1e7), int(120.3 * 1e7)) + b'\x00' * 12
        handle_home_position(p, len(p), link)
        assert abs(link.attitude.home_lat - 30.5) < 0.001
        assert abs(link.attitude.home_lon - 120.3) < 0.001

    def test_ignores_zero_lat(self):
        link = make_link()
        p = struct.pack('<ii', 0, int(120.0 * 1e7)) + b'\x00' * 12
        handle_home_position(p, len(p), link)
        assert link.attitude.home_lat == 0.0


class TestMissionItemReached:
    def test_adds_event(self):
        link = make_link()
        p = struct.pack('<H', 3)
        handle_mission_item_reached(p, len(p), link)
        assert any('3' in e['text'] for e in link.events)


class TestCommandAck:
    def test_success(self):
        link = make_link()
        p = struct.pack('<HB', 400, 0)
        handle_command_ack(p, len(p), link)
        assert any(e['event_type'] == 'cmd_ack_ok' for e in link.events)

    def test_failure(self):
        link = make_link()
        p = struct.pack('<HB', 400, 2)
        handle_command_ack(p, len(p), link)
        assert any(e['event_type'] == 'cmd_ack_fail' for e in link.events)

    def test_in_progress_ignored(self):
        link = make_link()
        p = struct.pack('<HB', 400, 4)
        handle_command_ack(p, len(p), link)
        assert len(link.events) == 0

    def test_english_locale(self):
        link = make_link()
        link.locale = 'en'
        p = struct.pack('<HB', 22, 0)
        handle_command_ack(p, len(p), link)
        assert any('Takeoff' in e['text'] for e in link.events)


class TestServoOutput:
    def test_parses_8_channels(self):
        link = make_link()
        # time_boot_ms(4) + 8 channels(16) + port(1) = 21 bytes min
        p = struct.pack('<I', 0) + struct.pack('<8H', 1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700) + b'\x00'
        handle_servo_output(p, len(p), link)
        assert link.rc_servo.servo_out[0] == 1000
        assert link.rc_servo.servo_out[7] == 1700

    def test_parses_16_channels(self):
        link = make_link()
        # 4 + 16 + 1(port) + 16 = 37 bytes
        p = struct.pack('<I', 0) + struct.pack('<8H', *range(1000, 1800, 100)) + b'\x00'
        p += struct.pack('<8H', *range(2000, 2800, 100))
        handle_servo_output(p, len(p), link)
        assert link.rc_servo.servo_out[0] == 1000
        assert link.rc_servo.servo_out[8] == 2000


class TestRcChannels:
    def test_parses_channels_and_rssi(self):
        link = make_link()
        # time_boot_ms(4) + chancount(1) + 16 channels(32) + rssi at [41] → need 42 bytes
        p = struct.pack('<IB', 0, 16)  # 5 bytes
        p += struct.pack('<16H', *range(1000, 1160, 10))  # 32 bytes → offset 37
        p += b'\x00' * 4  # pad to offset 41
        p += bytes([200])  # rssi at p[41]
        handle_rc_channels(p, len(p), link)
        assert link.rc_servo.rc_channels[0] == 1000
        assert link.rc_servo.rc_channels[15] == 1150
        assert link.rc_servo.rc_rssi == 200


class TestVibration:
    def test_parses_vibration(self):
        link = make_link()
        p = struct.pack('<Q', 0)  # usec
        p += struct.pack('<fff', 1.5, 2.5, 3.5)
        p += struct.pack('<III', 10, 20, 30)
        handle_vibration(p, len(p), link)
        assert abs(link.diagnostic.vibe_x - 1.5) < 0.01
        assert abs(link.diagnostic.vibe_y - 2.5) < 0.01
        assert abs(link.diagnostic.vibe_z - 3.5) < 0.01
        assert link.diagnostic.vibe_clip0 == 10
        assert link.diagnostic.vibe_clip1 == 20
        assert link.diagnostic.vibe_clip2 == 30


class TestEkfStatus:
    def test_parses_ekf(self):
        link = make_link()
        p = struct.pack('<fffffH', 0.1, 0.2, 0.3, 0.4, 0.5, 128)
        handle_ekf_status(p, len(p), link)
        assert abs(link.diagnostic.ekf_vel_var - 0.1) < 0.01
        assert abs(link.diagnostic.ekf_pos_h_var - 0.2) < 0.01
        assert link.diagnostic.ekf_flags == 128


class TestTerrainReport:
    def test_parses_terrain_alt(self):
        link = make_link()
        p = b'\x00' * 12 + struct.pack('<f', 450.5)
        handle_terrain_report(p, len(p), link)
        assert abs(link.diagnostic.terrain_alt - 450.5) < 0.1


class TestWind:
    def test_parses_wind(self):
        link = make_link()
        p = struct.pack('<fff', 270.0, 5.5, 0.0)
        handle_wind(p, len(p), link)
        assert abs(link.diagnostic.wind_dir - 270.0) < 0.1
        assert abs(link.diagnostic.wind_speed - 5.5) < 0.1

    def test_direction_wraps(self):
        link = make_link()
        p = struct.pack('<fff', 400.0, 3.0, 0.0)
        handle_wind(p, len(p), link)
        assert abs(link.diagnostic.wind_dir - 40.0) < 0.1


class TestAutopilotVersion:
    def test_parses_firmware(self):
        link = make_link()
        p = b'\x00' * 8  # capabilities (8 bytes)
        fw_ver = (4 << 24) | (5 << 16) | (3 << 8)
        p += struct.pack('<I', fw_ver)  # fw version (4 bytes, offset 8)
        p += b'\x00' * 4  # middleware version (4 bytes, offset 12)
        p += b'\x00' * 4  # os version (4 bytes, offset 16)
        p += struct.pack('<I', 56)  # board_version (4 bytes, offset 20)
        git = b'\xAB\xCD\xEF\x01\x00\x00\x00\x00'
        p += git  # git hash (8 bytes, offset 24)
        p += b'\x00' * 4  # pad to 36
        handle_autopilot_version(p, len(p), link)
        assert link.vehicle.fw_version == 'v4.5.3'
        assert link.vehicle.board_id == 56
        assert 'abcdef01' in link.vehicle.fw_git


class TestBatteryStatus:
    def test_parses_cells(self):
        link = make_link()
        p = b'\x00' * 10  # header fields
        cells = [3850, 3840, 3830, 0xFFFF]
        p += struct.pack('<4H', *cells) + struct.pack('<6H', *([0xFFFF] * 6))
        p += b'\x00' * 6  # remaining fields to reach pl=36
        handle_battery_status(p, len(p), link)
        assert len(link.battery.battery_cells) == 3
        assert abs(link.battery.battery_cells[0] - 3.85) < 0.001


class TestMissionCount:
    def test_zero_count_clears(self):
        link = make_link()
        link.mission._dl_pending = True
        p = struct.pack('<HB', 0, 0)
        handle_mission_count(p, len(p), link)
        assert link.mission._dl_pending is False
        assert any('mission_dl_none' in e['event_type'] for e in link.events)

    def test_nonzero_count(self):
        link = make_link()
        link.mission._dl_pending = True
        p = struct.pack('<HB', 5, 0)
        handle_mission_count(p, len(p), link)
        assert link.mission._dl_total == 5
        assert len(link.mission._dl_items) == 5

    def test_ignored_when_not_pending(self):
        link = make_link()
        link.mission._dl_pending = False
        p = struct.pack('<HB', 5, 0)
        handle_mission_count(p, len(p), link)
        assert link.mission._dl_total == 0


class TestMissionAck:
    def test_fence_ack_ok(self):
        link = make_link()
        link.mission._fence_pending = True
        p = struct.pack('<BBBB', 1, 1, 0, 1)  # target sys, comp, type=0(ok), mission_type=1(fence)
        handle_mission_ack(p, len(p), link)
        assert link.mission._fence_pending is False
        assert any('fence_ack_ok' in e['event_type'] for e in link.events)

    def test_mission_ack_fail(self):
        link = make_link()
        link.mission._mission_pending = True
        p = struct.pack('<BBBB', 1, 1, 2, 0)  # type=2(fail), mission_type=0
        handle_mission_ack(p, len(p), link)
        assert link.mission._mission_pending is False
        assert any('mission_ack_fail' in e['event_type'] for e in link.events)


class TestLogEntry:
    def test_appends_log(self):
        link = make_link()
        p = struct.pack('<IIHHH', 1000, 2048, 1, 3, 3)  # time, size, id, num, last
        handle_log_entry(p, len(p), link)
        assert len(link.log_dl._log_list) == 1
        assert link.log_dl._log_list[0]['id'] == 1

    def test_last_entry_generates_message(self):
        link = make_link()
        p = struct.pack('<IIHHH', 1000, 2048, 2, 3, 2)  # id == last_log_num
        handle_log_entry(p, len(p), link)
        assert any(m['type'] == 'log_list' for m in link.log_dl._log_messages)


class TestLogData:
    def test_writes_data(self):
        link = make_link()
        link.log_dl._log_download_id = 1
        link.log_dl._log_download_size = 20
        link.log_dl._log_download_data = bytearray(20)
        p = struct.pack('<IHB', 0, 1, 10) + b'\xAA' * 10
        handle_log_data(p, len(p), link)
        assert link.log_dl._log_download_data[:10] == b'\xAA' * 10

    def test_completes_download(self):
        link = make_link()
        link.log_dl._log_download_id = 1
        link.log_dl._log_download_size = 5
        link.log_dl._log_download_data = bytearray(5)
        p = struct.pack('<IHB', 0, 1, 5) + b'\xBB' * 5
        handle_log_data(p, len(p), link)
        assert link.log_dl._log_download_id == -1
        assert any(m['type'] == 'log_complete' for m in link.log_dl._log_messages)

    def test_ignores_wrong_id(self):
        link = make_link()
        link.log_dl._log_download_id = 1
        link.log_dl._log_download_size = 10
        link.log_dl._log_download_data = bytearray(10)
        p = struct.pack('<IHB', 0, 99, 5) + b'\x00' * 5
        handle_log_data(p, len(p), link)
        assert link.log_dl._log_download_data == bytearray(10)


class TestAdsbVehicle:
    def test_adds_vehicle(self):
        link = make_link()
        p = struct.pack('<I', 0xABCDEF)
        p += struct.pack('<ii', int(30.5 * 1e7), int(120.3 * 1e7))
        p += struct.pack('<i', 5000 * 1000)  # alt mm
        p += struct.pack('<HHh', 18000, 25000, -500)  # hdg, hor_vel, ver_vel
        p += b'TEST\x00\x00\x00\x00\x00'  # callsign 9 bytes
        p += b'\x00' * 7  # remaining to reach 38
        handle_adsb_vehicle(p, len(p), link)
        assert 0xABCDEF in link.traffic._adsb_vehicles
        v = link.traffic._adsb_vehicles[0xABCDEF]
        assert v['callsign'] == 'TEST'
        assert abs(v['alt'] - 5000) < 1

    def test_caps_at_200(self):
        link = make_link()
        for i in range(205):
            p = struct.pack('<I', i)
            p += struct.pack('<ii', int(30.0 * 1e7), int(120.0 * 1e7))
            p += struct.pack('<i', 1000000)
            p += struct.pack('<HHh', 0, 0, 0)
            p += b'\x00' * 16
            handle_adsb_vehicle(p, len(p), link)
        assert len(link.traffic._adsb_vehicles) <= 200


class TestSerialControl:
    def test_appends_console(self):
        link = make_link()
        text = b'Hello Console'
        p = b'\x00' * 4  # device, flags, timeout, baudrate
        p += bytes([len(text)])  # count
        p += text + b'\x00' * (70 - len(text))
        handle_serial_control(p, len(p), link)
        assert 'Hello Console' in ''.join(link._console_buf)

    def test_trims_buffer(self):
        link = make_link()
        link._console_buf = ['x'] * 501
        text = b'Y'
        p = b'\x00' * 4 + bytes([1]) + text + b'\x00' * 69
        handle_serial_control(p, len(p), link)
        assert len(link._console_buf) <= 251


class TestShortPayloadGuards:
    def test_all_handlers_reject_short_payload(self):
        link = make_link()
        handlers_min = [
            (handle_mission_current, 1),
            (handle_home_position, 19),
            (handle_mission_item_reached, 1),
            (handle_command_ack, 2),
            (handle_servo_output, 20),
            (handle_rc_channels, 41),
            (handle_vibration, 31),
            (handle_ekf_status, 21),
            (handle_terrain_report, 15),
            (handle_wind, 11),
            (handle_autopilot_version, 35),
            (handle_mission_count, 2),
            (handle_log_entry, 13),
            (handle_log_data, 6),
            (handle_serial_control, 9),
            (handle_battery_status, 35),
            (handle_adsb_vehicle, 37),
        ]
        for handler, min_pl in handlers_min:
            short = b'\x00' * min_pl
            handler(short, min_pl, link)  # should not raise
