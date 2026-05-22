"""RTSP → MJPEG video proxy for browser display."""
from __future__ import annotations

import asyncio
import ipaddress
import shutil
import subprocess
import threading
from urllib.parse import urlparse

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .config import cfg

router = APIRouter()

_ALLOWED_SCHEMES = {'rtsp', 'rtmp', 'http', 'https'}


def _validate_video_url(url: str) -> str | None:
    """Validate video URL. Returns error message or None if valid."""
    if len(url) > cfg.VIDEO_URL_MAX_LEN:
        return 'URL too long'
    try:
        parsed = urlparse(url)
    except ValueError:
        return 'Malformed URL'
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return 'Only rtsp/rtmp/http/https schemes allowed'
    host = parsed.hostname or ''
    if not host:
        return 'No hostname in URL'
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback or addr.is_reserved:
            return 'Private/loopback addresses not allowed'
    except ValueError:
        if host in ('localhost', 'localhost.localdomain'):
            return 'Private/loopback addresses not allowed'
    return None

_active_proc: subprocess.Popen | None = None
_proc_lock = threading.Lock()


def _ffmpeg_available() -> bool:
    return shutil.which('ffmpeg') is not None


@router.get('/api/video')
async def video_stream(url: str = ''):
    """Proxy RTSP/video stream as MJPEG for browser display."""
    global _active_proc

    if not url:
        return {'error': 'No video URL provided'}
    url_err = _validate_video_url(url)
    if url_err:
        return {'error': f'Invalid video URL: {url_err}'}
    if not _ffmpeg_available():
        return {'error': 'ffmpeg not installed on server'}

    with _proc_lock:
        if _active_proc is not None:
            try:
                _active_proc.kill()
                _active_proc.wait(timeout=3)
            except OSError:
                pass

    async def generate():
        global _active_proc  # noqa: PLW0603
        proc = subprocess.Popen(
            [
                'ffmpeg',
                '-rtsp_transport', 'tcp',
                '-i', url,
                '-f', 'mjpeg',
                '-q:v', '5',
                '-r', '15',
                '-an',
                'pipe:1',
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        with _proc_lock:
            _active_proc = proc
        loop = asyncio.get_event_loop()
        try:
            buf = b''
            while True:
                chunk = await loop.run_in_executor(
                    None, proc.stdout.read, 4096  # type: ignore[union-attr]
                )
                if not chunk:
                    break
                buf += chunk
                # Extract complete JPEG frames (FF D8 … FF D9).
                while True:
                    start = buf.find(b'\xff\xd8')
                    end = buf.find(b'\xff\xd9', start + 2) if start >= 0 else -1
                    if start >= 0 and end >= 0:
                        frame = buf[start:end + 2]
                        buf = buf[end + 2:]
                        yield (
                            b'--frame\r\n'
                            b'Content-Type: image/jpeg\r\n\r\n'
                            + frame
                            + b'\r\n'
                        )
                    else:
                        break
        finally:
            proc.kill()
            proc.wait()
            with _proc_lock:
                _active_proc = None

    return StreamingResponse(
        generate(),
        media_type='multipart/x-mixed-replace; boundary=frame',
    )


@router.get('/api/video/stop')
async def video_stop():
    """Stop active video stream."""
    global _active_proc  # noqa: PLW0603
    with _proc_lock:
        if _active_proc is not None:
            try:
                _active_proc.kill()
                _active_proc.wait(timeout=3)
            except OSError:
                pass
            _active_proc = None
    return {'ok': True}


@router.get('/api/video/capabilities')
async def video_capabilities():
    """Report video streaming capabilities."""
    return {
        'mjpeg': _ffmpeg_available(),
        'webrtc': False,
        'protocols': ['rtsp', 'rtmp', 'http'] if _ffmpeg_available() else [],
    }

