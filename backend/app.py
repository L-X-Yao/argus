from __future__ import annotations
import glob
import shutil
import sys
import urllib.request as urlreq
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import cfg
from .drone_link import DroneLink
from .param_meta import get_metadata
from .video import router as video_router
from .ws_manager import WSManager
from .auth import auth_middleware, verify_ws_token, auth_required, generate_token, verify_token

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
    'google_sat': 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
    'google_street': 'https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
    'google_hybrid': 'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
    'google_terrain': 'https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}',
    'carto_dark': 'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
    'carto_light': 'https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png',
    'esri_topo': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
    'tdt_vec': 'https://t0.tianditu.gov.cn/vec_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=vec&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILECOL={x}&TILEROW={y}&TILEMATRIX={z}&tk=',
    'tdt_sat': 'https://t0.tianditu.gov.cn/img_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=img&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILECOL={x}&TILEROW={y}&TILEMATRIX={z}&tk=',
    'tdt_label': 'https://t0.tianditu.gov.cn/cia_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=cia&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILECOL={x}&TILEROW={y}&TILEMATRIX={z}&tk=',
}

TILE_SOURCES = {
    'amap': {
        'name': 'Amap (Gaode)',
        'sat': '6', 'vec': '7', 'label': '8',
        'gcj02': True, 'region': 'china',
    },
    'google_sat': {
        'name': 'Google Satellite',
        'sat': 'google_sat', 'vec': 'google_street', 'label': None,
        'gcj02': False, 'region': 'global',
    },
    'google_hybrid': {
        'name': 'Google Hybrid',
        'sat': 'google_hybrid', 'vec': 'google_street', 'label': None,
        'gcj02': False, 'region': 'global',
    },
    'osm': {
        'name': 'OpenStreetMap',
        'sat': 'osm_sat', 'vec': 'osm', 'label': None,
        'gcj02': False, 'region': 'global',
    },
    'carto_dark': {
        'name': 'CartoDB Dark',
        'sat': 'carto_dark', 'vec': 'carto_dark', 'label': None,
        'gcj02': False, 'region': 'global',
    },
    'carto_light': {
        'name': 'CartoDB Light',
        'sat': 'carto_light', 'vec': 'carto_light', 'label': None,
        'gcj02': False, 'region': 'global',
    },
    'esri': {
        'name': 'Esri Satellite + Topo',
        'sat': 'osm_sat', 'vec': 'esri_topo', 'label': None,
        'gcj02': False, 'region': 'global',
    },
    'tianditu': {
        'name': 'Tianditu',
        'sat': 'tdt_sat', 'vec': 'tdt_vec', 'label': 'tdt_label',
        'gcj02': False, 'region': 'china',
    },
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.link = DroneLink()
    app.state.ws_mgr = WSManager(app.state.link)
    yield
    app.state.link.disconnect()


app = FastAPI(
    title='PL-Link GCS API',
    description='Universal Web Ground Control Station — REST API for MAVLink vehicle control',
    version='3.3.0',
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(video_router)
app.middleware('http')(auth_middleware)


@app.get('/health', tags=['System'])
async def health():
    """Health check endpoint."""
    return {'ok': True}


@app.get('/api/session', tags=['System'])
async def api_session(request):
    """Current session info: connected clients, vehicle state."""
    link = request.app.state.link
    mgr = request.app.state.ws_mgr
    return {
        'clients': mgr.client_count,
        'connected': link.connected,
        'armed': link.armed,
        'sysid': link.sysid,
        'mode': link.mode,
        'vtype': link.vtype_raw,
    }


@app.get('/api/version', tags=['System'])
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
        'version': '3.2.0',
        'git': git_hash,
        'protocols': ['standard', 'pllink'],
        'vehicles': ['copter', 'plane', 'rover', 'sub'],
        'features': ['i18n', 'param_meta', 'gamepad', 'pwa', 'global_tiles'],
    }


@app.post('/api/auth/login', tags=['Auth'])
async def api_auth_login(request: Request):
    """Authenticate with token. Returns ok if valid."""
    body = await request.json()
    token = body.get('token', '')
    if verify_token(token):
        return {'ok': True}
    return JSONResponse(status_code=401, content={'ok': False, 'error': 'invalid token'})


@app.get('/api/auth/status', tags=['Auth'])
async def api_auth_status():
    """Check if authentication is enabled."""
    return {'auth_required': auth_required()}


@app.post('/api/auth/generate', tags=['Auth'])
async def api_auth_generate():
    """Generate a new auth token (only works if no token exists yet)."""
    if auth_required():
        return JSONResponse(status_code=403, content={'error': 'token already exists'})
    token = generate_token()
    return {'token': token}


@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket):
    if not verify_ws_token(ws):
        await ws.close(code=4001, reason='unauthorized')
        return
    await app.state.ws_mgr.handle_client(ws)


@app.get('/api/tile_sources')
async def api_tile_sources():
    return TILE_SOURCES


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


@app.get('/api/terrain/elevation', tags=['Map'])
async def api_terrain_elevation(request: Request):
    """Get ground elevation for a list of lat/lon points using SRTM data."""
    import math
    params = request.query_params
    points_str = params.get('points', '')
    if not points_str:
        return {'elevations': []}
    points = []
    for p in points_str.split(';'):
        parts = p.split(',')
        if len(parts) >= 2:
            points.append((float(parts[0]), float(parts[1])))
    elevations = []
    for lat, lon in points:
        elev = await _get_srtm_elevation(lat, lon)
        elevations.append(elev)
    return {'elevations': elevations}


SRTM_CACHE = V3_DIR / 'srtm_cache'


async def _get_srtm_elevation(lat: float, lon: float) -> float:
    import math, struct
    ilat = int(math.floor(lat))
    ilon = int(math.floor(lon))
    ns = 'N' if ilat >= 0 else 'S'
    ew = 'E' if ilon >= 0 else 'W'
    fname = '%s%02d%s%03d.hgt' % (ns, abs(ilat), ew, abs(ilon))
    cache_file = SRTM_CACHE / fname
    if not cache_file.exists():
        SRTM_CACHE.mkdir(parents=True, exist_ok=True)
        url = 'https://elevation-tiles-prod.s3.amazonaws.com/skadi/%s%02d/%s' % (ns, abs(ilat), fname)
        try:
            req = urlreq.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            data = urlreq.urlopen(req, timeout=10).read()
            cache_file.write_bytes(data)
        except Exception:
            return 0
    try:
        data = cache_file.read_bytes()
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
        elev = struct.unpack('>h', data[idx:idx + 2])[0]
        if elev == -32768:
            return 0
        return float(elev)
    except Exception:
        return 0


@app.post('/api/tile_bulk_download', tags=['Map'])
async def api_tile_bulk_download(request: Request):
    """Download tiles for a bounding box at specified zoom levels."""
    import asyncio, math
    body = await request.json()
    lat_min, lat_max = body.get('lat_min', 0), body.get('lat_max', 0)
    lon_min, lon_max = body.get('lon_min', 0), body.get('lon_max', 0)
    z_min, z_max = body.get('z_min', 10), min(body.get('z_max', 16), 18)
    style = body.get('style', '6')
    total = downloaded = skipped = 0
    for z in range(z_min, z_max + 1):
        n = 2 ** z
        x_min = int((lon_min + 180) / 360 * n)
        x_max = int((lon_max + 180) / 360 * n)
        y_min = int((1 - math.log(math.tan(math.radians(lat_max)) + 1 / math.cos(math.radians(lat_max))) / math.pi) / 2 * n)
        y_max = int((1 - math.log(math.tan(math.radians(lat_min)) + 1 / math.cos(math.radians(lat_min))) / math.pi) / 2 * n)
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                total += 1
                cache_file = TILE_CACHE / style / str(z) / str(x) / ('%d.png' % y)
                if cache_file.exists():
                    skipped += 1
                    continue
                url = TILE_URLS.get(style, TILE_URLS['6']).format(x=x, y=y, z=z)
                try:
                    req = urlreq.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    data = urlreq.urlopen(req, timeout=5).read()
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cache_file.write_bytes(data)
                    downloaded += 1
                except Exception:
                    pass
                if total > 5000:
                    return {'total': total, 'downloaded': downloaded, 'skipped': skipped, 'truncated': True}
    return {'total': total, 'downloaded': downloaded, 'skipped': skipped, 'truncated': False}


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


import base64 as _b64
_FW_BASE = _b64.b64decode(b'aHR0cHM6Ly9maXJtd2FyZS5hcmR1cGlsb3Qub3JnLw==').decode()

_BOARD_MAP = {
    56: ('Plane', 'Plkj-Industrial'),
    57: ('Copter', 'Plkj-caac'),
}


@app.get('/api/firmware/online')
async def api_firmware_online(board_id: int = 0):
    board_info = _BOARD_MAP.get(board_id)
    if not board_info:
        return {'versions': [], 'error': 'Unknown board_id'}
    vehicle, board_name = board_info
    versions = []
    try:
        url = '%s%s/stable-%s/' % (_FW_BASE, vehicle, board_name)
        req = urlreq.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urlreq.urlopen(req, timeout=10).read().decode('utf-8', errors='replace')
        import re
        for m in re.finditer(r'href="([^"]*\.apj)"', html):
            fname = m.group(1)
            ver_m = re.search(r'(\d+\.\d+\.\d+)', fname)
            ver = ver_m.group(1) if ver_m else fname
            versions.append({
                'version': ver,
                'date': '',
                'url': url + fname,
                'size': 0,
            })
    except Exception:
        pass
    return {'versions': versions[-10:]}


@app.post('/api/firmware/download')
async def api_firmware_download(request: Request):
    body = await request.json()
    fw_url = body.get('url', '')
    filename = body.get('filename', 'firmware.apj')
    if not fw_url or not filename.endswith('.apj'):
        return {'ok': False, 'error': 'Invalid params'}
    try:
        req = urlreq.Request(fw_url, headers={'User-Agent': 'Mozilla/5.0'})
        data = urlreq.urlopen(req, timeout=60).read()
        FIRMWARE_DIR.mkdir(exist_ok=True)
        (FIRMWARE_DIR / filename).write_bytes(data)
        return {'ok': True, 'filename': filename, 'size': len(data)}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


if DIST_DIR.exists():
    app.mount('/assets', StaticFiles(directory=str(DIST_DIR / 'assets')), name='assets')
    if (DIST_DIR / 'images').exists():
        app.mount('/images', StaticFiles(directory=str(DIST_DIR / 'images')), name='images')
    if (DIST_DIR / 'lib').exists():
        app.mount('/lib', StaticFiles(directory=str(DIST_DIR / 'lib')), name='lib')

    @app.get('/')
    async def index():
        return FileResponse(str(DIST_DIR / 'index.html'))
