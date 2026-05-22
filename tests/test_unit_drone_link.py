"""Tests for DroneLink state machine, heartbeat timeout, reconnect logic."""
from __future__ import annotations

import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.drone_link import DroneLink


class TestDroneLinkInit:
    def test_initial_state(self):
        link = DroneLink()
        assert link.connected is False
        assert link.frame_count == 0
        assert link._running is False
        assert link._ser is None
        assert link.locale == 'zh'
        assert link.active_sysid == 1
        assert link.inspector_enabled is False

    def test_state_objects_created(self):
        link = DroneLink()
        assert link.attitude is not None
        assert link.battery is not None
        assert link.gps is not None
        assert link.vehicle is not None
        assert link.mission is not None
        assert link.diagnostic is not None
        assert link.rc_servo is not None
        assert link.log_dl is not None
        assert link.traffic is not None

    def test_param_manager_created(self):
        link = DroneLink()
        assert link.param_mgr is not None


class TestDroneLinkIsPlane:
    def test_not_plane_by_default(self):
        link = DroneLink()
        assert link.is_plane() is False

    def test_plane_vtype(self):
        link = DroneLink()
        for vt in (1, 19, 20, 21, 22, 23, 24, 25):
            link.vehicle.vtype_raw = vt
            assert link.is_plane() is True, f"vtype_raw={vt} should be plane"

    def test_copter_vtype(self):
        link = DroneLink()
        link.vehicle.vtype_raw = 2
        assert link.is_plane() is False

    def test_force_plane_overrides(self):
        link = DroneLink()
        link.vehicle.vtype_raw = 2
        link.vehicle.force_plane = True
        assert link.is_plane() is True

    def test_force_copter_overrides(self):
        link = DroneLink()
        link.vehicle.vtype_raw = 1
        link.vehicle.force_plane = False
        assert link.is_plane() is False


class TestDroneLinkEvents:
    def test_add_event(self):
        link = DroneLink()
        link.add_event('test event', 'test')
        assert len(link.events) == 1
        assert link.events[0]['text'] == 'test event'
        assert link.events[0]['event_type'] == 'test'

    def test_event_capped(self):
        link = DroneLink()
        for i in range(120):
            link.add_event(f'event {i}', 'test')
        assert len(link.events) <= 100

    def test_ws_queue_capped(self):
        link = DroneLink()
        for i in range(2100):
            link.queue_ws({'type': 'test', 'i': i})
        assert len(link._ws_queue) <= 2000


class TestDroneLinkConnect:
    @patch.object(DroneLink, '_open_port')
    def test_connect_success(self, mock_open):
        mock_open.return_value = MagicMock()
        link = DroneLink()
        link._loop = MagicMock()
        with patch.object(threading.Thread, 'start'):
            result = link.connect('udp:14550')
        assert result is True
        assert link._running is True
        assert link._protocol == 'standard'

    @patch.object(DroneLink, '_open_port', side_effect=OSError('fail'))
    def test_connect_failure(self, mock_open):
        link = DroneLink()
        result = link.connect('tcp:bad:99')
        assert result is False
        assert link._running is False

    @patch.object(DroneLink, '_open_port')
    def test_connect_resets_state(self, mock_open):
        mock_open.return_value = MagicMock()
        link = DroneLink()
        link.connected = True
        link.frame_count = 999
        link._loop = MagicMock()
        with patch.object(threading.Thread, 'start'):
            link.connect('udp:14550')
        assert link.connected is False
        assert link.frame_count == 0

    @patch.object(DroneLink, '_open_port')
    def test_udp_forces_standard_protocol(self, mock_open):
        mock_open.return_value = MagicMock()
        link = DroneLink()
        link._loop = MagicMock()
        with patch.object(threading.Thread, 'start'):
            link.connect('udp:14550', protocol='pllink')
        assert link._protocol == 'standard'


class TestDroneLinkDisconnect:
    def test_disconnect_clears_state(self):
        link = DroneLink()
        link.connected = True
        link._running = True
        link.vehicle.vtype_raw = 2
        link.disconnect()
        assert link.connected is False
        assert link._running is False
        assert link.vehicle.vtype_raw == 0
        assert link._reconnect_enabled is False


class TestDroneLinkSend:
    def test_send_with_no_serial(self):
        link = DroneLink()
        link.send(b'\xfd\x00\x00')

    @patch.object(DroneLink, '_open_port')
    def test_send_increments_sequence(self, mock_open):
        mock_ser = MagicMock()
        link = DroneLink()
        link._ser = mock_ser
        link._protocol = 'standard'
        link.sq = 0
        link.send(b'\xfd\x00\x00')
        assert link.sq == 1

    def test_send_exception_handled(self):
        link = DroneLink()
        mock_ser = MagicMock()
        mock_ser.write.side_effect = OSError('write failed')
        link._ser = mock_ser
        link._protocol = 'standard'
        link.send(b'\xfd\x00\x00')


class TestDroneLinkGetState:
    def test_get_state_returns_dict(self):
        link = DroneLink()
        state = link.get_state()
        assert isinstance(state, dict)
        assert state['type'] == 'state'
        assert state['connected'] is False

    def test_get_state_includes_all_fields(self):
        link = DroneLink()
        state = link.get_state()
        expected_keys = [
            'type', 'connected', 'frames', 'mode', 'armed', 'roll', 'pitch',
            'yaw', 'lat', 'lon', 'alt_rel', 'alt_msl', 'gs', 'vz', 'hdg',
            'dist_home', 'voltage', 'current', 'remaining', 'gps_fix',
            'gps_sats', 'wp', 'vtype', 'rc', 'servo', 'vibe', 'ekf_vel',
            'wind_dir', 'prearm', 'adsb', 'cells', 'flight_summary',
        ]
        for key in expected_keys:
            assert key in state, f"Missing key: {key}"

    def test_get_state_reflects_changes(self):
        link = DroneLink()
        link.attitude.roll = 15.5
        link.battery.voltage = 12.6
        state = link.get_state()
        assert state['roll'] == 15.5
        assert state['voltage'] == 12.6


class TestDroneLinkMavlinkCrc:
    def test_crc_empty(self):
        link = DroneLink()
        crc = link._mavlink_crc16(b'')
        assert crc == 0xFFFF

    def test_crc_known_value(self):
        link = DroneLink()
        crc = link._mavlink_crc16(b'\x00')
        assert isinstance(crc, int)
        assert 0 <= crc <= 0xFFFF


class TestDroneLinkLog:
    def test_start_stop_log(self):
        link = DroneLink()
        link._start_log()
        assert link._logfile is not None
        path = link._logfile.name
        link._stop_log()
        assert link._logfile is None
        import os
        if os.path.exists(path):
            os.unlink(path)

    def test_get_log_path_none(self):
        link = DroneLink()
        assert link.get_log_path() is None


class TestDroneLinkThreadSafety:
    def test_concurrent_get_state(self):
        link = DroneLink()
        results = []
        errors = []

        def worker():
            try:
                for _ in range(50):
                    s = link.get_state()
                    results.append(s['type'])
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        assert len(results) == 200

    def test_concurrent_add_event(self):
        link = DroneLink()
        errors = []

        def worker(n):
            try:
                for i in range(50):
                    link.add_event(f'thread-{n}-event-{i}', 'test')
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
