from __future__ import annotations
import glob
import shutil
import sys
import urllib.request as urlreq
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import cfg
from .drone_link import DroneLink
from .param_meta import get_metadata
from .video import router as video_router
from .ws_manager import WSManager

V3_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = V3_DIR / 'dist'
TILE_CACHE = V3_DIR / 'tile_cache'
_TILE_MAX = cfg.TILE_CACHE_MAX
_tile_count = -1

TILE_URLS = {
    '6': 'https://webst01.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}',
    '7': 'https://wprd01.is.autonavi.com/appmaptile?x={x}&y={y}&z={z}&lang=zh_cn&size=1&scl=1&style=7',
    '8': 'https://wprd01.is.autonavi.com/appmaptile?x={x}&y={y}&z={z}&lang=zh_cn&size=1&scl=1&style=8',
    'osm': 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    'osm_sat': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.link = DroneLink()
    app.state.ws_mgr = WSManager(app.state.link)
    yield
    app.state.link.disconnect()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(video_router)


@app.get('/health')
async def health():
    return {'ok': True}


@app.get('/api/version')
async def api_version():
    import subprocess
    git_hash = ''
    try:
        git_hash = subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=str(V3_DIR), timeout=cfg.GIT_HASH_TIMEOUT, stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        pass
    return {
        'version': '3.1.0',
        'git': git_hash,
        'protocols': ['standard', 'pllink'],
        'vehicles': ['copter', 'plane', 'rover', 'sub'],
        'features': ['i18n', 'param_meta', 'gamepad', 'pwa', 'global_tiles'],
    }


@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
    await app.state.ws_mgr.handle_client(ws)


@app.get('/api/tile_sources')
async def api_tile_sources():
    return {
        'china': {'sat': '6', 'vec': '7', 'label': '8', 'gcj02': True},
        'global': {'sat': 'osm_sat', 'vec': 'osm', 'label': None, 'gcj02': False},
    }


@app.get('/api/param_meta')
async def api_param_meta(vehicle: str = 'copter'):
    return get_metadata(vehicle)


@app.get('/api/ports')
async def api_ports():
    if sys.platform == 'win32':
        ports = []
        try:
            from serial.tools.list_ports import comports
            ports = sorted(p.device for p in comports())
        except Exception:
            pass
        return {'ports': ports or ['COM3']}
    else:
        return {'ports': sorted(glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')) or ['/dev/ttyUSB0']}


@app.get('/api/log')
async def api_log():
    link: DroneLink = app.state.link
    path = link.get_log_path()
    if path:
        import os
        return FileResponse(
            path,
            media_type='text/csv',
            filename=os.path.basename(path),
        )
    return Response(status_code=404, content='无活动日志')


@app.get('/api/tile/{style}/{z}/{x}/{y}')
async def api_tile(style: str, z: int, x: int, y: int):
    global _tile_count
    cache_dir = TILE_CACHE / style / str(z) / str(x)
    cache_file = cache_dir / ('%d.png' % y)
    if cache_file.exists():
        return Response(content=cache_file.read_bytes(), media_type='image/png',
                        headers={'Cache-Control': 'public, max-age=604800'})
    url = TILE_URLS.get(style, TILE_URLS['6']).format(x=x, y=y, z=z)
    try:
        req = urlreq.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = urlreq.urlopen(req, timeout=cfg.TILE_DOWNLOAD_TIMEOUT).read()
        if _tile_count < 0:
            _tile_count = sum(1 for _ in TILE_CACHE.rglob('*.png')) if TILE_CACHE.exists() else 0
        if _tile_count < _TILE_MAX:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(data)
            _tile_count += 1
        return Response(content=data, media_type='image/png',
                        headers={'Cache-Control': 'public, max-age=604800'})
    except Exception:
        return Response(status_code=404, content='tile unavailable')


@app.get('/api/tile_cache')
async def api_tile_cache():
    if not TILE_CACHE.exists():
        return {'size': 0, 'count': 0}
    total = count = 0
    for f in TILE_CACHE.rglob('*'):
        if f.is_file():
            total += f.stat().st_size
            count += 1
    return {'size': total, 'count': count}


@app.post('/api/tile_cache_clear')
async def api_tile_cache_clear():
    global _tile_count
    if TILE_CACHE.exists():
        shutil.rmtree(TILE_CACHE)
    _tile_count = 0
    return {'ok': True}


FIRMWARE_DIR = V3_DIR / 'firmware'
MBTILES_DIR = V3_DIR / 'mbtiles'


@app.get('/api/mbtiles/list')
async def api_mbtiles_list():
    if not MBTILES_DIR.exists():
        return {'files': []}
    return {'files': [f.name for f in sorted(MBTILES_DIR.glob('*.mbtiles'))]}


@app.get('/api/mbtiles/{name}/{z}/{x}/{y}')
async def api_mbtiles_tile(name: str, z: int, x: int, y: int):
    import sqlite3
    path = MBTILES_DIR / name
    if not path.exists() or not name.endswith('.mbtiles'):
        return Response(status_code=404, content='not found')
    tms_y = (1 << z) - 1 - y
    try:
        conn = sqlite3.connect(str(path))
        row = conn.execute('SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?',
                           (z, x, tms_y)).fetchone()
        conn.close()
        if row:
            return Response(content=row[0], media_type='image/png',
                            headers={'Cache-Control': 'public, max-age=604800'})
    except Exception:
        pass
    return Response(status_code=404, content='tile not found')


@app.post('/api/firmware/upload')
async def api_firmware_upload(file: UploadFile):
    if not file.filename or not file.filename.endswith('.apj'):
        return {'ok': False, 'error': 'Only .apj files accepted'}
    FIRMWARE_DIR.mkdir(exist_ok=True)
    dest = FIRMWARE_DIR / file.filename
    data = await file.read()
    dest.write_bytes(data)
    return {'ok': True, 'filename': file.filename, 'size': len(data)}


@app.get('/api/firmware/list')
async def api_firmware_list():
    if not FIRMWARE_DIR.exists():
        return {'files': []}
    files = []
    for f in sorted(FIRMWARE_DIR.glob('*.apj')):
        files.append({'name': f.name, 'size': f.stat().st_size})
    return {'files': files}


if DIST_DIR.exists():
    app.mount('/assets', StaticFiles(directory=str(DIST_DIR / 'assets')), name='assets')
    if (DIST_DIR / 'images').exists():
        app.mount('/images', StaticFiles(directory=str(DIST_DIR / 'images')), name='images')
    if (DIST_DIR / 'lib').exists():
        app.mount('/lib', StaticFiles(directory=str(DIST_DIR / 'lib')), name='lib')

    @app.get('/')
    async def index():
        return FileResponse(str(DIST_DIR / 'index.html'))
