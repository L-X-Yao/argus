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


# ─────────────────────────────────────────────────────────────────────────
# CRC_EXTRA conformance
# ─────────────────────────────────────────────────────────────────────────


class TestCrcExtraMatchesPymavlink:
    """For every msg id we have an entry for, verify the CRC extra matches
    what pymavlink computes from the canonical XML definition. A mismatch
    means our table is wrong and the parser will reject valid frames."""

    def test_all_known_crc_extras(self):
        from backend.drone_link import _CRC_EXTRA
        # pymavlink stores crc_extra in the message class's `crc_extra` attribute
        mismatches: list[str] = []
        unknown: list[int] = []
        for mid, our_value in _CRC_EXTRA.items():
            cls = mavlink.mavlink_map.get(mid)
            if cls is None:
                unknown.append(mid)
                continue
            if cls.crc_extra != our_value:
                mismatches.append(
                    f'  msg {mid} ({cls.msgname}): ours={our_value} canonical={cls.crc_extra}'
                )
        assert not mismatches, '\nCRC_EXTRA mismatches:\n' + '\n'.join(mismatches)
        # Unknown ids are informational; only fail if a HUGE number show up
        # since some ardupilotmega-only ids may be missing from base common.xml
        # for older pymavlink versions.
        assert len(unknown) < 5, f'Many msg ids unknown to pymavlink: {unknown}'
