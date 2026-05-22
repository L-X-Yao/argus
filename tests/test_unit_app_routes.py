"""Tests for backend/app.py — HTTP route coverage via TestClient."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.drone_link import DroneLink
from backend.ws_manager import WSManager

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _setup_app_state():
    """Ensure app.state.link and app.state.ws_mgr exist for route handlers."""
    if not hasattr(app.state, 'link'):
        app.state.link = DroneLink()
        app.state.ws_mgr = WSManager(app.state.link)
    yield


class TestHealthAndSystem:
    def test_health(self):
        r = client.get('/health')
        assert r.status_code == 200
        assert r.json()['ok'] is True

    def test_session(self):
        r = client.get('/api/session')
        assert r.status_code == 200
        data = r.json()
        assert 'connected' in data
        assert 'clients' in data
        assert 'armed' in data

    def test_version(self):
        r = client.get('/api/version')
        assert r.status_code == 200
        data = r.json()
        assert data['version'] == '3.3.0'
        assert 'protocols' in data
        assert 'pllink' in data['protocols']
        assert 'vehicles' in data

    def test_tile_sources(self):
        r = client.get('/api/tile_sources')
        assert r.status_code == 200
        data = r.json()
        assert 'amap' in data
        assert 'osm' in data

    def test_ports(self):
        r = client.get('/api/ports')
        assert r.status_code == 200
        data = r.json()
        assert 'ports' in data
        assert isinstance(data['ports'], list)


class TestAuth:
    def test_auth_status(self):
        r = client.get('/api/auth/status')
        assert r.status_code == 200
        assert 'auth_required' in r.json()

    def test_login_invalid_token(self):
        with patch('backend.auth._load_token', return_value='real_token'):
            r = client.post('/api/auth/login', json={'token': 'bad_token'})
        assert r.status_code == 401

    def test_generate_when_exists(self):
        with patch('backend.app.auth_required', return_value=True):
            r = client.post('/api/auth/generate')
        assert r.status_code == 403


class TestTileCache:
    def test_tile_cache_stats(self):
        r = client.get('/api/tile_cache')
        assert r.status_code == 200
        data = r.json()
        assert 'size' in data
        assert 'count' in data


class TestLog:
    def test_log_no_active(self):
        r = client.get('/api/log')
        assert r.status_code == 404


class TestFirmware:
    def test_firmware_list_empty(self):
        r = client.get('/api/firmware/list')
        assert r.status_code == 200
        assert 'files' in r.json()


class TestMbtiles:
    def test_mbtiles_list(self):
        r = client.get('/api/mbtiles/list')
        assert r.status_code == 200
        assert 'files' in r.json()


class TestVideo:
    def test_video_capabilities(self):
        r = client.get('/api/video/capabilities')
        assert r.status_code == 200
        data = r.json()
        assert 'mjpeg' in data
        assert 'webrtc' in data
        assert data['webrtc'] is False

    def test_video_stop(self):
        r = client.get('/api/video/stop')
        assert r.status_code == 200
        assert r.json()['ok'] is True

    def test_video_no_url(self):
        r = client.get('/api/video')
        assert r.status_code == 200
        data = r.json()
        assert 'error' in data
