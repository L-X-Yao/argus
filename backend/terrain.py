"""SRTM terrain elevation lookup."""

from __future__ import annotations

import asyncio
import gzip
import io
import math
import struct
import urllib.error
import urllib.request as urlreq

from fastapi import APIRouter, Request

from .config import ROOT_DIR, aio, aio_download, cfg

router = APIRouter()

SRTM_CACHE = ROOT_DIR / "srtm_cache"
_tile_locks: dict[str, asyncio.Lock] = {}


@router.get("/api/terrain/elevation", tags=["Map"])
async def api_terrain_elevation(request: Request):
    """Get ground elevation for a list of lat/lon points using SRTM data."""
    params = request.query_params
    points_str = params.get("points", "")
    if not points_str:
        return {"elevations": []}
    points = []
    for p in points_str.split(";"):
        parts = p.split(",")
        if len(parts) >= 2:
            try:
                lat, lon = float(parts[0]), float(parts[1])
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    points.append((lat, lon))
            except ValueError:
                pass
    elevations = await asyncio.gather(*(_get_srtm_elevation(lat, lon) for lat, lon in points))
    return {"elevations": list(elevations)}


async def _fetch_tile(ns: str, ilat: int, fname: str, cache_file) -> bool:
    # The server only holds them gzipped: a plain .hgt is a 404.
    url = "https://elevation-tiles-prod.s3.amazonaws.com/skadi/%s%02d/%s.gz" % (ns, abs(ilat), fname)
    try:
        req = urlreq.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = await aio_download(
            lambda: urlreq.urlopen(req, timeout=cfg.SRTM_DOWNLOAD_TIMEOUT).read(cfg.SRTM_FILE_MAX)
        )
        if len(data) >= cfg.SRTM_FILE_MAX:
            return False
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as tile:
            raw = await aio(tile.read, cfg.SRTM_FILE_MAX)
        await aio(cache_file.write_bytes, raw)
        return True
    except (OSError, EOFError, urllib.error.URLError):
        return False


async def _get_srtm_elevation(lat: float, lon: float) -> float:
    ilat = int(math.floor(lat))
    ilon = int(math.floor(lon))
    ns = "N" if ilat >= 0 else "S"
    ew = "E" if ilon >= 0 else "W"
    fname = "%s%02d%s%03d.hgt" % (ns, abs(ilat), ew, abs(ilon))
    cache_file = SRTM_CACHE / fname
    if not cache_file.exists():
        SRTM_CACHE.mkdir(parents=True, exist_ok=True)
        # The points of a route mostly share a tile, and each would download it otherwise.
        lock = _tile_locks.setdefault(fname, asyncio.Lock())
        try:
            async with lock:
                if not cache_file.exists():
                    srtm_count = await aio(lambda: sum(1 for _ in SRTM_CACHE.glob("*.hgt")))
                    if srtm_count >= cfg.SRTM_CACHE_MAX or not await _fetch_tile(ns, ilat, fname, cache_file):
                        return 0
        finally:
            _tile_locks.pop(fname, None)
    try:
        data = await aio(cache_file.read_bytes)
        samples = 1201
        if len(data) == 2884802:
            samples = 1201
        elif len(data) == 25934402:
            samples = 3601
        else:
            return 0
        frac_lat = lat - ilat
        frac_lon = lon - ilon
        row = int((1 - frac_lat) * (samples - 1))
        col = int(frac_lon * (samples - 1))
        idx = (row * samples + col) * 2
        if idx + 2 > len(data):
            return 0
        elev = struct.unpack(">h", data[idx : idx + 2])[0]
        if elev == -32768:
            return 0
        return float(elev)
    except (OSError, struct.error):
        return 0
