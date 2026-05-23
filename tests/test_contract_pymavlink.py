"""Use pymavlink (the official Python MAVLink library, generated from the
canonical XML definitions) as an oracle to verify our hand-written backend
encoding and decoding.

For every command our backend SENDS, we invoke the real cmd_xxx handler with
a fake link, capture the bytes it writes, hand them to pymavlink, and assert
the decoded fields match what the operator asked for.

For every message our backend RECEIVES, we encode it with pymavlink and feed
the payload to the handler, then assert the resulting state update is what
the field values imply.

This is byte-level contract verification. It catches:
  - wrong msg_id, wrong CRC_EXTRA, wrong field offsets, wrong endianness
  - extension fields silently truncated / mis-positioned

It does NOT catch (these need source-citation audits — see CLAUDE.md):
  - private protocol semantics that ArduPilot layers on top of MAVLink
    (e.g., AccelCal::handle_command_ack reinterprets command/result)
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest
from pymavlink.dialects.v20 import ardupilotmega as mavlink

from backend import commands
from backend.mavlink_handlers import (
    handle_attitude,
    handle_battery_status,
    handle_command_ack,
    handle_global_position_int,
    handle_gps_raw_int,
    handle_mag_cal_progress,
    handle_mag_cal_report,
    handle_mission_ack,
    handle_mission_count,
    handle_servo_output,
    handle_sys_status,
    handle_vfr_hud,
    handle_vibration,
)

# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────


class FakeLink:
    """Minimal DroneLink shim that captures send() bytes for inspection."""
    def __init__(self):
        self.sq = 0
        self.vehicle = SimpleNamespace(sysid=1, armed=False)
        self.locale = 'zh'
        self.captured: list[bytes] = []
        self._lock = threading.Lock()
        self._mag_cal_pct = -1
        self._mag_cal_done = False
        self._prearm_messages: list[str] = []
        # state subsystems used by handlers
        from backend.state import (
            AttitudeState,
            BatteryState,
            DiagnosticState,
            GpsState,
            LogState,
            MissionState,
            RcServoState,
            TrafficState,
            VehicleState,
        )
        self.attitude = AttitudeState()
        self.battery = BatteryState()
        self.gps = GpsState()
        self.vehicle = VehicleState()
        self.vehicle.sysid = 1
        self.mission = MissionState()
        self.diagnostic = DiagnosticState()
        self.rc_servo = RcServoState()
        self.traffic = TrafficState()
        self.log_dl = LogState()
        self.connected = True
        self.events: list[dict] = []

    def send(self, frame: bytes) -> None:
        self.captured.append(frame)

    def add_event(self, text: str, event_type: str = '') -> None:
        self.events.append({'text': text, 'event_type': event_type})

    def _get_vehicle_info(self):
        return ({}, [], 'Multirotor')

    def is_plane(self) -> bool:
        return False


def _decode_one(frame: bytes) -> mavlink.MAVLink_message:
    """Decode exactly one MAVLink 2 frame using pymavlink as oracle."""
    parser = mavlink.MAVLink(None)
    parser.robust_parsing = True
    msgs = parser.parse_buffer(frame)
    assert msgs, f'pymavlink could not parse our frame: {frame.hex()}'
    return msgs[0]


# ─────────────────────────────────────────────────────────────────────────
# OUTGOING: bytes we produce are correctly parseable by pymavlink
# ─────────────────────────────────────────────────────────────────────────


class TestOutgoingCommands:
    def test_arm(self):
        link = FakeLink()
        commands.execute('arm', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.get_msgId() == mavlink.MAVLINK_MSG_ID_COMMAND_LONG
        assert msg.command == mavlink.MAV_CMD_COMPONENT_ARM_DISARM  # 400
        assert msg.param1 == 1.0   # arm
        assert msg.target_system == 1

    def test_disarm(self):
        link = FakeLink()
        commands.execute('disarm', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_COMPONENT_ARM_DISARM
        assert msg.param1 == 0.0   # disarm

    def test_force_disarm(self):
        link = FakeLink()
        commands.execute('force_disarm', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_COMPONENT_ARM_DISARM
        assert msg.param1 == 0.0
        assert msg.param2 == 21196.0  # MAGIC FORCE-DISARM number

    def test_takeoff(self):
        link = FakeLink()
        commands.execute('takeoff', None, link, {'alt': 50})
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_NAV_TAKEOFF
        assert msg.param7 == 50.0  # altitude

    def test_rtl(self):
        link = FakeLink()
        commands.execute('rtl', None, link)
        msg = _decode_one(link.captured[0])
        # cmd_rtl sends a SET_MODE (msg 11), not COMMAND_LONG
        assert msg.get_msgId() == mavlink.MAVLINK_MSG_ID_SET_MODE

    def test_cal_compass(self):
        link = FakeLink()
        commands.execute('cal_compass', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_DO_START_MAG_CAL  # 42424

    def test_cal_compass_accept(self):
        link = FakeLink()
        commands.execute('cal_compass_accept', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_DO_ACCEPT_MAG_CAL  # 42425

    def test_cal_cancel(self):
        link = FakeLink()
        commands.execute('cal_cancel', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_DO_CANCEL_MAG_CAL  # 42426

    def test_cal_accel(self):
        link = FakeLink()
        commands.execute('cal_accel', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_PREFLIGHT_CALIBRATION  # 241
        assert msg.param5 == 1.0   # accel

    def test_cal_gyro(self):
        link = FakeLink()
        commands.execute('cal_gyro', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_PREFLIGHT_CALIBRATION
        assert msg.param1 == 1.0   # gyro

    def test_cal_level(self):
        link = FakeLink()
        commands.execute('cal_level', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_PREFLIGHT_CALIBRATION
        assert msg.param5 == 4.0   # level

    def test_cal_baro(self):
        link = FakeLink()
        commands.execute('cal_baro', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_PREFLIGHT_CALIBRATION
        assert msg.param3 == 1.0   # baro

    def test_cal_accel_next_uses_qgc_protocol(self):
        """Regression: AP_AccelCal::handle_command_ack requires command<=6,
        result==1 (TEMPORARILY_REJECTED). Was buggy with command=42429."""
        link = FakeLink()
        commands.execute('cal_accel_next', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.get_msgId() == mavlink.MAVLINK_MSG_ID_COMMAND_ACK
        assert msg.command == 0
        assert msg.result == mavlink.MAV_RESULT_TEMPORARILY_REJECTED  # 1


class TestOutgoingFrameStructure:
    """Verify framing-level invariants hold for any outgoing frame."""

    def test_all_outgoing_frames_are_mavlink2(self):
        """Every frame we emit must start with 0xFD (MAVLink 2 magic)."""
        link = FakeLink()
        for cmd_name in ('arm', 'disarm', 'rtl', 'cal_compass', 'cal_accel'):
            link.captured.clear()
            commands.execute(cmd_name, None, link)
            for frame in link.captured:
                assert frame[0] == 0xFD, f'{cmd_name} sent non-MAVLink2 frame'

    def test_sysid_is_consistent(self):
        """All outgoing frames advertise the same sysid as the heartbeat."""
        link = FakeLink()
        commands.execute('arm', None, link)
        commands.execute('disarm', None, link)
        sysids = {frame[5] for frame in link.captured}
        assert len(sysids) == 1, f'mixed sysids in outgoing frames: {sysids}'


# ─────────────────────────────────────────────────────────────────────────
# INCOMING: pymavlink-encoded payloads decode correctly through our handlers
# ─────────────────────────────────────────────────────────────────────────


def _encode_payload(msg) -> tuple[bytes, int]:
    """Return (zero-padded payload bytes, original payload length) using
    pymavlink's canonical field ordering. Pads the payload to 256 bytes the
    same way DroneLink._process does in production, so handlers can read past
    pl on truncated payloads. Returns the original pl so handlers see the same
    `pl` value they'd see in production."""
    mav = mavlink.MAVLink(None, srcSystem=1, srcComponent=1)
    full = msg.pack(mav)
    # MAVLink 2 frame: 0xFD | len | incompat | compat | seq | sys | comp | mid(3) | payload | crc(2)
    payload_len = full[1]
    payload = full[10:10 + payload_len]
    padded = payload + b'\x00' * (256 - payload_len)
    return padded, payload_len


class TestIncomingHandlers:
    def test_attitude(self):
        link = FakeLink()
        msg = mavlink.MAVLink_attitude_message(
            time_boot_ms=1000, roll=0.5, pitch=-0.3, yaw=1.57,
            rollspeed=0.1, pitchspeed=0.0, yawspeed=0.0,
        )
        payload, pl = _encode_payload(msg)
        handle_attitude(payload, pl, link)
        assert link.attitude.roll == pytest.approx(0.5 * 57.2958, abs=0.01)
        assert link.attitude.pitch == pytest.approx(-0.3 * 57.2958, abs=0.01)
        assert link.attitude.yaw == pytest.approx(1.57 * 57.2958, abs=0.01) or \
               link.attitude.yaw == pytest.approx(1.57 * 57.2958 + 360, abs=0.01)

    def test_global_position_int(self):
        link = FakeLink()
        msg = mavlink.MAVLink_global_position_int_message(
            time_boot_ms=1000, lat=340000000, lon=-1184000000,
            alt=100000, relative_alt=50000, vx=100, vy=-200, vz=10, hdg=18000,
        )
        payload, pl = _encode_payload(msg)
        handle_global_position_int(payload, pl, link)
        assert link.attitude.lat == pytest.approx(34.0, abs=1e-5)
        assert link.attitude.lon == pytest.approx(-118.4, abs=1e-5)
        assert link.attitude.alt_msl == pytest.approx(100.0, abs=0.01)
        assert link.attitude.alt_rel == pytest.approx(50.0, abs=0.01)
        assert link.attitude.hdg == pytest.approx(180.0, abs=0.01)

    def test_vfr_hud(self):
        link = FakeLink()
        msg = mavlink.MAVLink_vfr_hud_message(
            airspeed=15.5, groundspeed=12.0, heading=270, throttle=50,
            alt=100.0, climb=2.5,
        )
        payload, pl = _encode_payload(msg)
        handle_vfr_hud(payload, pl, link)
        assert link.attitude.airspeed == pytest.approx(15.5, abs=0.01)
        assert link.attitude.throttle == 50
        assert link.attitude.climb == pytest.approx(2.5, abs=0.01)

    def test_sys_status(self):
        link = FakeLink()
        msg = mavlink.MAVLink_sys_status_message(
            onboard_control_sensors_present=0, onboard_control_sensors_enabled=0,
            onboard_control_sensors_health=0, load=500,
            voltage_battery=12600, current_battery=1500, battery_remaining=85,
            drop_rate_comm=0, errors_comm=0,
            errors_count1=0, errors_count2=0, errors_count3=0, errors_count4=0,
        )
        payload, pl = _encode_payload(msg)
        handle_sys_status(payload, pl, link)
        assert link.battery.voltage == pytest.approx(12.6, abs=0.01)
        assert link.battery.current == pytest.approx(15.0, abs=0.01)
        assert link.battery.remaining == 85

    def test_gps_raw_int(self):
        link = FakeLink()
        msg = mavlink.MAVLink_gps_raw_int_message(
            time_usec=0, fix_type=3, lat=0, lon=0, alt=0, eph=0, epv=0,
            vel=0, cog=0, satellites_visible=12,
        )
        payload, pl = _encode_payload(msg)
        handle_gps_raw_int(payload, pl, link)
        assert link.gps.gps_fix == 3
        assert link.gps.gps_sats == 12

    def test_vibration(self):
        link = FakeLink()
        msg = mavlink.MAVLink_vibration_message(
            time_usec=0, vibration_x=0.5, vibration_y=0.3, vibration_z=0.2,
            clipping_0=1, clipping_1=2, clipping_2=3,
        )
        payload, pl = _encode_payload(msg)
        handle_vibration(payload, pl, link)
        assert link.diagnostic.vibe_x == pytest.approx(0.5, abs=0.01)
        assert link.diagnostic.vibe_clip0 == 1

    def test_mag_cal_progress(self):
        link = FakeLink()
        msg = mavlink.MAVLink_mag_cal_progress_message(
            compass_id=0, cal_mask=1, cal_status=3,
            attempt=0, completion_pct=42,
            completion_mask=bytes(10),
            direction_x=0.0, direction_y=0.0, direction_z=0.0,
        )
        payload, pl = _encode_payload(msg)
        handle_mag_cal_progress(payload, pl, link)
        assert link._mag_cal_pct == 42

    def test_mag_cal_report_success(self):
        link = FakeLink()
        msg = mavlink.MAVLink_mag_cal_report_message(
            compass_id=0, cal_mask=1, cal_status=4,  # SUCCESS
            autosaved=0, fitness=0.5,
            ofs_x=0, ofs_y=0, ofs_z=0,
            diag_x=1, diag_y=1, diag_z=1,
            offdiag_x=0, offdiag_y=0, offdiag_z=0,
            orientation_confidence=1.0, old_orientation=0, new_orientation=0,
            scale_factor=1.0,
        )
        payload, pl = _encode_payload(msg)
        handle_mag_cal_report(payload, pl, link)
        assert link._mag_cal_done is True
        assert any('完成' in e['text'] or 'complete' in e['text'] for e in link.events)

    def test_battery_status(self):
        link = FakeLink()
        cells = [3700, 3700, 3700, 3700] + [0xFFFF] * 6
        msg = mavlink.MAVLink_battery_status_message(
            id=0, battery_function=0, type=3, temperature=25,
            voltages=cells,
            current_battery=1000, current_consumed=500, energy_consumed=1000,
            battery_remaining=80,
        )
        payload, pl = _encode_payload(msg)
        handle_battery_status(payload, pl, link)
        assert len(link.battery.battery_cells) == 4
        assert link.battery.battery_cells[0] == pytest.approx(3.7, abs=0.01)

    def test_servo_output(self):
        link = FakeLink()
        msg = mavlink.MAVLink_servo_output_raw_message(
            time_usec=0, port=0,
            servo1_raw=1500, servo2_raw=1500, servo3_raw=1500, servo4_raw=1500,
            servo5_raw=0, servo6_raw=0, servo7_raw=0, servo8_raw=0,
            servo9_raw=0, servo10_raw=0, servo11_raw=0, servo12_raw=0,
            servo13_raw=0, servo14_raw=0, servo15_raw=0, servo16_raw=0,
        )
        payload, pl = _encode_payload(msg)
        handle_servo_output(payload, pl, link)
        assert link.rc_servo.servo_out[0] == 1500

    def test_command_ack_success_for_arm(self):
        link = FakeLink()
        msg = mavlink.MAVLink_command_ack_message(
            command=400, result=0, progress=0, result_param2=0,
            target_system=255, target_component=1,
        )
        payload, pl = _encode_payload(msg)
        handle_command_ack(payload, pl, link)
        assert any('解锁/锁定' in e['text'] or 'Arm' in e['text'] for e in link.events)

    def test_mission_count(self):
        link = FakeLink()
        link.mission._dl_pending = True
        msg = mavlink.MAVLink_mission_count_message(
            target_system=255, target_component=1, count=5, mission_type=0,
        )
        payload, pl = _encode_payload(msg)
        handle_mission_count(payload, pl, link)
        assert link.mission._dl_total == 5

    def test_mission_ack_ok(self):
        link = FakeLink()
        link.mission._mission_pending = True
        msg = mavlink.MAVLink_mission_ack_message(
            target_system=255, target_component=1, type=0, mission_type=0,
        )
        payload, pl = _encode_payload(msg)
        handle_mission_ack(payload, pl, link)
        assert link.mission._mission_pending is False

    def test_heartbeat_armed_flag(self):
        from backend.mavlink_handlers import handle_heartbeat
        link = FakeLink()
        msg = mavlink.MAVLink_heartbeat_message(
            type=2, autopilot=3, base_mode=0x81, system_status=4,
            mavlink_version=3, custom_mode=5,
        )
        payload, pl = _encode_payload(msg)
        # Setting raw_sysid so handle_heartbeat copies it
        link._raw_sysid = 1
        handle_heartbeat(payload, pl, link)
        assert link.vehicle.mode == 5
        assert link.vehicle.vtype_raw == 2
        assert link.vehicle.armed is True

    def test_heartbeat_disarmed(self):
        from backend.mavlink_handlers import handle_heartbeat
        link = FakeLink()
        link.vehicle.armed = True  # was armed, now becoming disarmed
        link.vehicle.armed_time = 1.0
        msg = mavlink.MAVLink_heartbeat_message(
            type=2, autopilot=3, base_mode=0x00, system_status=4,
            mavlink_version=3, custom_mode=5,
        )
        payload, pl = _encode_payload(msg)
        link._raw_sysid = 1
        handle_heartbeat(payload, pl, link)
        assert link.vehicle.armed is False

    def test_home_position(self):
        from backend.mavlink_handlers import handle_home_position
        link = FakeLink()
        msg = mavlink.MAVLink_home_position_message(
            latitude=340000000, longitude=-1184000000, altitude=100000,
            x=0, y=0, z=0, q=[1.0, 0.0, 0.0, 0.0],
            approach_x=0, approach_y=0, approach_z=0, time_usec=0,
        )
        payload, pl = _encode_payload(msg)
        handle_home_position(payload, pl, link)
        assert link.attitude.home_lat == pytest.approx(34.0, abs=1e-5)
        assert link.attitude.home_lon == pytest.approx(-118.4, abs=1e-5)

    def test_mission_current(self):
        from backend.mavlink_handlers import handle_mission_current
        link = FakeLink()
        msg = mavlink.MAVLink_mission_current_message(seq=42)
        payload, pl = _encode_payload(msg)
        handle_mission_current(payload, pl, link)
        assert link.mission.wp_seq == 42

    def test_mission_item_reached(self):
        from backend.mavlink_handlers import handle_mission_item_reached
        link = FakeLink()
        msg = mavlink.MAVLink_mission_item_reached_message(seq=7)
        payload, pl = _encode_payload(msg)
        handle_mission_item_reached(payload, pl, link)
        assert any('7' in e['text'] for e in link.events)

    def test_rc_channels(self):
        from backend.mavlink_handlers import handle_rc_channels
        link = FakeLink()
        msg = mavlink.MAVLink_rc_channels_message(
            time_boot_ms=0, chancount=8,
            chan1_raw=1500, chan2_raw=1501, chan3_raw=1502, chan4_raw=1503,
            chan5_raw=1504, chan6_raw=1505, chan7_raw=1506, chan8_raw=1507,
            chan9_raw=0, chan10_raw=0, chan11_raw=0, chan12_raw=0,
            chan13_raw=0, chan14_raw=0, chan15_raw=0, chan16_raw=0,
            chan17_raw=0, chan18_raw=0, rssi=200,
        )
        payload, pl = _encode_payload(msg)
        handle_rc_channels(payload, pl, link)
        assert link.rc_servo.rc_channels[0] == 1500
        assert link.rc_servo.rc_channels[7] == 1507
        assert link.rc_servo.rc_rssi == 200

    def test_ekf_status(self):
        from backend.mavlink_handlers import handle_ekf_status
        link = FakeLink()
        msg = mavlink.MAVLink_ekf_status_report_message(
            flags=0x1F, velocity_variance=0.1, pos_horiz_variance=0.2,
            pos_vert_variance=0.3, compass_variance=0.4, terrain_alt_variance=0.5,
        )
        payload, pl = _encode_payload(msg)
        handle_ekf_status(payload, pl, link)
        assert link.diagnostic.ekf_vel_var == pytest.approx(0.1, abs=0.001)
        assert link.diagnostic.ekf_pos_h_var == pytest.approx(0.2, abs=0.001)
        assert link.diagnostic.ekf_compass_var == pytest.approx(0.4, abs=0.001)
        assert link.diagnostic.ekf_flags == 0x1F

    def test_mount_status(self):
        from backend.mavlink_handlers import handle_mount_status
        link = FakeLink()
        msg = mavlink.MAVLink_mount_status_message(
            target_system=1, target_component=1,
            pointing_a=-4500, pointing_b=0, pointing_c=9000,
        )
        payload, pl = _encode_payload(msg)
        handle_mount_status(payload, pl, link)
        assert link.diagnostic.gimbal_pitch == pytest.approx(-45.0, abs=0.01)
        assert link.diagnostic.gimbal_yaw == pytest.approx(90.0, abs=0.01)

    def test_terrain_report(self):
        from backend.mavlink_handlers import handle_terrain_report
        link = FakeLink()
        msg = mavlink.MAVLink_terrain_report_message(
            lat=0, lon=0, spacing=100, terrain_height=125.5, current_height=120.0,
            pending=0, loaded=10,
        )
        payload, pl = _encode_payload(msg)
        handle_terrain_report(payload, pl, link)
        assert link.diagnostic.terrain_alt == pytest.approx(125.5, abs=0.01)

    def test_wind(self):
        from backend.mavlink_handlers import handle_wind
        link = FakeLink()
        msg = mavlink.MAVLink_wind_message(
            direction=270.0, speed=5.5, speed_z=0.0,
        )
        payload, pl = _encode_payload(msg)
        handle_wind(payload, pl, link)
        assert link.diagnostic.wind_dir == pytest.approx(270.0, abs=0.01)
        assert link.diagnostic.wind_speed == pytest.approx(5.5, abs=0.01)

    def test_autopilot_version(self):
        from backend.mavlink_handlers import handle_autopilot_version
        link = FakeLink()
        # firmware version encoded as major<<24 | minor<<16 | patch<<8
        # for ArduCopter 4.5.3 → 0x04050300
        fw_ver = (4 << 24) | (5 << 16) | (3 << 8)
        msg = mavlink.MAVLink_autopilot_version_message(
            capabilities=0, flight_sw_version=fw_ver, middleware_sw_version=0,
            os_sw_version=0, board_version=12345,
            flight_custom_version=b'\x12\x34\x56\x78\x9a\xbc\xde\xf0',
            middleware_custom_version=bytes(8), os_custom_version=bytes(8),
            vendor_id=0, product_id=0, uid=0, uid2=bytes(18),
        )
        payload, pl = _encode_payload(msg)
        handle_autopilot_version(payload, pl, link)
        assert link.vehicle.fw_version == 'v4.5.3'
        assert link.vehicle.board_id == 12345

    def test_mission_item_int_waypoint(self):
        """seq=0 is reserved for HOME position; only seq>=1 counts as a real
        waypoint (handle_mission_item_int line filters `seq > 0`). So this
        test sends two items: HOME at seq=0, NAV_WAYPOINT at seq=1."""
        from backend.mavlink_handlers import handle_mission_item_int
        link = FakeLink()
        link.mission._dl_pending = True
        link.mission._dl_total = 2
        link.mission._dl_items = [None, None]
        # HOME placeholder (seq=0 — most fields ignored by Argus)
        home = mavlink.MAVLink_mission_item_int_message(
            target_system=255, target_component=1,
            seq=0, frame=3, command=16, current=1, autocontinue=1,
            param1=0, param2=0, param3=0, param4=0,
            x=0, y=0, z=0, mission_type=0,
        )
        payload, pl = _encode_payload(home)
        handle_mission_item_int(payload, pl, link)
        # Now the waypoint at seq=1
        wp_msg = mavlink.MAVLink_mission_item_int_message(
            target_system=255, target_component=1,
            seq=1, frame=3, command=16, current=0, autocontinue=1,
            param1=0, param2=0, param3=0, param4=0,
            x=340000000, y=-1184000000, z=100.0,
            mission_type=0,
        )
        payload, pl = _encode_payload(wp_msg)
        handle_mission_item_int(payload, pl, link)
        assert link.mission._dl_pending is False
        last = link.mission._dl_messages[-1]
        assert last['type'] == 'mission_downloaded'
        assert len(last['waypoints']) == 1
        wp = last['waypoints'][0]
        assert wp['lat'] == pytest.approx(34.0, abs=1e-5)
        assert wp['lon'] == pytest.approx(-118.4, abs=1e-5)
        assert wp['type'] == 'wp'

    def test_log_entry(self):
        from backend.mavlink_handlers import handle_log_entry
        link = FakeLink()
        msg = mavlink.MAVLink_log_entry_message(
            id=5, num_logs=1, last_log_num=5, time_utc=1700000000, size=102400,
        )
        payload, pl = _encode_payload(msg)
        handle_log_entry(payload, pl, link)
        assert len(link.log_dl._log_list) == 1
        assert link.log_dl._log_list[0]['id'] == 5
        assert link.log_dl._log_list[0]['size'] == 102400

    def test_log_data(self):
        from backend.mavlink_handlers import handle_log_data
        link = FakeLink()
        link.log_dl._log_download_id = 5
        link.log_dl._log_download_size = 1000
        link.log_dl._log_download_data = bytearray(1000)
        link.log_dl._log_download_ofs = 0
        chunk = bytes(range(90))
        msg = mavlink.MAVLink_log_data_message(
            id=5, ofs=0, count=90, data=list(chunk) + [0] * (90 - len(chunk)),
        )
        payload, pl = _encode_payload(msg)
        handle_log_data(payload, pl, link)
        assert link.log_dl._log_download_data[:90] == chunk

    def test_param_value(self):
        # param_manager is the entry point; handle_param_value forwards.
        link = FakeLink()
        # Mock param_mgr to capture
        class FakeParamMgr:
            def __init__(self):
                self.calls = []
            def handle_param_value(self, p, pl):
                self.calls.append((bytes(p), pl))
            def request_all(self):
                pass
            def set_param(self, *a):
                pass
            def get_status(self):
                return {'param_count': 0, 'param_total': 0, 'param_fetching': False}
            def check_timeout(self):
                pass
            def save_to_file(self):
                return ''
        link.param_mgr = FakeParamMgr()
        from backend.mavlink_handlers import handle_param_value
        msg = mavlink.MAVLink_param_value_message(
            param_id=b'BATT_CAPACITY', param_value=5300.0, param_type=9,
            param_count=700, param_index=42,
        )
        payload, pl = _encode_payload(msg)
        handle_param_value(payload, pl, link)
        assert len(link.param_mgr.calls) == 1


# ─────────────────────────────────────────────────────────────────────────
# More outgoing commands
# ─────────────────────────────────────────────────────────────────────────


class TestOutgoingMoreCommands:
    def test_mode(self):
        link = FakeLink()
        # cmd_mode takes the mode as `param`, not data
        commands.execute('mode', 5, link)
        msg = _decode_one(link.captured[0])
        assert msg.get_msgId() == mavlink.MAVLINK_MSG_ID_SET_MODE
        assert msg.custom_mode == 5

    def test_mission_start(self):
        link = FakeLink()
        commands.execute('mission_start', None, link)
        # cmd_mission_start first sends SET_MODE(AUTO) then a delayed MISSION_START.
        # Synchronously we only see the SET_MODE.
        msg = _decode_one(link.captured[0])
        assert msg.get_msgId() == mavlink.MAVLINK_MSG_ID_SET_MODE
        # Copter AUTO is mode 3, Plane AUTO is mode 10. FakeLink.is_plane() returns False.
        assert msg.custom_mode == 3

    def test_mission_clear(self):
        link = FakeLink()
        commands.execute('mission_clear', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.get_msgId() == mavlink.MAVLINK_MSG_ID_MISSION_CLEAR_ALL  # 45

    def test_log_list(self):
        link = FakeLink()
        commands.execute('log_list', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.get_msgId() == mavlink.MAVLINK_MSG_ID_LOG_REQUEST_LIST  # 117
        assert msg.start == 0
        assert msg.end == 0xFFFF

    def test_log_cancel(self):
        link = FakeLink()
        commands.execute('log_cancel', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.get_msgId() == mavlink.MAVLINK_MSG_ID_LOG_REQUEST_END  # 122

    def test_log_download(self):
        link = FakeLink()
        # Need an entry first
        link.log_dl._log_list = [{'id': 3, 'size': 5000, 'time_utc': 0}]
        commands.execute('log_download', None, link, {'id': 3})
        # First frame is LOG_REQUEST_DATA
        msg = _decode_one(link.captured[0])
        assert msg.get_msgId() == mavlink.MAVLINK_MSG_ID_LOG_REQUEST_DATA  # 119
        assert msg.id == 3

    def test_motor_test_one_based(self):
        """Regression: cmd_motor_test must send 1-based motor index, not 0-based."""
        link = FakeLink()
        commands.execute('motor_test', None, link, {'motor': 0, 'throttle': 5, 'duration': 2})
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_DO_MOTOR_TEST  # 209
        assert msg.param1 == 1.0  # 0+1 → 1-based

    def test_camera_trigger_sends_p5_1(self):
        """Regression: cmd_camera_trigger must send param5=1 to actually trigger."""
        link = FakeLink()
        commands.execute('camera_trigger', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_DO_DIGICAM_CONTROL  # 203
        assert msg.param5 == 1.0

    def test_gimbal_angle(self):
        link = FakeLink()
        commands.execute('gimbal_angle', None, link, {'pitch': -30, 'yaw': 45})
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_DO_MOUNT_CONTROL  # 205
        assert msg.param1 == -30.0
        assert msg.param3 == 45.0
        assert msg.param7 == 2.0  # MAV_MOUNT_MODE_MAVLINK_TARGETING

    def test_camera_video_start(self):
        link = FakeLink()
        commands.execute('camera_video_start', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_VIDEO_START_CAPTURE  # 2500

    def test_camera_video_stop(self):
        link = FakeLink()
        commands.execute('camera_video_stop', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_VIDEO_STOP_CAPTURE  # 2501

    def test_camera_zoom(self):
        link = FakeLink()
        commands.execute('camera_zoom', None, link, {'zoom': 50})
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_SET_CAMERA_ZOOM  # 531
        assert msg.param2 == 50.0

    def test_do_set_roi(self):
        link = FakeLink()
        commands.execute('do_set_roi', None, link, {'lat': 34.0, 'lon': -118.4, 'alt': 100})
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_DO_SET_ROI  # 201

    def test_reboot(self):
        link = FakeLink()
        commands.execute('reboot', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN  # 246
        assert msg.param1 == 1.0  # reboot autopilot

    def test_reboot_bootloader(self):
        link = FakeLink()
        commands.execute('reboot_bootloader', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN
        assert msg.param1 == 3.0  # reboot to bootloader

    def test_drop_relay_on(self):
        link = FakeLink()
        commands.execute('drop', None, link)
        msg = _decode_one(link.captured[0])
        assert msg.command == mavlink.MAV_CMD_DO_SET_RELAY  # 181

    def test_guided_goto(self):
        link = FakeLink()
        commands.execute('guided_goto', None, link, {'lat': 34.0, 'lon': -118.4, 'alt': 100})
        msg = _decode_one(link.captured[-1])
        # cmd_guided_goto may send multiple — last should be SET_POSITION_TARGET_GLOBAL_INT
        assert msg.get_msgId() == mavlink.MAVLINK_MSG_ID_SET_POSITION_TARGET_GLOBAL_INT  # 86

    def test_param_request_read_for_gap_fill(self):
        """ParamManager._request_one builds msg 20 to recover a missing
        index after the initial PARAM_REQUEST_LIST burst loses packets."""
        from backend.param_manager import ParamManager
        link = FakeLink()
        mgr = ParamManager(link)
        mgr._request_one(42)
        msg = _decode_one(link.captured[0])
        assert msg.get_msgId() == mavlink.MAVLINK_MSG_ID_PARAM_REQUEST_READ  # 20
        assert msg.param_index == 42
        assert msg.target_system == 1


# ─────────────────────────────────────────────────────────────────────────
# CRC_EXTRA conformance
# ─────────────────────────────────────────────────────────────────────────


class TestCrcExtraMatchesPymavlink:
    """For every msg id we have an entry for, verify the CRC extra matches
    what pymavlink computes from the canonical XML definition. A mismatch
    means our table is wrong and the parser will reject valid frames."""

    def test_backend_crc_extra(self):
        from backend.drone_link import _CRC_EXTRA
        self._check_table('backend.drone_link._CRC_EXTRA', _CRC_EXTRA)

    def test_frontend_crc_extra(self):
        """Parse src/lib/mavlink/crc.ts and verify it against pymavlink. The
        frontend codec has its own copy of CRC_EXTRA — must stay in sync."""
        import re
        from pathlib import Path
        ts_path = Path(__file__).resolve().parent.parent / 'src' / 'lib' / 'mavlink' / 'crc.ts'
        src = ts_path.read_text(encoding='utf-8')
        # match lines like "  76: 152,    // COMMAND_LONG"
        entries: dict[int, int] = {}
        for m in re.finditer(r'^\s*(\d+):\s*(\d+)\s*,', src, re.MULTILINE):
            entries[int(m.group(1))] = int(m.group(2))
        assert len(entries) >= 30, f'Frontend CRC_EXTRA parser found only {len(entries)} entries'
        self._check_table('src/lib/mavlink/crc.ts CRC_EXTRA', entries)

    @staticmethod
    def _check_table(name: str, table: dict[int, int]) -> None:
        mismatches: list[str] = []
        unknown: list[int] = []
        for mid, our_value in table.items():
            cls = mavlink.mavlink_map.get(mid)
            if cls is None:
                unknown.append(mid)
                continue
            if cls.crc_extra != our_value:
                mismatches.append(
                    f'  msg {mid} ({cls.msgname}): ours={our_value} canonical={cls.crc_extra}'
                )
        assert not mismatches, f'\n{name} mismatches:\n' + '\n'.join(mismatches)
        # Unknown ids are informational; fail only if a huge number show up.
        assert len(unknown) < 5, f'{name}: many ids unknown to pymavlink: {unknown}'
