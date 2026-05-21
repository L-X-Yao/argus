from __future__ import annotations
import struct
import math
import time
from typing import TYPE_CHECKING

from . import mavlink_dispatch
from .statustext_filter import filter_statustext
from .constants import PLANE_MODES, COPTER_MODES
from .locale_text import lt

if TYPE_CHECKING:
    from .drone_link import DroneLink


def handle_heartbeat(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 7:
        return
    link.mode = p[0] | (p[1] << 8) | (p[2] << 16) | (p[3] << 24)
    old_vtype = link.vtype_raw
    link.vtype_raw = p[4]
    if old_vtype != link.vtype_raw and link.vtype_raw > 0:
        link.add_event(lt('vehicle_type', link.locale) % link._get_vehicle_info()[2], 'vehicle_type')
    new_armed = bool(p[6] & 0x80)
    if new_armed != link.armed:
        link.add_event(lt('armed', link.locale) if new_armed else lt('disarmed', link.locale),
                       'armed' if new_armed else 'disarmed')
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
        link.add_event(lt('connected', link.locale) % link.sysid, 'connected')


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
        link.add_event(lt('home_set', link.locale) % (link.lat, link.lon), 'home_set')
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
    link.add_event(lt('wp_reached', link.locale) % seq, 'wp_reached')


_CMD_NAMES_ZH = {
    22: '起飞', 176: '模式', 181: '继电器', 241: '校准', 300: '任务开始',
    400: '解锁/锁定', 410: '引导',
}
_CMD_NAMES_EN = {
    22: 'Takeoff', 176: 'Mode', 181: 'Relay', 241: 'Calibration', 300: 'Mission Start',
    400: 'Arm/Disarm', 410: 'Guided',
}
_ACK_RESULTS_ZH = {0: '成功', 1: '暂时拒绝', 2: '拒绝', 3: '不支持', 4: '进行中', 5: '已取消'}
_ACK_RESULTS_EN = {0: 'success', 1: 'temporarily rejected', 2: 'denied', 3: 'unsupported', 4: 'in progress', 5: 'cancelled'}

def handle_command_ack(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 3:
        return
    import struct
    cmd_id = struct.unpack_from('<H', p, 0)[0]
    result = p[2]
    en = link.locale == 'en'
    cmd_name = (_CMD_NAMES_EN if en else _CMD_NAMES_ZH).get(cmd_id, str(cmd_id))
    result_text = (_ACK_RESULTS_EN if en else _ACK_RESULTS_ZH).get(result, 'unknown(%d)' % result if en else '未知(%d)' % result)
    if result == 4:
        return
    etype = 'cmd_ack_ok' if result == 0 else 'cmd_ack_fail'
    link.add_event(lt('cmd_ack', link.locale) % (cmd_name, result_text), etype)


def handle_statustext(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 2:
        return
    text = bytes(p[1:51]).split(b'\x00')[0].decode('ascii', 'replace').strip()
    if text:
        if text.startswith('PreArm:') or text.startswith('Arm:'):
            msg = text.split(':', 1)[1].strip()
            if msg not in link._prearm_messages:
                link._prearm_messages.append(msg)
                if len(link._prearm_messages) > 20:
                    link._prearm_messages = link._prearm_messages[-10:]
        text = filter_statustext(text, link.locale)
        link.add_event(('%s: %s' % ('FC' if link.locale == 'en' else '飞控', text)), 'statustext')


def handle_servo_output(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 21:
        return
    link.servo_out = [struct.unpack_from('<H', p, 4 + i * 2)[0] for i in range(8)]
    if pl >= 37:
        link.servo_out += [struct.unpack_from('<H', p, 21 + i * 2)[0] for i in range(8)]
    else:
        link.servo_out += [0] * 8


def handle_rc_channels(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 42:
        return
    link.rc_channels = [struct.unpack_from('<H', p, 5 + i * 2)[0] for i in range(16)]
    link.rc_rssi = p[41]


def handle_vibration(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 32:
        return
    link.vibe_x = struct.unpack_from('<f', p, 8)[0]
    link.vibe_y = struct.unpack_from('<f', p, 12)[0]
    link.vibe_z = struct.unpack_from('<f', p, 16)[0]
    link.vibe_clip0 = struct.unpack_from('<I', p, 20)[0]
    link.vibe_clip1 = struct.unpack_from('<I', p, 24)[0]
    link.vibe_clip2 = struct.unpack_from('<I', p, 28)[0]


def handle_ekf_status(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 22:
        return
    vel, pos_h, pos_v, comp, terr, flags = struct.unpack_from('<fffffH', p)
    link.ekf_vel_var = vel
    link.ekf_pos_h_var = pos_h
    link.ekf_pos_v_var = pos_v
    link.ekf_compass_var = comp
    link.ekf_terrain_var = terr
    link.ekf_flags = flags


def handle_terrain_report(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 16:
        return
    link.terrain_alt = struct.unpack_from('<f', p, 12)[0]


def handle_wind(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 12:
        return
    direction, speed, _ = struct.unpack_from('<fff', p)
    link.wind_dir = direction % 360
    link.wind_speed = speed


def handle_param_value(p: bytes, pl: int, link: DroneLink) -> None:
    link.param_mgr.handle_param_value(p, pl)


def handle_autopilot_version(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 36:
        return
    fw_ver = struct.unpack_from('<I', p, 8)[0]
    major = (fw_ver >> 24) & 0xFF
    minor = (fw_ver >> 16) & 0xFF
    patch = (fw_ver >> 8) & 0xFF
    board = struct.unpack_from('<I', p, 20)[0]
    git_bytes = bytes(p[24:32])
    git = ''.join('%02x' % b for b in git_bytes if b != 0)[:8]
    link.fw_version = 'v%d.%d.%d' % (major, minor, patch)
    link.fw_git = git
    link.board_id = board
    link.add_event(lt('fw_info', link.locale) % (link.fw_version, link.fw_git), 'fw_info')


def handle_mission_count(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 3 or not link._dl_pending:
        return
    count = struct.unpack_from('<H', p, 0)[0]
    link._dl_total = count
    link._dl_items = [None] * count
    if count > 0:
        _request_dl_item(link, 0)
        link.add_event(lt('mission_dl_n', link.locale) % count, 'mission_dl_n')
    else:
        link._dl_pending = False
        link.add_event(lt('mission_dl_none', link.locale), 'mission_dl_none')


def handle_mission_item_int(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 37 or not link._dl_pending:
        return
    p1 = struct.unpack_from('<f', p, 0)[0]
    p2 = struct.unpack_from('<f', p, 4)[0]
    lat = struct.unpack_from('<i', p, 16)[0] / 1e7
    lon = struct.unpack_from('<i', p, 20)[0] / 1e7
    alt = struct.unpack_from('<f', p, 24)[0]
    seq = struct.unpack_from('<H', p, 28)[0]
    cmd = struct.unpack_from('<H', p, 30)[0]
    if seq < link._dl_total:
        link._dl_items[seq] = {'seq': seq, 'cmd': cmd, 'lat': lat, 'lon': lon, 'alt': alt, 'p1': p1, 'p2': p2}
    if seq + 1 < link._dl_total:
        _request_dl_item(link, seq + 1)
    else:
        link._dl_pending = False
        items = [i for i in link._dl_items if i is not None]
        wps = []
        pending_speed = 0.0
        for item in items:
            if item['cmd'] == 178:
                pending_speed = item.get('p2', 0)
            elif item['cmd'] in (16, 18, 19) and item['seq'] > 0:
                wtype = 'loiter_turns' if item['cmd'] == 18 else ('loiter_time' if item['cmd'] == 19 else 'wp')
                wps.append({'lat': item['lat'], 'lon': item['lon'], 'alt': item['alt'],
                            'drop': False, 'delay': item['p1'] if item['cmd'] == 16 else 0,
                            'speed': pending_speed, 'type': wtype,
                            'loiter_param': item['p1'] if item['cmd'] in (18, 19) else 0})
                pending_speed = 0.0
            elif item['cmd'] == 181 and wps:
                wps[-1]['drop'] = True
        link._dl_messages.append({'type': 'mission_downloaded', 'waypoints': wps})
        if len(link._dl_messages) > 500:
            link._dl_messages = link._dl_messages[-200:]
        link.add_event(lt('mission_dl_done', link.locale) % len(wps), 'mission_dl_done')
        from pllink_proto import bm
        link.send(bm(47, struct.pack('<BBB', link.sysid, 1, 0), link.sq, 153))


def _request_dl_item(link: DroneLink, seq: int) -> None:
    from pllink_proto import bm
    link.send(bm(51, struct.pack('<HBBB', seq, link.sysid, 1, 0), link.sq, 196))


def handle_mission_request(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 2:
        return
    seq = p[0] | (p[1] << 8)
    mission_type = p[4] if pl >= 5 else 0
    from . import commands as cmd_mod
    if mission_type == 1 and link._fence_pending:
        if seq < len(link._fence_items):
            cmd_mod.send_fence_item_int(link, link._fence_items[seq])
    elif link._mission_pending:
        if seq < len(link._mission_items):
            cmd_mod.send_mission_item_int(link, link._mission_items[seq])


def handle_mission_ack(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 3:
        return
    mtype = p[2]
    mission_type = p[3] if pl >= 4 else 0
    if mission_type == 1 and link._fence_pending:
        link._fence_pending = False
        link.add_event((lt('fence_ack_ok', link.locale) if mtype == 0 else lt('fence_ack_fail', link.locale) % mtype),
                       'fence_ack_ok' if mtype == 0 else 'fence_ack_fail')
    elif link._mission_pending:
        link._mission_pending = False
        link.add_event((lt('mission_ack_ok', link.locale) if mtype == 0 else lt('mission_ack_fail', link.locale) % mtype),
                       'mission_ack_ok' if mtype == 0 else 'mission_ack_fail')


def handle_log_entry(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 14:
        return
    time_utc, size, log_id, num_logs, last_log_num = struct.unpack_from('<IIHHH', p, 0)
    link._log_list.append({'id': log_id, 'size': size, 'time_utc': time_utc})
    if log_id == last_log_num:
        link._log_messages.append({'type': 'log_list', 'logs': list(link._log_list)})
        link.add_event(lt('log_list_n', link.locale) % len(link._log_list), 'log_list_n')


def handle_adsb_vehicle(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 38:
        return
    icao = struct.unpack_from('<I', p, 0)[0]
    lat = struct.unpack_from('<i', p, 4)[0] / 1e7
    lon = struct.unpack_from('<i', p, 8)[0] / 1e7
    alt = struct.unpack_from('<i', p, 12)[0] / 1000.0
    hdg = struct.unpack_from('<H', p, 16)[0] / 100.0
    hor_vel = struct.unpack_from('<H', p, 18)[0] / 100.0
    ver_vel = struct.unpack_from('<h', p, 20)[0] / 100.0
    callsign = bytes(p[22:31]).split(b'\x00')[0].decode('ascii', 'replace').strip()
    link._adsb_vehicles[icao] = {
        'icao': icao, 'lat': round(lat, 7), 'lon': round(lon, 7),
        'alt': round(alt, 0), 'hdg': round(hdg, 0), 'speed': round(hor_vel, 1),
        'vs': round(ver_vel, 1), 'callsign': callsign, 't': time.time(),
    }
    if len(link._adsb_vehicles) > 200:
        oldest = min(link._adsb_vehicles, key=lambda k: link._adsb_vehicles[k]['t'])
        del link._adsb_vehicles[oldest]


def handle_serial_control(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 10:
        return
    count = p[4]
    if count > 0 and count <= 70:
        text = bytes(p[5:5 + count]).decode('ascii', 'replace')
        link._console_buf.append(text)
        if len(link._console_buf) > 500:
            link._console_buf = link._console_buf[-250:]


def handle_log_data(p: bytes, pl: int, link: DroneLink) -> None:
    if pl < 7:
        return
    ofs, log_id, count = struct.unpack_from('<IHB', p, 0)
    if log_id != link._log_download_id:
        return
    data = p[7:7 + count]
    end = ofs + count
    if end <= link._log_download_size:
        link._log_download_data[ofs:end] = data
    link._log_download_ofs = end
    if not hasattr(link, '_log_progress_counter'):
        link._log_progress_counter = 0
    link._log_progress_counter += 1
    if link._log_progress_counter >= 10 and end < link._log_download_size:
        link._log_progress_counter = 0
        link._log_messages.append({
            'type': 'log_progress',
            'received': end,
            'total': link._log_download_size,
        })
        if len(link._log_messages) > 500:
            link._log_messages = link._log_messages[-200:]
    if end >= link._log_download_size:
        import base64
        b64 = base64.b64encode(bytes(link._log_download_data)).decode('ascii')
        link._log_messages.append({
            'type': 'log_complete',
            'id': log_id,
            'data': b64,
            'size': link._log_download_size,
        })
        link.add_event(lt('log_dl_done', link.locale) % (log_id, link._log_download_size // 1024), 'log_dl_done')
        link._log_download_id = -1
    else:
        from pllink_proto import bm
        remaining = link._log_download_size - end
        chunk = min(90 * 50, remaining)
        link.send(bm(119, struct.pack('<IIHBB', end, chunk, log_id, link.sysid, 1), link.sq, 116))


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
    mavlink_dispatch.register(74, handle_ekf_status)
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
