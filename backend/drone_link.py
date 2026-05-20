from __future__ import annotations
import math
import socket
import struct
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from pllink_proto import ple, pld, bm

from .constants import (COPTER_MODES, PLANE_MODES, ROVER_MODES, SUB_MODES,
                        COPTER_BTNS, PLANE_BTNS, ROVER_BTNS, SUB_BTNS, FIX_NAMES,
                        COPTER_MODES_EN, PLANE_MODES_EN, ROVER_MODES_EN, SUB_MODES_EN,
                        COPTER_BTNS_EN, PLANE_BTNS_EN, ROVER_BTNS_EN, SUB_BTNS_EN, FIX_NAMES_EN)
from . import mavlink_dispatch
from .mavlink_handlers import init_handlers
from . import commands as cmd_module
from .param_manager import ParamManager
from .locale_text import lt


class TcpWrapper:
    def __init__(self, sock: socket.socket):
        self._sock = sock

    def read(self, n: int) -> bytes:
        try:
            return self._sock.recv(n)
        except (socket.timeout, OSError):
            return b''

    def write(self, data: bytes) -> None:
        self._sock.sendall(data)

    def close(self) -> None:
        self._sock.close()


class UdpWrapper:
    def __init__(self, port: int, host: str = ''):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.settimeout(0.1)
        self._sock.bind((host or '', port))
        self._remote = None

    def read(self, n: int) -> bytes:
        try:
            data, addr = self._sock.recvfrom(n)
            if not self._remote:
                self._remote = addr
            return data
        except (socket.timeout, OSError):
            return b''

    def write(self, data: bytes) -> None:
        if self._remote:
            try:
                self._sock.sendto(data, self._remote)
            except OSError:
                pass

    def close(self) -> None:
        self._sock.close()


class DroneLink:
    def __init__(self):
        init_handlers()
        self._ser = None
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._buf = b''
        self.sq = 0
        self._parse_errors = 0
        self._raw_sysid = 1
        self._logfile = None
        self._last_log_time = 0.0
        self._last_port = ''
        self._last_baud = 57600
        self._reconnect_enabled = True

        self._protocol = 'auto'
        self.locale = 'zh'
        self._vehicles: dict[int, dict] = {}
        self.connected = False
        self.frame_count = 0
        self.last_frame_time = 0.0
        self.start_time = 0.0
        self.events: list[dict] = []

        self.roll = self.pitch = self.yaw = 0.0
        self.lat = self.lon = self.alt_rel = self.alt_msl = 0.0
        self.vx = self.vy = self.vz = self.gs = self.hdg = 0.0
        self.home_lat = self.home_lon = 0.0
        self.dist_home = 0.0
        self.armed_time = 0.0
        self.voltage = self.current = 0.0
        self.remaining = -1
        self.mode = 0
        self.armed = False
        self.gps_fix = 0
        self.gps_sats = 0
        self.wp_seq = 0
        self.vtype_raw = 0
        self.force_plane = None
        self.sysid = 1
        self.max_alt = self.max_speed = self.total_dist = 0.0
        self._prev_pos = None
        self._bat_history: list[tuple[float, int]] = []
        self.bat_time_remaining = -1
        self._bat_start_pct = -1
        self._mission_items: list[dict] = []
        self._mission_pending = False
        self._seq_to_wp: dict[int, int] = {}
        self._fence_items: list[dict] = []
        self._fence_pending = False
        self.flight_summary = None
        self.param_mgr = ParamManager(self)
        self.fw_version = ''
        self.fw_git = ''
        self.board_id = 0
        self._dl_pending = False
        self._dl_total = 0
        self._dl_items: list[dict | None] = []
        self._dl_messages: list[dict] = []
        self._ws_queue: list[dict] = []
        self._log_list: list[dict] = []
        self._log_download_id = -1
        self._log_download_data = bytearray()
        self._log_download_size = 0
        self._log_download_ofs = 0
        self._log_messages: list[dict] = []
        self.rc_channels: list[int] = [0] * 16
        self.rc_rssi = 0
        self.vibe_x = self.vibe_y = self.vibe_z = 0.0
        self.vibe_clip0 = self.vibe_clip1 = self.vibe_clip2 = 0
        self.ekf_vel_var = 0.0
        self.ekf_pos_h_var = 0.0
        self.ekf_pos_v_var = 0.0
        self.ekf_compass_var = 0.0
        self.ekf_terrain_var = 0.0
        self.ekf_flags = 0
        self.servo_out: list[int] = [0] * 16
        self.wind_dir = 0.0
        self.wind_speed = 0.0
        self.terrain_alt = -1.0

    def is_plane(self) -> bool:
        if self.force_plane is not None:
            return self.force_plane
        return self.vtype_raw in (1, 19, 20, 21, 22, 23, 24, 25)

    def queue_ws(self, msg: dict) -> None:
        self._ws_queue.append(msg)
        if len(self._ws_queue) > 2000:
            self._ws_queue = self._ws_queue[-1000:]

    def add_event(self, text: str) -> None:
        self.events.append({'time': time.strftime('%H:%M:%S'), 'text': text})
        if len(self.events) > 100:
            self.events = self.events[-50:]

    def send(self, frame: bytes) -> None:
        with self._lock:
            if self._ser:
                try:
                    if self._protocol in ('pllink', 'auto'):
                        self._ser.write(ple(frame, self.sq & 0xFF))
                    else:
                        self._ser.write(frame)
                    self.sq += 1
                except Exception:
                    pass

    def connect(self, port: str, baudrate: int = 57600, protocol: str = 'auto') -> bool:
        self._protocol = 'standard' if port.startswith('udp:') else protocol
        try:
            self._ser = self._open_port(port, baudrate)
            if port.startswith('udp:'):
                self.add_event(lt('udp', self.locale) % port[4:])
            elif port.startswith('tcp:'):
                self.add_event(lt('tcp', self.locale) % port[4:])
        except Exception as e:
            self.add_event(lt('connect_fail', self.locale) % e)
            return False
        self._running = True
        self.connected = False
        self.frame_count = 0
        self._buf = b''
        self.sq = 0
        self.vtype_raw = 0
        self.home_lat = self.home_lon = 0.0
        self.dist_home = 0.0
        self.armed_time = 0.0
        self.last_frame_time = 0.0
        self.start_time = time.time()
        self._last_port = port
        self._last_baud = baudrate
        self._reconnect_enabled = True
        self._start_log()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def disconnect(self) -> None:
        self._running = False
        self._reconnect_enabled = False
        if self._thread:
            self._thread.join(timeout=3)
        try:
            if self._ser:
                self._ser.close()
        except Exception:
            pass
        self._ser = None
        self.connected = False
        self.vtype_raw = 0
        self.force_plane = None
        self._prev_pos = None
        self._mission_pending = False
        self._stop_log()
        self.add_event(lt('disconnected', self.locale))

    def reconnect(self) -> bool:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        try:
            if self._ser:
                self._ser.close()
        except Exception:
            pass
        self._ser = None
        self.connected = False
        self._buf = b''
        try:
            self._ser = self._open_port(self._last_port, self._last_baud)
        except Exception as e:
            self.add_event(lt('reconnect_err', self.locale) % e)
            return False
        self._running = True
        self.sq = 0
        self.add_event(lt('reconnected', self.locale))
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def _get_vehicle_info(self) -> tuple[dict, list, str]:
        vt = self.vtype_raw
        en = self.locale == 'en'
        if self.force_plane is True:
            return (PLANE_MODES_EN if en else PLANE_MODES, PLANE_BTNS_EN if en else PLANE_BTNS,
                    'Fixed Wing' if en else '固定翼')
        if self.force_plane is False:
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
        md, btns, vn = self._get_vehicle_info()
        return {
            'type': 'state',
            'connected': self.connected,
            'frames': self.frame_count,
            'mode': md.get(self.mode, 'MODE%d' % self.mode),
            'mode_id': self.mode,
            'armed': self.armed,
            'roll': round(self.roll, 1),
            'pitch': round(self.pitch, 1),
            'yaw': round(self.yaw, 1),
            'lat': round(self.lat, 7),
            'lon': round(self.lon, 7),
            'alt_rel': round(self.alt_rel, 1),
            'alt_msl': round(self.alt_msl, 1),
            'gs': round(self.gs, 1),
            'vz': round(-self.vz, 1),
            'hdg': round(self.hdg, 0),
            'dist_home': round(self.dist_home, 0),
            'flight_time': int(time.time() - self.armed_time) if self.armed and self.armed_time else 0,
            'voltage': round(self.voltage, 2),
            'current': round(self.current, 2),
            'remaining': self.remaining,
            'gps_fix': (FIX_NAMES_EN if self.locale == 'en' else FIX_NAMES).get(self.gps_fix, '?'),
            'gps_sats': self.gps_sats,
            'wp': self.wp_seq,
            'vtype': vn,
            'vtype_raw': self.vtype_raw,
            'mode_btns': btns,
            'link_age': round(time.time() - self.last_frame_time, 1) if self.connected and self.last_frame_time > 0 else -1,
            'bat_time': self.bat_time_remaining if self.bat_time_remaining > 0 else -1,
            'home_lat': round(self.home_lat, 7),
            'home_lon': round(self.home_lon, 7),
            'parse_errors': self._parse_errors,
            'flight_summary': self.flight_summary,
            'log_active': self._logfile is not None,
            'fw_version': self.fw_version,
            'fw_git': self.fw_git,
            'board_id': self.board_id,
            'rc': self.rc_channels,
            'rc_rssi': self.rc_rssi,
            'vibe': [round(self.vibe_x, 1), round(self.vibe_y, 1), round(self.vibe_z, 1)],
            'vibe_clip': [self.vibe_clip0, self.vibe_clip1, self.vibe_clip2],
            'servo': self.servo_out,
            'ekf_vel': round(self.ekf_vel_var, 4),
            'ekf_pos_h': round(self.ekf_pos_h_var, 4),
            'ekf_pos_v': round(self.ekf_pos_v_var, 4),
            'ekf_compass': round(self.ekf_compass_var, 4),
            'ekf_flags': self.ekf_flags,
            'wind_dir': round(self.wind_dir, 1),
            'wind_speed': round(self.wind_speed, 1),
            'terrain_alt': round(self.terrain_alt, 1),
            **self.param_mgr.get_status(),
            'vehicles': [v for v in self._vehicles.values()
                         if v.get('lat', 0) != 0 and v['sysid'] != self.sysid
                         and time.time() - v.get('t', 0) < 10],
        }

    def _start_log(self) -> None:
        log_dir = Path(__file__).resolve().parent.parent / 'logs'
        log_dir.mkdir(exist_ok=True)
        logname = str(log_dir / time.strftime('pllink_%Y%m%d_%H%M%S.csv'))
        self._logfile = open(logname, 'w')
        self._logfile.write('time,roll,pitch,yaw,lat,lon,alt_rel,alt_msl,gs,vz,voltage,current,remaining,mode,mode_name,armed,gps_fix,sats,wp,hdg,dist,bat_time\n')
        self._last_log_time = 0.0
        self.add_event(lt('log_file', self.locale) % logname)

    def _stop_log(self) -> None:
        try:
            if self._logfile:
                self._logfile.close()
        except Exception:
            pass
        self._logfile = None

    def get_log_path(self) -> str | None:
        if self._logfile:
            self._logfile.flush()
            return self._logfile.name
        return None

    def _write_log_line(self) -> None:
        now = time.time()
        if not self._logfile or now - self._last_log_time < 0.25:
            return
        self._last_log_time = now
        md = PLANE_MODES if self.is_plane() else COPTER_MODES
        t = now - self.start_time
        try:
            self._logfile.write(
                '%.2f,%.2f,%.2f,%.1f,%.7f,%.7f,%.1f,%.1f,%.1f,%.1f,%.2f,%.2f,%d,%d,%s,%d,%d,%d,%d,%.0f,%.0f,%d\n'
                % (t, self.roll, self.pitch, self.yaw, self.lat, self.lon,
                   self.alt_rel, self.alt_msl, self.gs, self.vz,
                   self.voltage, self.current, self.remaining,
                   self.mode, md.get(self.mode, '?'), self.armed,
                   self.gps_fix, self.gps_sats, self.wp_seq, self.hdg,
                   self.dist_home,
                   self.bat_time_remaining if self.bat_time_remaining > 0 else -1)
            )
            self._logfile.flush()
        except Exception:
            pass

    def _open_port(self, port: str, baudrate: int):
        if port.startswith('udp:'):
            parts = port[4:].split(':')
            if len(parts) == 2:
                host, udp_port = parts[0], int(parts[1])
            else:
                host, udp_port = '', int(parts[0])
            return UdpWrapper(udp_port, host)
        elif port.startswith('tcp:'):
            parts = port[4:].split(':')
            host, tcp_port = parts[0], int(parts[1])
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, tcp_port))
            sock.settimeout(0.1)
            return TcpWrapper(sock)
        else:
            import serial
            s = serial.Serial(port, baudrate, timeout=0.1)
            s.reset_input_buffer()
            return s

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
        return bytes(buf[:frame_len]), frame_len

    def _next_frame(self):
        if self._protocol == 'auto' and len(self._buf) >= 2:
            if self._buf[0] == 0x50 and self._buf[1] == 0x4C:
                self._protocol = 'pllink'
                self.add_event(lt('proto_pllink', self.locale))
            else:
                self._protocol = 'standard'
                self.add_event(lt('proto_std', self.locale))
        if self._protocol == 'pllink':
            return pld(self._buf)
        return self._parse_mavlink_frame()

    def _loop(self) -> None:
        last_hb = 0.0
        while self._running:
            now = time.time()
            if now - last_hb >= 0.5:
                cmd_module.send_heartbeat(self)
                last_hb = now
                if not self.connected and self.frame_count < 3:
                    cmd_module.request_streams(self)
            if self.connected and self.last_frame_time > 0 and now - self.last_frame_time > 5:
                self.add_event(lt('link_lost', self.locale))
                self.connected = False
                if self._reconnect_enabled and self._last_port:
                    self.add_event(lt('reconnecting', self.locale))
                    try:
                        if self._ser:
                            self._ser.close()
                    except Exception:
                        pass
                    self._buf = b''
                    try:
                        self._ser = self._open_port(self._last_port, self._last_baud)
                        self.sq = 0
                        self.add_event(lt('reconnected', self.locale))
                    except Exception:
                        self.add_event(lt('reconnect_fail', self.locale))
                        time.sleep(3)
                    continue
            try:
                data = self._ser.read(1024)
                if data:
                    self._buf += data
            except Exception:
                time.sleep(0.1)
                continue
            while len(self._buf) >= 7:
                payload, consumed = self._next_frame()
                if payload:
                    self._buf = self._buf[consumed:]
                    self.frame_count += 1
                    try:
                        self._process(payload)
                    except Exception:
                        self._parse_errors += 1
                        if self._parse_errors == 1 or self._parse_errors % 100 == 0:
                            import traceback
                            print('[GCS] parse error #%d: %s' % (
                                self._parse_errors,
                                traceback.format_exc().splitlines()[-1]
                            ), file=sys.stderr)
                elif consumed > 0:
                    self._buf = self._buf[consumed:]
                else:
                    break
            self._write_log_line()
            time.sleep(0.02)

    def _process(self, payload: bytes) -> None:
        if len(payload) < 12 or payload[0] != 0xFD:
            return
        self.last_frame_time = time.time()
        self._raw_sysid = payload[5]
        mid = payload[7] | (payload[8] << 8) | (payload[9] << 16)
        p = payload[10:10 + payload[1]]
        pl = payload[1]
        sid = self._raw_sysid
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
