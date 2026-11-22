"""The SIM button's on-demand simulator start."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend import sim_launcher
from backend.app import app


class FakeProc:
    def __init__(self, code=None):
        self.code = code
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return 0


def _probe(values):
    """A port probe that also pins the argument: a timeout passed as the port made the
    launcher wait 10 s against port 0.1 while the simulator was already listening."""
    seq = iter(values)

    def probe(*args, **kwargs):
        assert not args or args[0] == sim_launcher.SIM_PORT
        return next(seq)

    return probe


@pytest.fixture(autouse=True)
def _reset_proc(monkeypatch):
    monkeypatch.setattr(sim_launcher, "_proc", None)
    monkeypatch.setattr(sim_launcher, "_port_open", _probe([False] * 100))
    monkeypatch.setattr(sim_launcher, "_simulator_script", lambda: None)


def test_already_running_is_not_started_again(monkeypatch):
    monkeypatch.setattr(sim_launcher, "_port_open", _probe([True]))
    with patch.object(sim_launcher.subprocess, "Popen") as popen:
        assert sim_launcher.start_simulator() == {"ok": True, "started": False}
    popen.assert_not_called()


def test_missing_script_names_the_manual_launcher():
    result = sim_launcher.start_simulator()
    assert result["ok"] is False
    assert "simulator.py" in result["error"] and "启动仿真器.bat" in result["error"]


def test_starts_the_bundled_script_and_waits_for_the_port(tmp_path, monkeypatch):
    script = tmp_path / "simulator.py"
    script.write_text("", encoding="utf-8")
    proc = FakeProc()
    monkeypatch.setattr(sim_launcher, "_simulator_script", lambda: script)
    monkeypatch.setattr(sim_launcher, "_port_open", _probe([False, False, True]))
    with patch.object(sim_launcher.subprocess, "Popen", return_value=proc) as popen:
        result = sim_launcher.start_simulator()
    assert result == {"ok": True, "started": True}
    args, kwargs = popen.call_args
    assert args[0][1:] == [str(script), str(sim_launcher.SIM_PORT)]
    assert kwargs["cwd"] == str(sim_launcher.ROOT_DIR)
    assert kwargs["stdin"] is sim_launcher.subprocess.DEVNULL
    assert kwargs["stdout"] is sim_launcher.subprocess.DEVNULL
    assert sim_launcher._proc is proc


def test_a_second_click_reuses_the_process_started_by_the_first(tmp_path, monkeypatch):
    script = tmp_path / "simulator.py"
    script.write_text("", encoding="utf-8")
    proc = FakeProc()
    monkeypatch.setattr(sim_launcher, "_simulator_script", lambda: script)
    monkeypatch.setattr(sim_launcher, "_port_open", _probe([False, False, True, True]))
    with patch.object(sim_launcher.subprocess, "Popen", return_value=proc) as popen:
        sim_launcher.start_simulator()
        assert sim_launcher.start_simulator() == {"ok": True, "started": False}
    assert popen.call_count == 1


def test_a_script_that_exits_reports_the_code(tmp_path, monkeypatch):
    script = tmp_path / "simulator.py"
    script.write_text("", encoding="utf-8")
    proc = FakeProc(code=1)
    monkeypatch.setattr(sim_launcher, "_simulator_script", lambda: script)
    monkeypatch.setattr(sim_launcher, "_port_open", _probe([False, False, False]))
    with patch.object(sim_launcher.subprocess, "Popen", return_value=proc):
        result = sim_launcher.start_simulator()
    assert result["ok"] is False
    assert "exited with code 1" in result["error"]


def test_spawn_failure_is_returned_not_raised(tmp_path, monkeypatch):
    script = tmp_path / "simulator.py"
    script.write_text("", encoding="utf-8")
    monkeypatch.setattr(sim_launcher, "_simulator_script", lambda: script)
    with patch.object(sim_launcher.subprocess, "Popen", side_effect=OSError("denied")):
        result = sim_launcher.start_simulator()
    assert result == {"ok": False, "error": "denied"}


def test_timeout_terminates_the_child(tmp_path, monkeypatch):
    script = tmp_path / "simulator.py"
    script.write_text("", encoding="utf-8")
    proc = FakeProc()
    monkeypatch.setattr(sim_launcher, "_simulator_script", lambda: script)
    monkeypatch.setattr(sim_launcher, "START_TIMEOUT", 0)
    with patch.object(sim_launcher.subprocess, "Popen", return_value=proc):
        result = sim_launcher.start_simulator()
    assert result["ok"] is False
    assert "did not open" in result["error"]
    assert proc.terminated


def test_stop_terminates_only_a_simulator_it_started():
    proc = FakeProc()
    sim_launcher._proc = proc
    sim_launcher.stop_simulator()
    assert proc.terminated
    assert sim_launcher._proc is None
    # A simulator started by hand has no _proc and is left alone.
    sim_launcher.stop_simulator()


def test_route_returns_the_launcher_answer():
    client = TestClient(app, base_url="http://localhost")
    with patch("backend.app.start_simulator", return_value={"ok": True, "started": True}):
        response = client.post("/api/simulator/start")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "started": True}
