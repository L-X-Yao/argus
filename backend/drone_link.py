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

from .constants import COPTER_MODES, PLANE_MODES, COPTER_BTNS, PLANE_BTNS, FIX_NAMES
from . import mavlink_dispatch
from .mavlink_handlers import init_handlers
from . import commands as cmd_module
from .param_manager import ParamManager


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
                    self._ser.write(ple(frame, self.sq & 0xFF))
                    self.sq += 1
                except Exception:
                    pass

    def connect(self, port: str, baudrate: int = 57600) -> bool:
        try:
            self._ser = self._open_port(port, baudrate)
            if port.startswith('tcp:'):
                self.add_event('TCP %s' % port[4:])
        except Exception as e:
            self.add_event('连接失败: %s' % e)
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
        self.add_event('已断开')

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
            self.add_event('重连失败: %s' % e)
            return False
        self._running = True
        self.sq = 0
        self.add_event('已重连')
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def get_state(self) -> dict:
        md = PLANE_MODES if self.is_plane() else COPTER_MODES
        vn = '固定翼' if self.is_plane() else ('多旋翼' if self.vtype_raw > 0 else '')
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
            'vz': round(self.vz, 1),
            'hdg': round(self.hdg, 0),
            'dist_home': round(self.dist_home, 0),
            'flight_time': int(time.time() - self.armed_time) if self.armed and self.armed_time else 0,
            'voltage': round(self.voltage, 2),
            'current': round(self.current, 2),
            'remaining': self.remaining,
            'gps_fix': FIX_NAMES.get(self.gps_fix, '?'),
            'gps_sats': self.gps_sats,
            'wp': self.wp_seq,
            'vtype': vn,
            'vtype_raw': self.vtype_raw,
            'mode_btns': PLANE_BTNS if self.is_plane() else COPTER_BTNS,
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
            **self.param_mgr.get_status(),
        }

    def _start_log(self) -> None:
        log_dir = Path(__file__).resolve().parent.parent / 'logs'
        log_dir.mkdir(exist_ok=True)
        logname = str(log_dir / time.strftime('pllink_%Y%m%d_%H%M%S.csv'))
        self._logfile = open(logname, 'w')
        self._logfile.write('time,roll,pitch,yaw,lat,lon,alt_rel,alt_msl,gs,vz,voltage,current,remaining,mode,mode_name,armed,gps_fix,sats,wp,hdg,dist,bat_time\n')
        self._last_log_time = 0.0
        self.add_event('日志: %s' % logname)

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
        if port.startswith('tcp:'):
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
                self.add_event('链路丢失')
                self.connected = False
                if self._reconnect_enabled and self._last_port:
                    self.add_event('自动重连...')
                    try:
                        if self._ser:
                            self._ser.close()
                    except Exception:
                        pass
                    self._buf = b''
                    try:
                        self._ser = self._open_port(self._last_port, self._last_baud)
                        self.sq = 0
                        self.add_event('已重连')
                    except Exception:
                        self.add_event('重连失败, 3秒后重试')
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
                payload, consumed = pld(self._buf)
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
        mavlink_dispatch.dispatch(mid, p, pl, self)
