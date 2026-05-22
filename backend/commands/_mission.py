from __future__ import annotations

import struct
import threading
import time
from typing import TYPE_CHECKING

from ..config import cfg
from ..locale_text import lt
from ..pllink_proto import bm
from ._helpers import send_cmd, send_fence_count, send_mission_count, send_set_mode

if TYPE_CHECKING:
    from ..drone_link import DroneLink

_mission_timer: threading.Timer | None = None
_timer_lock = threading.Lock()


def cmd_mission_start(link: DroneLink, param, data: dict):
    global _mission_timer
    am = 10 if link.is_plane() else 3
    link.add_event(lt('mission_start', link.locale), 'mission_start')
    send_set_mode(link, am)

    def _delayed():
        try:
            send_cmd(link, 300)
        except OSError:
            link.add_event('Mission start command failed', 'cmd_ack_fail')

    with _timer_lock:
        if _mission_timer:
            _mission_timer.cancel()
        _mission_timer = threading.Timer(cfg.MISSION_START_DELAY, _delayed)
        _mission_timer.daemon = True
        _mission_timer.start()


def cmd_mission_clear(link: DroneLink, param, data: dict):
    link.send(bm(45, bytes([link.vehicle.sysid, 1, 0]), link.sq, 232))
    link.add_event(lt('mission_clear', link.locale), 'mission_clear')


def cmd_mission_upload(link: DroneLink, param, data: dict):
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


def cmd_fence_upload(link: DroneLink, param, data: dict):
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
    send_fence_count(link, len(items))
    link.add_event(lt('fence_upload', link.locale) % len(polygon), 'fence_upload')


def cmd_mission_download(link: DroneLink, param, data: dict):
    link.mission._dl_pending = True
    link.mission._dl_total = 0
    link.mission._dl_items = []
    link.mission._dl_start_time = time.time()
    link.add_event(lt('mission_dl', link.locale), 'mission_dl')
    link.send(bm(43, struct.pack('<BBB', link.vehicle.sysid, 1, 0), link.sq, 132))


def check_mission_dl_timeout(link: DroneLink) -> None:
    m = link.mission
    if m._dl_pending and m._dl_start_time > 0:
        if time.time() - m._dl_start_time > cfg.MISSION_DL_TIMEOUT:
            m._dl_pending = False
            m._dl_start_time = 0.0
            link.add_event(lt('mission_dl_timeout', link.locale), 'mission_dl_timeout')


def cmd_rally_upload(link: DroneLink, param, data: dict):
    points = data.get('points', [])
    if points:
        _upload_rally(link, points)


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
    send_mission_count(link, len(items))
    drop_n = sum(1 for w in waypoints if w.get('drop'))
    link.add_event(lt('mission_upload', link.locale) % (len(waypoints), drop_n, takeoff_alt))


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
