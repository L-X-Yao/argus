from __future__ import annotations

import base64
import struct
from typing import TYPE_CHECKING

from ..locale_text import lt
from ..pllink_proto import bm
from ._helpers import send_cmd, send_serial_control

if TYPE_CHECKING:
    from ..drone_link import DroneLink


# --- Vehicle ---

def cmd_set_vtype(link: DroneLink, param, data: dict):
    v = data.get('vtype', 'auto')
    link.vehicle.force_plane = True if v == 'plane' else (False if v == 'copter' else None)
    vname = lt('vtype_plane' if v == 'plane' else 'vtype_copter' if v == 'copter' else 'vtype_auto', link.locale)
    link.add_event(lt('vtype_set', link.locale) % vname, 'vtype_set')


def cmd_guided_goto(link: DroneLink, param, data: dict):
    lat = float(data.get('lat', 0))
    lon = float(data.get('lon', 0))
    alt = float(data.get('alt', 30))
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180) or not (-500 <= alt <= 100000):
        return {'ok': False, 'error': lt('err_bad_coord', link.locale)}
    lat7 = int(lat * 1e7)
    lon7 = int(lon * 1e7)
    gm = 15 if link.is_plane() else 4
    from ._helpers import send_set_mode
    send_set_mode(link, gm)
    link.add_event(lt('guided', link.locale) % (lat7 / 1e7, lon7 / 1e7, alt), 'guided')
    p = struct.pack('<IiifffffffffHBBB',
                    0, lat7, lon7, alt, 0, 0, 0, 0, 0, 0, 0, 0,
                    0x0FF8, link.vehicle.sysid, 1, 6)
    link.send(bm(84, p, link.sq, 5))


def cmd_switch_vehicle(link: DroneLink, param, data: dict):
    new_sysid = int(data.get('sysid', 1))
    link.active_sysid = new_sysid
    link.vehicle.sysid = new_sysid
    link.add_event(lt('vehicle_switch', link.locale) % new_sysid, 'vehicle_switch')


def cmd_clear_summary(link: DroneLink, param, data: dict):
    link.vehicle.flight_summary = None


# --- System ---

def cmd_reboot(link: DroneLink, param, data: dict):
    link.add_event(lt('reboot', link.locale), 'reboot')
    send_cmd(link, 246, p1=1)


def cmd_reboot_bootloader(link: DroneLink, param, data: dict):
    link.add_event(lt('reboot_bl', link.locale), 'reboot_bl')
    send_cmd(link, 246, p1=3)


def cmd_inspector_toggle(link: DroneLink, param, data: dict):
    link.inspector_enabled = not link.inspector_enabled


def cmd_serial_control(link: DroneLink, param, data: dict):
    text = data.get('text', '')
    if text:
        send_serial_control(link, text)


def cmd_inject_rtcm(link: DroneLink, param, data: dict):
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

def cmd_rc_override(link: DroneLink, param, data: dict):
    channels = data.get('channels', [])
    if not isinstance(channels, list) or len(channels) < 8:
        return None
    try:
        p = struct.pack('<BB', link.vehicle.sysid, 1)
        for i in range(8):
            p += struct.pack('<H', max(0, min(65535, int(channels[i]))))
        link.send(bm(70, p, link.sq, 124))
    except (TypeError, ValueError):
        return {'ok': False, 'error': 'Invalid channel data'}


def cmd_motor_test(link: DroneLink, param, data: dict):
    motor = int(data.get('motor', 0))
    if not 0 <= motor <= 7:
        return {'ok': False, 'error': 'Motor index must be 0-7'}
    throttle = float(data.get('throttle', 5))
    if not 0 <= throttle <= 100:
        return {'ok': False, 'error': 'Throttle must be 0-100%'}
    duration = float(data.get('duration', 2))
    if not 0 < duration <= 30:
        return {'ok': False, 'error': 'Duration must be 0-30s'}
    link.add_event(lt('motor_test', link.locale) % (motor + 1, throttle), 'motor_test')
    send_cmd(link, 209, p1=float(motor), p2=0, p3=throttle, p4=duration, p5=1)


def cmd_motor_test_stop(link: DroneLink, param, data: dict):
    for i in range(8):
        send_cmd(link, 209, p1=float(i), p2=0, p3=0, p4=0, p5=1)


# --- Camera / Gimbal ---

def cmd_gimbal_angle(link: DroneLink, param, data: dict):
    pitch = float(data.get('pitch', 0))
    yaw = float(data.get('yaw', 0))
    if not -90 <= pitch <= 90 or not -180 <= yaw <= 180:
        return {'ok': False, 'error': 'Gimbal angle out of range'}
    send_cmd(link, 205, p1=pitch, p4=yaw)


def cmd_gimbal_rate(link: DroneLink, param, data: dict):
    pitch_rate = float(data.get('pitch_rate', 0))
    yaw_rate = float(data.get('yaw_rate', 0))
    if not -100 <= pitch_rate <= 100 or not -100 <= yaw_rate <= 100:
        return {'ok': False, 'error': 'Gimbal rate out of range'}
    p = struct.pack('<ffffffBBB', 0, 0, 0, float(pitch_rate * 100), 0, float(yaw_rate * 100),
                    link.vehicle.sysid, 1, 2)
    link.send(bm(282, p, link.sq, 0))


def cmd_camera_trigger(link: DroneLink, param, data: dict):
    send_cmd(link, 203)


def cmd_camera_video_start(link: DroneLink, param, data: dict):
    send_cmd(link, 2500, p1=0, p2=0, p3=1)


def cmd_camera_video_stop(link: DroneLink, param, data: dict):
    send_cmd(link, 2501)


def cmd_camera_zoom(link: DroneLink, param, data: dict):
    zoom_val = float(data.get('zoom', 1))
    if not 0.1 <= zoom_val <= 100:
        return {'ok': False, 'error': 'Zoom must be 0.1-100'}
    send_cmd(link, 531, p1=1, p2=zoom_val)


def cmd_do_set_roi(link: DroneLink, param, data: dict):
    lat = float(data.get('lat', 0))
    lon = float(data.get('lon', 0))
    alt = float(data.get('alt', 0))
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        return {'ok': False, 'error': lt('err_bad_coord', link.locale)}
    send_cmd(link, 201, p5=lat, p6=lon, p7=alt)
