"""Comprehensive unit tests for the video module.

Tests RTSP URL validation, video start/stop lifecycle, duplicate process
prevention, cleanup behavior, and capabilities endpoint.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backend.video as video_module
from backend.app import app
from backend.drone_link import DroneLink
from backend.video import _proc_lock
from backend.ws_manager import WSManager


@pytest.fixture(autouse=True)
def _reset_video_state():
    """Reset video module global state between tests."""
    with _proc_lock:
        video_module._active_proc = None
    yield
    with _proc_lock:
        video_module._active_proc = None


@pytest.fixture
def client():
    """FastAPI TestClient with app state initialized."""
    if not hasattr(app.state, 'link'):
        app.state.link = DroneLink()
        app.state.ws_mgr = WSManager(app.state.link)
    return TestClient(app, raise_server_exceptions=False)


class TestRtspUrlValidation:
    def test_empty_url_returns_error(self, client):
        r = client.get('/api/video')
        assert r.status_code == 200
        data = r.json()
        assert 'error' in data
        assert 'No video URL' in data['error']

    def test_empty_string_url_returns_error(self, client):
        r = client.get('/api/video?url=')
        assert r.status_code == 200
        data = r.json()
        assert 'error' in data

    @patch('backend.video._ffmpeg_available', return_value=False)
    def test_no_ffmpeg_returns_error(self, mock_ff, client):
        r = client.get('/api/video?url=rtsp://192.168.1.100:554/stream')
        assert r.status_code == 200
        data = r.json()
        assert 'error' in data
        assert 'ffmpeg' in data['error'].lower()

    @patch('backend.video._ffmpeg_available', return_value=True)
    @patch('subprocess.Popen')
    def test_valid_rtsp_url_starts_stream(self, mock_popen, mock_ff, client):
        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.read = MagicMock(return_value=b'')
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        mock_popen.return_value = mock_proc

        r = client.get('/api/video?url=rtsp://192.168.1.100:554/stream')
        assert r.status_code == 200

    @patch('backend.video._ffmpeg_available', return_value=True)
    @patch('subprocess.Popen')
    def test_http_url_accepted(self, mock_popen, mock_ff, client):
        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.read = MagicMock(return_value=b'')
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        mock_popen.return_value = mock_proc

        r = client.get('/api/video?url=http://example.com/live.m3u8')
        assert r.status_code == 200


class TestVideoLifecycle:
    @patch('backend.video._ffmpeg_available', return_value=True)
    @patch('subprocess.Popen')
    def test_start_creates_process(self, mock_popen, mock_ff, client):
        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.read = MagicMock(return_value=b'')
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        mock_popen.return_value = mock_proc

        r = client.get('/api/video?url=rtsp://10.0.0.1/cam')
        assert r.status_code == 200
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == 'ffmpeg'
        assert 'rtsp://10.0.0.1/cam' in args

    @patch('backend.video._ffmpeg_available', return_value=True)
    @patch('subprocess.Popen')
    def test_ffmpeg_args_include_mjpeg_output(self, mock_popen, mock_ff, client):
        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.read = MagicMock(return_value=b'')
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        mock_popen.return_value = mock_proc

        client.get('/api/video?url=rtsp://10.0.0.1/cam')
        args = mock_popen.call_args[0][0]
        assert '-f' in args
        idx = args.index('-f')
        assert args[idx + 1] == 'mjpeg'
        assert 'pipe:1' in args

    def test_stop_when_no_process(self, client):
        r = client.get('/api/video/stop')
        assert r.status_code == 200
        assert r.json()['ok'] is True

    def test_stop_kills_active_process(self, client):
        mock_proc = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        with _proc_lock:
            video_module._active_proc = mock_proc

        r = client.get('/api/video/stop')
        assert r.status_code == 200
        assert r.json()['ok'] is True
        mock_proc.kill.assert_called_once()
        with _proc_lock:
            assert video_module._active_proc is None


class TestDuplicateProcessPrevention:
    @patch('backend.video._ffmpeg_available', return_value=True)
    def test_starting_twice_kills_first_process(self, mock_ff, client):
        """Starting video a second time should kill the first process."""
        first_proc = MagicMock()
        first_proc.kill = MagicMock()
        first_proc.wait = MagicMock()
        with _proc_lock:
            video_module._active_proc = first_proc

        second_proc = MagicMock()
        second_proc.stdout = MagicMock()
        second_proc.stdout.read = MagicMock(return_value=b'')
        second_proc.kill = MagicMock()
        second_proc.wait = MagicMock()

        with patch('subprocess.Popen', return_value=second_proc):
            client.get('/api/video?url=rtsp://10.0.0.1/new')

        first_proc.kill.assert_called_once()


class TestCleanupOnStop:
    def test_stop_clears_global_reference(self, client):
        mock_proc = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = MagicMock()
        with _proc_lock:
            video_module._active_proc = mock_proc

        client.get('/api/video/stop')
        with _proc_lock:
            assert video_module._active_proc is None

    def test_stop_handles_process_already_dead(self, client):
        """Stop gracefully handles a process that raises on kill."""
        mock_proc = MagicMock()
        mock_proc.kill = MagicMock(side_effect=OSError('already dead'))
        mock_proc.wait = MagicMock()
        with _proc_lock:
            video_module._active_proc = mock_proc

        r = client.get('/api/video/stop')
        assert r.status_code == 200
        assert r.json()['ok'] is True


class TestVideoCapabilities:
    def test_capabilities_returns_correct_format(self, client):
        r = client.get('/api/video/capabilities')
        assert r.status_code == 200
        data = r.json()
        assert 'mjpeg' in data
        assert 'webrtc' in data
        assert 'protocols' in data
        assert isinstance(data['mjpeg'], bool)
        assert data['webrtc'] is False
        assert isinstance(data['protocols'], list)

    @patch('backend.video._ffmpeg_available', return_value=True)
    def test_capabilities_with_ffmpeg(self, mock_ff, client):
        r = client.get('/api/video/capabilities')
        data = r.json()
        assert data['mjpeg'] is True
        assert 'rtsp' in data['protocols']
        assert 'rtmp' in data['protocols']
        assert 'http' in data['protocols']

    @patch('backend.video._ffmpeg_available', return_value=False)
    def test_capabilities_without_ffmpeg(self, mock_ff, client):
        r = client.get('/api/video/capabilities')
        data = r.json()
        assert data['mjpeg'] is False
        assert data['protocols'] == []
