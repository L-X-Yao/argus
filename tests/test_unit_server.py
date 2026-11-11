"""Tests for backend/server.py — sidecar entry point."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.auth import note_for_other_devices, refuse_if_exposed
from backend.config import allowed_origins, cfg
from backend.server import _open_browser, main


class TestOpenBrowser:
    @patch("webbrowser.open")
    @patch("urllib.request.urlopen")
    def test_opens_browser_after_health_ok(self, mock_urlopen, mock_open):
        mock_urlopen.return_value = MagicMock()
        _open_browser(8100)
        mock_open.assert_called_once_with("http://localhost:8100")

    @patch("webbrowser.open")
    @patch("urllib.request.urlopen", side_effect=OSError("not ready"))
    def test_retries_on_failure(self, mock_urlopen, mock_open):
        _open_browser(8100)
        assert mock_urlopen.call_count == 30
        mock_open.assert_not_called()


class TestMain:
    @patch("backend.server.uvicorn.run")
    def test_default_args(self, mock_run):
        # Patch Thread: without --no-browser, main() spawns a daemon that
        # polls http://127.0.0.1:8100/health every 0.3s for ~9s. Left running,
        # that thread's real urlopen leaks into whatever test patches urlopen
        # next (backend.tiles.urlreq is the same module object) — a cross-test
        # flake that fails test_unit_tile_proxy's assert_called_once.
        with patch("sys.argv", ["server.py"]), patch("backend.server.threading.Thread"):
            main()
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs["port"] == 8100
        assert call_kwargs.kwargs["host"] == "127.0.0.1"

    @patch("backend.server.uvicorn.run")
    def test_custom_port(self, mock_run):
        with patch("sys.argv", ["server.py", "--port", "9000", "--no-browser"]):
            main()
        assert mock_run.call_args.kwargs["port"] == 9000

    @patch("backend.server.uvicorn.run")
    def test_no_browser_flag(self, mock_run):
        with patch("sys.argv", ["server.py", "--no-browser"]), patch("backend.server.threading.Thread") as mock_thread:
            main()
            mock_thread.assert_not_called()


class TestExposure:
    """Whoever reaches the websocket can arm the vehicle, so a token comes before the network."""

    @pytest.mark.parametrize("host", ["0.0.0.0", "::", "", "192.168.1.5", "argus.lan"])
    def test_anything_beyond_this_machine_needs_a_token(self, host):
        with patch("backend.auth.auth_required", return_value=False), pytest.raises(SystemExit) as refused:
            refuse_if_exposed(host)
        assert "GCS_AUTH_TOKEN" in str(refused.value)

    @pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "localhost", "LOCALHOST"])
    def test_this_machine_needs_none(self, host):
        with patch("backend.auth.auth_required", return_value=False):
            refuse_if_exposed(host)

    def test_a_token_opens_the_network(self):
        with patch("backend.auth.auth_required", return_value=True):
            refuse_if_exposed("0.0.0.0")

    @patch("backend.server.uvicorn.run")
    def test_the_package_does_not_start(self, serve):
        argv = ["server.py", "--host", "0.0.0.0", "--no-browser"]
        with (
            patch("sys.argv", argv),
            patch("backend.auth.auth_required", return_value=False),
            pytest.raises(SystemExit),
        ):
            main()
        serve.assert_not_called()

    def test_the_launcher_does_not_start_either(self, monkeypatch):
        import run
        from backend.config import cfg

        monkeypatch.setattr(cfg, "HOST", cfg.HOST)  # parse_args writes these, and this puts them back
        monkeypatch.setattr(cfg, "PORT", cfg.PORT)
        with (
            patch("sys.argv", ["run.py", "--host", "0.0.0.0", "--sim"]),
            patch("backend.auth.auth_required", return_value=False),
            patch("uvicorn.run") as serve,
            patch("run.subprocess.Popen") as simulator,
            pytest.raises(SystemExit),
        ):
            run.main()
        serve.assert_not_called()
        simulator.assert_not_called()


class TestNoteForOtherDevices:
    """A phone on the network gets the page, and then a refusal at the login that nothing on
    the phone can explain. The console Argus was started from is where it can be said."""

    ORIGINS = ["http://localhost:8100", "http://127.0.0.1:8100"]
    FOUND = patch("backend.auth._address_on_the_network", return_value="192.168.1.5")

    @pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "localhost"])
    def test_nothing_to_say_on_this_machine(self, host):
        assert note_for_other_devices(host, 8100, self.ORIGINS) is None

    VALUE = "  http://localhost:8100,http://127.0.0.1:8100,http://192.168.1.5:8100"

    @pytest.mark.parametrize("host", ["0.0.0.0", ""])
    def test_gives_the_address_and_the_value_that_lists_it(self, host):
        with self.FOUND:
            note = note_for_other_devices(host, 8100, self.ORIGINS)
        assert note.startswith("From another device, open http://192.168.1.5:8100,")
        assert self.VALUE in note.splitlines()
        # A guess: a hotspot this machine provides puts the other device on another address.
        assert "names the address to add" in note

    def test_no_shell_syntax_in_it(self):
        # The Windows package runs in cmd, where NAME=value is no command.
        with self.FOUND:
            note = note_for_other_devices("0.0.0.0", 8100, self.ORIGINS)
        assert "ARGUS_CORS_ORIGINS=" not in note

    def test_gives_only_the_address_once_it_is_listed(self):
        with self.FOUND:
            note = note_for_other_devices("0.0.0.0", 8100, [*self.ORIGINS, "http://192.168.1.5:8100"])
        assert "http://192.168.1.5:8100" in note
        assert "Set ARGUS_CORS_ORIGINS" not in note

    def test_an_address_to_listen_on_is_the_address_to_open(self):
        note = note_for_other_devices("10.0.0.7", 8200, self.ORIGINS)
        assert note.startswith("From another device, open http://10.0.0.7:8200.")
        assert "192.168" not in note
        assert "names the address to add" not in note

    # _from_own_page compares the Origin header as text: the note has to write it as browsers do.
    @pytest.mark.parametrize("host", ["fd00::7", "FD00:0:0::7"])
    def test_an_ipv6_address_is_written_as_a_browser_writes_it(self, host):
        assert "http://[fd00::7]:8100" in note_for_other_devices(host, 8100, self.ORIGINS)

    def test_a_name_is_written_in_lower_case(self):
        # The whole line, not a substring: CodeQL reads `"http://..." in text` as a URL check.
        note = note_for_other_devices("MyPC.lan", 8100, self.ORIGINS)
        assert note.splitlines()[0] == "From another device, open http://mypc.lan:8100."

    def test_port_80_is_left_out_as_a_browser_leaves_it_out(self):
        note = note_for_other_devices("192.168.1.5", 80, ["http://192.168.1.5"])
        assert note == "From another device, open http://192.168.1.5."

    @pytest.mark.parametrize("host", ["::", "0:0::0"])
    def test_every_ipv6_interface_gets_no_ipv4_address(self, host):
        # asyncio binds "::" for IPv6 only: an IPv4 address would find nothing listening.
        with self.FOUND:
            note = note_for_other_devices(host, 8100, self.ORIGINS)
        assert "192.168" not in note
        assert "IPv6" in note

    def test_says_what_is_needed_when_this_machine_has_no_address_to_give(self):
        with patch("backend.auth._address_on_the_network", return_value=None):
            note = note_for_other_devices("0.0.0.0", 8100, self.ORIGINS)
        assert "ARGUS_CORS_ORIGINS" in note

    def test_a_machine_without_a_network_gives_no_address(self):
        from backend.auth import _address_on_the_network

        with patch("backend.auth.socket.socket", side_effect=OSError("network is unreachable")):
            assert _address_on_the_network() is None

    def test_a_loopback_answer_is_no_address_for_another_device(self):
        from backend.auth import _address_on_the_network

        with patch("backend.auth.socket.socket") as made:
            made.return_value.__enter__.return_value.getsockname.return_value = ("127.0.0.1", 40000)
            assert _address_on_the_network() is None

    @patch("backend.server.uvicorn.run")
    def test_the_package_prints_it(self, serve, monkeypatch, capsys):
        monkeypatch.setattr(cfg, "HOST", cfg.HOST)  # main writes these, and this puts them back
        monkeypatch.setattr(cfg, "PORT", cfg.PORT)
        monkeypatch.delenv("ARGUS_CORS_ORIGINS", raising=False)
        argv = ["server.py", "--host", "0.0.0.0", "--port", "8100", "--no-browser"]
        with patch("sys.argv", argv), patch("backend.auth.auth_required", return_value=True), self.FOUND:
            main()
        serve.assert_called_once()
        assert "Set ARGUS_CORS_ORIGINS to" in capsys.readouterr().out

    @patch("backend.server.uvicorn.run")
    def test_the_package_prints_nothing_of_it_on_this_machine(self, serve, capsys):
        with patch("sys.argv", ["server.py", "--no-browser"]):
            main()
        assert "ARGUS_CORS_ORIGINS" not in capsys.readouterr().out

    def test_the_launcher_prints_it_too(self, monkeypatch, capsys):
        import run

        monkeypatch.setattr(cfg, "HOST", cfg.HOST)
        monkeypatch.setattr(cfg, "PORT", cfg.PORT)
        monkeypatch.setenv("ARGUS_NO_BROWSER", "1")
        monkeypatch.setenv("ARGUS_CORS_ORIGINS", "http://localhost:8100")
        with (
            patch("sys.argv", ["run.py", "--host", "0.0.0.0", "--port", "8100"]),
            patch("backend.auth.auth_required", return_value=True),
            patch("uvicorn.run") as serve,
            self.FOUND,
        ):
            run.main()
        serve.assert_called_once()
        assert "  http://localhost:8100,http://192.168.1.5:8100" in capsys.readouterr().out.splitlines()


class TestAllowedOrigins:
    def test_the_default_is_this_machine_on_the_port_given(self, monkeypatch):
        monkeypatch.delenv("ARGUS_CORS_ORIGINS", raising=False)
        assert allowed_origins(9000) == [
            "http://localhost:5173",
            "http://localhost:9000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:9000",
        ]

    def test_a_list_of_your_own_replaces_it(self, monkeypatch):
        monkeypatch.setenv("ARGUS_CORS_ORIGINS", " http://localhost:8100 , http://192.168.1.5:8100,")
        assert allowed_origins(9000) == ["http://localhost:8100", "http://192.168.1.5:8100"]
