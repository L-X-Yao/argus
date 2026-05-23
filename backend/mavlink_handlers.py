from __future__ import annotations

import math
import struct
import time
from typing import TYPE_CHECKING

from . import mavlink_dispatch
from .locale_text import lt
from .statustext_filter import filter_statustext

if TYPE_CHECKING:
    from .drone_link import DroneLink


def _pad(p: bytes, n: int) -> bytes:
    """Return p zero-padded to at least n bytes.

    MAVLink 2 senders may zero-trim trailing zero bytes from a payload to save
    bandwidth; receivers are required to treat the trimmed bytes as zero. Our
    handlers read named fields by offset and would either crash on a short
    buffer or return early on a strict `pl < N` check. Calling `_pad` before
    unpacking lets each handler read at any offset up to n without worrying
    about the wire-level truncation. `pl` still reflects the original size, so
    conditional reads on extension fields remain correct.
    """
    return p if len(p) >= n else p + b'\x00' * (n - len(p))


def handle_heartbeat(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 9)
    v = link.vehicle
    v.mode = p[0] | (p[1] << 8) | (p[2] << 16) | (p[3] << 24)
    old_vtype = v.vtype_raw
    v.vtype_raw = p[4]
    if old_vtype != v.vtype_raw and v.vtype_raw > 0:
        link.add_event(lt('vehicle_type', link.locale) % link._get_vehicle_info()[2], 'vehicle_type')
    new_armed = bool(p[6] & 0x80)
    if new_armed != v.armed:
        link.add_event(lt('armed', link.locale) if new_armed else lt('disarmed', link.locale),
                       'armed' if new_armed else 'disarmed')
        if new_armed:
            v.armed_time = time.time()
            v.max_alt = v.max_speed = v.total_dist = 0
            link.attitude._prev_pos = None
            link.battery._bat_history = []
            link.battery._bat_start_pct = link.battery.remaining
        else:
            dur = int(time.time() - v.armed_time) if v.armed_time else 0
            bat = link.battery
            bat_used = (bat._bat_start_pct - bat.remaining) if bat._bat_start_pct >= 0 and bat.remaining >= 0 else -1
            v.flight_summary = {
                'duration': dur, 'max_alt': round(v.max_alt, 1),
                'max_speed': round(v.max_speed, 1), 'total_dist': round(v.total_dist),
                'bat_used': bat_used,
            }
            bat.bat_time_remaining = -1
    v.armed = new_armed
    v.sysid = link._raw_sysid
    if not link.connected:
        link.connected = True
        link.add_event(lt('connected', link.locale) % v.sysid, 'connected')


def handle_attitude(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 16)
    a = link.attitude
    a.roll = struct.unpack_from('<f', p, 4)[0] * 57.2958
    a.pitch = struct.unpack_from('<f', p, 8)[0] * 57.2958
    a.yaw = struct.unpack_from('<f', p, 12)[0] * 57.2958
    if a.yaw < 0:
        a.yaw += 360


def handle_global_position_int(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 28)
    a = link.attitude
    a.lat = struct.unpack_from('<i', p, 4)[0] / 1e7
    a.lon = struct.unpack_from('<i', p, 8)[0] / 1e7
    a.alt_msl = struct.unpack_from('<i', p, 12)[0] / 1000.0
    a.alt_rel = struct.unpack_from('<i', p, 16)[0] / 1000.0
    if pl >= 22:
        a.vx = struct.unpack_from('<h', p, 20)[0] / 100.0
    if pl >= 24:
        a.vy = struct.unpack_from('<h', p, 22)[0] / 100.0
    if pl >= 26:
        a.vz = struct.unpack_from('<h', p, 24)[0] / 100.0
    a.gs = (a.vx ** 2 + a.vy ** 2) ** 0.5
    if pl >= 28:
        a.hdg = struct.unpack_from('<H', p, 26)[0] / 100.0
    if a.home_lat == 0 and a.home_lon == 0 and abs(a.lat) > 0.001:
        a.home_lat = a.lat
        a.home_lon = a.lon
        link.add_event(lt('home_set', link.locale) % (a.lat, a.lon), 'home_set')
    if a.home_lat != 0:
        dlat = (a.lat - a.home_lat) * 111320
        dlon = (a.lon - a.home_lon) * 111320 * math.cos(math.radians(a.lat))
        a.dist_home = (dlat ** 2 + dlon ** 2) ** 0.5
    v = link.vehicle
    if v.armed:
        if a.alt_rel > v.max_alt:
            v.max_alt = a.alt_rel
        if a.gs > v.max_speed:
            v.max_speed = a.gs
        if a._prev_pos:
            dp = ((a.lat - a._prev_pos[0]) * 111320) ** 2 + \
                 ((a.lon - a._prev_pos[1]) * 111320 * math.cos(math.radians(a.lat))) ** 2
            v.total_dist += dp ** 0.5
        a._prev_pos = (a.lat, a.lon)


def handle_sys_status(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 31)
    bat = link.battery
    bat.voltage = (p[14] | (p[15] << 8)) / 1000.0
    if pl >= 18:
        bat.current = struct.unpack_from('<h', p, 16)[0] / 100.0
    if pl > 30:
        bat.remaining = struct.unpack_from('<b', p, 30)[0]
    if bat.remaining >= 0 and link.vehicle.armed:
        now = time.time()
        bat._bat_history.append((now, bat.remaining))
        bat._bat_history = [(t, r) for t, r in bat._bat_history if now - t < 120]
        if len(bat._bat_history) >= 2:
            dt = bat._bat_history[-1][0] - bat._bat_history[0][0]
            dr = bat._bat_history[0][1] - bat._bat_history[-1][1]
            if dt > 10 and dr > 0:
                bat.bat_time_remaining = int(bat.remaining / (dr / dt))


def handle_gps_raw_int(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 30)
    link.gps.gps_fix = p[28]
    link.gps.gps_sats = p[29]


def handle_mission_current(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 2)
    link.mission.wp_seq = p[0] | (p[1] << 8)


def handle_home_position(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 20)
    hlat = struct.unpack_from('<i', p, 0)[0] / 1e7
    hlon = struct.unpack_from('<i', p, 4)[0] / 1e7
    if abs(hlat) > 0.001:
        link.attitude.home_lat = hlat
        link.attitude.home_lon = hlon


def handle_mission_item_reached(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 2)
    seq = p[0] | (p[1] << 8)
    link.add_event(lt('wp_reached', link.locale) % seq, 'wp_reached')


_CMD_NAMES_ZH = {
    22: '起飞', 176: '模式', 181: '继电器', 241: '校准', 300: '任务开始',
    400: '解锁/锁定', 410: '引导',
    42424: '罗盘校准', 42425: '接受罗盘校准', 42426: '取消罗盘校准',
}
_CMD_NAMES_EN = {
    22: 'Takeoff', 176: 'Mode', 181: 'Relay', 241: 'Calibration', 300: 'Mission Start',
    400: 'Arm/Disarm', 410: 'Guided',
    42424: 'Compass Cal', 42425: 'Accept Compass Cal', 42426: 'Cancel Compass Cal',
}
_ACK_RESULTS_ZH = {0: '成功', 1: '暂时拒绝', 2: '拒绝', 3: '不支持', 4: '进行中', 5: '已取消'}
_ACK_RESULTS_EN = {0: 'success', 1: 'temporarily rejected', 2: 'denied', 3: 'unsupported', 4: 'in progress', 5: 'cancelled'}

def handle_command_ack(p: bytes, pl: int, link: DroneLink) -> None:
    # Min check 2: command at 0-1. result (offset 2) reads 0 (ACCEPTED) when
    # the byte was trimmed.
    if pl < 2:
        return
    p = _pad(p, 3)
    import struct
    cmd_id = struct.unpack_from('<H', p, 0)[0]
    result = p[2]
    en = link.locale == 'en'
    cmd_name = (_CMD_NAMES_EN if en else _CMD_NAMES_ZH).get(cmd_id, str(cmd_id))
    result_text = (_ACK_RESULTS_EN if en else _ACK_RESULTS_ZH).get(result, 'unknown(%d)' % result if en else '未知(%d)' % result)
    if result == 4:
        return
    if result == 0 and cmd_id in (241, 42424, 42425, 42426):
        return
    etype = 'cmd_ack_ok' if result == 0 else 'cmd_ack_fail'
    link.add_event(lt('cmd_ack', link.locale) % (cmd_name, result_text), etype)


def handle_mag_cal_progress(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 17)
    if getattr(link, '_mag_cal_done', False):
        return
    pct = p[16]
    prev = getattr(link, '_mag_cal_pct', -1)
    if pct > prev:
        link._mag_cal_pct = pct
        if (pct // 5) != (prev // 5):
            link.add_event(lt('mag_cal_pct', link.locale) % pct, 'cal_compass')


def handle_mag_cal_report(p: bytes, pl: int, link: DroneLink) -> None:
    # cal_status at offset 42. autosaved (43) and the orientation extension
    # fields commonly trim down to pl=43 when autosaved=0.
    if pl < 43:
        return
    p = _pad(p, 44)
    if getattr(link, '_mag_cal_done', False):
        return
    cal_status = p[42]
    link._mag_cal_done = True
    link._mag_cal_pct = -1
    if cal_status == 4:
        link.add_event(lt('mag_cal_done', link.locale), 'cal_compass')
        link.add_event(lt('mag_cal_reboot', link.locale), 'cal_compass')
    else:
        link.add_event(lt('mag_cal_fail', link.locale), 'cal_compass')


def handle_statustext(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 2:
        return
    text = bytes(p[1:51]).split(b'\x00')[0].decode('ascii', 'replace').strip()
    if not text:
        return
    if text.startswith('PreArm:') or text.startswith('Arm:'):
        msg = text.split(':', 1)[1].strip()
        # PreArm checks run every ~5s and re-emit the same warnings until the
        # condition is fixed. Dedup against _prearm_messages so the event log
        # gets one entry per distinct cause, not one every cycle.
        if msg in link._prearm_messages:
            return
        link._prearm_messages.append(msg)
        if len(link._prearm_messages) > 20:
            link._prearm_messages = link._prearm_messages[-10:]
    text = filter_statustext(text, link.locale)
    link.add_event(('%s: %s' % ('FC' if link.locale == 'en' else '飞控', text)), 'statustext')


def handle_servo_output(p: bytes, pl: int, link: DroneLink) -> None:
    # Min check 6 (servo1 last byte). Trim could drop port (offset 20) and the
    # extension servo9-16 if those values are all zero.
    if pl < 6:
        return
    p = _pad(p, 37)
    rc = link.rc_servo
    rc.servo_out = [struct.unpack_from('<H', p, 4 + i * 2)[0] for i in range(8)]
    if pl >= 37:
        rc.servo_out += [struct.unpack_from('<H', p, 21 + i * 2)[0] for i in range(8)]
    else:
        rc.servo_out += [0] * 8


def handle_rc_channels(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 6:
        return
    p = _pad(p, 42)
    link.rc_servo.rc_channels = [struct.unpack_from('<H', p, 4 + i * 2)[0] for i in range(16)]
    link.rc_servo.rc_rssi = p[41]


def handle_vibration(p: bytes, pl: int, link: DroneLink) -> None:
    # Min check 12: vibration_x first useful field. Trim can drop trailing
    # clipping counters when they're zero.
    if pl < 12:
        return
    p = _pad(p, 32)
    d = link.diagnostic
    d.vibe_x = struct.unpack_from('<f', p, 8)[0]
    d.vibe_y = struct.unpack_from('<f', p, 12)[0]
    d.vibe_z = struct.unpack_from('<f', p, 16)[0]
    d.vibe_clip0 = struct.unpack_from('<I', p, 20)[0]
    d.vibe_clip1 = struct.unpack_from('<I', p, 24)[0]
    d.vibe_clip2 = struct.unpack_from('<I', p, 28)[0]


def handle_vfr_hud(p: bytes, pl: int, link: DroneLink) -> None:
    # Min check 4 (airspeed): MAVLink 2 zero-trim can shrink this from the
    # nominal 20 bytes down to as little as 4 when throttle/heading/climb are
    # zero.
    if pl < 4:
        return
    p = _pad(p, 20)
    airspeed, gs, alt, climb, heading, throttle = struct.unpack_from('<ffffhH', p)
    a = link.attitude
    a.airspeed = airspeed
    a.throttle = throttle
    a.climb = climb


def handle_ekf_status(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 22)
    vel, pos_h, pos_v, comp, terr, flags = struct.unpack_from('<fffffH', p)
    d = link.diagnostic
    d.ekf_vel_var = vel
    d.ekf_pos_h_var = pos_h
    d.ekf_pos_v_var = pos_v
    d.ekf_compass_var = comp
    d.ekf_terrain_var = terr
    d.ekf_flags = flags


def handle_mount_status(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 12)
    pitch_cdeg, _roll_cdeg, yaw_cdeg = struct.unpack_from('<iii', p)
    d = link.diagnostic
    d.gimbal_pitch = pitch_cdeg / 100.0
    d.gimbal_yaw = yaw_cdeg / 100.0


def handle_terrain_report(p: bytes, pl: int, link: DroneLink) -> None:
    # TERRAIN_REPORT (136) wire layout (MAVLink 2, sorted by size):
    #   lat (i32, 0..3), lon (i32, 4..7), terrain_height (float, 8..11),
    #   current_height (float, 12..15), spacing (u16, 16..17),
    #   pending (u16, 18..19), loaded (u16, 20..21).
    # We want terrain_height (ground elevation) for "terrain altitude" display,
    # not current_height (vehicle altitude above the ground).
    if pl < 1:
        return
    p = _pad(p, 16)
    link.diagnostic.terrain_alt = struct.unpack_from('<f', p, 8)[0]


def handle_wind(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 12)
    direction, speed, _ = struct.unpack_from('<fff', p)
    link.diagnostic.wind_dir = direction % 360
    link.diagnostic.wind_speed = speed


def handle_param_value(p: bytes, pl: int, link: DroneLink) -> None:
    link.param_mgr.handle_param_value(p, pl)


def handle_autopilot_version(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 44)
    fw_ver = struct.unpack_from('<I', p, 16)[0]
    major = (fw_ver >> 24) & 0xFF
    minor = (fw_ver >> 16) & 0xFF
    patch = (fw_ver >> 8) & 0xFF
    board = struct.unpack_from('<I', p, 28)[0]
    git_bytes = bytes(p[36:44])
    git = ''.join('%02x' % b for b in git_bytes if b != 0)[:8]
    v = link.vehicle
    v.fw_version = 'v%d.%d.%d' % (major, minor, patch)
    v.fw_git = git
    v.board_id = board
    link.add_event(lt('fw_info', link.locale) % (v.fw_version, v.fw_git), 'fw_info')


def handle_mission_count(p: bytes, pl: int, link: DroneLink) -> None:
    m = link.mission
    if pl < 1 or not m._dl_pending:
        return
    p = _pad(p, 3)
    count = struct.unpack_from('<H', p, 0)[0]
    m._dl_total = count
    m._dl_items = [None] * count
    if count > 0:
        _request_dl_item(link, 0)
        link.add_event(lt('mission_dl_n', link.locale) % count, 'mission_dl_n')
    else:
        m._dl_pending = False
        link.add_event(lt('mission_dl_none', link.locale), 'mission_dl_none')


def handle_mission_item_int(p: bytes, pl: int, link: DroneLink) -> None:
    m = link.mission
    if pl < 1 or not m._dl_pending:
        return
    p = _pad(p, 37)
    p1 = struct.unpack_from('<f', p, 0)[0]
    p2 = struct.unpack_from('<f', p, 4)[0]
    lat = struct.unpack_from('<i', p, 16)[0] / 1e7
    lon = struct.unpack_from('<i', p, 20)[0] / 1e7
    alt = struct.unpack_from('<f', p, 24)[0]
    seq = struct.unpack_from('<H', p, 28)[0]
    cmd = struct.unpack_from('<H', p, 30)[0]
    if seq < m._dl_total:
        m._dl_items[seq] = {'seq': seq, 'cmd': cmd, 'lat': lat, 'lon': lon, 'alt': alt, 'p1': p1, 'p2': p2}
    if seq + 1 < m._dl_total:
        _request_dl_item(link, seq + 1)
    else:
        m._dl_pending = False
        items = [i for i in m._dl_items if i is not None]
        wps = []
        pending_speed = 0.0
        for item in items:
            if item['cmd'] == 178:
                pending_speed = item.get('p2', 0)
            elif item['cmd'] in (16, 18, 19, 82) and item['seq'] > 0:
                wtype = 'loiter_turns' if item['cmd'] == 18 else ('loiter_time' if item['cmd'] == 19 else ('spline' if item['cmd'] == 82 else 'wp'))
                wps.append({'lat': item['lat'], 'lon': item['lon'], 'alt': item['alt'],
                            'drop': False, 'delay': item['p1'] if item['cmd'] == 16 else 0,
                            'speed': pending_speed, 'type': wtype,
                            'loiter_param': item['p1'] if item['cmd'] in (18, 19) else 0})
                pending_speed = 0.0
            elif item['cmd'] == 181 and wps:
                wps[-1]['drop'] = True
        m._dl_messages.append({'type': 'mission_downloaded', 'waypoints': wps})
        if len(m._dl_messages) > 500:
            m._dl_messages = m._dl_messages[-200:]
        link.add_event(lt('mission_dl_done', link.locale) % len(wps), 'mission_dl_done')
        from .pllink_proto import bm
        link.send(bm(47, struct.pack('<BBB', link.vehicle.sysid, 1, 0), link.sq, 153))


def _request_dl_item(link: DroneLink, seq: int) -> None:
    from .pllink_proto import bm
    link.send(bm(51, struct.pack('<HBBB', seq, link.vehicle.sysid, 1, 0), link.sq, 196))


def handle_mission_request(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 5)
    seq = p[0] | (p[1] << 8)
    mission_type = p[4]
    m = link.mission
    from . import commands as cmd_mod
    if mission_type == 1 and m._fence_pending:
        if seq < len(m._fence_items):
            cmd_mod.send_fence_item_int(link, m._fence_items[seq])
    elif mission_type == 2 and m._rally_pending:
        if seq < len(m._rally_items):
            cmd_mod.send_rally_item_int(link, m._rally_items[seq])
    elif mission_type == 0 and m._mission_pending:
        if seq < len(m._mission_items):
            cmd_mod.send_mission_item_int(link, m._mission_items[seq])


def handle_mission_ack(p: bytes, pl: int, link: DroneLink) -> None:
    # Min check 1: target_system. type (offset 2) reads 0=ACCEPTED from
    # zero-padded buffer if trimmed.
    if pl < 1:
        return
    p = _pad(p, 4)
    mtype = p[2]
    mission_type = p[3]
    m = link.mission
    if mission_type == 1 and m._fence_pending:
        m._fence_pending = False
        link.add_event((lt('fence_ack_ok', link.locale) if mtype == 0 else lt('fence_ack_fail', link.locale) % mtype),
                       'fence_ack_ok' if mtype == 0 else 'fence_ack_fail')
    elif mission_type == 2 and m._rally_pending:
        m._rally_pending = False
        # No fence_ack_ok/fail-equivalent for rally; reuse mission text.
        link.add_event((lt('mission_ack_ok', link.locale) if mtype == 0 else lt('mission_ack_fail', link.locale) % mtype),
                       'mission_ack_ok' if mtype == 0 else 'mission_ack_fail')
    elif mission_type == 0 and m._mission_pending:
        m._mission_pending = False
        link.add_event((lt('mission_ack_ok', link.locale) if mtype == 0 else lt('mission_ack_fail', link.locale) % mtype),
                       'mission_ack_ok' if mtype == 0 else 'mission_ack_fail')


def handle_log_entry(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 14)
    time_utc, size, log_id, num_logs, last_log_num = struct.unpack_from('<IIHHH', p, 0)
    lg = link.log_dl
    lg._log_list.append({'id': log_id, 'size': size, 'time_utc': time_utc})
    if log_id == last_log_num:
        lg._log_messages.append({'type': 'log_list', 'logs': list(lg._log_list)})
        link.add_event(lt('log_list_n', link.locale) % len(lg._log_list), 'log_list_n')


def handle_battery_status(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 10:
        return
    p = _pad(p, 36)
    cells = []
    for i in range(10):
        v = struct.unpack_from('<H', p, 10 + i * 2)[0]
        if v == 0xFFFF:
            break
        cells.append(v / 1000.0)
    link.battery.battery_cells = cells


def handle_adsb_vehicle(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 1:
        return
    p = _pad(p, 38)
    icao = struct.unpack_from('<I', p, 0)[0]
    lat = struct.unpack_from('<i', p, 4)[0] / 1e7
    lon = struct.unpack_from('<i', p, 8)[0] / 1e7
    alt = struct.unpack_from('<i', p, 12)[0] / 1000.0
    hdg = struct.unpack_from('<H', p, 16)[0] / 100.0
    hor_vel = struct.unpack_from('<H', p, 18)[0] / 100.0
    ver_vel = struct.unpack_from('<h', p, 20)[0] / 100.0
    callsign = bytes(p[27:36]).split(b'\x00')[0].decode('ascii', 'replace').strip()
    tr = link.traffic
    tr._adsb_vehicles[icao] = {
        'icao': icao, 'lat': round(lat, 7), 'lon': round(lon, 7),
        'alt': round(alt, 0), 'hdg': round(hdg, 0), 'speed': round(hor_vel, 1),
        'vs': round(ver_vel, 1), 'callsign': callsign, 't': time.time(),
    }
    if len(tr._adsb_vehicles) > 200:
        oldest = min(tr._adsb_vehicles, key=lambda k: tr._adsb_vehicles[k]['t'])
        del tr._adsb_vehicles[oldest]


def handle_serial_control(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 9:
        return
    p = _pad(p, 79)
    count = p[8]
    if count > 0 and count <= 70:
        text = bytes(p[9:9 + count]).decode('ascii', 'replace')
        link._console_buf.append(text)
        if len(link._console_buf) > 500:
            link._console_buf = link._console_buf[-250:]


def handle_log_data(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 7:
        return
    p = _pad(p, 97)
    lg = link.log_dl
    ofs, log_id, count = struct.unpack_from('<IHB', p, 0)
    if log_id != lg._log_download_id:
        return
    # FC documents count=0 as EOF / error per MAVLink common.xml: previously
    # this fell through to `end = ofs + 0 = ofs`; with end < size we re-
    # requested forever in a tight loop (LOG_REQUEST_DATA never receives data
    # because the source log is gone or unreadable).
    if count == 0:
        link.add_event(lt('log_dl_done', link.locale) % (log_id, ofs // 1024), 'log_dl_done')
        lg._log_messages.append({
            'type': 'log_complete',
            'id': log_id,
            'data': '',
            'size': ofs,
            'truncated': True,
        })
        lg._log_download_id = -1
        return
    data = p[7:7 + count]
    end = ofs + count
    if end <= lg._log_download_size:
        lg._log_download_data[ofs:end] = data
    # Use max() so an out-of-order or duplicate chunk doesn't rewind progress
    # and trigger re-requesting already-received bytes (auditor finding C2).
    lg._log_download_ofs = max(lg._log_download_ofs, end)
    end = lg._log_download_ofs
    if not hasattr(link, '_log_progress_counter'):
        link._log_progress_counter = 0
    link._log_progress_counter += 1
    if link._log_progress_counter >= 10 and end < lg._log_download_size:
        link._log_progress_counter = 0
        lg._log_messages.append({
            'type': 'log_progress',
            'received': end,
            'total': lg._log_download_size,
        })
        if len(lg._log_messages) > 500:
            lg._log_messages = lg._log_messages[-200:]
    if end >= lg._log_download_size:
        import base64
        b64 = base64.b64encode(bytes(lg._log_download_data)).decode('ascii')
        lg._log_messages.append({
            'type': 'log_complete',
            'id': log_id,
            'data': b64,
            'size': lg._log_download_size,
        })
        link.add_event(lt('log_dl_done', link.locale) % (log_id, lg._log_download_size // 1024), 'log_dl_done')
        lg._log_download_id = -1
    else:
        from .pllink_proto import bm
        remaining = lg._log_download_size - end
        chunk = min(90 * 50, remaining)
        link.send(bm(119, struct.pack('<IIHBB', end, chunk, log_id, link.vehicle.sysid, 1), link.sq, 116))


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
    mavlink_dispatch.register(36, handle_servo_output)
    mavlink_dispatch.register(65, handle_rc_channels)
    mavlink_dispatch.register(241, handle_vibration)
    mavlink_dispatch.register(74, handle_vfr_hud)
    mavlink_dispatch.register(193, handle_ekf_status)
    mavlink_dispatch.register(158, handle_mount_status)
    mavlink_dispatch.register(136, handle_terrain_report)
    mavlink_dispatch.register(168, handle_wind)
    mavlink_dispatch.register(22, handle_param_value)
    mavlink_dispatch.register(148, handle_autopilot_version)
    mavlink_dispatch.register(44, handle_mission_count)
    mavlink_dispatch.register(73, handle_mission_item_int)
    mavlink_dispatch.register(40, handle_mission_request)
    mavlink_dispatch.register(51, handle_mission_request)
    mavlink_dispatch.register(47, handle_mission_ack)
    mavlink_dispatch.register(118, handle_log_entry)
    mavlink_dispatch.register(120, handle_log_data)
    mavlink_dispatch.register(126, handle_serial_control)
    mavlink_dispatch.register(246, handle_adsb_vehicle)
    mavlink_dispatch.register(191, handle_mag_cal_progress)
    mavlink_dispatch.register(192, handle_mag_cal_report)
    mavlink_dispatch.register(147, handle_battery_status)
