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
        try:
            lat, lon = float(wp.get('lat', 0)), float(wp.get('lon', 0))
        except (TypeError, ValueError):
            return {'ok': False, 'error': lt('err_bad_coord', link.locale)}
        if abs(lat) < 0.001 or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return {'ok': False, 'error': lt('err_bad_coord', link.locale)}
        try:
            alt = float(wp.get('alt', 0))
        except (TypeError, ValueError):
            return {'ok': False, 'error': lt('err_bad_coord', link.locale)}
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
        items.append({'seq': seq, 'cmd': nav_cmd, 'lat': float(wp['lat']), 'lon': float(wp['lon']),
                      'alt': float(wp.get('alt', takeoff_alt)), 'p1': p1_val, 'p2': 0})
        seq += 1
        servo = wp.get('cmd_servo')
        if servo:
            items.append({'seq': seq, 'cmd': 183, 'lat': 0, 'lon': 0, 'alt': 0,
                          'p1': int(servo.get('num', 1)), 'p2': float(servo.get('pwm', 1500))})
            seq += 1
        roi = wp.get('cmd_roi')
        if roi:
            items.append({'seq': seq, 'cmd': 201, 'lat': float(roi.get('lat', 0)),
                          'lon': float(roi.get('lon', 0)), 'alt': float(roi.get('alt', 0)),
                          'p1': 0, 'p2': 0})
            seq += 1
        cam = wp.get('cmd_cam_trig')
        if cam:
            items.append({'seq': seq, 'cmd': 206, 'lat': 0, 'lon': 0, 'alt': 0,
                          'p1': float(cam.get('dist', 0)), 'p2': 0})
            seq += 1
        yaw = wp.get('cmd_yaw')
        if yaw:
            items.append({'seq': seq, 'cmd': 115, 'lat': 0, 'lon': 0, 'alt': 0,
                          'p1': float(yaw.get('deg', 0)), 'p2': 0,
                          'p3': float(yaw.get('dir', 1)), 'p4': 0})
            seq += 1
        vtol = wp.get('cmd_vtol')
        if vtol:
            items.append({'seq': seq, 'cmd': 3000, 'lat': 0, 'lon': 0, 'alt': 0,
                          'p1': int(vtol.get('mode', 4)), 'p2': 0})
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
        if wp.get('cmd_servo'):
            s2 += 1
        if wp.get('cmd_roi'):
            s2 += 1
        if wp.get('cmd_cam_trig'):
            s2 += 1
        if wp.get('cmd_yaw'):
            s2 += 1
        if wp.get('cmd_vtol'):
            s2 += 1
        if wp.get('drop'):
            s2 += 1
    m._mission_pending = True
    send_mission_count(link, len(items))
    drop_n = sum(1 for w in waypoints if w.get('drop'))
    link.add_event(lt('mission_upload', link.locale) % (len(waypoints), drop_n, takeoff_alt))


def _upload_rally(link: DroneLink, points: list) -> None:
    # AP_Mission requires the GCS to follow the proper request/response
    # handshake: COUNT -> wait for REQUEST -> ITEM -> ... -> ACK. The previous
    # implementation blasted all items immediately after COUNT, which AP
    # rejected as MAV_MISSION_INVALID_SEQUENCE. Stash items on the link and
    # let handle_mission_request stream them out one at a time.
    items: list[dict] = []
    for i, pt in enumerate(points):
        items.append({
            'seq': i,
            'cmd': 5100,             # MAV_CMD_NAV_RALLY_POINT
            'lat': float(pt.get('lat', 0)),
            'lon': float(pt.get('lon', 0)),
            'alt': float(pt.get('alt', 100)),
            'p1': 0, 'p2': 0,
        })
    m = link.mission
    m._rally_items = items
    m._rally_pending = True
    count = len(items)
    link.send(bm(44, struct.pack('<HBB', count, link.vehicle.sysid, 1) + bytes([2]), link.sq, 221))
    link.add_event(lt('rally_uploaded', link.locale) % count, 'rally_uploaded')
