from __future__ import annotations

import glob
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .auth import (
    auth_middleware,
    auth_required,
    generate_token,
    set_session_cookie,
    verify_token,
    verify_ws_cookie,
    verify_ws_token,
    ws_exposure_error,
)
from .config import (
    ROOT_DIR,
    VERSION,
    BodyTooLarge,
    aio,
    aio_download,
    allowed_origins,
    cfg,
    json_object,
)
from .drone_link import DroneLink
from .firmware import router as firmware_router
from .param_meta import get_metadata
from .terrain import router as terrain_router
from .tiles import router as tiles_router
from .video import router as video_router
from .ws_manager import WSManager

DIST_DIR = ROOT_DIR / "dist"
# Without this the browser reuses its cached shell by heuristic, for days if the
# build is old, and that shell points at hashed chunks an upgrade has deleted.
_REVALIDATE = {"Cache-Control": "no-cache"}

# What the page may load and run. Its scripts come from this server and from nowhere else, so
# markup that gets into the page cannot bring a handler that runs: the map writes icons,
# tooltips and popups with innerHTML, from mission files, browser storage and telemetry.
# Sent with the page only — an API answer is no page, and /docs is disabled.
#   style-src 'unsafe-inline'   the map libraries and the components set style attributes
#   ELEVATION                   the one other server the page reads, for the 3D view
#                               (src/components/map/Map3DView.svelte): that bucket, not the host
#   connect-src without ws:/wss:  the page's one websocket is to the server that served it,
#                               which 'self' covers (CSP3); a scheme source like ws: would let
#                               the page open a socket to ANY host and port (audit 2026-11-16
#                               L14). The e2e suite drives the whole app over that websocket
#                               under this policy, which is the proof that 'self' holds it.
ELEVATION = "https://s3.amazonaws.com/elevation-tiles-prod/"
CONTENT_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        f"img-src 'self' data: blob: {ELEVATION}",
        "font-src 'self' data:",
        f"connect-src 'self' {ELEVATION}",
        "worker-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.link = DroneLink()
    app.state.ws_mgr = WSManager(app.state.link)
    yield
    app.state.link.disconnect()


app = FastAPI(
    title="Argus GCS API",
    description="Web ground control station for ArduPilot vehicles: REST API",
    version=VERSION,
    lifespan=lifespan,
    # The schema stays at /openapi.json; the Swagger and ReDoc pages are off
    # (audit 2026-11-16 L16): they were the one page that loaded scripts from
    # a CDN — unpinned jsdelivr — on the token's origin, and they are also why
    # the page's content policy could not go with every HTML answer.
    docs_url=None,
    redoc_url=None,
)

_cors_origins = allowed_origins(cfg.PORT)
app.state.cors_origins = _cors_origins
# The names a browser may know this server by: see auth._asked_by_our_name.
app.state.own_hosts = {urlsplit(origin).hostname for origin in _cors_origins} - {None}
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(video_router)
app.include_router(tiles_router)
app.include_router(terrain_router)
app.include_router(firmware_router)
app.middleware("http")(auth_middleware)


@app.middleware("http")
async def firmware_upload_size(request: Request, call_next):
    # FastAPI otherwise parses multipart into a temporary file before api_firmware_upload runs.
    # Check the declared body first, allowing 64 KiB for multipart headers and boundaries.
    if request.method == "POST" and request.scope["path"] == "/api/firmware/upload":
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > cfg.FIRMWARE_MAX_SIZE + 64 * 1024:
            return JSONResponse(
                status_code=413,
                content={
                    "ok": False,
                    "error": f"File too large (max {cfg.FIRMWARE_MAX_SIZE // 1024 // 1024} MB)",
                },
            )
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.get("/health", tags=["System"])
async def health():
    """Health check endpoint."""
    return {"ok": True}


@app.exception_handler(BodyTooLarge)
async def body_too_large(request: Request, exc: BodyTooLarge):
    """A JSON body past the cap (config.json_object) is refused, not parsed (audit M1)."""
    return JSONResponse(status_code=413, content={"error": "body too large"})


@app.get("/api/session", tags=["System"])
async def api_session(request: Request):
    """Current session info: connected clients, vehicle state."""
    link = request.app.state.link
    mgr = request.app.state.ws_mgr
    return {
        "clients": mgr.client_count,
        "assistants": mgr.assistant_count,
        "connected": link.connected,
        "armed": link.vehicle.armed,
        "sysid": link.vehicle.sysid,
        "mode": link.vehicle.mode,
        "vtype": link.vehicle.vtype_raw,
    }


@app.get("/api/version", tags=["System"])
async def api_version():
    import subprocess

    def _git_hash() -> str:
        try:
            return (
                subprocess.check_output(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=str(ROOT_DIR),
                    timeout=cfg.GIT_HASH_TIMEOUT,
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .strip()
            )
        except (OSError, subprocess.SubprocessError):
            return ""

    git_hash = await aio(_git_hash)
    return {
        "version": VERSION,
        "git": git_hash,
        "protocols": ["standard"],
        "vehicles": ["copter", "plane", "rover", "sub"],
        "features": ["i18n", "param_meta", "gamepad", "pwa", "global_tiles"],
    }


@app.post("/api/auth/login", tags=["Auth"])
async def api_auth_login(request: Request):
    """Authenticate with token. A valid one also gets a session cookie."""
    body = await json_object(request)
    token = body.get("token", "")
    if verify_token(token):
        response = JSONResponse({"ok": True})
        if auth_required():
            set_session_cookie(response, secure=request.url.scheme == "https")
        return response
    return JSONResponse(status_code=401, content={"ok": False, "error": "invalid token"})


@app.get("/api/auth/status", tags=["Auth"])
async def api_auth_status():
    """Check if authentication is enabled."""
    return {"auth_required": auth_required()}


@app.post("/api/auth/generate", tags=["Auth"])
async def api_auth_generate(request: Request):
    """Generate a new auth token (only works if no token exists yet)."""
    client = request.client
    if not client or client.host not in ("127.0.0.1", "::1"):
        return JSONResponse(status_code=403, content={"error": "token generation only allowed from localhost"})
    if auth_required():
        return JSONResponse(status_code=403, content={"error": "token already exists"})
    token = generate_token()
    return {"token": token}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    origin = (ws.headers.get("origin") or "").rstrip("/")
    if origin and origin not in _cors_origins:
        await ws.close(code=4003, reason="origin not allowed")
        return
    # With no token, only this machine talks to the server (audit 2026-11-16
    # L18/L17). The middleware that holds HTTP to that rule never sees a
    # websocket scope, so the handshake asks it here.
    if not auth_required():
        refusal = ws_exposure_error(ws)
        if refusal is not None:
            await ws.close(code=4003, reason=refusal)
            return
    # The logged-in page is authorized by its HttpOnly session cookie, so the
    # token need not travel in the URL (audit 2026-11-16 L15). The query
    # token stays for the clients that cannot hold a cookie: the MCP server.
    if not verify_ws_token(ws) and not verify_ws_cookie(ws):
        await ws.close(code=4001, reason="unauthorized")
        return
    await app.state.ws_mgr.handle_client(ws)


@app.get("/api/param_meta")
async def api_param_meta(vehicle: str = "copter"):
    return await aio_download(get_metadata, vehicle)


@app.get("/api/ports")
async def api_ports():
    if sys.platform == "win32":
        ports = []
        try:
            from serial.tools.list_ports import comports

            ports = sorted(p.device for p in comports())
        except (ImportError, OSError):
            pass
        return {"ports": ports or ["COM3"]}
    else:
        found = await aio(lambda: sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")))
        return {"ports": found or ["/dev/ttyUSB0"]}


@app.get("/api/log")
async def api_log():
    link: DroneLink = app.state.link
    path = link.get_log_path()
    if path:
        import os

        # The link keeps appending to this file. FileResponse sends what is there by the
        # time it reads, past the length it announced, and the download dies half way.
        size = os.path.getsize(path)

        def snapshot():
            left = size
            with open(path, "rb") as f:
                while left > 0:
                    chunk = f.read(min(65536, left))
                    if not chunk:
                        return
                    left -= len(chunk)
                    yield chunk

        name = os.path.basename(path)
        return StreamingResponse(
            snapshot(),
            media_type="text/csv",
            headers={"Content-Length": str(size), "Content-Disposition": f'attachment; filename="{name}"'},
        )
    return Response(status_code=404, content="No active log")


def _active_tlog_name() -> str:
    """The .tlog of the session that is recording now, from the CSV get_log_path names."""
    csv_path = app.state.link.get_log_path()
    return Path(csv_path).with_suffix(".tlog").name if csv_path else ""


@app.get("/api/logs")
async def api_local_logs():
    active = _active_tlog_name()
    files = []
    if cfg.LOG_DIR.exists():
        for path in sorted(cfg.LOG_DIR.glob("*.tlog"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                st = path.stat()
            except OSError:
                continue
            files.append(
                {
                    "name": path.name,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                    "active": path.name == active,
                }
            )
    return {"files": files}


@app.post("/api/logs/delete")
async def api_local_logs_delete(request: Request):
    body = await json_object(request)
    names = body.get("names", [])
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names) or len(names) > 500:
        return {"ok": False, "error": "Invalid names"}
    active = _active_tlog_name()
    root = cfg.LOG_DIR.resolve()
    deleted, refused = [], []
    for name in names:
        safe = Path(name).name
        if safe != name or not safe.endswith(".tlog") or safe == active:
            refused.append(name)
            continue
        path = (root / safe).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            refused.append(name)
            continue
        if not path.is_file():
            refused.append(name)
            continue
        try:
            path.unlink()
            # The CSV recorded beside a tlog describes the same session; keep them together.
            csv_path = path.with_suffix(".csv")
            if csv_path.is_file():
                csv_path.unlink()
            deleted.append(safe)
        except OSError:
            refused.append(name)
    return {"ok": True, "deleted": deleted, "refused": refused}


if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")
    if (DIST_DIR / "images").exists():
        app.mount("/images", StaticFiles(directory=str(DIST_DIR / "images")), name="images")
    if (DIST_DIR / "lib").exists():
        app.mount("/lib", StaticFiles(directory=str(DIST_DIR / "lib")), name="lib")

    @app.get("/manifest.json")
    async def manifest():
        return FileResponse(str(DIST_DIR / "manifest.json"), headers=_REVALIDATE)

    @app.get("/sw.js")
    async def service_worker():
        return FileResponse(str(DIST_DIR / "sw.js"), media_type="application/javascript", headers=_REVALIDATE)

    @app.get("/")
    async def index():
        headers = {**_REVALIDATE, "Content-Security-Policy": CONTENT_POLICY}
        return FileResponse(str(DIST_DIR / "index.html"), headers=headers)
