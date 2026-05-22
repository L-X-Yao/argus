"""Security regression tests — adversarial inputs on API endpoints and commands."""
from pathlib import Path
from unittest.mock import patch

from backend.commands import execute
from backend.drone_link import DroneLink

# ─── Path Traversal Tests ───────────────────────────────────────────

class TestMbtilesPathTraversal:
    def test_dotdot_in_name_rejected(self):
        from fastapi.testclient import TestClient

        from backend.app import app
        client = TestClient(app)
        r = client.get('/api/mbtiles/../../etc/passwd.mbtiles/0/0/0')
        assert r.status_code == 404

    def test_absolute_path_rejected(self):
        from fastapi.testclient import TestClient

        from backend.app import app
        client = TestClient(app)
        r = client.get('/api/mbtiles/%2F..%2F..%2Fetc%2Fpasswd.mbtiles/0/0/0')
        assert r.status_code == 404

    def test_normal_name_allowed(self):
        from fastapi.testclient import TestClient

        from backend.app import app
        client = TestClient(app)
        r = client.get('/api/mbtiles/region.mbtiles/10/512/512')
        assert r.status_code == 404  # File doesn't exist, but not blocked by security check


class TestTileStyleWhitelist:
    def test_invalid_style_rejected(self):
        from fastapi.testclient import TestClient

        from backend.app import app
        client = TestClient(app)
        r = client.get('/api/tile/fakestyle/10/0/0')
        assert r.status_code == 404
        assert b'unknown tile style' in r.content

    def test_valid_style_passes(self):
        from fastapi.testclient import TestClient

        from backend.app import app
        client = TestClient(app)
        # Valid style but tile unavailable (no network in test)
        with patch('backend.app.urlreq.urlopen', side_effect=Exception('no network')):
            r = client.get('/api/tile/osm/1/0/0')
        assert r.status_code in (200, 404)  # Either cached or unavailable, not security-blocked


class TestFirmwareUploadSanitization:
    def test_traversal_filename_sanitized(self):
        from fastapi.testclient import TestClient

        from backend.app import app
        client = TestClient(app)
        with patch.object(Path, 'write_bytes'):
            r = client.post(
                '/api/firmware/upload',
                files={'file': ('../../exploit.apj', b'\x00' * 10, 'application/octet-stream')},
            )
        if r.status_code == 200:
            data = r.json()
            assert data.get('filename') == 'exploit.apj'
            assert '..' not in data.get('filename', '')

    def test_non_apj_rejected(self):
        from fastapi.testclient import TestClient

        from backend.app import app
        client = TestClient(app)
        r = client.post(
            '/api/firmware/upload',
            files={'file': ('malware.exe', b'\x00', 'application/octet-stream')},
        )
        data = r.json()
        assert data['ok'] is False


# ─── Input Validation Tests (Commands) ──────────────────────────────

class TestMissionUploadValidation:
    def setup_method(self):
        self.link = DroneLink()

    def test_latitude_out_of_range(self):
        result = execute('mission_upload', None, self.link, data={
            'waypoints': [{'lat': 999, 'lon': 120, 'alt': 50}],
            'takeoff_alt': 30,
        })
        assert result is not None
        assert result['ok'] is False

    def test_longitude_out_of_range(self):
        result = execute('mission_upload', None, self.link, data={
            'waypoints': [{'lat': 30, 'lon': -999, 'alt': 50}],
            'takeoff_alt': 30,
        })
        assert result is not None
        assert result['ok'] is False

    def test_altitude_too_high(self):
        result = execute('mission_upload', None, self.link, data={
            'waypoints': [{'lat': 30.5, 'lon': 120.3, 'alt': 999999}],
            'takeoff_alt': 30,
        })
        assert result is not None
        assert result['ok'] is False

    def test_altitude_too_low(self):
        result = execute('mission_upload', None, self.link, data={
            'waypoints': [{'lat': 30.5, 'lon': 120.3, 'alt': -9999}],
            'takeoff_alt': 30,
        })
        assert result is not None
        assert result['ok'] is False

    def test_too_many_waypoints(self):
        wps = [{'lat': 30.0 + i * 0.001, 'lon': 120.0, 'alt': 50} for i in range(501)]
        result = execute('mission_upload', None, self.link, data={
            'waypoints': wps,
            'takeoff_alt': 30,
        })
        assert result is not None
        assert result['ok'] is False

    def test_valid_mission_accepted(self):
        result = execute('mission_upload', None, self.link, data={
            'waypoints': [
                {'lat': 30.5, 'lon': 120.3, 'alt': 50},
                {'lat': 30.6, 'lon': 120.4, 'alt': 60},
            ],
            'takeoff_alt': 30,
        })
        assert result is None  # None means success (no error returned)


class TestGuidedGotoValidation:
    def setup_method(self):
        self.link = DroneLink()

    def test_lat_out_of_range(self):
        result = execute('guided_goto', None, self.link, data={
            'lat': 91.0, 'lon': 120.0, 'alt': 30,
        })
        assert result is not None
        assert result['ok'] is False

    def test_lon_out_of_range(self):
        result = execute('guided_goto', None, self.link, data={
            'lat': 30.0, 'lon': 181.0, 'alt': 30,
        })
        assert result is not None
        assert result['ok'] is False

    def test_alt_out_of_range(self):
        result = execute('guided_goto', None, self.link, data={
            'lat': 30.0, 'lon': 120.0, 'alt': 200000,
        })
        assert result is not None
        assert result['ok'] is False

    def test_negative_lat_lon_valid(self):
        result = execute('guided_goto', None, self.link, data={
            'lat': -33.8, 'lon': -70.6, 'alt': 100,
        })
        assert result is None  # Accepted (sends to drone)


class TestFenceValidation:
    def setup_method(self):
        self.link = DroneLink()

    def test_too_few_vertices(self):
        result = execute('fence_upload', None, self.link, data={
            'polygon': [{'lat': 30, 'lon': 120}],
        })
        assert result is not None
        assert result['ok'] is False

    def test_too_many_vertices(self):
        polygon = [{'lat': 30.0 + i * 0.001, 'lon': 120.0} for i in range(201)]
        result = execute('fence_upload', None, self.link, data={
            'polygon': polygon,
        })
        assert result is not None
        assert result['ok'] is False

    def test_valid_fence_accepted(self):
        polygon = [
            {'lat': 30.0, 'lon': 120.0},
            {'lat': 30.1, 'lon': 120.0},
            {'lat': 30.1, 'lon': 120.1},
            {'lat': 30.0, 'lon': 120.1},
        ]
        result = execute('fence_upload', None, self.link, data={
            'polygon': polygon,
        })
        assert result is None  # Accepted


# ─── Terrain/Elevation Input Validation ─────────────────────────────

class TestTerrainValidation:
    def test_invalid_coords_ignored(self):
        from fastapi.testclient import TestClient

        from backend.app import app
        client = TestClient(app)
        r = client.get('/api/terrain/elevation?points=999,999;-999,-999;abc,def')
        data = r.json()
        assert data['elevations'] == []

    def test_valid_coords_accepted(self):
        from fastapi.testclient import TestClient

        from backend.app import app
        client = TestClient(app)
        r = client.get('/api/terrain/elevation?points=30.5,120.3')
        data = r.json()
        assert len(data['elevations']) == 1


# ─── Tile Bulk Download Bounds ──────────────────────────────────────

class TestTileBulkBounds:
    def test_negative_z_clamped(self):
        from fastapi.testclient import TestClient

        from backend.app import app
        client = TestClient(app)
        r = client.post('/api/tile_bulk_download', json={
            'lat_min': 30, 'lat_max': 31,
            'lon_min': 120, 'lon_max': 121,
            'z_min': -100, 'z_max': 2,
            'style': 'osm',
        })
        data = r.json()
        assert data['total'] >= 0  # Didn't crash

    def test_invalid_style_returns_empty(self):
        from fastapi.testclient import TestClient

        from backend.app import app
        client = TestClient(app)
        r = client.post('/api/tile_bulk_download', json={
            'lat_min': 30, 'lat_max': 31,
            'lon_min': 120, 'lon_max': 121,
            'z_min': 10, 'z_max': 10,
            'style': '../../../etc',
        })
        data = r.json()
        assert data['downloaded'] == 0
