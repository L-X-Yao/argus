"""Unit tests: command builder and mission upload logic."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.drone_link import DroneLink


def make_link():
    link = DroneLink()
    link._ser = MagicMock()
    link.connected = True
    link.vehicle.sysid = 1
    return link


class TestCommandExecute:
    def test_arm_sends(self):
        from backend import commands
        link = make_link()
        commands.execute('arm', None, link)
        assert link._ser.write.called

    def test_disarm_sends(self):
        from backend import commands
        link = make_link()
        commands.execute('disarm', None, link)
        assert link._ser.write.called

    def test_force_disarm_sends(self):
        from backend import commands
        link = make_link()
        commands.execute('force_disarm', None, link)
        assert link._ser.write.called

    def test_rtl_copter(self):
        from backend import commands
        link = make_link()
        link.vehicle.vtype_raw = 2
        commands.execute('rtl', None, link)
        assert any('返航' in e['text'] for e in link.events)

    def test_rtl_plane(self):
        from backend import commands
        link = make_link()
        link.vehicle.vtype_raw = 1
        commands.execute('rtl', None, link)
        assert any('返航' in e['text'] for e in link.events)

    def test_mode_change(self):
        from backend import commands
        link = make_link()
        commands.execute('mode', 5, link)
        assert any('模式' in e['text'] for e in link.events)

    def test_takeoff(self):
        from backend import commands
        link = make_link()
        commands.execute('takeoff', None, link, data={'alt': 50})
        assert any('起飞' in e['text'] for e in link.events)

    def test_drop(self):
        from backend import commands
        link = make_link()
        commands.execute('drop', None, link)
        assert any('投放' in e['text'] for e in link.events)

    def test_set_vtype_plane(self):
        from backend import commands
        link = make_link()
        commands.execute('set_vtype', None, link, data={'vtype': 'plane'})
        assert link.vehicle.force_plane is True

    def test_set_vtype_auto(self):
        from backend import commands
        link = make_link()
        commands.execute('set_vtype', None, link, data={'vtype': 'auto'})
        assert link.vehicle.force_plane is None

    def test_clear_summary(self):
        from backend import commands
        link = make_link()
        link.vehicle.flight_summary = {'duration': 100}
        commands.execute('clear_summary', None, link)
        assert link.vehicle.flight_summary is None

    # -- 20 new command tests below --

    def test_drop_stop(self):
        from backend import commands
        link = make_link()
        commands.execute('drop_stop', None, link)
        assert any('投放停止' in e['text'] for e in link.events)

    def test_mission_start_copter(self):
        from backend import commands
        link = make_link()
        link.vehicle.vtype_raw = 2  # copter
        commands.execute('mission_start', None, link)
        assert any('任务开始' in e['text'] for e in link.events)
        assert link._ser.write.called

    def test_mission_start_plane(self):
        from backend import commands
        link = make_link()
        link.vehicle.vtype_raw = 1  # plane
        commands.execute('mission_start', None, link)
        assert any('任务开始' in e['text'] for e in link.events)

    def test_mission_clear(self):
        from backend import commands
        link = make_link()
        commands.execute('mission_clear', None, link)
        assert any('任务已清除' in e['text'] for e in link.events)

    def test_fence_upload_sets_pending(self):
        from backend import commands
        link = make_link()
        polygon = [
            {'lat': 34.0, 'lon': 108.0},
            {'lat': 34.1, 'lon': 108.0},
            {'lat': 34.1, 'lon': 108.1},
        ]
        commands.execute('fence_upload', None, link, data={'polygon': polygon})
        assert link.mission._fence_pending is True
        assert len(link.mission._fence_items) == 3
        assert any('围栏' in e['text'] for e in link.events)

    def test_fence_upload_too_few_points(self):
        from backend import commands
        link = make_link()
        result = commands.execute('fence_upload', None, link, data={
            'polygon': [{'lat': 34.0, 'lon': 108.0}, {'lat': 34.1, 'lon': 108.0}],
        })
        assert result is not None and not result['ok']
        assert '3' in result['error']

    def test_guided_goto(self):
        from backend import commands
        link = make_link()
        link.vehicle.vtype_raw = 2  # copter
        commands.execute('guided_goto', None, link, data={
            'lat': 34.25800, 'lon': 108.94200, 'alt': 50,
        })
        assert any('引导飞往' in e['text'] and '34.25800' in e['text'] for e in link.events)

    def test_cal_compass(self):
        from backend import commands
        link = make_link()
        commands.execute('cal_compass', None, link)
        assert any('罗盘校准' in e['text'] for e in link.events)

    def test_cal_accel(self):
        from backend import commands
        link = make_link()
        commands.execute('cal_accel', None, link)
        assert any('加速度计校准' in e['text'] for e in link.events)

    def test_cal_gyro(self):
        from backend import commands
        link = make_link()
        commands.execute('cal_gyro', None, link)
        assert any('陀螺仪校准' in e['text'] for e in link.events)

    def test_cal_level(self):
        from backend import commands
        link = make_link()
        commands.execute('cal_level', None, link)
        assert any('水平校准' in e['text'] for e in link.events)

    def test_cal_baro(self):
        from backend import commands
        link = make_link()
        commands.execute('cal_baro', None, link)
        assert any('气压计校准' in e['text'] for e in link.events)

    def test_cal_cancel(self):
        from backend import commands
        link = make_link()
        commands.execute('cal_cancel', None, link)
        assert any('取消' in e['text'] for e in link.events)

    def test_mission_download(self):
        from backend import commands
        link = make_link()
        commands.execute('mission_download', None, link)
        assert link.mission._dl_pending is True
        assert link.mission._dl_total == 0
        assert link.mission._dl_items == []
        assert any('下载' in e['text'] for e in link.events)

    def test_param_request_all(self):
        from backend import commands
        link = make_link()
        commands.execute('param_request_all', None, link)
        assert link.param_mgr.fetching is True

    def test_param_set(self):
        from backend import commands
        link = make_link()
        commands.execute('param_set', None, link, data={'name': 'ARMING_CHECK', 'value': 0})
        assert any('ARMING_CHECK' in e['text'] for e in link.events)

    def test_param_save(self):
        from backend import commands
        link = make_link()
        link.param_mgr.params = {
            'ARMING_CHECK': {'name': 'ARMING_CHECK', 'value': 1.0, 'type': 9, 'index': 0},
        }
        result = commands.execute('param_save', None, link)
        assert result is not None and result['ok']
        assert result['path'].endswith('.json')
        # clean up
        import os
        if os.path.exists(result['path']):
            os.remove(result['path'])

    def test_param_load(self):
        from backend import commands
        link = make_link()
        # pre-populate a param so load_from_file detects a change
        link.param_mgr.params = {
            'ARMING_CHECK': {'name': 'ARMING_CHECK', 'value': 1.0, 'type': 9, 'index': 0},
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'ARMING_CHECK': 0.0}, f)
            tmp_path = f.name
        result = commands.execute('param_load', None, link, data={'path': tmp_path})
        assert result is not None and result['ok']
        assert 'ARMING_CHECK' in result['changed']
        import os
        os.remove(tmp_path)

    def test_log_list(self):
        from backend import commands
        link = make_link()
        commands.execute('log_list', None, link)
        assert link.log_dl._log_list == []
        assert any('日志' in e['text'] for e in link.events)

    def test_log_download(self):
        from backend import commands
        link = make_link()
        link.log_dl._log_list = [{'id': 5, 'size': 10240}]
        commands.execute('log_download', None, link, data={'id': 5})
        assert link.log_dl._log_download_id == 5
        assert link.log_dl._log_download_size == 10240
        assert any('下载 #5' in e['text'] for e in link.events)

    def test_log_download_invalid_id(self):
        from backend import commands
        link = make_link()
        link.log_dl._log_list = [{'id': 5, 'size': 10240}]
        result = commands.execute('log_download', None, link, data={'id': 99})
        assert result is not None and not result['ok']

    def test_log_cancel(self):
        from backend import commands
        link = make_link()
        link.log_dl._log_download_id = 5
        commands.execute('log_cancel', None, link)
        assert link.log_dl._log_download_id == -1
        assert any('取消' in e['text'] for e in link.events)

    def test_rc_override(self):
        from backend import commands
        link = make_link()
        channels = [1500, 1500, 1100, 1500, 1000, 1000, 1000, 1000]
        commands.execute('rc_override', None, link, data={'channels': channels})
        assert link._ser.write.called


class TestMissionUpload:
    def test_empty_waypoints_returns_error(self):
        from backend import commands
        link = make_link()
        result = commands.execute('mission_upload', None, link, data={'waypoints': []})
        assert result and not result['ok']

    def test_invalid_coords_returns_error(self):
        from backend import commands
        link = make_link()
        result = commands.execute('mission_upload', None, link, data={
            'waypoints': [{'lat': 0, 'lon': 0, 'alt': 30}],
        })
        assert result and not result['ok']

    def test_valid_mission(self):
        from backend import commands
        link = make_link()
        wps = [
            {'lat': 34.258, 'lon': 108.942, 'alt': 30},
            {'lat': 34.259, 'lon': 108.943, 'alt': 30, 'drop': True},
        ]
        commands.execute('mission_upload', None, link, data={
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
