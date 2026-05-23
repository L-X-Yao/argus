from __future__ import annotations

import struct
import threading
import time
from pathlib import Path

from . import commands as cmd_module
from . import mavlink_dispatch
from .config import cfg
from .connection import open_port
from .constants import (
    COPTER_BTNS,
    COPTER_BTNS_EN,
    COPTER_MODES,
    COPTER_MODES_EN,
    FIX_NAMES,
    FIX_NAMES_EN,
    PLANE_BTNS,
    PLANE_BTNS_EN,
    PLANE_MODES,
    PLANE_MODES_EN,
    ROVER_BTNS,
    ROVER_BTNS_EN,
    ROVER_MODES,
    ROVER_MODES_EN,
    SUB_BTNS,
    SUB_BTNS_EN,
    SUB_MODES,
    SUB_MODES_EN,
)
from .locale_text import lt
from .log import logger
from .mavlink_handlers import init_handlers
from .param_manager import ParamManager
from .pllink_proto import pld, ple
from .state import (
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

_CRC_EXTRA = {
    0: 50, 1: 124, 22: 220, 24: 24, 30: 39, 33: 104, 35: 244, 36: 222,
    40: 230, 42: 28, 43: 132, 44: 221, 46: 11, 47: 153, 51: 196, 65: 118,
    70: 124, 73: 38, 74: 20, 77: 143, 83: 22, 85: 140, 87: 150, 105: 93,
    116: 76, 117: 128, 118: 56, 119: 116, 120: 134, 125: 203, 126: 220,
    136: 1, 147: 154, 148: 178, 158: 134, 163: 127, 168: 1, 178: 47,
    191: 92, 192: 36, 193: 71, 233: 35,
    241: 90, 242: 104, 246: 184, 253: 83, 310: 28, 311: 95,
}

_MSG_NAMES = {
    0: 'HEARTBEAT', 1: 'SYS_STATUS', 22: 'PARAM_VALUE', 24: 'GPS_RAW_INT',
    30: 'ATTITUDE', 33: 'GLOBAL_POSITION_INT', 35: 'RC_CHANNELS_RAW',
    36: 'SERVO_OUTPUT_RAW', 40: 'MISSION_REQUEST', 42: 'MISSION_CURRENT',
    43: 'MISSION_REQUEST_LIST', 44: 'MISSION_COUNT', 46: 'MISSION_ITEM_REACHED',
    47: 'MISSION_ACK', 51: 'MISSION_REQUEST_INT', 65: 'RC_CHANNELS',
    69: 'MANUAL_CONTROL', 70: 'RC_CHANNELS_OVERRIDE', 73: 'MISSION_ITEM_INT',
    74: 'VFR_HUD', 77: 'COMMAND_ACK', 83: 'ATTITUDE_TARGET',
    85: 'POSITION_TARGET_LOCAL_NED', 87: 'POSITION_TARGET_GLOBAL_INT',
    105: 'HIGHRES_IMU', 116: 'SCALED_IMU2', 117: 'LOG_REQUEST_LIST',
    118: 'LOG_ENTRY', 119: 'LOG_REQUEST_DATA', 120: 'LOG_DATA',
    125: 'POWER_STATUS', 126: 'SERIAL_CONTROL', 136: 'TERRAIN_REPORT',
    147: 'BATTERY_STATUS', 148: 'AUTOPILOT_VERSION', 158: 'MOUNT_STATUS',
    163: 'AHRS', 168: 'WIND', 178: 'AHRS2', 241: 'VIBRATION', 242: 'HOME_POSITION',
    193: 'EKF_STATUS_REPORT',
    253: 'STATUSTEXT', 310: 'UAVCAN_NODE_STATUS', 311: 'UAVCAN_NODE_INFO',
}



class DroneLink:
    def __init__(self):
        init_handlers()
        self._ser = None
        self._running = False
        self._thread = None
        self._lock = threading.Lock()           # protects _ser.write() only
        self._state_lock = threading.RLock()    # protects all state reads/writes (handlers + get_state)
        self._buf = b''
        self.sq = 0
        self._parse_errors = 0
        self._raw_sysid = 1
        self._logfile = None
        self._last_log_time = 0.0
        self._last_port = ''
        self._last_baud = cfg.SERIAL_BAUD
        self._reconnect_enabled = True

        self._protocol = 'auto'
        self.locale = 'zh'
        self._vehicles: dict[int, dict] = {}
        self.connected = False
        self.frame_count = 0
        self.last_frame_time = 0.0
        self.start_time = 0.0
        self.events: list[dict] = []
        self._ws_queue: list[dict] = []
        self.active_sysid = 1
        self.inspector_enabled = False
        self._msg_stats: dict[int, dict] = {}
        self._msg_stats_window = 5.0
        self._console_buf: list[str] = []
        self._prearm_messages: list[str] = []
        self._unknown_msg_ids: dict[int, int] = {}  # msg_id -> drop count (fail-loud throttle)
        # Monotonic event counter (see add_event) — ws_manager tracks this.
        self._events_emitted_total: int = 0
        # Exponential backoff counter for the in-loop silent reconnect path
        # (auditor W1). Resets to 0 on a successful reconnect.
        self._reconnect_attempts: int = 0
        self.param_mgr = ParamManager(self)

        self.attitude = AttitudeState()
        self.battery = BatteryState()
        self.gps = GpsState()
        self.vehicle = VehicleState()
        self.mission = MissionState()
        self.diagnostic = DiagnosticState()
        self.rc_servo = RcServoState()
        self.log_dl = LogState()
        self.traffic = TrafficState()



    def is_plane(self) -> bool:
        v = self.vehicle
        if v.force_plane is not None:
            return v.force_plane
        return v.vtype_raw in (1, 19, 20, 21, 22, 23, 24, 25)

    def queue_ws(self, msg: dict) -> None:
        self._ws_queue.append(msg)
        if len(self._ws_queue) > 2000:
            self._ws_queue = self._ws_queue[-1000:]

    def add_event(self, text: str, event_type: str = '') -> None:
        # Monotonic counter — ws_manager uses this rather than the array index
        # so a trim (100 → 50 below) doesn't shift the cursor and cause
        # duplicate-event spam to every connected client.
        self._events_emitted_total += 1
        self.events.append({
            'time': time.strftime('%H:%M:%S'),
            'text': text,
            'event_type': event_type,
            'seq': self._events_emitted_total,
        })
        if len(self.events) > 100:
            self.events = self.events[-50:]

    def send(self, frame: bytes) -> None:
        with self._lock:
            if self._ser:
                try:
                    if self._protocol == 'pllink':
                        self._ser.write(ple(frame, self.sq & 0xFF))
                    else:
                        self._ser.write(frame)
                    self.sq += 1
                except OSError:
                    logger.debug('send failed', exc_info=True)
                except ValueError:
                    # bm() raises ValueError for payload >255 bytes — a
                    # programming error caller-side, but we must not let it
                    # crash the link thread.
                    logger.warning('refusing to send malformed frame', exc_info=True)

    def connect(self, port: str, baudrate: int = 57600, protocol: str = 'auto') -> bool:
        if self._running:
            self.disconnect()
        if port.startswith('udp:') or (port.startswith('tcp:') and protocol == 'auto'):
            self._protocol = 'standard'
        else:
            self._protocol = protocol
        try:
            self._ser = self._open_port(port, baudrate)
            if port.startswith('udp:'):
                self.add_event(lt('udp', self.locale) % port[4:], 'udp')
            elif port.startswith('tcp:'):
                self.add_event(lt('tcp', self.locale) % port[4:], 'tcp')
        except OSError as e:
            self.add_event(lt('connect_fail', self.locale) % e, 'connect_fail')
            return False
        self._running = True
        with self._state_lock:
            self.connected = False
            self.frame_count = 0
            self._buf = b''
            self.sq = 0
            self.vehicle.vtype_raw = 0
            self.attitude.home_lat = self.attitude.home_lon = 0.0
            self.attitude.dist_home = 0.0
            self.vehicle.armed_time = 0.0
            self.last_frame_time = 0.0
            self.start_time = time.time()
        self._last_port = port
        self._last_baud = baudrate
        self._reconnect_enabled = True
        self._start_log()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def _reset_session_state(self) -> None:
        """Clear all per-session state. Called from both the user-driven
        disconnect path AND the in-loop silent reconnect path (auditor C1+C2:
        only the user path was clearing zombies, so an FC drop-then-reconnect
        would leak fence/rally/download pending flags + a 100MB log buffer
        + never re-issue stream requests because frame_count was non-zero)."""
        with self._state_lock:
            self.connected = False
            self.vehicle.vtype_raw = 0
            self.vehicle.force_plane = None
            self.attitude._prev_pos = None
            self.attitude._home_set = False
            # Force a re-fire of request_streams() on the next heartbeat by
            # zeroing frame_count (the gate is `frame_count < 3`). Without
            # this, the FC's stream subscriptions silently lapse after a
            # transport reset and the UI freezes.
            self.frame_count = 0
            self.last_frame_time = 0.0
            self.mission._mission_pending = False
            self.mission._fence_pending = False
            self.mission._rally_pending = False
            self.mission._dl_pending = False
            self.mission._dl_start_time = 0.0
            self.mission._mission_ul_start_time = 0.0
            self.mission._fence_ul_start_time = 0.0
            self.mission._rally_ul_start_time = 0.0
            self.log_dl._log_download_id = -1
            self.log_dl._log_download_size = 0
            self.log_dl._log_download_data = bytearray()
            self.log_dl._log_download_ofs = 0
            self.log_dl._log_emit_ofs = 0
            self._prearm_messages = []
        # param_mgr's `fetching` flag could otherwise stay True forever if a
        # PARAM_REQUEST_LIST was in flight when the link dropped (auditor W2)
        # — drops the pending state without re-clearing the params cache.
        if self.param_mgr.fetching:
            self.param_mgr.fetching = False
            self.param_mgr._fetch_start = 0.0
            self.param_mgr._complete_emitted = False

    def disconnect(self) -> None:
        self._running = False
        self._reconnect_enabled = False
        if self._thread:
            self._thread.join(timeout=3)
        try:
            if self._ser:
                self._ser.close()
        except OSError:
            pass
        self._ser = None
        self._reset_session_state()
        self._stop_log()
        self.add_event(lt('disconnected', self.locale), 'disconnected')

    def reconnect(self) -> bool:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        try:
            if self._ser:
                self._ser.close()
        except OSError:
            pass
        self._ser = None
        with self._state_lock:
            self.connected = False
            self._buf = b''
        self._protocol = 'auto'
        try:
            self._ser = self._open_port(self._last_port, self._last_baud)
        except OSError as e:
            self.add_event(lt('reconnect_err', self.locale) % e, 'reconnect_err')
            return False
        self._running = True
        self.sq = 0
        self.add_event(lt('reconnected', self.locale), 'reconnected')
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def _get_vehicle_info(self) -> tuple[dict, list, str]:
        vt = self.vehicle.vtype_raw
        en = self.locale == 'en'
        if self.vehicle.force_plane is True:
            return (PLANE_MODES_EN if en else PLANE_MODES, PLANE_BTNS_EN if en else PLANE_BTNS,
                    'Fixed Wing' if en else '固定翼')
        if self.vehicle.force_plane is False:
            return (COPTER_MODES_EN if en else COPTER_MODES, COPTER_BTNS_EN if en else COPTER_BTNS,
                    'Multirotor' if en else '多旋翼')
        if vt in (1, 19, 20, 21, 22, 23, 24, 25):
            return (PLANE_MODES_EN if en else PLANE_MODES, PLANE_BTNS_EN if en else PLANE_BTNS,
                    'Fixed Wing' if en else '固定翼')
        if vt == 10:
            return (ROVER_MODES_EN if en else ROVER_MODES, ROVER_BTNS_EN if en else ROVER_BTNS,
                    'Rover' if en else '地面车')
        if vt == 12:
            return (SUB_MODES_EN if en else SUB_MODES, SUB_BTNS_EN if en else SUB_BTNS,
                    'Sub' if en else '水下机器人')
        if vt > 0:
            return (COPTER_MODES_EN if en else COPTER_MODES, COPTER_BTNS_EN if en else COPTER_BTNS,
                    'Multirotor' if en else '多旋翼')
        return (COPTER_MODES_EN if en else COPTER_MODES, COPTER_BTNS_EN if en else COPTER_BTNS, '')

    def get_state(self) -> dict:
        with self._state_lock:
            return self._build_state()

    def _build_state(self) -> dict:
        md, btns, vn = self._get_vehicle_info()
        a, v, bat, g = self.attitude, self.vehicle, self.battery, self.gps
        d, rc, m = self.diagnostic, self.rc_servo, self.mission
        return {
            'type': 'state',
            'connected': self.connected,
            'frames': self.frame_count,
            'mode': md.get(v.mode, 'MODE%d' % v.mode),
            'mode_id': v.mode,
            'armed': v.armed,
            'roll': round(a.roll, 1),
            'pitch': round(a.pitch, 1),
            'yaw': round(a.yaw, 1),
            'lat': round(a.lat, 7),
            'lon': round(a.lon, 7),
            'alt_rel': round(a.alt_rel, 1),
            'alt_msl': round(a.alt_msl, 1),
            'gs': round(a.gs, 1),
            'airspeed': round(a.airspeed, 1),
            'throttle': a.throttle,
            'climb': round(a.climb, 1),
            'vz': round(-a.vz, 1),
            'hdg': round(a.hdg, 0),
            'dist_home': round(a.dist_home, 0),
            'flight_time': int(time.time() - v.armed_time) if v.armed and v.armed_time else 0,
            'voltage': round(bat.voltage, 2),
            'current': round(bat.current, 2),
            'remaining': bat.remaining,
            'gps_fix': (FIX_NAMES_EN if self.locale == 'en' else FIX_NAMES).get(g.gps_fix, '?'),
            'gps_fix_raw': g.gps_fix,
            'gps_sats': g.gps_sats,
            'wp': m.wp_seq,
            'vtype': vn,
            'vtype_raw': v.vtype_raw,
            'mode_btns': btns,
            'link_age': round(time.time() - self.last_frame_time, 1) if self.connected and self.last_frame_time > 0 else -1,
            'bat_time': bat.bat_time_remaining if bat.bat_time_remaining > 0 else -1,
            'home_lat': round(a.home_lat, 7),
            'home_lon': round(a.home_lon, 7),
            'parse_errors': self._parse_errors,
            'flight_summary': v.flight_summary,
            'log_active': self._logfile is not None,
            'fw_version': v.fw_version,
            'fw_git': v.fw_git,
            'board_id': v.board_id,
            'rc': rc.rc_channels,
            'rc_rssi': rc.rc_rssi,
            'vibe': [round(d.vibe_x, 1), round(d.vibe_y, 1), round(d.vibe_z, 1)],
            'vibe_clip': [d.vibe_clip0, d.vibe_clip1, d.vibe_clip2],
            'servo': rc.servo_out,
            'ekf_vel': round(d.ekf_vel_var, 4),
            'ekf_pos_h': round(d.ekf_pos_h_var, 4),
            'ekf_pos_v': round(d.ekf_pos_v_var, 4),
            'ekf_compass': round(d.ekf_compass_var, 4),
            'ekf_flags': d.ekf_flags,
            'wind_dir': round(d.wind_dir, 1),
            'wind_speed': round(d.wind_speed, 1),
            'terrain_alt': round(d.terrain_alt, 1),
            'gimbal_pitch': round(d.gimbal_pitch, 1),
            'gimbal_yaw': round(d.gimbal_yaw, 1),
            **self.param_mgr.get_status(),
            'vehicles': [veh for veh in self._vehicles.values()
                         if veh.get('lat', 0) != 0 and veh['sysid'] != v.sysid
                         and time.time() - veh.get('t', 0) < 10],
            'prearm': self._prearm_messages,
            'adsb': [av for av in self.traffic._adsb_vehicles.values() if time.time() - av.get('t', 0) < 60],
            'cells': bat.battery_cells,
        }

    def _start_log(self) -> None:
        log_dir = Path(__file__).resolve().parent.parent / 'logs'
        log_dir.mkdir(exist_ok=True)
        logname = str(log_dir / time.strftime('argus_%Y%m%d_%H%M%S.csv'))
        self._logfile = open(logname, 'w', encoding='utf-8')
        self._logfile.write('time,roll,pitch,yaw,lat,lon,alt_rel,alt_msl,gs,vz,voltage,current,remaining,mode,mode_name,armed,gps_fix,sats,wp,hdg,dist,bat_time\n')
        self._last_log_time = 0.0
        self.add_event(lt('log_file', self.locale) % logname, 'log_file')

    def _stop_log(self) -> None:
        try:
            if self._logfile:
                self._logfile.close()
        except OSError:
            pass
        self._logfile = None

    def get_log_path(self) -> str | None:
        if self._logfile:
            self._logfile.flush()
            return self._logfile.name
        return None

    def _write_log_line(self) -> None:
        now = time.time()
        if not self._logfile or now - self._last_log_time < cfg.LOG_WRITE_INTERVAL:
            return
        self._last_log_time = now
        md = PLANE_MODES if self.is_plane() else COPTER_MODES
        t = now - self.start_time
        a, v, bat, g = self.attitude, self.vehicle, self.battery, self.gps
        try:
            self._logfile.write(
                '%.2f,%.2f,%.2f,%.1f,%.7f,%.7f,%.1f,%.1f,%.1f,%.1f,%.2f,%.2f,%d,%d,%s,%d,%d,%d,%d,%.0f,%.0f,%d\n'
                % (t, a.roll, a.pitch, a.yaw, a.lat, a.lon,
                   a.alt_rel, a.alt_msl, a.gs, a.vz,
                   bat.voltage, bat.current, bat.remaining,
                   v.mode, md.get(v.mode, '?'), v.armed,
                   g.gps_fix, g.gps_sats, self.mission.wp_seq, a.hdg,
                   a.dist_home,
                   bat.bat_time_remaining if bat.bat_time_remaining > 0 else -1)
            )
            self._logfile.flush()
        except OSError:
            pass

    def _open_port(self, port: str, baudrate: int):
        return open_port(port, baudrate)

    def _mavlink_crc16(self, data: bytes) -> int:
        crc = 0xFFFF
        for b in data:
            tmp = b ^ (crc & 0xFF)
            tmp ^= (tmp << 4) & 0xFF
            crc = (crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)
            crc &= 0xFFFF
        return crc

    def _parse_mavlink_frame(self):
        buf = self._buf
        idx = buf.find(b'\xfd')
        if idx < 0:
            return None, max(1, len(buf))
        if idx > 0:
            return None, idx
        if len(buf) < 12:
            return None, 0
        payload_len = buf[1]
        has_sig = bool(buf[2] & 0x01)
        frame_len = 12 + payload_len + (13 if has_sig else 0)
        if len(buf) < frame_len:
            return None, 0
        crc_offset = 10 + payload_len
        if crc_offset + 2 <= len(buf):
            expected_crc = buf[crc_offset] | (buf[crc_offset + 1] << 8)
            crc_data = bytes(buf[1:10 + payload_len])
            mid = buf[7] | (buf[8] << 8) | (buf[9] << 16)
            crc_extra = _CRC_EXTRA.get(mid)
            if crc_extra is None:
                # Unknown msg id: drop silently. This covers two cases that
                # both produce the same outcome here: (a) legitimate ArduPilot
                # messages we never registered a handler for, and (b) parse
                # sync errors where 0xFD landed in the middle of a payload and
                # the trailing bytes happen to look like a frame. We can't tell
                # them apart at this layer, and either way there's no consumer.
                # The "handler exists but CRC_EXTRA missing" bug class — which
                # this used to catch at runtime — is covered statically by
                # tests/test_contract_handlers_crc.py.
                # Cap dict size at 256 distinct ids so a noisy serial line that
                # generates random sync errors can't grow this unboundedly.
                if len(self._unknown_msg_ids) < 256 or mid in self._unknown_msg_ids:
                    self._unknown_msg_ids[mid] = self._unknown_msg_ids.get(mid, 0) + 1
                self._parse_errors += 1
                return None, 1
            calc_crc = self._mavlink_crc16(crc_data + bytes([crc_extra]))
            if calc_crc != expected_crc:
                return None, 1
        return bytes(buf[:frame_len]), frame_len

    def _next_frame(self):
        if self._protocol == 'auto' and len(self._buf) >= 2:
            # Search the buffer for the first occurrence of either magic
            # sequence (rather than locking based on byte[0] alone). Auditor
            # W7: if the very first bytes received are noise (a partial
            # MAVLink frame caught mid-stream, USB enumeration garbage,
            # etc.) the old one-shot detect locked to the wrong protocol
            # permanently — only full disconnect/reconnect could recover.
            scan_len = min(len(self._buf) - 1, 256)
            pllink_idx = -1
            for i in range(scan_len):
                if self._buf[i] == 0x50 and self._buf[i + 1] == 0x4C:
                    pllink_idx = i
                    break
            std_idx = self._buf.find(b'\xfd')
            if std_idx > scan_len:
                std_idx = -1
            if pllink_idx >= 0 and (std_idx < 0 or pllink_idx <= std_idx):
                self._buf = self._buf[pllink_idx:]
                self._protocol = 'pllink'
                self.add_event(lt('proto_pllink', self.locale), 'proto_pllink')
            elif std_idx >= 0:
                self._buf = self._buf[std_idx:]
                self._protocol = 'standard'
                self.add_event(lt('proto_std', self.locale), 'proto_std')
            else:
                # Neither magic found in the first 256 bytes — drop them
                # and wait for more. (Otherwise we'd spin parsing garbage.)
                self._buf = self._buf[scan_len:]
                return None, 0
        if self._protocol == 'pllink':
            return pld(self._buf)
        return self._parse_mavlink_frame()

    def _loop(self) -> None:
        last_hb = 0.0
        while self._running:
            now = time.time()
            if now - last_hb >= cfg.HEARTBEAT_INTERVAL:
                cmd_module.send_heartbeat(self)
                last_hb = now
                if not self.connected and self.frame_count < 3:
                    cmd_module.request_streams(self)
            if self.connected and self.last_frame_time > 0 and now - self.last_frame_time > cfg.LINK_LOST_TIMEOUT:
                self.add_event(lt('link_lost', self.locale), 'link_lost')
                # Clear pending uploads / log buffer / etc. — same hygiene as
                # user-driven disconnect (auditor C1). Also resets frame_count
                # so request_streams() re-fires on the next heartbeat (C2).
                self._reset_session_state()
                if self._reconnect_enabled and self._last_port:
                    self.add_event(lt('reconnecting', self.locale), 'reconnecting')
                    try:
                        if self._ser:
                            self._ser.close()
                    except OSError:
                        pass
                    self._buf = b''
                    self._protocol = 'auto'
                    try:
                        self._ser = self._open_port(self._last_port, self._last_baud)
                        self.sq = 0
                        self._reconnect_attempts = 0
                        self.add_event(lt('reconnected', self.locale), 'reconnected')
                    except OSError:
                        # Exponential backoff capped at 60s. Auditor W1:
                        # without this the loop spun on a permanently-bad
                        # port (cable unplugged, host firewalled) at the
                        # fixed RECONNECT_DELAY cadence forever, masking
                        # any other diagnostic the operator might check.
                        self._reconnect_attempts += 1
                        delay = min(cfg.RECONNECT_DELAY * (2 ** min(self._reconnect_attempts, 5)), 60.0)
                        self.add_event(lt('reconnect_fail', self.locale), 'reconnect_fail')
                        time.sleep(delay)
                    continue
            try:
                data = self._ser.read(1024)
                if data:
                    self._buf += data
                    if len(self._buf) > 65536:
                        self._buf = self._buf[-32768:]
                        self._parse_errors += 1
            except OSError:
                time.sleep(0.1)
                continue
            while len(self._buf) >= 7:
                payload, consumed = self._next_frame()
                if payload:
                    self._buf = self._buf[consumed:]
                    self.frame_count += 1
                    try:
                        self._process(payload)
                    except (struct.error, ValueError, IndexError):
                        self._parse_errors += 1
                        if self._parse_errors == 1 or self._parse_errors % 100 == 0:
                            import traceback
                            logger.warning('parse error #%d: %s',
                                           self._parse_errors,
                                           traceback.format_exc().splitlines()[-1])
                elif consumed > 0:
                    self._buf = self._buf[consumed:]
                else:
                    break
            self._write_log_line()
            self.param_mgr.check_timeout()
            self._check_mission_dl_timeout()
            time.sleep(cfg.MAIN_LOOP_SLEEP)

    def _check_mission_dl_timeout(self) -> None:
        from .commands._mission import check_mission_dl_timeout
        check_mission_dl_timeout(self)

    def get_inspector_data(self) -> list[dict]:
        # _msg_stats is mutated by _process() under _state_lock; iterating it
        # without the lock from the asyncio push thread races with the link
        # thread and can raise RuntimeError("dictionary changed size during
        # iteration") when the FC sends a new msg id (auditor finding C6).
        now = time.time()
        # Drop msg ids that haven't been seen for >5x the stats window —
        # otherwise old/transient mids (e.g. a one-off MAG_CAL_REPORT) stick
        # in the inspector forever (auditor N3, small leak).
        STALE_AGE = self._msg_stats_window * 5
        result = []
        with self._state_lock:
            for mid in sorted(self._msg_stats):
                st = self._msg_stats[mid]
                times = [t for t in st.get('times', []) if now - t < self._msg_stats_window]
                last_seen = st.get('last_seen', 0)
                if not times and last_seen and now - last_seen > STALE_AGE:
                    del self._msg_stats[mid]
                    continue
                st['times'] = times
                hz = len(times) / self._msg_stats_window if times else 0
                result.append({
                    'id': mid, 'name': st.get('name', ''),
                    'hz': round(hz, 1), 'count': st.get('count', 0),
                    'size': st.get('size', 0), 'last_fields': st.get('last_fields', {}),
                })
        return result

    def _process(self, payload: bytes) -> None:
        if len(payload) < 12 or payload[0] != 0xFD:
            return
        mid = payload[7] | (payload[8] << 8) | (payload[9] << 16)
        p = payload[10:10 + payload[1]]
        pl = payload[1]
        sid = payload[5]
        with self._state_lock:
            self.last_frame_time = time.time()
            self._raw_sysid = sid
            if self.inspector_enabled:
                now = time.time()
                st = self._msg_stats.get(mid)
                if not st:
                    st = {'name': _MSG_NAMES.get(mid, ''), 'count': 0, 'size': pl, 'times': [], 'last_fields': {}, 'last_seen': 0.0}
                    self._msg_stats[mid] = st
                st['count'] += 1
                st['size'] = pl
                st['last_seen'] = now
                st['times'].append(now)
                if len(st['times']) > 100:
                    st['times'] = st['times'][-50:]
            if mid == 33 and pl >= 20:
                lat = struct.unpack_from('<i', p, 4)[0] / 1e7
                lon = struct.unpack_from('<i', p, 8)[0] / 1e7
                alt = struct.unpack_from('<i', p, 16)[0] / 1000.0
                hdg = struct.unpack_from('<H', p, 26)[0] / 100.0 if pl >= 28 else 0
                v = self._vehicles.get(sid, {})
                v.update({'sysid': sid, 'lat': round(lat, 7), 'lon': round(lon, 7),
                          'alt': round(alt, 1), 'hdg': round(hdg, 0), 't': time.time()})
                self._vehicles[sid] = v
            if mid == 0 and pl >= 7:
                v = self._vehicles.get(sid, {'sysid': sid, 'lat': 0, 'lon': 0, 'alt': 0, 'hdg': 0, 't': 0})
                v['armed'] = bool(p[6] & 0x80)
                v['mode'] = p[0] | (p[1] << 8) | (p[2] << 16) | (p[3] << 24)
                v['vtype'] = p[4]
                self._vehicles[sid] = v
            mavlink_dispatch.dispatch(mid, p, pl, self)
