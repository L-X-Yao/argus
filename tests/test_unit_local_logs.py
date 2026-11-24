"""The local flight-log list and delete routes."""

import os
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
        assert r.json() == {"ok": True, "deleted": ["argus_b.tlog"], "refused": [], "csv_left": []}
        assert not (tmp_path / "argus_b.tlog").exists()
        assert not (tmp_path / "argus_b.csv").exists()
        assert (tmp_path / "argus_a.tlog").exists()

    def test_a_csv_held_by_another_program_is_reported_as_left_behind(self, tmp_path, monkeypatch):
        # On Windows a spreadsheet holds the CSV it shows. The flight log goes all the same,
        # and the answer says which CSV stayed: before, the name was refused after its
        # tlog had been deleted.
        (tmp_path / "argus_b.tlog").write_bytes(b"b")
        (tmp_path / "argus_b.csv").write_text("b", encoding="utf-8")
        monkeypatch.setattr(cfg, "LOG_DIR", tmp_path)
        real_unlink = os.unlink

        def held_csv(path, *args, **kwargs):
            if str(path).endswith(".csv"):
                raise PermissionError(13, "held open by another program")
            return real_unlink(path, *args, **kwargs)

        monkeypatch.setattr(os, "unlink", held_csv)
        r = client.post("/api/logs/delete", json={"names": ["argus_b.tlog"]})
        assert r.json() == {"ok": True, "deleted": ["argus_b.tlog"], "refused": [], "csv_left": ["argus_b.tlog"]}
        assert not (tmp_path / "argus_b.tlog").exists()
        assert (tmp_path / "argus_b.csv").exists()

    def test_a_link_to_the_active_sessions_tlog_is_refused_and_not_listed(self, tmp_path, monkeypatch):
        # The route goes by the folder's entries and follows no link: before, resolving the
        # name led to the active session's own file, past the check that keeps it.
        (tmp_path / "argus_a.tlog").write_bytes(b"a")
        (tmp_path / "alias.tlog").symlink_to(tmp_path / "argus_a.tlog")
        monkeypatch.setattr(cfg, "LOG_DIR", tmp_path)
        with patch.object(app.state.link, "get_log_path", return_value=str(tmp_path / "argus_a.csv")):
            listed = [f["name"] for f in client.get("/api/logs").json()["files"]]
            r = client.post("/api/logs/delete", json={"names": ["alias.tlog"]})
        assert listed == ["argus_a.tlog"]
        assert r.json() == {"ok": True, "deleted": [], "refused": ["alias.tlog"], "csv_left": []}
        assert (tmp_path / "argus_a.tlog").exists()
        assert (tmp_path / "alias.tlog").is_symlink()

    def test_a_link_out_of_the_folder_is_refused(self, tmp_path, monkeypatch):
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "x.tlog").write_bytes(b"x")
        logs = tmp_path / "logs"
        logs.mkdir()
        (logs / "link.tlog").symlink_to(outside / "x.tlog")
        monkeypatch.setattr(cfg, "LOG_DIR", logs)
        r = client.post("/api/logs/delete", json={"names": ["link.tlog"]})
        assert r.json()["deleted"] == []
        assert (outside / "x.tlog").exists()

    def test_a_name_that_differs_only_in_case_from_the_active_file_is_refused(self, tmp_path, monkeypatch):
        # On a case-insensitive file system that is the active session's file under another
        # name; on a case-sensitive one no such entry exists. Either way it is not deleted.
        (tmp_path / "argus_a.tlog").write_bytes(b"a")
        monkeypatch.setattr(cfg, "LOG_DIR", tmp_path)
        with patch.object(app.state.link, "get_log_path", return_value=str(tmp_path / "argus_a.csv")):
            r = client.post("/api/logs/delete", json={"names": ["ARGUS_A.tlog"]})
        assert r.json()["deleted"] == []
        assert (tmp_path / "argus_a.tlog").exists()

    def test_the_same_name_twice_is_answered_once(self, tmp_path, monkeypatch):
        (tmp_path / "argus_b.tlog").write_bytes(b"b")
        monkeypatch.setattr(cfg, "LOG_DIR", tmp_path)
        r = client.post("/api/logs/delete", json={"names": ["argus_b.tlog", "argus_b.tlog"]})
        assert r.json() == {"ok": True, "deleted": ["argus_b.tlog"], "refused": [], "csv_left": []}

    def test_a_folder_that_is_a_link_is_taken_as_its_target(self, tmp_path, monkeypatch):
        # The logs folder itself may be a link (a folder on another disk); what is in it
        # is the operator's sessions all the same.
        real = tmp_path / "real"
        real.mkdir()
        (real / "argus_b.tlog").write_bytes(b"b")
        link = tmp_path / "logs"
        try:
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"this system does not make folder links: {exc}")
        monkeypatch.setattr(cfg, "LOG_DIR", link)
        r = client.post("/api/logs/delete", json={"names": ["argus_b.tlog"]})
        assert r.json()["deleted"] == ["argus_b.tlog"]
        assert not (real / "argus_b.tlog").exists()

    def test_with_no_logs_folder_every_name_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cfg, "LOG_DIR", tmp_path / "missing")
        r = client.post("/api/logs/delete", json={"names": ["argus_b.tlog"]})
        assert r.json() == {"ok": True, "deleted": [], "refused": ["argus_b.tlog"], "csv_left": []}

    def test_a_tlog_the_system_will_not_remove_is_refused_and_its_csv_stays(self, tmp_path, monkeypatch):
        (tmp_path / "argus_b.tlog").write_bytes(b"b")
        (tmp_path / "argus_b.csv").write_text("b", encoding="utf-8")
        monkeypatch.setattr(cfg, "LOG_DIR", tmp_path)
        real_unlink = os.unlink

        def held_tlog(path, *args, **kwargs):
            if str(path).endswith(".tlog"):
                raise PermissionError(13, "held open by another program")
            return real_unlink(path, *args, **kwargs)

        monkeypatch.setattr(os, "unlink", held_tlog)
        r = client.post("/api/logs/delete", json={"names": ["argus_b.tlog"]})
        assert r.json() == {"ok": True, "deleted": [], "refused": ["argus_b.tlog"], "csv_left": []}
        assert (tmp_path / "argus_b.tlog").exists()
        assert (tmp_path / "argus_b.csv").exists()

    def test_the_active_session_is_refused_before_any_file_is_touched(self, tmp_path, monkeypatch):
        # Not left to the operating system: Windows would refuse to unlink the file this
        # backend holds open, Linux and macOS would not.
        (tmp_path / "argus_a.tlog").write_bytes(b"a")
        monkeypatch.setattr(cfg, "LOG_DIR", tmp_path)
        calls = []
        real_unlink = os.unlink

        def record(path, *args, **kwargs):
            calls.append(os.fspath(path))
            return real_unlink(path, *args, **kwargs)

        monkeypatch.setattr(os, "unlink", record)
        with patch.object(app.state.link, "get_log_path", return_value=str(tmp_path / "argus_a.csv")):
            r = client.post("/api/logs/delete", json={"names": ["argus_a.tlog"]})
        assert r.json()["refused"] == ["argus_a.tlog"]
        assert calls == []
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
