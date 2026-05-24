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
        assert data['version'] == '3.4.0'
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


class TestTileProxy:
    def test_invalid_style_404(self):
        r = client.get('/api/tile/fakestyle/10/0/0')
        assert r.status_code == 404
        assert b'unknown tile style' in r.content

    def test_valid_style_no_network(self):
        with patch('backend.tiles.urlreq.urlopen', side_effect=OSError('no network')):
            r = client.get('/api/tile/osm/1/0/0')
        assert r.status_code in (200, 404)


class TestTerrain:
    def test_empty_points(self):
        r = client.get('/api/terrain/elevation?points=')
        assert r.status_code == 200
        assert r.json()['elevations'] == []

    def test_no_points_param(self):
        r = client.get('/api/terrain/elevation')
        assert r.status_code == 200
        assert r.json()['elevations'] == []

    def test_invalid_coords_filtered(self):
        r = client.get('/api/terrain/elevation?points=999,999;abc,def')
        assert r.status_code == 200
        assert r.json()['elevations'] == []

    def test_valid_point_returns_one(self):
        r = client.get('/api/terrain/elevation?points=30.5,120.3')
        assert r.status_code == 200
        assert len(r.json()['elevations']) == 1

    def test_multiple_valid_points(self):
        r = client.get('/api/terrain/elevation?points=30.5,120.3;31.0,121.0')
        assert r.status_code == 200
        assert len(r.json()['elevations']) == 2


class TestFirmwareUpload:
    def test_non_apj_rejected(self):
        r = client.post(
            '/api/firmware/upload',
            files={'file': ('test.exe', b'\x00', 'application/octet-stream')},
        )
        data = r.json()
        assert data['ok'] is False

    def test_empty_filename_rejected(self):
        r = client.post(
            '/api/firmware/upload',
            files={'file': ('', b'\x00', 'application/octet-stream')},
        )
        data = r.json()
        assert data.get('ok') is False or 'error' in data or r.status_code >= 400

    def test_valid_apj_accepted(self, tmp_path):
        import backend.firmware as fw_mod
        with patch.object(fw_mod, 'FIRMWARE_DIR', tmp_path):
            r = client.post(
                '/api/firmware/upload',
                files={'file': ('test.apj', b'\x00' * 100, 'application/octet-stream')},
            )
        data = r.json()
        assert data['ok'] is True
        assert data['filename'] == 'test.apj'
        assert data['size'] == 100

    def test_dotfile_apj_rejected(self):
        r = client.post(
            '/api/firmware/upload',
            files={'file': ('.apj', b'\x00', 'application/octet-stream')},
        )
        data = r.json()
        assert data['ok'] is False


class TestFirmwareDownload:
    def test_missing_url_rejected(self):
        r = client.post('/api/firmware/download', json={'url': '', 'filename': 'fw.apj'})
        data = r.json()
        assert data['ok'] is False

    def test_http_url_rejected(self):
        r = client.post('/api/firmware/download', json={'url': 'http://example.com/fw.apj', 'filename': 'fw.apj'})
        data = r.json()
        assert data['ok'] is False
        assert 'HTTPS' in data['error']

    def test_non_apj_filename_rejected(self):
        r = client.post('/api/firmware/download', json={'url': 'https://example.com/fw.bin', 'filename': 'fw.bin'})
        data = r.json()
        assert data['ok'] is False


class TestMbtilesTraversal:
    def test_dotdot_rejected(self):
        r = client.get('/api/mbtiles/../../etc/passwd.mbtiles/0/0/0')
        assert r.status_code == 404

    def test_nonexistent_file(self):
        r = client.get('/api/mbtiles/region.mbtiles/10/512/512')
        assert r.status_code == 404


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

    def test_video_private_ip_rejected(self):
        r = client.get('/api/video?url=rtsp://192.168.1.1:554/stream')
        assert r.status_code == 200
        data = r.json()
        assert 'error' in data
        assert 'Invalid' in data['error']

    def test_video_file_scheme_rejected(self):
        r = client.get('/api/video?url=file:///etc/passwd')
        assert r.status_code == 200
        data = r.json()
        assert 'error' in data


class TestFirmwareOnline:
    def test_unknown_board_id(self):
        r = client.get('/api/firmware/online?board_id=999')
        data = r.json()
        assert 'error' in data
        assert data['versions'] == []

    def test_default_board_id_zero(self):
        r = client.get('/api/firmware/online')
        data = r.json()
        assert data['versions'] == []
        assert 'error' in data

    def test_valid_board_parses_html(self):
        html = (
            '<html><body>'
            '<a href="firmware-v4.6.3.apj">firmware-v4.6.3.apj</a>'
            '<a href="firmware-v4.5.7.apj">firmware-v4.5.7.apj</a>'
            '<a href="README.md">README.md</a>'
            '</body></html>'
        )
        mock_resp = type('R', (), {'read': lambda self, n: html.encode()})()
        with patch('backend.firmware.urlreq.urlopen', return_value=mock_resp):
            r = client.get('/api/firmware/online?board_id=56')
        data = r.json()
        assert len(data['versions']) == 2
        assert data['versions'][0]['version'] == '4.6.3'
        assert data['versions'][1]['version'] == '4.5.7'
        assert data['versions'][0]['url'].endswith('firmware-v4.6.3.apj')

    def test_network_error_returns_empty(self):
        with patch('backend.firmware.urlreq.urlopen', side_effect=OSError('timeout')):
            r = client.get('/api/firmware/online?board_id=56')
        data = r.json()
        assert data['versions'] == []

    def test_max_10_versions(self):
        links = ''.join(f'<a href="fw-v1.0.{i}.apj">fw</a>' for i in range(20))
        html = f'<html>{links}</html>'
        mock_resp = type('R', (), {'read': lambda self, n: html.encode()})()
        with patch('backend.firmware.urlreq.urlopen', return_value=mock_resp):
            r = client.get('/api/firmware/online?board_id=56')
        data = r.json()
        assert len(data['versions']) == 10


class TestSecurityHeaders:
    def test_nosniff(self):
        r = client.get('/health')
        assert r.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_frame_deny(self):
        r = client.get('/health')
        assert r.headers.get('X-Frame-Options') == 'DENY'

    def test_referrer_policy(self):
        r = client.get('/health')
        assert r.headers.get('Referrer-Policy') == 'strict-origin-when-cross-origin'

    def test_headers_on_api_route(self):
        r = client.get('/api/version')
        assert r.headers.get('X-Content-Type-Options') == 'nosniff'
        assert r.headers.get('X-Frame-Options') == 'DENY'


class TestWebSocketGuards:
    def test_bad_origin_rejected_4003(self):
        from starlette.websockets import WebSocketDisconnect
        with pytest.raises(WebSocketDisconnect) as exc, \
             client.websocket_connect('/ws', headers={'origin': 'https://evil.com'}):
            pass
        assert exc.value.code == 4003

    def test_allowed_origin_accepted(self):
        with client.websocket_connect('/ws', headers={'origin': 'http://localhost:5173'}) as ws:
            ws.send_json({'type': 'disconnect'})

    def test_no_origin_accepted(self):
        with client.websocket_connect('/ws') as ws:
            ws.send_json({'type': 'disconnect'})


class TestParamMeta:
    def test_param_meta_returns(self):
        r = client.get('/api/param_meta')
        assert r.status_code == 200
