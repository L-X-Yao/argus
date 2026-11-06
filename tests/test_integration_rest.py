"""Integration: REST routes on a real backend, with real files and the real upstream servers.

The unit tests mock these servers, and the mocks answered what the code expected: the
terrain and firmware URLs had both been 404s for as long as anyone can tell. So the tests
here go to the real servers, and only skip when the network is down, which they find out
from the server's own address and not through the code under test.
"""

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
TERRAIN_TILE = "https://elevation-tiles-prod.s3.amazonaws.com/skadi/S36/S36E149.hgt.gz"
FIRMWARE_PAGE = "https://firmware.ardupilot.org/Copter/stable/Pixhawk1/"
PIXHAWK1 = 9


def needs(url: str) -> None:
    try:
        if httpx.head(url, timeout=15, follow_redirects=True).status_code == 200:
            return
    except httpx.HTTPError:
        pass
    pytest.skip(f"{url} cannot be reached")


class TestOfflineMaps:
    NAME = "argus-integration.mbtiles"
    TILE = b"\x89PNG not really"

    @pytest.fixture
    def mbtiles(self):
        folder = ROOT / "mbtiles"
        made = not folder.exists()
        folder.mkdir(exist_ok=True)
        path = folder / self.NAME
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE tiles (zoom_level INT, tile_column INT, tile_row INT, tile_data BLOB)")
        # MBTiles counts rows from the south: tile 2/1/1 of the map is row 2 in the file.
        db.execute("INSERT INTO tiles VALUES (2, 1, 2, ?)", (self.TILE,))
        db.commit()
        db.close()
        yield
        path.unlink()
        if made:
            folder.rmdir()

    def test_a_file_in_the_folder_is_listed(self, backend_url, mbtiles):
        assert self.NAME in httpx.get(f"{backend_url}/api/mbtiles/list").json()["files"]

    def test_a_tile_comes_back_with_its_row_flipped(self, backend_url, mbtiles):
        r = httpx.get(f"{backend_url}/api/mbtiles/{self.NAME}/2/1/1")
        assert r.status_code == 200
        assert r.content == self.TILE
        assert r.headers["content-type"] == "image/png"

    def test_a_tile_outside_the_file_is_a_404(self, backend_url, mbtiles):
        assert httpx.get(f"{backend_url}/api/mbtiles/{self.NAME}/2/1/2").status_code == 404

    def test_a_file_that_is_not_there_is_a_404(self, backend_url):
        assert httpx.get(f"{backend_url}/api/mbtiles/nothing.mbtiles/2/1/1").status_code == 404


class TestTerrain:
    def test_a_real_tile_gives_the_ground_height(self, backend_url):
        needs(TERRAIN_TILE)
        r = httpx.get(f"{backend_url}/api/terrain/elevation", params={"points": "-35.363261,149.165230"}, timeout=600)
        # CMAC, the airfield SITL starts at: 584 m in Tools/autotest/locations.txt.
        assert 560 < r.json()["elevations"][0] < 610


class TestFirmware:
    def test_the_list_of_a_folder_with_nothing_in_it_is_empty_or_real(self, backend_url):
        files = httpx.get(f"{backend_url}/api/firmware/list").json()["files"]
        assert all(f["name"].endswith(".apj") for f in files)

    def test_the_real_server_offers_a_build_and_it_downloads(self, backend_url):
        needs(FIRMWARE_PAGE)
        data = httpx.get(f"{backend_url}/api/firmware/online", params={"board_id": PIXHAWK1}, timeout=60).json()
        assert "error" not in data
        version = data["versions"][0]
        assert version["version"].count(".") == 2
        assert version["url"].endswith("/Copter/stable/Pixhawk1/arducopter.apj")

        name = "argus-integration.apj"
        try:
            r = httpx.post(
                f"{backend_url}/api/firmware/download", json={"url": version["url"], "filename": name}, timeout=600
            )
            assert r.json()["ok"] is True
            assert r.json()["size"] > 100_000
            listed = httpx.get(f"{backend_url}/api/firmware/list").json()["files"]
            assert name in [f["name"] for f in listed]
        finally:
            (ROOT / "firmware" / name).unlink(missing_ok=True)

    def test_a_download_from_inside_the_network_is_refused(self, backend_url):
        r = httpx.post(
            f"{backend_url}/api/firmware/download",
            json={"url": "https://127.0.0.1/fw.apj", "filename": "fw.apj"},
            timeout=30,
        )
        assert r.json()["ok"] is False


class TestTileBulkDownload:
    def test_counts_the_tiles_of_an_area(self, backend_url):
        # One tile at this zoom. Whether a map server serves it is up to that server.
        body = {"lat_min": 34.2, "lat_max": 34.21, "lon_min": 108.9, "lon_max": 108.91, "z_min": 3, "z_max": 3}
        r = httpx.post(f"{backend_url}/api/tile_bulk_download", json=body, timeout=60)
        data = r.json()
        assert data["total"] == 1
        assert data["truncated"] is False

    def test_a_style_that_does_not_exist_downloads_nothing(self, backend_url):
        r = httpx.post(f"{backend_url}/api/tile_bulk_download", json={"style": "nope"}, timeout=30)
        assert r.json() == {"total": 0, "downloaded": 0, "skipped": 0, "truncated": False}


class TestVideoCapabilities:
    def test_says_what_this_machine_has(self, backend_url):
        data = httpx.get(f"{backend_url}/api/video/capabilities").json()
        assert data["mjpeg"] is bool(shutil.which("ffmpeg"))
        assert data["webrtc"] is False


class TestTokenGeneration:
    """On a backend of its own: a token turns login on for everything after it."""

    @pytest.fixture
    def fresh_backend(self, tmp_path):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        code = (
            "import pathlib, uvicorn, backend.auth as a\n"
            f"a.TOKEN_FILE = pathlib.Path({str(tmp_path / 'token')!r})\n"
            f"uvicorn.run('backend.app:app', host='127.0.0.1', port={port}, log_level='warning')\n"
        )
        proc = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, env={**os.environ, "ARGUS_NO_BROWSER": "1"})
        url = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        yield url
        proc.terminate()
        proc.wait(timeout=10)

    def test_the_first_token_is_given_and_the_second_refused(self, fresh_backend):
        assert httpx.get(f"{fresh_backend}/api/auth/status").json()["auth_required"] is False

        first = httpx.post(f"{fresh_backend}/api/auth/generate")
        assert first.status_code == 200
        token = first.json()["token"]
        assert len(token) >= 16

        assert httpx.get(f"{fresh_backend}/api/auth/status").json()["auth_required"] is True
        assert httpx.post(f"{fresh_backend}/api/auth/generate").status_code == 401

        assert httpx.get(f"{fresh_backend}/api/ports").status_code == 401
        login = httpx.post(f"{fresh_backend}/api/auth/login", json={"token": token})
        assert login.status_code == 200
