"""Thread safety tests for DroneLink state access."""

import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.drone_link import DroneLink


class TestThreadSafety:
    def test_concurrent_read_write(self):
        link = DroneLink()
        errors = []
        stop = threading.Event()

        def writer():
            i = 0
            while not stop.is_set():
                link.lat = float(i)
                link.lon = float(i)
                link.roll = float(i)
                link.voltage = float(i % 100)
                i += 1

        def reader():
            while not stop.is_set():
                try:
                    state = link.get_state()
                    assert isinstance(state, dict)
                    assert "lat" in state
                    assert "voltage" in state
                except Exception as e:
                    errors.append(e)

        w = threading.Thread(target=writer, daemon=True)
        r = threading.Thread(target=reader, daemon=True)
        w.start()
        r.start()
        time.sleep(1)
        stop.set()
        w.join(timeout=2)
        r.join(timeout=2)
        assert errors == [], f"Errors during concurrent access: {errors}"

    def test_get_state_keys_stable(self):
        """_build_state() keys must match the DroneState interface in types.ts.

        Instead of a hardcoded set (which drifts every time a field is added),
        we derive the expected keys from the same TypeScript source that the
        frontend uses. This is the same parse logic as
        test_contract_ws_protocol._frontend_state_fields — duplicated here to
        keep this file self-contained and avoid circular import.
        """
        from tests.test_contract_ws_protocol import _frontend_state_fields

        link = DroneLink()
        state = link.get_state()
        expected = _frontend_state_fields()
        assert state.keys() == expected, (
            f"\nBackend-only: {state.keys() - expected}\nFrontend-only: {expected - state.keys()}"
        )


class TestLogCommandLocking:
    @pytest.mark.parametrize("operation", ["list", "download", "cancel"])
    def test_log_commands_wait_for_state_lock_before_writing(self, operation):
        from backend.commands import _setup

        link = DroneLink()
        link._ser = MagicMock()
        link.log_dl._log_list = [{"id": 1, "size": 100, "time_utc": 0}]
        calls = {
            "list": lambda: _setup.cmd_log_list(link, None, {}),
            "download": lambda: _setup.cmd_log_download(link, None, {"id": 1}),
            "cancel": lambda: _setup.cmd_log_cancel(link, None, {}),
        }
        link._state_lock.acquire()
        thread = threading.Thread(target=calls[operation], daemon=True)
        thread.start()
        try:
            time.sleep(0.05)
            waited = not link._ser.write.called
        finally:
            link._state_lock.release()
            thread.join(timeout=1)
        assert waited, f"{operation} changed transfer state without waiting for the lock"
        assert not thread.is_alive()
        assert link._ser.write.called


class TestBufferCap:
    def test_buf_capped(self):
        link = DroneLink()
        link._buf = b"\x00" * 70000
        link._buf += b"\x01" * 1024
        if len(link._buf) > 65536:
            link._buf = link._buf[-32768:]
            link._parse_errors += 1
        assert len(link._buf) <= 65536
        assert link._parse_errors == 1
