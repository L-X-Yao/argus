from __future__ import annotations

import base64
import struct
import threading
import time
from typing import TYPE_CHECKING

from .config import cfg
from .locale_text import lt
from .pllink_proto import bm

if TYPE_CHECKING:
    from .drone_link import DroneLink

_mission_timer: threading.Timer | None = None


def execute(cmd: str, param, link: DroneLink, data: dict | None = None) -> dict | None:
    data = data or {}
    handler = _DISPATCH.get(cmd)
    if handler:
        return handler(link, param, data)
    return None


# --- Flight control ---


def _cmd_arm(link: DroneLink, param, data: dict):
    link.add_event(lt('arm_send', link.locale), 'arm_send')
    _send_cmd(link, 400, p1=1.0)


def _cmd_disarm(link: DroneLink, param, data: dict):
    link.add_event(lt('disarm_send', link.locale), 'disarm_send')
    _send_cmd(link, 400, p1=0)


def _cmd_force_disarm(link: DroneLink, param, data: dict):
    link.add_event(lt('force_disarm', link.locale), 'force_disarm')
    _send_cmd(link, 400, p1=0, p2=21196)


def _cmd_rtl(link: DroneLink, param, data: dict):
    rm = 21 if link.is_plane() else 6
    link.add_event(lt('rtl', link.locale) % rm, 'rtl')
    _send_set_mode(link, rm)


def _cmd_mode(link: DroneLink, param, data: dict):
    if param is None:
        return None
    from .constants import COPTER_MODES, PLANE_MODES
    md = PLANE_MODES if link.is_plane() else COPTER_MODES
    link.add_event(lt('mode_to', link.locale) % md.get(int(param), str(param)), 'mode_to')
    _send_set_mode(link, int(param))


def _cmd_takeoff(link: DroneLink, param, data: dict):
    alt = float(data.get('alt', 30))
    link.add_event(lt('takeoff', link.locale) % alt, 'takeoff')
    _send_cmd(link, 22, p7=alt)


def _cmd_drop(link: DroneLink, param, data: dict):
    link.add_event(lt('drop_on', link.locale), 'drop_on')
    _send_cmd(link, 181, p1=0, p2=0)


def _cmd_drop_stop(link: DroneLink, param, data: dict):
    link.add_event(lt('drop_off', link.locale), 'drop_off')
    _send_cmd(link, 181, p1=0, p2=1)


# --- Mission ---


def _cmd_mission_start(link: DroneLink, param, data: dict):
    global _mission_timer
    if _mission_timer:
        _mission_timer.cancel()
    am = 10 if link.is_plane() else 3
    link.add_event(lt('mission_start', link.locale), 'mission_start')
    _send_set_mode(link, am)

    def _delayed():
        try:
            _send_cmd(link, 300)
        except Exception:
            link.add_event('Mission start command failed', 'cmd_ack_fail')

    _mission_timer = threading.Timer(cfg.MISSION_START_DELAY, _delayed)
    _mission_timer.daemon = True
    _mission_timer.start()


def _cmd_mission_clear(link: DroneLink, param, data: dict):
    link.send(bm(45, bytes([link.vehicle.sysid, 1, 0]), link.sq, 232))
    link.add_event(lt('mission_clear', link.locale), 'mission_clear')


def _cmd_mission_upload(link: DroneLink, param, data: dict):
    wps = data.get('waypoints', [])
    takeoff_alt = float(data.get('takeoff_alt', 30))
    if not wps:
        return {'ok': False, 'error': lt('err_no_wp', link.locale)}
    if len(wps) > 500:
        return {'ok': False, 'error': 'Mission too large (max 500 WP)'}
    for wp in wps:
        lat, lon = wp.get('lat', 0), wp.get('lon', 0)
        if abs(lat) < 0.001 or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return {'ok': False, 'error': lt('err_bad_coord', link.locale)}
        alt = wp.get('alt', 0)
        if not (-500 <= alt <= 100000):
            return {'ok': False, 'error': lt('err_bad_coord', link.locale)}
    _upload_mission(link, wps, takeoff_alt)


def _cmd_fence_upload(link: DroneLink, param, data: dict):
    polygon = data.get('polygon', [])
    if len(polygon) < 3 or len(polygon) > 200:
        return {'ok': False, 'error': lt('err_fence_min', link.locale)}
    items = []
    for i, pt in enumerate(polygon):
        items.append({
            'seq': i, 'cmd': 5001, 'lat': pt['lat'], 'lon': pt['lon'],
            'alt': 0, 'p1': len(polygon), 'p2': 0,
        })
    link.mission._fence_items = items
    link.mission._fence_pending = True
    _send_fence_count(link, len(items))
    link.add_event(lt('fence_upload', link.locale) % len(polygon), 'fence_upload')


def _cmd_mission_download(link: DroneLink, param, data: dict):
    link.mission._dl_pending = True
    link.mission._dl_total = 0
    link.mission._dl_items = []
    link.add_event(lt('mission_dl', link.locale), 'mission_dl')
    link.send(bm(43, struct.pack('<BBB', link.vehicle.sysid, 1, 0), link.sq, 132))


def _cmd_rally_upload(link: DroneLink, param, data: dict):
    points = data.get('points', [])
    if points:
        _upload_rally(link, points)


# --- Vehicle ---


def _cmd_set_vtype(link: DroneLink, param, data: dict):
    v = data.get('vtype', 'auto')
    link.vehicle.force_plane = True if v == 'plane' else (False if v == 'copter' else None)
    vname = lt('vtype_plane' if v == 'plane' else 'vtype_copter' if v == 'copter' else 'vtype_auto', link.locale)
    link.add_event(lt('vtype_set', link.locale) % vname, 'vtype_set')


def _cmd_guided_goto(link: DroneLink, param, data: dict):
    lat = float(data.get('lat', 0))
    lon = float(data.get('lon', 0))
    alt = float(data.get('alt', 30))
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180) or not (-500 <= alt <= 100000):
        return {'ok': False, 'error': lt('err_bad_coord', link.locale)}
    lat7 = int(lat * 1e7)
    lon7 = int(lon * 1e7)
    gm = 15 if link.is_plane() else 4
    _send_set_mode(link, gm)
    link.add_event(lt('guided', link.locale) % (lat7 / 1e7, lon7 / 1e7, alt), 'guided')
    p = struct.pack('<IiifffffffffHBBB',
                    0, lat7, lon7, alt, 0, 0, 0, 0, 0, 0, 0, 0,
                    0x0FF8, link.vehicle.sysid, 1, 6)
    link.send(bm(84, p, link.sq, 5))


def _cmd_switch_vehicle(link: DroneLink, param, data: dict):
    new_sysid = int(data.get('sysid', 1))
    link.active_sysid = new_sysid
    link.vehicle.sysid = new_sysid
    link.add_event(lt('vehicle_switch', link.locale) % new_sysid, 'vehicle_switch')


def _cmd_clear_summary(link: DroneLink, param, data: dict):
    link.vehicle.flight_summary = None


# --- Calibration ---


def _cmd_cal_compass(link: DroneLink, param, data: dict):
    link.add_event(lt('cal_compass', link.locale), 'cal_compass')
    _send_cmd(link, 241, p2=1)


def _cmd_cal_accel(link: DroneLink, param, data: dict):
    link.add_event(lt('cal_accel', link.locale), 'cal_accel')
    _send_cmd(link, 241, p5=1)


def _cmd_cal_gyro(link: DroneLink, param, data: dict):
    link.add_event(lt('cal_gyro', link.locale), 'cal_gyro')
    _send_cmd(link, 241, p1=1)


def _cmd_cal_level(link: DroneLink, param, data: dict):
    link.add_event(lt('cal_level', link.locale), 'cal_level')
    _send_cmd(link, 241, p5=4)


def _cmd_cal_baro(link: DroneLink, param, data: dict):
    link.add_event(lt('cal_baro', link.locale), 'cal_baro')
    _send_cmd(link, 241, p3=1)


def _cmd_cal_cancel(link: DroneLink, param, data: dict):
    link.add_event(lt('cal_cancel', link.locale), 'cal_cancel')
    _send_cmd(link, 241)


# --- Parameters ---


def _cmd_param_request_all(link: DroneLink, param, data: dict):
    link.param_mgr.request_all()


def _cmd_param_set(link: DroneLink, param, data: dict):
    name = data.get('name', '')
    value = float(data.get('value', 0))
    if name:
        link.param_mgr.set_param(name, value)


def _cmd_param_save(link: DroneLink, param, data: dict):
    path = link.param_mgr.save_to_file()
    return {'ok': True, 'path': path}


def _cmd_param_load(link: DroneLink, param, data: dict):
    path = data.get('path', '')
    if path:
        changed = link.param_mgr.load_from_file(path)
        return {'ok': True, 'changed': changed}


# --- Logs ---


def _cmd_log_list(link: DroneLink, param, data: dict):
    link.log_dl._log_list = []
    link.send(bm(117, struct.pack('<HHBB', 0, 0xFFFF, link.vehicle.sysid, 1), link.sq, 128))
    link.add_event(lt('log_list_req', link.locale), 'log_list_req')


def _cmd_log_download(link: DroneLink, param, data: dict):
    log_id = int(data.get('id', 0))
    lg = link.log_dl
    log_entry = next((l for l in lg._log_list if l['id'] == log_id), None)
    if not log_entry:
        return {'ok': False, 'error': lt('err_log_not_found', link.locale)}
    lg._log_download_id = log_id
    lg._log_download_size = log_entry['size']
    lg._log_download_data = bytearray(log_entry['size'])
    lg._log_download_ofs = 0
    link.add_event(lt('log_dl', link.locale) % (log_id, log_entry['size'] // 1024), 'log_dl')
    chunk = min(90 * 50, log_entry['size'])
    link.send(bm(119, struct.pack('<IIHBB', 0, chunk, log_id, link.vehicle.sysid, 1), link.sq, 116))


def _cmd_log_cancel(link: DroneLink, param, data: dict):
    link.send(bm(126, struct.pack('<BB', link.vehicle.sysid, 1), link.sq, 203))
    link.log_dl._log_download_id = -1
    link.add_event(lt('log_dl_cancel', link.locale), 'log_dl_cancel')


# --- System ---


def _cmd_reboot(link: DroneLink, param, data: dict):
    link.add_event(lt('reboot', link.locale), 'reboot')
    _send_cmd(link, 246, p1=1)


def _cmd_reboot_bootloader(link: DroneLink, param, data: dict):
    link.add_event(lt('reboot_bl', link.locale), 'reboot_bl')
    _send_cmd(link, 246, p1=3)


def _cmd_inspector_toggle(link: DroneLink, param, data: dict):
    link.inspector_enabled = not link.inspector_enabled


def _cmd_serial_control(link: DroneLink, param, data: dict):
    text = data.get('text', '')
    if text:
        _send_serial_control(link, text)


def _cmd_inject_rtcm(link: DroneLink, param, data: dict):
    rtcm_data = data.get('data', '')
    if not rtcm_data:
        return
    raw = base64.b64decode(rtcm_data)
    for i in range(0, len(raw), 110):
        chunk = raw[i:i + 110]
        flags = 0x01
        if i == 0:
            flags |= 0x04
        if i + 110 >= len(raw):
            flags |= 0x08
        p = struct.pack('<BBHB', 0, flags, len(chunk), len(chunk))
        p += chunk + b'\x00' * (110 - len(chunk))
        link.send(bm(233, p, link.sq, 0))


# --- RC / Motor ---


def _cmd_rc_override(link: DroneLink, param, data: dict):
    channels = data.get('channels', [])
    if len(channels) >= 8:
        p = struct.pack('<BB', link.vehicle.sysid, 1)
        for i in range(8):
            p += struct.pack('<H', max(0, min(65535, int(channels[i]))))
        link.send(bm(70, p, link.sq, 124))


def _cmd_motor_test(link: DroneLink, param, data: dict):
    motor = int(data.get('motor', 0))
    throttle = float(data.get('throttle', 5))
    duration = float(data.get('duration', 2))
    link.add_event(lt('motor_test', link.locale) % (motor + 1, throttle), 'motor_test')
    _send_cmd(link, 209, p1=float(motor), p2=0, p3=throttle, p4=duration, p5=1)


def _cmd_motor_test_stop(link: DroneLink, param, data: dict):
    for i in range(8):
        _send_cmd(link, 209, p1=float(i), p2=0, p3=0, p4=0, p5=1)


# --- Camera / Gimbal ---


def _cmd_gimbal_angle(link: DroneLink, param, data: dict):
    pitch = float(data.get('pitch', 0))
    yaw = float(data.get('yaw', 0))
    _send_cmd(link, 205, p1=pitch, p4=yaw)


def _cmd_gimbal_rate(link: DroneLink, param, data: dict):
    pitch_rate = float(data.get('pitch_rate', 0))
    yaw_rate = float(data.get('yaw_rate', 0))
    p = struct.pack('<ffffffBBB', 0, 0, 0, float(pitch_rate * 100), 0, float(yaw_rate * 100),
                    link.vehicle.sysid, 1, 2)
    link.send(bm(282, p, link.sq, 0))


def _cmd_camera_trigger(link: DroneLink, param, data: dict):
    _send_cmd(link, 203)


def _cmd_camera_video_start(link: DroneLink, param, data: dict):
    _send_cmd(link, 2500, p1=0, p2=0, p3=1)


def _cmd_camera_video_stop(link: DroneLink, param, data: dict):
    _send_cmd(link, 2501)


def _cmd_camera_zoom(link: DroneLink, param, data: dict):
    zoom_val = float(data.get('zoom', 1))
    _send_cmd(link, 531, p1=1, p2=zoom_val)


def _cmd_do_set_roi(link: DroneLink, param, data: dict):
    lat = float(data.get('lat', 0))
    lon = float(data.get('lon', 0))
    alt = float(data.get('alt', 0))
    _send_cmd(link, 201, p5=lat, p6=lon, p7=alt)


# --- Dispatch table ---

_DISPATCH = {
    'arm': _cmd_arm,
    'disarm': _cmd_disarm,
    'force_disarm': _cmd_force_disarm,
    'rtl': _cmd_rtl,
    'mode': _cmd_mode,
    'takeoff': _cmd_takeoff,
    'drop': _cmd_drop,
    'drop_stop': _cmd_drop_stop,
    'mission_start': _cmd_mission_start,
    'mission_clear': _cmd_mission_clear,
    'mission_upload': _cmd_mission_upload,
    'fence_upload': _cmd_fence_upload,
    'mission_download': _cmd_mission_download,
    'rally_upload': _cmd_rally_upload,
    'set_vtype': _cmd_set_vtype,
    'guided_goto': _cmd_guided_goto,
    'switch_vehicle': _cmd_switch_vehicle,
    'clear_summary': _cmd_clear_summary,
    'cal_compass': _cmd_cal_compass,
    'cal_accel': _cmd_cal_accel,
    'cal_gyro': _cmd_cal_gyro,
    'cal_level': _cmd_cal_level,
    'cal_baro': _cmd_cal_baro,
    'cal_cancel': _cmd_cal_cancel,
    'param_request_all': _cmd_param_request_all,
    'param_set': _cmd_param_set,
    'param_save': _cmd_param_save,
    'param_load': _cmd_param_load,
    'log_list': _cmd_log_list,
    'log_download': _cmd_log_download,
    'log_cancel': _cmd_log_cancel,
    'reboot': _cmd_reboot,
    'reboot_bootloader': _cmd_reboot_bootloader,
    'inspector_toggle': _cmd_inspector_toggle,
    'serial_control': _cmd_serial_control,
    'inject_rtcm': _cmd_inject_rtcm,
    'rc_override': _cmd_rc_override,
    'motor_test': _cmd_motor_test,
    'motor_test_stop': _cmd_motor_test_stop,
    'gimbal_angle': _cmd_gimbal_angle,
    'gimbal_rate': _cmd_gimbal_rate,
    'camera_trigger': _cmd_camera_trigger,
    'camera_video_start': _cmd_camera_video_start,
    'camera_video_stop': _cmd_camera_video_stop,
    'camera_zoom': _cmd_camera_zoom,
    'do_set_roi': _cmd_do_set_roi,
}


# --- MAVLink helpers (used by dispatch and external callers) ---


def _upload_mission(link: DroneLink, waypoints: list, takeoff_alt: float) -> None:
    items = []
    items.append({'seq': 0, 'cmd': 16, 'lat': 0, 'lon': 0, 'alt': 0, 'p1': 0, 'p2': 0})
    items.append({'seq': 1, 'cmd': 22, 'lat': 0, 'lon': 0, 'alt': takeoff_alt, 'p1': 0, 'p2': 0})
    seq = 2
    for wp in waypoints:
        spd = float(wp.get('speed', 0))
        if spd > 0:
            items.append({'seq': seq, 'cmd': 178, 'lat': 0, 'lon': 0, 'alt': 0, 'p1': 1, 'p2': spd})
            seq += 1
        wtype = wp.get('type', 'wp')
        if wtype == 'loiter_turns':
            nav_cmd = 18
            p1_val = float(wp.get('loiter_param', 3))
        elif wtype == 'loiter_time':
            nav_cmd = 19
            p1_val = float(wp.get('loiter_param', 10))
        elif wtype == 'spline':
            nav_cmd = 82
            p1_val = float(wp.get('delay', 0))
        else:
            nav_cmd = 16
            p1_val = float(wp.get('delay', 0))
        items.append({'seq': seq, 'cmd': nav_cmd, 'lat': wp['lat'], 'lon': wp['lon'],
                      'alt': float(wp.get('alt', takeoff_alt)), 'p1': p1_val, 'p2': 0})
        seq += 1
        if wp.get('drop'):
            items.append({'seq': seq, 'cmd': 181, 'lat': 0, 'lon': 0, 'alt': 0, 'p1': 0, 'p2': 0})
            seq += 1
    items.append({'seq': seq, 'cmd': 20, 'lat': 0, 'lon': 0, 'alt': 0, 'p1': 0, 'p2': 0})
    m = link.mission
    m._mission_items = items
    m._seq_to_wp = {}
    s2 = 2
    for i, wp in enumerate(waypoints):
        if float(wp.get('speed', 0)) > 0:
            s2 += 1
        m._seq_to_wp[s2] = i
        s2 += 1
        if wp.get('drop'):
            s2 += 1
    m._mission_pending = True
    _send_mission_count(link, len(items))
    drop_n = sum(1 for w in waypoints if w.get('drop'))
    link.add_event(lt('mission_upload', link.locale) % (len(waypoints), drop_n, takeoff_alt))


def _send_cmd(link: DroneLink, command: int, p1=0, p2=0, p3=0, p4=0, p5=0, p6=0, p7=0) -> None:
    payload = struct.pack('<fffffffHBBB', float(p1), float(p2), float(p3), float(p4),
                          float(p5), float(p6), float(p7), command, link.vehicle.sysid, 1, 0)
    link.send(bm(76, payload, link.sq, 152))


def _send_set_mode(link: DroneLink, mode: int) -> None:
    payload = struct.pack('<IBB', mode, link.vehicle.sysid, 0x01)
    link.send(bm(11, payload, link.sq, 89))


def _send_mission_count(link: DroneLink, count: int) -> None:
    link.send(bm(44, struct.pack('<HBB', count, link.vehicle.sysid, 1) + bytes([0]), link.sq, 221))


def _send_fence_count(link: DroneLink, count: int) -> None:
    link.send(bm(44, struct.pack('<HBB', count, link.vehicle.sysid, 1) + bytes([1]), link.sq, 221))


def send_fence_item_int(link: DroneLink, item: dict) -> None:
    lat7 = int(item.get('lat', 0) * 1e7)
    lon7 = int(item.get('lon', 0) * 1e7)
    p = struct.pack('<ffffiifHHBBBBBB',
                    float(item.get('p1', 0)), float(item.get('p2', 0)), 0.0, 0.0,
                    lat7, lon7, float(item.get('alt', 0)),
                    item['seq'], item['cmd'],
                    link.vehicle.sysid, 1, 3,
                    0, 1, 1)
    link.send(bm(73, p, link.sq, 38))


def send_mission_item_int(link: DroneLink, wp: dict) -> None:
    frame = 3 if wp['cmd'] in (16, 19, 21, 22, 82) else 2
    lat7 = int(wp.get('lat', 0) * 1e7)
    lon7 = int(wp.get('lon', 0) * 1e7)
    p = struct.pack('<ffffiifHHBBBBBB',
                    float(wp.get('p1', 0)), float(wp.get('p2', 0)), 0.0, 0.0,
                    lat7, lon7, float(wp.get('alt', 0)),
                    wp['seq'], wp['cmd'],
                    link.vehicle.sysid, 1, frame,
                    1 if wp['seq'] == 0 else 0, 1, 0)
    link.send(bm(73, p, link.sq, 38))


def _send_serial_control(link: DroneLink, text: str) -> None:
    data = (text + '\n').encode('ascii', 'replace')[:70]
    flags = 0x06
    p = struct.pack('<BBHB', 10, flags, 0, len(data))
    p += data + b'\x00' * (70 - len(data))
    link.send(bm(126, p, link.sq, 220))


def send_heartbeat(link: DroneLink) -> None:
    payload = struct.pack('<IBBBBB', 0, 6, 8, 0, 0, 3)
    link.send(bm(0, payload, link.sq, 50))


def _upload_rally(link: DroneLink, points: list) -> None:
    count = len(points)
    link.send(bm(44, struct.pack('<HBB', count, link.vehicle.sysid, 1) + bytes([2]), link.sq, 221))
    for i, pt in enumerate(points):
        lat7 = int(float(pt.get('lat', 0)) * 1e7)
        lon7 = int(float(pt.get('lon', 0)) * 1e7)
        alt = float(pt.get('alt', 100))
        p = struct.pack('<ffffiifHHBBBBBB',
                        0.0, 0.0, 0.0, 0.0, lat7, lon7, alt,
                        i, 5100, link.vehicle.sysid, 1, 3, 0, 2, 0)
        link.send(bm(73, p, link.sq, 38))
    link.add_event(lt('rally_uploaded', link.locale) % count, 'rally_uploaded')


def request_streams(link: DroneLink) -> None:
    streams = [
        (30, 250000), (33, 250000), (24, 250000),
        (1, 1000000), (42, 1000000),
        (36, 500000), (65, 500000), (241, 1000000),
        (74, 1000000),
    ]
    for mid, interval in streams:
        payload = struct.pack('<fffffffHBBB',
                              float(mid), float(interval), 0, 0, 0, 0, 0,
                              511, link.vehicle.sysid, 1, 0)
        link.send(bm(76, payload, link.sq, 152))
        time.sleep(cfg.STREAM_REQUEST_SPACING)
    _send_cmd(link, 512, p1=148.0)
