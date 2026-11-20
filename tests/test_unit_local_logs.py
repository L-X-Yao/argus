"""The local flight-log list and delete routes."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.config import cfg
from backend.drone_link import DroneLink
from backend.ws_manager import WSManager

client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _setup_app_state():
    if not hasattr(app.state, "link"):
        app.state.link = DroneLink()
        app.state.ws_mgr = WSManager(app.state.link)
    yield


class TestLocalLogs:
    def test_lists_tlogs_and_marks_the_active_session(self, tmp_path, monkeypatch):
        (tmp_path / "argus_a.tlog").write_bytes(b"\x00" * 10)
        (tmp_path / "argus_a.csv").write_text("x", encoding="utf-8")
        (tmp_path / "argus_b.tlog").write_bytes(b"\x00" * 20)
        (tmp_path / "assistant_audit.jsonl").write_text("{}\n", encoding="utf-8")
        monkeypatch.setattr(cfg, "LOG_DIR", tmp_path)
        with patch.object(app.state.link, "get_log_path", return_value=str(tmp_path / "argus_a.csv")):
            r = client.get("/api/logs")
        files = r.json()["files"]
        assert [f["name"] for f in files] == ["argus_b.tlog", "argus_a.tlog"] or [f["name"] for f in files] == [
            "argus_a.tlog",
            "argus_b.tlog",
        ]
        by_name = {f["name"]: f for f in files}
        assert by_name["argus_a.tlog"]["active"] is True
        assert by_name["argus_b.tlog"]["active"] is False
        assert "assistant_audit.jsonl" not in by_name

    def test_delete_removes_the_tlog_and_its_csv(self, tmp_path, monkeypatch):
        (tmp_path / "argus_a.tlog").write_bytes(b"a")
        (tmp_path / "argus_a.csv").write_text("a", encoding="utf-8")
        (tmp_path / "argus_b.tlog").write_bytes(b"b")
        (tmp_path / "argus_b.csv").write_text("b", encoding="utf-8")
        monkeypatch.setattr(cfg, "LOG_DIR", tmp_path)
        with patch.object(app.state.link, "get_log_path", return_value=str(tmp_path / "argus_a.csv")):
            r = client.post("/api/logs/delete", json={"names": ["argus_b.tlog"]})
        assert r.json() == {"ok": True, "deleted": ["argus_b.tlog"], "refused": []}
        assert not (tmp_path / "argus_b.tlog").exists()
        assert not (tmp_path / "argus_b.csv").exists()
        assert (tmp_path / "argus_a.tlog").exists()

    def test_delete_refuses_the_active_session_and_bad_names(self, tmp_path, monkeypatch):
        (tmp_path / "argus_a.tlog").write_bytes(b"a")
        monkeypatch.setattr(cfg, "LOG_DIR", tmp_path)
        with patch.object(app.state.link, "get_log_path", return_value=str(tmp_path / "argus_a.csv")):
            r = client.post(
                "/api/logs/delete",
                json={"names": ["argus_a.tlog", "../argus_a.tlog", "nope.tlog"]},
            )
        assert r.json()["deleted"] == []
        assert set(r.json()["refused"]) == {"argus_a.tlog", "../argus_a.tlog", "nope.tlog"}
        assert (tmp_path / "argus_a.tlog").exists()

    def test_delete_rejects_a_body_that_is_not_a_name_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cfg, "LOG_DIR", tmp_path)
        r = client.post("/api/logs/delete", json={"names": "argus_a.tlog"})
        assert r.json()["ok"] is False

    def test_a_name_that_cannot_be_a_path_is_refused_not_a_500(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cfg, "LOG_DIR", tmp_path)
        r = client.post("/api/logs/delete", json={"names": ["a\u0000.tlog", "x" * 5000 + ".tlog"]})
        assert r.status_code == 200
        assert r.json()["deleted"] == []
        assert len(r.json()["refused"]) == 2
