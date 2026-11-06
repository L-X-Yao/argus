"""Tests for backend/server.py — sidecar entry point."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.auth import refuse_if_exposed
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
