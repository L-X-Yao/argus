"""Tests for backend/param_manager.py — MAVLink PARAM protocol."""
import json
import struct
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.param_manager import ParamManager


def _make_link() -> MagicMock:
    link = MagicMock()
    link.locale = 'en'
    link.vehicle.sysid = 1
    link.sq = 0
    return link


def _param_payload(name: str, value: float, index: int, total: int, ptype: int = 9) -> bytes:
    p = struct.pack('<f', value)
    p += struct.pack('<HH', total, index)
    p += name.encode('ascii')[:16].ljust(16, b'\x00')
    p += struct.pack('<B', ptype)
    return p


class TestParamManagerInit:
    def test_initial_state(self):
        link = _make_link()
        mgr = ParamManager(link)
        assert mgr.total_count == -1
        assert mgr.received_count == 0
        assert mgr.fetching is False
        assert len(mgr.params) == 0


class TestRequestAll:
    def test_clears_and_fetches(self):
        link = _make_link()
        mgr = ParamManager(link)
        mgr.params = {'old': {'value': 1}}
        mgr.request_all()
        assert len(mgr.params) == 0
        assert mgr.fetching is True
        assert mgr.total_count == -1
        link.send.assert_called_once()
        link.add_event.assert_called_once()


class TestHandleParamValue:
    def test_parses_single_param(self):
        link = _make_link()
        mgr = ParamManager(link)
        p = _param_payload('BATT_CAPACITY', 5000.0, 0, 3)
        mgr.handle_param_value(p, len(p))
        assert 'BATT_CAPACITY' in mgr.params
        assert mgr.params['BATT_CAPACITY']['value'] == 5000.0
        assert mgr.received_count == 1
        assert mgr.total_count == 3

    def test_duplicate_param_not_double_counted(self):
        link = _make_link()
        mgr = ParamManager(link)
        p = _param_payload('BATT_CAPACITY', 5000.0, 0, 3)
        mgr.handle_param_value(p, len(p))
        mgr.handle_param_value(p, len(p))
        assert mgr.received_count == 1

    def test_all_params_completes_fetch(self):
        link = _make_link()
        mgr = ParamManager(link)
        mgr.fetching = True
        names = ['PARAM_A', 'PARAM_B', 'PARAM_C']
        for i, name in enumerate(names):
            p = _param_payload(name, float(i), i, 3)
            mgr.handle_param_value(p, len(p))
        assert mgr.fetching is False
        assert mgr.received_count == 3

    def test_short_payload_ignored(self):
        link = _make_link()
        mgr = ParamManager(link)
        mgr.handle_param_value(b'\x00' * 10, 10)
        assert len(mgr.params) == 0

    def test_messages_capped(self):
        link = _make_link()
        mgr = ParamManager(link)
        mgr.fetching = True
        for i in range(2100):
            name = f'P{i:04d}'[:16]
            p = _param_payload(name, float(i), i, 2100)
            mgr.handle_param_value(p, len(p))
        assert len(mgr._messages) <= 2000


class TestSetParam:
    def test_sends_param_set(self):
        link = _make_link()
        mgr = ParamManager(link)
        mgr.params = {'THR_MAX': {'name': 'THR_MAX', 'value': 80.0, 'type': 9, 'index': 0}}
        mgr.set_param('THR_MAX', 90.0)
        link.send.assert_called_once()
        link.add_event.assert_called_once()

    def test_unknown_param_uses_default_type(self):
        link = _make_link()
        mgr = ParamManager(link)
        mgr.set_param('NEW_PARAM', 42.0)
        link.send.assert_called_once()


class TestSaveToFile:
    def test_saves_json(self):
        link = _make_link()
        mgr = ParamManager(link)
        mgr.params = {
            'A': {'name': 'A', 'value': 1.0, 'type': 9, 'index': 0},
            'B': {'name': 'B', 'value': 2.0, 'type': 9, 'index': 1},
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            path = f.name
        result = mgr.save_to_file(path)
        assert result == path
        with open(path) as f:
            data = json.load(f)
        assert data == {'A': 1.0, 'B': 2.0}
        Path(path).unlink()

    def test_auto_path(self):
        link = _make_link()
        mgr = ParamManager(link)
        mgr.params = {'X': {'name': 'X', 'value': 1.0, 'type': 9, 'index': 0}}
        path = mgr.save_to_file()
        assert Path(path).exists()
        Path(path).unlink()


class TestLoadFromFile:
    def test_loads_and_sets_changed(self):
        link = _make_link()
        mgr = ParamManager(link)
        mgr.params = {
            'A': {'name': 'A', 'value': 1.0, 'type': 9, 'index': 0},
            'B': {'name': 'B', 'value': 2.0, 'type': 9, 'index': 1},
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'A': 1.0, 'B': 5.0}, f)
            path = f.name
        changed = mgr.load_from_file(path)
        assert 'B' in changed
        assert 'A' not in changed
        Path(path).unlink()

    def test_invalid_json_returns_empty(self):
        link = _make_link()
        mgr = ParamManager(link)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('not json{{{')
            path = f.name
        changed = mgr.load_from_file(path)
        assert changed == []
        Path(path).unlink()

    def test_missing_file_returns_empty(self):
        link = _make_link()
        mgr = ParamManager(link)
        changed = mgr.load_from_file('/nonexistent/path.json')
        assert changed == []


class TestGetStatus:
    def test_returns_status_dict(self):
        link = _make_link()
        mgr = ParamManager(link)
        mgr.received_count = 50
        mgr.total_count = 100
        mgr.fetching = True
        status = mgr.get_status()
        assert status == {'param_count': 50, 'param_total': 100, 'param_fetching': True}
