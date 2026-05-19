"""Unit tests: command builder and mission upload logic."""
import struct
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.drone_link import DroneLink


def make_link():
    link = DroneLink()
    link._ser = MagicMock()
    link.connected = True
    link.sysid = 1
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
        link.vtype_raw = 2
        commands.execute('rtl', None, link)
        assert any('返航' in e['text'] for e in link.events)

    def test_rtl_plane(self):
        from backend import commands
        link = make_link()
        link.vtype_raw = 1
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
        assert link.force_plane is True

    def test_set_vtype_auto(self):
        from backend import commands
        link = make_link()
        commands.execute('set_vtype', None, link, data={'vtype': 'auto'})
        assert link.force_plane is None

    def test_clear_summary(self):
        from backend import commands
        link = make_link()
        link.flight_summary = {'duration': 100}
        commands.execute('clear_summary', None, link)
        assert link.flight_summary is None


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
        assert link._mission_pending
        # home(0) + takeoff(1) + wp1(2) + wp2(3) + drop(4) + RTL(5) = 6
        assert len(link._mission_items) == 6
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
        import os, glob
        for f in glob.glob(str(Path(__file__).resolve().parent.parent / 'logs' / '*.csv')):
            os.remove(f)


class TestDroneLink:
    def test_is_plane_copter(self):
        link = DroneLink()
        link.vtype_raw = 2
        assert not link.is_plane()

    def test_is_plane_plane(self):
        link = DroneLink()
        link.vtype_raw = 1
        assert link.is_plane()

    def test_force_plane_override(self):
        link = DroneLink()
        link.vtype_raw = 2
        link.force_plane = True
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
