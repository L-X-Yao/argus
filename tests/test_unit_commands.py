"""Unit tests: command builder and mission upload logic."""
import base64
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.commands import execute
from backend.drone_link import DroneLink


def make_link():
    link = DroneLink()
    link._ser = MagicMock()
    link.connected = True
    link.vehicle.sysid = 1
    return link


class TestCommandExecute:
    def test_arm_sends(self):
        link = make_link()
        execute('arm', None, link)
        assert link._ser.write.called

    def test_disarm_sends(self):
        link = make_link()
        execute('disarm', None, link)
        assert link._ser.write.called

    def test_force_disarm_sends(self):
        link = make_link()
        execute('force_disarm', None, link)
        assert link._ser.write.called

    def test_rtl_copter(self):
        link = make_link()
        link.vehicle.vtype_raw = 2
        execute('rtl', None, link)
        assert any('返航' in e['text'] for e in link.events)

    def test_rtl_plane(self):
        link = make_link()
        link.vehicle.vtype_raw = 1
        execute('rtl', None, link)
        assert any('返航' in e['text'] for e in link.events)

    def test_mode_change(self):
        link = make_link()
        execute('mode', 5, link)
        assert any('模式' in e['text'] for e in link.events)

    def test_takeoff(self):
        link = make_link()
        execute('takeoff', None, link, data={'alt': 50})
        assert any('起飞' in e['text'] for e in link.events)

    def test_drop(self):
        link = make_link()
        execute('drop', None, link)
        assert any('投放' in e['text'] for e in link.events)

    def test_set_vtype_plane(self):
        link = make_link()
        execute('set_vtype', None, link, data={'vtype': 'plane'})
        assert link.vehicle.force_plane is True

    def test_set_vtype_auto(self):
        link = make_link()
        execute('set_vtype', None, link, data={'vtype': 'auto'})
        assert link.vehicle.force_plane is None

    def test_clear_summary(self):
        link = make_link()
        link.vehicle.flight_summary = {'duration': 100}
        execute('clear_summary', None, link)
        assert link.vehicle.flight_summary is None

    def test_drop_stop(self):
        link = make_link()
        execute('drop_stop', None, link)
        assert any('投放停止' in e['text'] for e in link.events)

    def test_mission_start_copter(self):
        link = make_link()
        link.vehicle.vtype_raw = 2  # copter
        execute('mission_start', None, link)
        assert any('任务开始' in e['text'] for e in link.events)
        assert link._ser.write.called

    def test_mission_start_plane(self):
        link = make_link()
        link.vehicle.vtype_raw = 1  # plane
        execute('mission_start', None, link)
        assert any('任务开始' in e['text'] for e in link.events)

    def test_mission_clear(self):
        link = make_link()
        execute('mission_clear', None, link)
        assert any('任务已清除' in e['text'] for e in link.events)

    def test_fence_upload_sets_pending(self):
        link = make_link()
        polygon = [
            {'lat': 34.0, 'lon': 108.0},
            {'lat': 34.1, 'lon': 108.0},
            {'lat': 34.1, 'lon': 108.1},
        ]
        execute('fence_upload', None, link, data={'polygon': polygon})
        assert link.mission._fence_pending is True
        assert len(link.mission._fence_items) == 3
        assert any('围栏' in e['text'] for e in link.events)

    def test_fence_upload_too_few_points(self):
        link = make_link()
        result = execute('fence_upload', None, link, data={
            'polygon': [{'lat': 34.0, 'lon': 108.0}, {'lat': 34.1, 'lon': 108.0}],
        })
        assert result is not None and not result['ok']
        assert '3' in result['error']

    def test_guided_goto(self):
        link = make_link()
        link.vehicle.vtype_raw = 2  # copter
        execute('guided_goto', None, link, data={
            'lat': 34.25800, 'lon': 108.94200, 'alt': 50,
        })
        assert any('引导飞往' in e['text'] and '34.25800' in e['text'] for e in link.events)

    def test_cal_compass(self):
        link = make_link()
        execute('cal_compass', None, link)
        assert any('罗盘校准' in e['text'] for e in link.events)

    def test_cal_accel(self):
        link = make_link()
        execute('cal_accel', None, link)
        assert any('加速度计校准' in e['text'] for e in link.events)

    def test_cal_gyro(self):
        link = make_link()
        execute('cal_gyro', None, link)
        assert any('陀螺仪校准' in e['text'] for e in link.events)

    def test_cal_level(self):
        link = make_link()
        execute('cal_level', None, link)
        assert any('水平校准' in e['text'] for e in link.events)

    def test_cal_baro(self):
        link = make_link()
        execute('cal_baro', None, link)
        assert any('气压计校准' in e['text'] for e in link.events)

    def test_cal_cancel(self):
        link = make_link()
        execute('cal_cancel', None, link)
        assert any('取消' in e['text'] for e in link.events)

    def test_mission_download(self):
        link = make_link()
        execute('mission_download', None, link)
        assert link.mission._dl_pending is True
        assert link.mission._dl_total == 0
        assert link.mission._dl_items == []
        assert any('下载' in e['text'] for e in link.events)

    def test_param_request_all(self):
        link = make_link()
        execute('param_request_all', None, link)
        assert link.param_mgr.fetching is True

    def test_param_set(self):
        link = make_link()
        execute('param_set', None, link, data={'name': 'ARMING_CHECK', 'value': 0})
        assert any('ARMING_CHECK' in e['text'] for e in link.events)

    def test_param_save(self):
        link = make_link()
        link.param_mgr.params = {
            'ARMING_CHECK': {'name': 'ARMING_CHECK', 'value': 1.0, 'type': 9, 'index': 0},
        }
        result = execute('param_save', None, link)
        assert result is not None and result['ok']
        assert result['path'].endswith('.json')
        # clean up
        import os
        if os.path.exists(result['path']):
            os.remove(result['path'])

    def test_param_load(self):
        link = make_link()
        # pre-populate a param so load_from_file detects a change
        link.param_mgr.params = {
            'ARMING_CHECK': {'name': 'ARMING_CHECK', 'value': 1.0, 'type': 9, 'index': 0},
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'ARMING_CHECK': 0.0}, f)
            tmp_path = f.name
        result = execute('param_load', None, link, data={'path': tmp_path})
        assert result is not None and result['ok']
        assert 'ARMING_CHECK' in result['changed']
        import os
        os.remove(tmp_path)

    def test_log_list(self):
        link = make_link()
        execute('log_list', None, link)
        assert link.log_dl._log_list == []
        assert any('日志' in e['text'] for e in link.events)

    def test_log_download(self):
        link = make_link()
        link.log_dl._log_list = [{'id': 5, 'size': 10240}]
        execute('log_download', None, link, data={'id': 5})
        assert link.log_dl._log_download_id == 5
        assert link.log_dl._log_download_size == 10240
        assert any('下载 #5' in e['text'] for e in link.events)

    def test_log_download_invalid_id(self):
        link = make_link()
        link.log_dl._log_list = [{'id': 5, 'size': 10240}]
        result = execute('log_download', None, link, data={'id': 99})
        assert result is not None and not result['ok']

    def test_log_cancel(self):
        link = make_link()
        link.log_dl._log_download_id = 5
        execute('log_cancel', None, link)
        assert link.log_dl._log_download_id == -1
        assert any('取消' in e['text'] for e in link.events)

    def test_rc_override(self):
        link = make_link()
        channels = [1500, 1500, 1100, 1500, 1000, 1000, 1000, 1000]
        execute('rc_override', None, link, data={'channels': channels})
        assert link._ser.write.called


class TestReboot:
    def test_reboot(self):
        link = make_link()
        execute('reboot', None, link)
        assert any('重启飞控' in e['text'] for e in link.events)
        assert link._ser.write.called

    def test_reboot_bootloader(self):
        link = make_link()
        execute('reboot_bootloader', None, link)
        assert any('引导程序' in e['text'] for e in link.events)


class TestMotorTest:
    def test_motor_test(self):
        link = make_link()
        execute('motor_test', None, link, data={'motor': 0, 'throttle': 10, 'duration': 2})
        assert any('电机测试' in e['text'] for e in link.events)
        assert link._ser.write.called

    def test_motor_test_stop(self):
        link = make_link()
        execute('motor_test_stop', None, link)
        assert link._ser.write.call_count >= 8


class TestGimbal:
    def test_gimbal_angle(self):
        link = make_link()
        execute('gimbal_angle', None, link, data={'pitch': -30, 'yaw': 90})
        assert link._ser.write.called

    def test_gimbal_rate(self):
        link = make_link()
        execute('gimbal_rate', None, link, data={'pitch_rate': 10, 'yaw_rate': 5})
        assert link._ser.write.called


class TestCamera:
    def test_camera_trigger(self):
        link = make_link()
        execute('camera_trigger', None, link)
        assert link._ser.write.called

    def test_camera_video_start(self):
        link = make_link()
        execute('camera_video_start', None, link)
        assert link._ser.write.called

    def test_camera_video_stop(self):
        link = make_link()
        execute('camera_video_stop', None, link)
        assert link._ser.write.called

    def test_camera_zoom(self):
        link = make_link()
        execute('camera_zoom', None, link, data={'zoom': 2.5})
        assert link._ser.write.called


class TestSwitchVehicle:
    def test_switch_vehicle(self):
        link = make_link()
        execute('switch_vehicle', None, link, data={'sysid': 3})
        assert link.active_sysid == 3
        assert link.vehicle.sysid == 3
        assert any('sysid=3' in e['text'] for e in link.events)


class TestInjectRtcm:
    def test_inject_rtcm(self):
        link = make_link()
        raw_data = b'\x01\x02\x03\x04\x05'
        b64 = base64.b64encode(raw_data).decode()
        execute('inject_rtcm', None, link, data={'data': b64})
        assert link._ser.write.called

    def test_inject_rtcm_large(self):
        link = make_link()
        raw_data = b'\xAA' * 250
        b64 = base64.b64encode(raw_data).decode()
        execute('inject_rtcm', None, link, data={'data': b64})
        assert link._ser.write.call_count >= 3  # 250/110 = 3 chunks

    def test_inject_rtcm_empty(self):
        link = make_link()
        execute('inject_rtcm', None, link, data={'data': ''})
        assert not link._ser.write.called


class TestRallyUpload:
    def test_rally_upload(self):
        link = make_link()
        points = [
            {'lat': 30.0, 'lon': 120.0, 'alt': 100},
            {'lat': 30.1, 'lon': 120.1, 'alt': 100},
        ]
        execute('rally_upload', None, link, data={'points': points})
        assert any('备降点' in e['text'] for e in link.events)

    def test_rally_upload_empty(self):
        link = make_link()
        execute('rally_upload', None, link, data={'points': []})
        assert not any('备降' in e['text'] for e in link.events)


class TestSerialControl:
    def test_serial_control(self):
        link = make_link()
        execute('serial_control', None, link, data={'text': 'help\n'})
        assert link._ser.write.called

    def test_serial_control_empty(self):
        link = make_link()
        execute('serial_control', None, link, data={'text': ''})
        assert not link._ser.write.called


class TestDoSetRoi:
    def test_do_set_roi(self):
        link = make_link()
        execute('do_set_roi', None, link, data={'lat': 30.5, 'lon': 120.3, 'alt': 100})
        assert link._ser.write.called


class TestInspectorToggle:
    def test_toggle_on(self):
        link = make_link()
        assert link.inspector_enabled is False
        execute('inspector_toggle', None, link)
        assert link.inspector_enabled is True

    def test_toggle_off(self):
        link = make_link()
        link.inspector_enabled = True
        execute('inspector_toggle', None, link)
        assert link.inspector_enabled is False


class TestMissionUpload:
    def test_empty_waypoints_returns_error(self):
        link = make_link()
        result = execute('mission_upload', None, link, data={'waypoints': []})
        assert result and not result['ok']

    def test_invalid_coords_returns_error(self):
        link = make_link()
        result = execute('mission_upload', None, link, data={
            'waypoints': [{'lat': 0, 'lon': 0, 'alt': 30}],
        })
        assert result and not result['ok']

    def test_valid_mission(self):
        link = make_link()
        wps = [
            {'lat': 34.258, 'lon': 108.942, 'alt': 30},
            {'lat': 34.259, 'lon': 108.943, 'alt': 30, 'drop': True},
        ]
        execute('mission_upload', None, link, data={
            'waypoints': wps, 'takeoff_alt': 30,
        })
        assert link.mission._mission_pending
        # home(0) + takeoff(1) + wp1(2) + wp2(3) + drop(4) + RTL(5) = 6
        assert len(link.mission._mission_items) == 6
        assert any('任务' in e['text'] for e in link.events)


class TestDroneLinkLog:
    def test_start_stop_log(self):
        link = make_link()
        link._start_log()
        assert link._logfile is not None
        path = link.get_log_path()
        assert path is not None
        assert path.endswith('.csv')
        link._stop_log()
        assert link._logfile is None
        assert link.get_log_path() is None
        import os
        if os.path.exists(path):
            os.remove(path)

    def test_state_includes_log_active(self):
        link = make_link()
        assert link.get_state()['log_active'] is False
        link._start_log()
        assert link.get_state()['log_active'] is True
        link._stop_log()
        assert link.get_state()['log_active'] is False
        import glob
        import os
        for f in glob.glob(str(Path(__file__).resolve().parent.parent / 'logs' / '*.csv')):
            os.remove(f)


class TestDroneLink:
    def test_is_plane_copter(self):
        link = DroneLink()
        link.vehicle.vtype_raw = 2
        assert not link.is_plane()

    def test_is_plane_plane(self):
        link = DroneLink()
        link.vehicle.vtype_raw = 1
        assert link.is_plane()

    def test_force_plane_override(self):
        link = DroneLink()
        link.vehicle.vtype_raw = 2
        link.vehicle.force_plane = True
        assert link.is_plane()

    def test_add_event_trims(self):
        link = DroneLink()
        for i in range(150):
            link.add_event(f'event {i}')
        assert len(link.events) <= 100

    def test_get_state_structure(self):
        link = DroneLink()
        state = link.get_state()
        assert 'type' in state
        assert state['type'] == 'state'
        assert 'connected' in state
        assert 'mode' in state
        assert 'lat' in state
        assert 'voltage' in state
        assert 'flight_summary' in state
