from __future__ import annotations
import struct
import math
import time
from typing import TYPE_CHECKING

from . import mavlink_dispatch
from .statustext_filter import filter_statustext
from .constants import PLANE_MODES, COPTER_MODES

if TYPE_CHECKING:
    from .drone_link import DroneLink


def handle_heartbeat(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 7:
        return
    link.mode = p[0] | (p[1] << 8) | (p[2] << 16) | (p[3] << 24)
    old_vtype = link.vtype_raw
    link.vtype_raw = p[4]
    if old_vtype != link.vtype_raw and link.vtype_raw > 0:
        link.add_event('机型: %s' % ('固定翼' if link.is_plane() else '多旋翼'))
    new_armed = bool(p[6] & 0x80)
    if new_armed != link.armed:
        link.add_event('已解锁' if new_armed else '已锁定')
        if new_armed:
            link.armed_time = time.time()
            link.max_alt = link.max_speed = link.total_dist = 0
            link._prev_pos = None
            link._bat_history = []
            link._bat_start_pct = link.remaining
        else:
            dur = int(time.time() - link.armed_time) if link.armed_time else 0
            bat_used = (link._bat_start_pct - link.remaining) if link._bat_start_pct >= 0 and link.remaining >= 0 else -1
            link.flight_summary = {
                'duration': dur, 'max_alt': round(link.max_alt, 1),
                'max_speed': round(link.max_speed, 1), 'total_dist': round(link.total_dist),
                'bat_used': bat_used,
            }
            link.bat_time_remaining = -1
    link.armed = new_armed
    link.sysid = link._raw_sysid
    if not link.connected:
        link.connected = True
        link.add_event('已连接 (sysid=%d)' % link.sysid)


def handle_attitude(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 16:
        return
    link.roll = struct.unpack_from('<f', p, 4)[0] * 57.2958
    link.pitch = struct.unpack_from('<f', p, 8)[0] * 57.2958
    link.yaw = struct.unpack_from('<f', p, 12)[0] * 57.2958
    if link.yaw < 0:
        link.yaw += 360


def handle_global_position_int(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 20:
        return
    link.lat = struct.unpack_from('<i', p, 4)[0] / 1e7
    link.lon = struct.unpack_from('<i', p, 8)[0] / 1e7
    link.alt_msl = struct.unpack_from('<i', p, 12)[0] / 1000.0
    link.alt_rel = struct.unpack_from('<i', p, 16)[0] / 1000.0
    if pl >= 22:
        link.vx = struct.unpack_from('<h', p, 20)[0] / 100.0
    if pl >= 24:
        link.vy = struct.unpack_from('<h', p, 22)[0] / 100.0
    if pl >= 26:
        link.vz = struct.unpack_from('<h', p, 24)[0] / 100.0
    link.gs = (link.vx ** 2 + link.vy ** 2) ** 0.5
    if pl >= 28:
        link.hdg = struct.unpack_from('<H', p, 26)[0] / 100.0
    if link.home_lat == 0 and link.home_lon == 0 and abs(link.lat) > 0.001:
        link.home_lat = link.lat
        link.home_lon = link.lon
        link.add_event('起飞点: %.5f, %.5f' % (link.lat, link.lon))
    if link.home_lat != 0:
        dlat = (link.lat - link.home_lat) * 111320
        dlon = (link.lon - link.home_lon) * 111320 * math.cos(math.radians(link.lat))
        link.dist_home = (dlat ** 2 + dlon ** 2) ** 0.5
    if link.armed:
        if link.alt_rel > link.max_alt:
            link.max_alt = link.alt_rel
        if link.gs > link.max_speed:
            link.max_speed = link.gs
        if link._prev_pos:
            dp = ((link.lat - link._prev_pos[0]) * 111320) ** 2 + \
                 ((link.lon - link._prev_pos[1]) * 111320 * math.cos(math.radians(link.lat))) ** 2
            link.total_dist += dp ** 0.5
        link._prev_pos = (link.lat, link.lon)


def handle_sys_status(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 16:
        return
    link.voltage = (p[14] | (p[15] << 8)) / 1000.0
    if pl >= 18:
        link.current = struct.unpack_from('<h', p, 16)[0] / 100.0
    if pl > 30:
        link.remaining = struct.unpack_from('<b', p, 30)[0]
    if link.remaining >= 0 and link.armed:
        now = time.time()
        link._bat_history.append((now, link.remaining))
        link._bat_history = [(t, r) for t, r in link._bat_history if now - t < 120]
        if len(link._bat_history) >= 2:
            dt = link._bat_history[-1][0] - link._bat_history[0][0]
            dr = link._bat_history[0][1] - link._bat_history[-1][1]
            if dt > 10 and dr > 0:
                link.bat_time_remaining = int(link.remaining / (dr / dt))


def handle_gps_raw_int(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 29:
        return
    link.gps_fix = p[28]
    link.gps_sats = p[29] if pl > 29 else 0


def handle_mission_current(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 2:
        return
    link.wp_seq = p[0] | (p[1] << 8)


def handle_home_position(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 20:
        return
    hlat = struct.unpack_from('<i', p, 0)[0] / 1e7
    hlon = struct.unpack_from('<i', p, 4)[0] / 1e7
    if abs(hlat) > 0.001:
        link.home_lat = hlat
        link.home_lon = hlon


def handle_mission_item_reached(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 2:
        return
    seq = p[0] | (p[1] << 8)
    link.add_event('航点 %d 已到达' % seq)


def handle_command_ack(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 3:
        return
    link.add_event('指令应答: %s' % ('成功' if p[2] == 0 else '失败(%d)' % p[2]))


def handle_statustext(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 2:
        return
    text = bytes(p[1:51]).split(b'\x00')[0].decode('ascii', 'replace').strip()
    if text:
        text = filter_statustext(text)
        link.add_event('飞控: %s' % text)


def handle_param_value(p: bytes, pl: int, link: DroneLink) -> None:
    link.param_mgr.handle_param_value(p, pl)


def handle_mission_request(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 2 or not link._mission_pending:
        return
    from . import commands as cmd_mod
    seq = p[0] | (p[1] << 8)
    if seq < len(link._mission_items):
        cmd_mod.send_mission_item_int(link, link._mission_items[seq])


def handle_mission_ack(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 3:
        return
    if link._mission_pending:
        mtype = p[2]
        link._mission_pending = False
        link.add_event('任务确认: %s' % ('成功' if mtype == 0 else '失败(%d)' % mtype))


def init_handlers() -> None:
    mavlink_dispatch.register(0, handle_heartbeat)
    mavlink_dispatch.register(30, handle_attitude)
    mavlink_dispatch.register(33, handle_global_position_int)
    mavlink_dispatch.register(1, handle_sys_status)
    mavlink_dispatch.register(24, handle_gps_raw_int)
    mavlink_dispatch.register(42, handle_mission_current)
    mavlink_dispatch.register(242, handle_home_position)
    mavlink_dispatch.register(46, handle_mission_item_reached)
    mavlink_dispatch.register(77, handle_command_ack)
    mavlink_dispatch.register(253, handle_statustext)
    mavlink_dispatch.register(22, handle_param_value)
    mavlink_dispatch.register(40, handle_mission_request)
    mavlink_dispatch.register(51, handle_mission_request)
    mavlink_dispatch.register(47, handle_mission_ack)
