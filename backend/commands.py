from __future__ import annotations
import struct
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .drone_link import DroneLink


def execute(cmd: str, param, link: DroneLink, data: dict | None = None) -> dict | None:
    data = data or {}
    if cmd == 'arm':
        link.add_event('发送解锁...')
        _send_cmd(link, 400, p1=1.0)
    elif cmd == 'disarm':
        link.add_event('发送锁定...')
        _send_cmd(link, 400, p1=0)
    elif cmd == 'force_disarm':
        link.add_event('强制锁定')
        _send_cmd(link, 400, p1=0, p2=21196)
    elif cmd == 'rtl':
        rm = 21 if link.is_plane() else 6
        link.add_event('!!! 返航 (模式 %d) !!!' % rm)
        _send_set_mode(link, rm)
    elif cmd == 'mode' and param is not None:
        from .constants import PLANE_MODES, COPTER_MODES
        md = PLANE_MODES if link.is_plane() else COPTER_MODES
        link.add_event('模式 -> %s' % md.get(int(param), str(param)))
        _send_set_mode(link, int(param))
    elif cmd == 'takeoff':
        alt = float(data.get('alt', 30))
        link.add_event('起飞至 %.0fm' % alt)
        _send_cmd(link, 22, p7=alt)
    elif cmd == 'drop':
        link.add_event('投放: 继电器 OFF')
        _send_cmd(link, 181, p1=0, p2=0)
    elif cmd == 'drop_stop':
        link.add_event('投放停止: 继电器 ON')
        _send_cmd(link, 181, p1=0, p2=1)
    elif cmd == 'mission_start':
        am = 10 if link.is_plane() else 3
        link.add_event('任务开始')
        _send_set_mode(link, am)
        threading.Thread(target=lambda: (time.sleep(0.3), _send_cmd(link, 300)), daemon=True).start()
    elif cmd == 'mission_clear':
        from pllink_proto import bm
        link.send(bm(45, bytes([link.sysid, 1, 0]), link.sq, 232))
        link.add_event('任务已清除')
    elif cmd == 'mission_upload':
        wps = data.get('waypoints', [])
        takeoff_alt = float(data.get('takeoff_alt', 30))
        if not wps:
            return {'ok': False, 'error': '无航点'}
        for wp in wps:
            if abs(wp.get('lat', 0)) < 0.001:
                return {'ok': False, 'error': '坐标无效'}
        _upload_mission(link, wps, takeoff_alt)
    elif cmd == 'set_vtype':
        v = data.get('vtype', 'auto')
        link.force_plane = True if v == 'plane' else (False if v == 'copter' else None)
        link.add_event('机型: %s' % {'plane': '固定翼', 'copter': '多旋翼', 'auto': '自动'}.get(v, v))
    elif cmd == 'guided_goto':
        lat7 = int(float(data.get('lat', 0)) * 1e7)
        lon7 = int(float(data.get('lon', 0)) * 1e7)
        alt = float(data.get('alt', 30))
        gm = 15 if link.is_plane() else 4
        _send_set_mode(link, gm)
        link.add_event('引导飞往 %.5f, %.5f @ %.0fm' % (lat7 / 1e7, lon7 / 1e7, alt))
        from pllink_proto import bm
        p = struct.pack('<IiifffffffffHBBB',
                        0, lat7, lon7, alt, 0, 0, 0, 0, 0, 0, 0, 0,
                        0x0FF8, link.sysid, 1, 6)
        link.send(bm(84, p, link.sq, 5))
    elif cmd == 'clear_summary':
        link.flight_summary = None
    elif cmd == 'mission_download':
        link._dl_pending = True
        link._dl_total = 0
        link._dl_items = []
        link.add_event('任务: 正在下载...')
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
    link.add_event('任务: %d 航点, %d 投放, 高度 %.0fm' % (len(waypoints), drop_n, takeoff_alt))


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


def send_mission_item_int(link: DroneLink, wp: dict) -> None:
    from pllink_proto import bm
    frame = 3 if wp['cmd'] in (16, 19, 21, 22) else 2
    lat7 = int(wp.get('lat', 0) * 1e7)
    lon7 = int(wp.get('lon', 0) * 1e7)
    p = struct.pack('<ffffiifHHBBBBBB',
                    float(wp.get('p1', 0)), float(wp.get('p2', 0)), 0.0, 0.0,
                    lat7, lon7, float(wp.get('alt', 0)),
                    wp['seq'], wp['cmd'],
                    link.sysid, 1, frame,
                    1 if wp['seq'] == 0 else 0, 1, 0)
    link.send(bm(73, p, link.sq, 38))


def send_heartbeat(link: DroneLink) -> None:
    from pllink_proto import bm
    payload = struct.pack('<IBBBBB', 0, 6, 8, 0, 0, 3)
    link.send(bm(0, payload, link.sq, 50))


def request_streams(link: DroneLink) -> None:
    from pllink_proto import bm
    streams = [
        (30, 250000), (33, 250000), (24, 250000),
        (1, 1000000), (42, 1000000),
        (36, 500000), (65, 500000), (241, 1000000),
    ]
    for mid, interval in streams:
        payload = struct.pack('<fffffffHBBB',
                              float(mid), float(interval), 0, 0, 0, 0, 0,
                              511, link.sysid, 1, 0)
        link.send(bm(76, payload, link.sq, 152))
        time.sleep(0.01)
    _send_cmd(link, 512, p1=148.0)
