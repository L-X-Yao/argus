from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from ..locale_text import lt
from ..pllink_proto import bm
from ._helpers import send_cmd

if TYPE_CHECKING:
    from ..drone_link import DroneLink


# --- Calibration ---

def cmd_cal_compass(link: DroneLink, param, data: dict):
    link.add_event(lt('cal_compass', link.locale), 'cal_compass')
    link._mag_cal_pct = -1
    link._mag_cal_done = False
    send_cmd(link, 42424, p1=0, p2=0, p3=0, p4=0)


def cmd_cal_compass_accept(link: DroneLink, param, data: dict):
    send_cmd(link, 42425, p1=0)


def cmd_cal_accel(link: DroneLink, param, data: dict):
    link.add_event(lt('cal_accel', link.locale), 'cal_accel')
    send_cmd(link, 241, p5=1)


def cmd_cal_gyro(link: DroneLink, param, data: dict):
    link.add_event(lt('cal_gyro', link.locale), 'cal_gyro')
    send_cmd(link, 241, p1=1)


def cmd_cal_level(link: DroneLink, param, data: dict):
    link.add_event(lt('cal_level', link.locale), 'cal_level')
    send_cmd(link, 241, p5=4)


def cmd_cal_baro(link: DroneLink, param, data: dict):
    link.add_event(lt('cal_baro', link.locale), 'cal_baro')
    send_cmd(link, 241, p3=1)


def cmd_cal_accel_next(link: DroneLink, param, data: dict):
    # ArduPilot's AP_AccelCal advances orientation only when it receives a
    # COMMAND_ACK whose `command` field equals MAV_CMD_ACCELCAL_VEHICLE_POS
    # (42429). A generic ACK is ignored — see AccelCal::handle_command_ack.
    payload = struct.pack('<HB', 42429, 0)
    link.send(bm(77, payload, link.sq, 143))


def cmd_cal_cancel(link: DroneLink, param, data: dict):
    link.add_event(lt('cal_cancel', link.locale), 'cal_cancel')
    send_cmd(link, 42426, p1=0)


# --- Parameters ---

def cmd_param_request_all(link: DroneLink, param, data: dict):
    link.param_mgr.request_all()


def cmd_param_set(link: DroneLink, param, data: dict):
    name = data.get('name', '')
    value = float(data.get('value', 0))
    if name:
        link.param_mgr.set_param(name, value)


def cmd_param_save(link: DroneLink, param, data: dict):
    path = link.param_mgr.save_to_file()
    return {'ok': True, 'path': path}


def cmd_param_load(link: DroneLink, param, data: dict):
    path = data.get('path', '')
    if not path:
        return None
    from pathlib import Path
    p = Path(path).resolve()
    params_dir = Path(__file__).resolve().parent.parent.parent / 'params'
    if not str(p).startswith(str(params_dir)):
        return {'ok': False, 'error': 'Path must be within params directory'}
    if p.suffix != '.json':
        return {'ok': False, 'error': 'Only .json parameter files allowed'}
    changed = link.param_mgr.load_from_file(str(p))
    return {'ok': True, 'changed': changed}


# --- Logs ---

def cmd_log_list(link: DroneLink, param, data: dict):
    link.log_dl._log_list = []
    link.send(bm(117, struct.pack('<HHBB', 0, 0xFFFF, link.vehicle.sysid, 1), link.sq, 128))
    link.add_event(lt('log_list_req', link.locale), 'log_list_req')


def cmd_log_download(link: DroneLink, param, data: dict):
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


def cmd_log_cancel(link: DroneLink, param, data: dict):
    link.send(bm(122, struct.pack('<BB', link.vehicle.sysid, 1), link.sq, 203))
    link.log_dl._log_download_id = -1
    link.add_event(lt('log_dl_cancel', link.locale), 'log_dl_cancel')
