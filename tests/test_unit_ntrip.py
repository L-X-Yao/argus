"""Tests for backend/commands/_ntrip.py — additional coverage for uncovered paths."""

import socket
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from backend.commands._ntrip import _inject_chunk, _ntrip_loop, cmd_ntrip_start, cmd_ntrip_stop
from backend.drone_link import DroneLink


def make_link():
    link = DroneLink()
    link._ser = MagicMock()
    link.connected = True
    link.vehicle.sysid = 1
    return link


class TestInjectChunk:
    def test_first_flag(self):
        link = make_link()
        _inject_chunk(link, b"\xd3" * 10, is_first=True, is_last=False)
        assert link._ser.write.called

    def test_last_flag(self):
        link = make_link()
        _inject_chunk(link, b"\xd3" * 10, is_first=False, is_last=True)
        assert link._ser.write.called

    def test_both_flags(self):
        link = make_link()
        _inject_chunk(link, b"\xd3" * 10, is_first=True, is_last=True)
        assert link._ser.write.called


class TestNtripLoopEdgeCases:
    def test_header_too_large(self, monkeypatch):
        sock = MagicMock()
        sock.recv.return_value = b"X" * 512
        monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: sock)

        link = make_link()
        stop = threading.Event()
        t = threading.Thread(target=_ntrip_loop, args=(link, "h", 1, "M", "u", "p", stop), daemon=True)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive()
        event_types = [e["event_type"] for e in link.events]
        assert "ntrip_error" in event_types

    def test_connection_closed_during_header(self, monkeypatch):
        sock = MagicMock()
        sock.recv.return_value = b""
        monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: sock)

        link = make_link()
        stop = threading.Event()
        t = threading.Thread(target=_ntrip_loop, args=(link, "h", 1, "M", "u", "p", stop), daemon=True)
        t.start()
        t.join(timeout=3)
        event_types = [e["event_type"] for e in link.events]
        assert "ntrip_error" in event_types

    def test_header_timeout(self, monkeypatch):
        sock = MagicMock()
        sock.recv.side_effect = TimeoutError("read timeout")
        monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: sock)

        link = make_link()
        stop = threading.Event()
        t = threading.Thread(target=_ntrip_loop, args=(link, "h", 1, "M", "u", "p", stop), daemon=True)
        t.start()
        t.join(timeout=3)
        event_types = [e["event_type"] for e in link.events]
        assert "ntrip_error" in event_types

    def test_http_v2_200_accepted(self, monkeypatch):
        sock = MagicMock()
        calls = {"n": 0}

        def fake_recv(_n):
            calls["n"] += 1
            if calls["n"] == 1:
                return b"HTTP/1.1 200 OK\r\nContent-Type: gnss\r\n\r\n"
            if calls["n"] <= 3:
                return b"\xd3" * 50
            return b""

        sock.recv.side_effect = fake_recv
        monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: sock)

        link = make_link()
        stop = threading.Event()
        t = threading.Thread(target=_ntrip_loop, args=(link, "h", 1, "M", "u", "p", stop), daemon=True)
        t.start()
        t.join(timeout=3)
        event_types = [e["event_type"] for e in link.events]
        assert "ntrip_connected" in event_types

    def test_the_caster_is_told_which_argus_asks(self, monkeypatch):
        """A caster logs its clients. The request named version 3.4.0 for as long as it existed."""
        from backend.config import VERSION

        sock = MagicMock()
        sock.recv.side_effect = [b"HTTP/1.1 200 OK\r\n\r\n", b""]
        monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: sock)
        stop = threading.Event()
        t = threading.Thread(target=_ntrip_loop, args=(make_link(), "h", 1, "M", "u", "p", stop), daemon=True)
        t.start()
        t.join(timeout=3)
        stop.set()
        request = sock.sendall.call_args.args[0]
        assert f"User-Agent: NTRIP Argus/{VERSION}\r\n".encode() in request

    def test_lf_only_header_separator(self, monkeypatch):
        sock = MagicMock()
        calls = {"n": 0}

        def fake_recv(_n):
            calls["n"] += 1
            if calls["n"] == 1:
                return b"ICY 200 OK\n\n"
            return b""

        sock.recv.side_effect = fake_recv
        monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: sock)

        link = make_link()
        stop = threading.Event()
        t = threading.Thread(target=_ntrip_loop, args=(link, "h", 1, "M", "u", "p", stop), daemon=True)
        t.start()
        t.join(timeout=3)
        event_types = [e["event_type"] for e in link.events]
        assert "ntrip_connected" in event_types

    def test_recv_timeout_continues(self, monkeypatch):
        """recv timeout during stream should not terminate — only EOF does."""
        sock = MagicMock()
        calls = {"n": 0}

        def fake_recv(_n):
            calls["n"] += 1
            if calls["n"] == 1:
                return b"ICY 200 OK\r\n\r\n"
            if calls["n"] <= 3:
                raise TimeoutError()
            if calls["n"] == 4:
                return b"\xd3" * 10
            return b""

        sock.recv.side_effect = fake_recv
        monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: sock)

        link = make_link()
        stop = threading.Event()
        t = threading.Thread(target=_ntrip_loop, args=(link, "h", 1, "M", "u", "p", stop), daemon=True)
        t.start()
        t.join(timeout=3)
        assert "ntrip_connected" in [e["event_type"] for e in link.events]
        assert link._ser.write.called


class TestPinnedConnection:
    """Audit 2026-11-16 L4: the connection goes to the addresses the guard
    checked, and asks by the name — a second resolution in between could
    hand the connection to a different machine than the one validated."""

    def test_start_connects_to_the_validated_address(self, monkeypatch):
        asked = []

        def fake_getaddrinfo(host, port, *a, **kw):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.7", port))]

        def fake_create_connection(addr, timeout=None):
            asked.append(addr)
            raise OSError("refused")

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        monkeypatch.setattr(socket, "create_connection", fake_create_connection)
        link = make_link()
        cmd_ntrip_start(link, None, {"host": "caster.example", "port": 2101, "mountpoint": "MNT"})
        deadline = time.time() + 5
        while time.time() < deadline and not any(e["event_type"] == "ntrip_error" for e in link.events):
            time.sleep(0.01)
        # Pre-fix this was ("caster.example", 2101): the loop resolved the
        # name a second time and connected to whatever it answered then.
        assert asked == [("203.0.113.7", 2101)]
        assert any(e["event_type"] == "ntrip_error" for e in link.events)

    def test_the_caster_is_asked_by_its_name_not_the_pinned_ip(self, monkeypatch):
        sock = MagicMock()
        sock.recv.side_effect = [b"ICY 200 OK\r\n\r\n", b""]

        def fake_getaddrinfo(host, port, *a, **kw):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.7", port))]

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: sock)
        link = make_link()
        cmd_ntrip_start(link, None, {"host": "caster.example", "port": 2101, "mountpoint": "MNT"})
        deadline = time.time() + 5
        while time.time() < deadline and not sock.sendall.called:
            time.sleep(0.01)
        request = sock.sendall.call_args.args[0]
        assert b"Host: caster.example\r\n" in request
        assert b"203.0.113.7" not in request

    def test_every_validated_address_is_tried_in_order(self, monkeypatch):
        asked = []

        def fake_getaddrinfo(host, port, *a, **kw):
            return [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::5", port)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.7", port)),
            ]

        def fake_create_connection(addr, timeout=None):
            asked.append(addr)
            if addr == ("2001:db8::5", 2101):
                raise OSError("v6 unreachable")
            ok = MagicMock()
            ok.recv.side_effect = [b"ICY 200 OK\r\n\r\n", b""]
            return ok

        monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
        monkeypatch.setattr(socket, "create_connection", fake_create_connection)
        link = make_link()
        cmd_ntrip_start(link, None, {"host": "caster.example", "port": 2101, "mountpoint": "MNT"})
        deadline = time.time() + 5
        while time.time() < deadline and "ntrip_connected" not in [e["event_type"] for e in link.events]:
            time.sleep(0.01)
        assert asked == [("2001:db8::5", 2101), ("203.0.113.7", 2101)]
        assert "ntrip_connected" in [e["event_type"] for e in link.events]


class TestPendingStartCancellation:
    @pytest.mark.parametrize("cancel", ["stop", "disconnect"])
    def test_stop_or_disconnect_invalidates_a_start_still_resolving(self, monkeypatch, cancel):
        entered = threading.Event()
        release = threading.Event()
        attempted = threading.Event()

        def resolving(host, port, *args, **kwargs):
            entered.set()
            release.wait(1)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.7", port))]

        def no_connection(*args, **kwargs):
            attempted.set()
            raise OSError("no connection")

        monkeypatch.setattr(socket, "getaddrinfo", resolving)
        monkeypatch.setattr(socket, "create_connection", no_connection)
        link = make_link()
        result = []
        caller = threading.Thread(
            target=lambda: result.append(
                cmd_ntrip_start(link, None, {"host": "caster.example", "port": 2101, "mountpoint": "MNT"})
            ),
            daemon=True,
        )
        caller.start()
        assert entered.wait(1)
        if cancel == "stop":
            cmd_ntrip_stop(link, None, {})
        else:
            link.disconnect()
        release.set()
        caller.join(1)
        assert not caller.is_alive()
        assert result and result[0] is not None and result[0]["ok"] is False
        assert not attempted.wait(0.2)
        assert link.ntrip_thread is None


class TestCmdNtripStartFullPath:
    def test_ssrf_guard_rejects_loopback(self):
        link = make_link()
        with patch(
            "backend.commands._ntrip.socket.getaddrinfo",
            return_value=[
                (2, 1, 6, "", ("127.0.0.1", 2101)),
            ],
        ):
            r = cmd_ntrip_start(
                link,
                None,
                {
                    "host": "evil.com",
                    "port": 2101,
                    "mountpoint": "M",
                    "username": "u",
                    "password": "p",
                },
            )
        assert r and r["ok"] is False
        assert r["error"]  # non-empty error message (locale-dependent)

    def test_dns_failure_rejected(self):
        link = make_link()
        with patch("backend.commands._ntrip.socket.getaddrinfo", side_effect=socket.gaierror("nope")):
            r = cmd_ntrip_start(
                link,
                None,
                {
                    "host": "nonexistent.example",
                    "port": 2101,
                    "mountpoint": "M",
                },
            )
        assert r and r["ok"] is False
        assert r["error"]  # non-empty error message (locale-dependent)

    @pytest.mark.parametrize("address", ["192.168.1.50", "10.8.0.2", "100.64.0.9"])
    def test_a_base_station_on_the_local_network_is_accepted(self, address):
        link = make_link()
        with (
            patch("backend.commands._ntrip.socket.getaddrinfo", return_value=[(2, 1, 6, "", (address, 2101))]),
            patch("backend.commands._ntrip.threading.Thread") as thread,
        ):
            r = cmd_ntrip_start(link, None, {"host": "base.lan", "port": 2101, "mountpoint": "M"})
        assert not r or r.get("ok") is not False
        assert thread.called

    @pytest.mark.parametrize(
        "address", ["169.254.169.254", "0.0.0.0", "::1", "::ffff:127.0.0.1", "fd00:ec2::254", "100.100.100.200"]
    )
    def test_this_machine_and_link_local_are_refused(self, address):
        link = make_link()
        with (
            patch("backend.commands._ntrip.socket.getaddrinfo", return_value=[(2, 1, 6, "", (address, 2101))]),
            patch("backend.commands._ntrip.threading.Thread") as thread,
        ):
            r = cmd_ntrip_start(link, None, {"host": "evil.example", "port": 2101, "mountpoint": "M"})
        assert r == {"ok": False, "error": "NTRIP 主机解析到本机或链路本地地址"}
        assert not thread.called

    def test_a_fake_ip_from_a_proxy_tool_is_not_private(self):
        link = make_link()
        with (
            patch("backend.commands._ntrip.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("198.18.0.52", 2101))]),
            patch("backend.commands._ntrip.threading.Thread"),
        ):
            r = cmd_ntrip_start(link, None, {"host": "rtk.example.com", "port": 2101, "mountpoint": "M"})
        assert not r or r.get("ok") is not False

    def test_already_running_rejected(self):
        link = make_link()
        fake_thread = MagicMock()
        fake_thread.is_alive.return_value = True
        link.ntrip_thread = fake_thread
        with patch(
            "backend.commands._ntrip.socket.getaddrinfo",
            return_value=[
                (2, 1, 6, "", ("93.184.216.34", 2101)),
            ],
        ):
            r = cmd_ntrip_start(
                link,
                None,
                {
                    "host": "rtk.example.com",
                    "port": 2101,
                    "mountpoint": "M",
                },
            )
        assert r and r["ok"] is False
        assert r["error"]  # non-empty error (locale-dependent)

    def test_successful_start_spawns_thread(self):
        link = make_link()
        with (
            patch(
                "backend.commands._ntrip.socket.getaddrinfo",
                return_value=[
                    (2, 1, 6, "", ("93.184.216.34", 2101)),
                ],
            ),
            patch("backend.commands._ntrip.socket.create_connection", side_effect=OSError("refused")),
        ):
            cmd_ntrip_start(
                link,
                None,
                {
                    "host": "rtk.example.com",
                    "port": 2101,
                    "mountpoint": "M",
                    "username": "u",
                    "password": "p",
                },
            )
        # Thread was spawned (even though it will fail immediately)
        import time

        time.sleep(0.5)
        assert link.ntrip_thread is None  # thread exited after connection error

    def test_crlf_in_host_rejected(self):
        """CRLF in host would inject an extra HTTP header — must be rejected."""
        link = make_link()
        r = cmd_ntrip_start(
            link,
            None,
            {
                "host": "rtk.example.com\r\nX-Evil: injected",
                "port": 2101,
                "mountpoint": "M",
                "username": "u",
                "password": "p",
            },
        )
        assert r and r["ok"] is False
        assert r["error"]

    def test_crlf_in_credentials_rejected(self):
        link = make_link()
        r = cmd_ntrip_start(
            link,
            None,
            {
                "host": "rtk.example.com",
                "port": 2101,
                "mountpoint": "M",
                "username": "admin\r\n",
                "password": "pass",
            },
        )
        assert r and r["ok"] is False
        assert r["error"]  # non-empty error (locale-dependent)


class TestCmdNtripStop:
    def test_stop_sets_event(self):
        link = make_link()
        stop_event = threading.Event()
        link.ntrip_stop = stop_event
        cmd_ntrip_stop(link, None, {})
        assert stop_event.is_set()

    def test_stop_noop_when_none(self):
        link = make_link()
        cmd_ntrip_stop(link, None, {})  # must not raise
