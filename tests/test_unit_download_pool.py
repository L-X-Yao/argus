"""A dead uplink must not hold up link connect and disconnect.

Both run on the default executor, which has cpu_count + 4 threads: 8 on a
4-core machine. A tile download can hold a thread for its full timeout, so
when the downloads shared that pool, Disconnect waited behind them.
"""

import asyncio
import threading
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from backend import app as app_module
from backend import firmware, param_meta, terrain, tiles


class _BulkRequest:
    async def json(self):
        return {"lat_min": 10, "lat_max": 10.1, "lon_min": 10, "lon_max": 10.1, "zoom_min": 12, "zoom_max": 12}


def _tiles():
    return [tiles.api_tile("osm", 12, x, 0) for x in range(4)]


def _tile_bulk():
    return [tiles.api_tile_bulk_download(_BulkRequest()) for _ in range(4)]


def _terrain():
    return [terrain._get_srtm_elevation(10 + i, 10) for i in range(4)]


def _firmware_list():
    return [firmware.api_firmware_online(board_id) for board_id in list(firmware._BOARD_MAP)[:4]]


class _FirmwareRequest:
    async def json(self):
        return {"url": "https://firmware.ardupilot.org/fw.apj", "filename": "fw.apj"}


def _firmware_download():
    return [firmware.api_firmware_download(_FirmwareRequest()) for _ in range(4)]


def _param_meta():
    return [app_module.api_param_meta(vehicle) for vehicle in ("copter", "plane", "rover", "sub")]


@pytest.mark.parametrize("start", [_tiles, _tile_bulk, _terrain, _firmware_list, _firmware_download, _param_meta])
def test_default_pool_stays_free_while_downloads_hang(start, tmp_path):
    release = threading.Event()
    hung = threading.Semaphore(0)

    def hang(*args, **kwargs):
        hung.release()
        release.wait(10)
        raise urllib.error.URLError("uplink down")

    async def both_hung():
        for _ in range(2):
            while not hung.acquire(blocking=False):
                await asyncio.sleep(0.01)

    async def scenario():
        # Few threads, so that two downloads fill the pool if they land on it.
        asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=2))
        downloads = [asyncio.create_task(coroutine) for coroutine in start()]
        try:
            await asyncio.wait_for(both_hung(), 5)
            return await asyncio.wait_for(asyncio.to_thread(lambda: "ran"), 1)
        finally:
            release.set()
            await asyncio.gather(*downloads, return_exceptions=True)

    with (
        patch("urllib.request.urlopen", hang),
        patch.object(tiles, "TILE_CACHE", tmp_path / "tiles"),
        patch.object(terrain, "SRTM_CACHE", tmp_path / "srtm"),
        patch.object(firmware, "FIRMWARE_DIR", tmp_path / "firmware"),
        patch.object(param_meta, "CACHE_DIR", tmp_path / "params"),
        patch.dict(param_meta._cache, clear=True),
        patch("socket.getaddrinfo", return_value=[(2, 1, 6, "", ("8.8.8.8", 443))]),
    ):
        assert asyncio.run(scenario()) == "ran"
