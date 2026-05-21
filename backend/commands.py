from __future__ import annotations
import struct
import threading
import time
from typing import TYPE_CHECKING

from .config import cfg
from .locale_text import lt

if TYPE_CHECKING:
    from .drone_link import DroneLink


def execute(cmd: str, param, link: DroneLink, data: dict | None = None) -> dict | None:
    data = data or {}
    if cmd == 'arm':
        link.add_event(lt('arm_send', link.locale), 'arm_send')
        _send_cmd(link, 400, p1=1.0)
    elif cmd == 'disarm':
        link.add_event(lt('disarm_send', link.locale), 'disarm_send')
        _send_cmd(link, 400, p1=0)
    elif cmd == 'force_disarm':
        link.add_event(lt('force_disarm', link.locale), 'force_disarm')
        _send_cmd(link, 400, p1=0, p2=21196)
    elif cmd == 'rtl':
        rm = 21 if link.is_plane() else 6
        link.add_event(lt('rtl', link.locale) % rm, 'rtl')
        _send_set_mode(link, rm)
    elif cmd == 'mode' and param is not None:
        from .constants import PLANE_MODES, COPTER_MODES
        md = PLANE_MODES if link.is_plane() else COPTER_MODES
        link.add_event(lt('mode_to', link.locale) % md.get(int(param), str(param)), 'mode_to')
        _send_set_mode(link, int(param))
    elif cmd == 'takeoff':
        alt = float(data.get('alt', 30))
        link.add_event(lt('takeoff', link.locale) % alt, 'takeoff')
        _send_cmd(link, 22, p7=alt)
    elif cmd == 'drop':
        link.add_event(lt('drop_on', link.locale), 'drop_on')
        _send_cmd(link, 181, p1=0, p2=0)
    elif cmd == 'drop_stop':
        link.add_event(lt('drop_off', link.locale), 'drop_off')
        _send_cmd(link, 181, p1=0, p2=1)
    elif cmd == 'mission_start':
        am = 10 if link.is_plane() else 3
        link.add_event(lt('mission_start', link.locale), 'mission_start')
        _send_set_mode(link, am)
        threading.Thread(target=lambda: (time.sleep(cfg.MISSION_START_DELAY), _send_cmd(link, 300)), daemon=True).start()
    elif cmd == 'mission_clear':
        from pllink_proto import bm
        link.send(bm(45, bytes([link.sysid, 1, 0]), link.sq, 232))
        link.add_event(lt('mission_clear', link.locale), 'mission_clear')
    elif cmd == 'mission_upload':
        wps = data.get('waypoints', [])
        takeoff_alt = float(data.get('takeoff_alt', 30))
        if not wps:
            return {'ok': False, 'error': lt('err_no_wp', link.locale)}
        for wp in wps:
            if abs(wp.get('lat', 0)) < 0.001:
                return {'ok': False, 'error': lt('err_bad_coord', link.locale)}
        _upload_mission(link, wps, takeoff_alt)
    elif cmd == 'fence_upload':
        polygon = data.get('polygon', [])
        if len(polygon) < 3:
            return {'ok': False, 'error': lt('err_fence_min', link.locale)}
        items = []
        for i, pt in enumerate(polygon):
            items.append({
                'seq': i, 'cmd': 5001, 'lat': pt['lat'], 'lon': pt['lon'],
                'alt': 0, 'p1': len(polygon), 'p2': 0,
            })
        link._fence_items = items
        link._fence_pending = True
        _send_fence_count(link, len(items))
        link.add_event(lt('fence_upload', link.locale) % len(polygon), 'fence_upload')
    elif cmd == 'set_vtype':
        v = data.get('vtype', 'auto')
        link.force_plane = True if v == 'plane' else (False if v == 'copter' else None)
        vname = lt('vtype_plane' if v == 'plane' else 'vtype_copter' if v == 'copter' else 'vtype_auto', link.locale)
        link.add_event(lt('vtype_set', link.locale) % vname, 'vtype_set')
    elif cmd == 'guided_goto':
        lat7 = int(float(data.get('lat', 0)) * 1e7)
        lon7 = int(float(data.get('lon', 0)) * 1e7)
        alt = float(data.get('alt', 30))
        gm = 15 if link.is_plane() else 4
        _send_set_mode(link, gm)
        link.add_event(lt('guided', link.locale) % (lat7 / 1e7, lon7 / 1e7, alt), 'guided')
        from pllink_proto import bm
        p = struct.pack('<IiifffffffffHBBB',
                        0, lat7, lon7, alt, 0, 0, 0, 0, 0, 0, 0, 0,
                        0x0FF8, link.sysid, 1, 6)
        link.send(bm(84, p, link.sq, 5))
    elif cmd == 'cal_compass':
        link.add_event(lt('cal_compass', link.locale), 'cal_compass')
        _send_cmd(link, 241, p2=1)
    elif cmd == 'cal_accel':
        link.add_event(lt('cal_accel', link.locale), 'cal_accel')
        _send_cmd(link, 241, p5=1)
    elif cmd == 'cal_gyro':
        link.add_event(lt('cal_gyro', link.locale), 'cal_gyro')
        _send_cmd(link, 241, p1=1)
    elif cmd == 'cal_level':
        link.add_event(lt('cal_level', link.locale), 'cal_level')
        _send_cmd(link, 241, p5=4)
    elif cmd == 'cal_baro':
        link.add_event(lt('cal_baro', link.locale), 'cal_baro')
        _send_cmd(link, 241, p3=1)
    elif cmd == 'cal_cancel':
        link.add_event(lt('cal_cancel', link.locale), 'cal_cancel')
        _send_cmd(link, 241)
    elif cmd == 'clear_summary':
        link.flight_summary = None
    elif cmd == 'mission_download':
        link._dl_pending = True
        link._dl_total = 0
        link._dl_items = []
        link.add_event(lt('mission_dl', link.locale), 'mission_dl')
        from pllink_proto import bm
        link.send(bm(43, struct.pack('<BBB', link.sysid, 1, 0), link.sq, 132))
    elif cmd == 'param_request_all':
        link.param_mgr.request_all()
    elif cmd == 'param_set':
        name = data.get('name', '')
        value = float(data.get('value', 0))
        if name:
            link.param_mgr.set_param(name, value)
    elif cmd == 'param_save':
        path = link.param_mgr.save_to_file()
        return {'ok': True, 'path': path}
    elif cmd == 'param_load':
        path = data.get('path', '')
        if path:
            changed = link.param_mgr.load_from_file(path)
            return {'ok': True, 'changed': changed}
    elif cmd == 'log_list':
        from pllink_proto import bm
        link._log_list = []
        link.send(bm(117, struct.pack('<HHBB', 0, 0xFFFF, link.sysid, 1), link.sq, 128))
        link.add_event(lt('log_list_req', link.locale), 'log_list_req')
    elif cmd == 'log_download':
        log_id = int(data.get('id', 0))
        log_entry = next((l for l in link._log_list if l['id'] == log_id), None)
        if not log_entry:
            return {'ok': False, 'error': lt('err_log_not_found', link.locale)}
        link._log_download_id = log_id
        link._log_download_size = log_entry['size']
        link._log_download_data = bytearray(log_entry['size'])
        link._log_download_ofs = 0
        link.add_event(lt('log_dl', link.locale) % (log_id, log_entry['size'] // 1024), 'log_dl')
        from pllink_proto import bm
        chunk = min(90 * 50, log_entry['size'])
        link.send(bm(119, struct.pack('<IIHBB', 0, chunk, log_id, link.sysid, 1), link.sq, 116))
    elif cmd == 'log_cancel':
        from pllink_proto import bm
        link.send(bm(126, struct.pack('<BB', link.sysid, 1), link.sq, 203))
        link._log_download_id = -1
        link.add_event(lt('log_dl_cancel', link.locale), 'log_dl_cancel')
    elif cmd == 'reboot_bootloader':
        link.add_event(lt('reboot_bl', link.locale), 'reboot_bl')
        _send_cmd(link, 246, p1=3)
    elif cmd == 'reboot':
        link.add_event(lt('reboot', link.locale), 'reboot')
        _send_cmd(link, 246, p1=1)
    elif cmd == 'rc_override':
        channels = data.get('channels', [])
        if len(channels) >= 8:
            from pllink_proto import bm
            p = struct.pack('<BB', link.sysid, 1)
            for i in range(8):
                p += struct.pack('<H', max(0, min(65535, int(channels[i]))))
            link.send(bm(70, p, link.sq, 124))
    elif cmd == 'motor_test':
        motor = int(data.get('motor', 0))
        throttle = float(data.get('throttle', 5))
        duration = float(data.get('duration', 2))
        link.add_event(lt('motor_test', link.locale) % (motor + 1, throttle), 'motor_test')
        _send_cmd(link, 209, p1=float(motor), p2=0, p3=throttle, p4=duration, p5=1)
    elif cmd == 'motor_test_stop':
        for i in range(8):
            _send_cmd(link, 209, p1=float(i), p2=0, p3=0, p4=0, p5=1)
    elif cmd == 'serial_control':
        text = data.get('text', '')
        if text:
            _send_serial_control(link, text)
    elif cmd == 'inspector_toggle':
        link.inspector_enabled = not link.inspector_enabled
    elif cmd == 'switch_vehicle':
        new_sysid = int(data.get('sysid', 1))
        link.active_sysid = new_sysid
        link.sysid = new_sysid
        link.add_event(lt('vehicle_switch', link.locale) % new_sysid, 'vehicle_switch')
    elif cmd == 'rally_upload':
        points = data.get('points', [])
        if points:
            _upload_rally(link, points)
    return None


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
    link._mission_items = items
    link._seq_to_wp = {}
    s2 = 2
    for i, wp in enumerate(waypoints):
        if float(wp.get('speed', 0)) > 0:
            s2 += 1
        link._seq_to_wp[s2] = i
        s2 += 1
        if wp.get('drop'):
            s2 += 1
    link._mission_pending = True
    _send_mission_count(link, len(items))
    drop_n = sum(1 for w in waypoints if w.get('drop'))
    link.add_event(lt('mission_upload', link.locale) % (len(waypoints), drop_n, takeoff_alt))


def _send_cmd(link: DroneLink, command: int, p1=0, p2=0, p3=0, p4=0, p5=0, p6=0, p7=0) -> None:
    from pllink_proto import bm
    payload = struct.pack('<fffffffHBBB', float(p1), float(p2), float(p3), float(p4),
                          float(p5), float(p6), float(p7), command, link.sysid, 1, 0)
    link.send(bm(76, payload, link.sq, 152))


def _send_set_mode(link: DroneLink, mode: int) -> None:
    from pllink_proto import bm
    payload = struct.pack('<IBB', mode, link.sysid, 0x01)
    link.send(bm(11, payload, link.sq, 89))


def _send_mission_count(link: DroneLink, count: int) -> None:
    from pllink_proto import bm
    link.send(bm(44, struct.pack('<HBB', count, link.sysid, 1) + bytes([0]), link.sq, 221))


def _send_fence_count(link: DroneLink, count: int) -> None:
    from pllink_proto import bm
    link.send(bm(44, struct.pack('<HBB', count, link.sysid, 1) + bytes([1]), link.sq, 221))


def send_fence_item_int(link: DroneLink, item: dict) -> None:
    from pllink_proto import bm
    lat7 = int(item.get('lat', 0) * 1e7)
    lon7 = int(item.get('lon', 0) * 1e7)
    p = struct.pack('<ffffiifHHBBBBBB',
                    float(item.get('p1', 0)), float(item.get('p2', 0)), 0.0, 0.0,
                    lat7, lon7, float(item.get('alt', 0)),
                    item['seq'], item['cmd'],
                    link.sysid, 1, 3,
                    0, 1, 1)
    link.send(bm(73, p, link.sq, 38))


def send_mission_item_int(link: DroneLink, wp: dict) -> None:
    from pllink_proto import bm
    frame = 3 if wp['cmd'] in (16, 19, 21, 22, 82) else 2
    lat7 = int(wp.get('lat', 0) * 1e7)
    lon7 = int(wp.get('lon', 0) * 1e7)
    p = struct.pack('<ffffiifHHBBBBBB',
                    float(wp.get('p1', 0)), float(wp.get('p2', 0)), 0.0, 0.0,
                    lat7, lon7, float(wp.get('alt', 0)),
                    wp['seq'], wp['cmd'],
                    link.sysid, 1, frame,
                    1 if wp['seq'] == 0 else 0, 1, 0)
    link.send(bm(73, p, link.sq, 38))


def _send_serial_control(link: DroneLink, text: str) -> None:
    from pllink_proto import bm
    data = (text + '\n').encode('ascii', 'replace')[:70]
    flags = 0x06
    p = struct.pack('<BBHB', 10, flags, 0, len(data))
    p += data + b'\x00' * (70 - len(data))
    link.send(bm(126, p, link.sq, 220))


def send_heartbeat(link: DroneLink) -> None:
    from pllink_proto import bm
    payload = struct.pack('<IBBBBB', 0, 6, 8, 0, 0, 3)
    link.send(bm(0, payload, link.sq, 50))


def _upload_rally(link: DroneLink, points: list) -> None:
    from pllink_proto import bm
    count = len(points)
    link.send(bm(44, struct.pack('<HBB', count, link.sysid, 1) + bytes([2]), link.sq, 221))
    for i, pt in enumerate(points):
        lat7 = int(float(pt.get('lat', 0)) * 1e7)
        lon7 = int(float(pt.get('lon', 0)) * 1e7)
        alt = float(pt.get('alt', 100))
        p = struct.pack('<ffffiifHHBBBBBB',
                        0.0, 0.0, 0.0, 0.0, lat7, lon7, alt,
                        i, 5100, link.sysid, 1, 3, 0, 2, 0)
        link.send(bm(73, p, link.sq, 38))
    link.add_event(lt('rally_uploaded', link.locale) % count, 'rally_uploaded')


def request_streams(link: DroneLink) -> None:
    from pllink_proto import bm
    streams = [
        (30, 250000), (33, 250000), (24, 250000),
        (1, 1000000), (42, 1000000),
        (36, 500000), (65, 500000), (241, 1000000),
        (74, 1000000),
    ]
    for mid, interval in streams:
        payload = struct.pack('<fffffffHBBB',
                              float(mid), float(interval), 0, 0, 0, 0, 0,
                              511, link.sysid, 1, 0)
        link.send(bm(76, payload, link.sq, 152))
        time.sleep(cfg.STREAM_REQUEST_SPACING)
    _send_cmd(link, 512, p1=148.0)
