from __future__ import annotations

from typing import TYPE_CHECKING

from ._flight import (
    cmd_arm,
    cmd_disarm,
    cmd_drop,
    cmd_drop_stop,
    cmd_force_disarm,
    cmd_mode,
    cmd_rtl,
    cmd_takeoff,
)
from ._hardware import (
    cmd_camera_trigger,
    cmd_camera_video_start,
    cmd_camera_video_stop,
    cmd_camera_zoom,
    cmd_clear_summary,
    cmd_do_set_roi,
    cmd_gimbal_angle,
    cmd_gimbal_rate,
    cmd_guided_goto,
    cmd_inject_rtcm,
    cmd_inspector_toggle,
    cmd_motor_test,
    cmd_motor_test_stop,
    cmd_rc_override,
    cmd_reboot,
    cmd_reboot_bootloader,
    cmd_serial_control,
    cmd_set_vtype,
    cmd_switch_vehicle,
)
from ._helpers import request_streams as request_streams
from ._helpers import send_fence_item_int as send_fence_item_int
from ._helpers import send_heartbeat as send_heartbeat
from ._helpers import send_mission_item_int as send_mission_item_int
from ._mission import (
    cmd_fence_upload,
    cmd_mission_clear,
    cmd_mission_download,
    cmd_mission_start,
    cmd_mission_upload,
    cmd_rally_upload,
)
from ._setup import (
    cmd_cal_accel,
    cmd_cal_baro,
    cmd_cal_cancel,
    cmd_cal_compass,
    cmd_cal_gyro,
    cmd_cal_level,
    cmd_log_cancel,
    cmd_log_download,
    cmd_log_list,
    cmd_param_load,
    cmd_param_request_all,
    cmd_param_save,
    cmd_param_set,
)

if TYPE_CHECKING:
    from ..drone_link import DroneLink


_DISPATCH = {
    'arm': cmd_arm,
    'disarm': cmd_disarm,
    'force_disarm': cmd_force_disarm,
    'rtl': cmd_rtl,
    'mode': cmd_mode,
    'takeoff': cmd_takeoff,
    'drop': cmd_drop,
    'drop_stop': cmd_drop_stop,
    'mission_start': cmd_mission_start,
    'mission_clear': cmd_mission_clear,
    'mission_upload': cmd_mission_upload,
    'fence_upload': cmd_fence_upload,
    'mission_download': cmd_mission_download,
    'rally_upload': cmd_rally_upload,
    'set_vtype': cmd_set_vtype,
    'guided_goto': cmd_guided_goto,
    'switch_vehicle': cmd_switch_vehicle,
    'clear_summary': cmd_clear_summary,
    'cal_compass': cmd_cal_compass,
    'cal_accel': cmd_cal_accel,
    'cal_gyro': cmd_cal_gyro,
    'cal_level': cmd_cal_level,
    'cal_baro': cmd_cal_baro,
    'cal_cancel': cmd_cal_cancel,
    'param_request_all': cmd_param_request_all,
    'param_set': cmd_param_set,
    'param_save': cmd_param_save,
    'param_load': cmd_param_load,
    'log_list': cmd_log_list,
    'log_download': cmd_log_download,
    'log_cancel': cmd_log_cancel,
    'reboot': cmd_reboot,
    'reboot_bootloader': cmd_reboot_bootloader,
    'inspector_toggle': cmd_inspector_toggle,
    'serial_control': cmd_serial_control,
    'inject_rtcm': cmd_inject_rtcm,
    'rc_override': cmd_rc_override,
    'motor_test': cmd_motor_test,
    'motor_test_stop': cmd_motor_test_stop,
    'gimbal_angle': cmd_gimbal_angle,
    'gimbal_rate': cmd_gimbal_rate,
    'camera_trigger': cmd_camera_trigger,
    'camera_video_start': cmd_camera_video_start,
    'camera_video_stop': cmd_camera_video_stop,
    'camera_zoom': cmd_camera_zoom,
    'do_set_roi': cmd_do_set_roi,
}


def execute(cmd: str, param, link: DroneLink, data: dict | None = None) -> dict | None:
    data = data or {}
    handler = _DISPATCH.get(cmd)
    if handler:
        try:
            return handler(link, param, data)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("Command '%s' failed", cmd)
            return {'ok': False, 'error': str(exc)[:200]}
    return None
