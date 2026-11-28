"""RTSP → MJPEG video proxy for browser display."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import shutil
import subprocess
import threading
import time
from urllib.parse import urlparse

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .config import cfg, off_limits

router = APIRouter()

_ALLOWED_SCHEMES = {"rtsp", "rtmp", "http", "https"}


def _validate_video_url(url: str) -> str | None:
    """Validate video URL. Returns error message or None if valid."""
    if len(url) > cfg.VIDEO_URL_MAX_LEN:
        return "URL too long"
    try:
        parsed = urlparse(url)
    except ValueError:
        return "Malformed URL"
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return "Only rtsp/rtmp/http/https schemes allowed"
    host = parsed.hostname or ""
    if not host:
        return "No hostname in URL"
    # Try IP literal first; if that fails, resolve the hostname via DNS and
    # check the result. Previously a hostname like `internal-server.lan`
    # that resolved to 127.0.0.1 / 169.254.169.254 (AWS metadata) would
    # slip past the IP-literal check entirely.
    try:
        addr = ipaddress.ip_address(host)
        if off_limits(addr):
            return "Loopback and link-local addresses not allowed"
        return None
    except ValueError:
        pass
    if host in ("localhost", "localhost.localdomain"):
        return "Loopback and link-local addresses not allowed"
    import socket as _socket

    try:
        addrs = _socket.getaddrinfo(host, None)
    except _socket.gaierror:
        return "Cannot resolve hostname"
    for _fam, *_rest, sockaddr in addrs:
        try:
            resolved = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if off_limits(resolved):
            return "Resolves to a loopback, link-local or reserved address"
    return None


_active_proc: subprocess.Popen | None = None
_proc_lock = threading.Lock()

# Why the last stream ended, for the page to show instead of "load failed". Keyed by
# the stream id the page generated: two pages can watch at once, and an error belongs
# to the page that asked for that stream.
_last_error: dict | None = None
_last_error_lock = threading.Lock()

_STDERR_TAIL = 8192

# ffmpeg answers a failed input on stderr with one of these. The order matters:
# "Server returned 404 Not Found" must read as not-found, "Exiting normally,
# received signal 9" as a stream its page stopped.
_ERROR_CODES = (
    ("refused", re.compile(r"connection refused", re.I)),
    ("timeout", re.compile(r"(connection|operation) timed out|timeout|operation too slow", re.I)),
    ("auth", re.compile(r"unauthorized|forbidden|authentication", re.I)),
    # Before "not found": ffmpeg says "Protocol not found" and "moov atom not found".
    (
        "protocol",
        re.compile(
            r"protocol not found|unknown input format|invalid data found when processing input"
            r"|moov atom not found|error while opening",
            re.I,
        ),
    ),
    ("notfound", re.compile(r"not found|\b404\b", re.I)),
    (
        "unreachable",
        re.compile(
            r"network is unreachable|no route to host|could not resolve|failed to resolve"
            r"|name or service not known|temporary failure in name resolution",
            re.I,
        ),
    ),
    ("server", re.compile(r"server returned 5", re.I)),
)

# A URL typed with user:pass is echoed by ffmpeg on failure; the page must not show it.
_URL_CREDENTIALS = re.compile(r"(://)[^/@\s]+@")
# ffmpeg echoes the input URL in its error lines, and a query string can carry the
# words a classifier looks for ("?timeout=1"). Classification sees <url> instead.
_URL_IN_TEXT = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://\S+")
# ffmpeg's progress statistics end in \r, not \n; the tail and the classifier both
# treat \r and \n as separators.
_SEGMENT_SPLIT = re.compile(r"[\r\n]+")


class _StderrTail(threading.Thread):
    """Reads ffmpeg's stderr to the end, keeping its tail.

    The stream writes MJPEG to stdout and logs to stderr; a pipe that nobody
    drains fills up and stops ffmpeg, so this runs beside the read loop.
    """

    def __init__(self, stream) -> None:
        super().__init__(daemon=True)
        self._stream = stream
        self._lock = threading.Lock()
        self._text = ""

    def run(self) -> None:
        try:
            while True:
                # read1, not readline: ffmpeg's progress statistics are \r-terminated
                # and readline() would hold all of them until a newline or EOF, so the
                # "tail" would grow with the stream instead of staying 8 KB.
                reader = getattr(self._stream, "read1", None) or self._stream.read
                chunk = reader(4096)
                if not chunk or not isinstance(chunk, (bytes, str)):
                    break
                text = chunk.decode("utf-8", "replace") if isinstance(chunk, bytes) else chunk
                with self._lock:
                    self._text = (self._text + text)[-_STDERR_TAIL:]
        except Exception:
            pass
        finally:
            try:
                self._stream.close()
            except Exception:
                pass

    def tail(self) -> str:
        with self._lock:
            return self._text


def _classify_ffmpeg_error(text: str) -> tuple[str, str]:
    """Map ffmpeg's stderr tail to (code, detail). Code "other" keeps the detail.

    The last meaningful segment decides: the URL is masked before matching, or a
    query string like "?timeout=1" would name the reason itself.
    """
    segments = [segment.strip() for segment in _SEGMENT_SPLIT.split(text) if segment.strip()]
    for segment in reversed(segments):
        cleaned = _URL_IN_TEXT.sub("<url>", segment)
        for name, pattern in _ERROR_CODES:
            if pattern.search(cleaned):
                return name, _URL_CREDENTIALS.sub(r"\1***@", segment)[:300]
    detail = _URL_CREDENTIALS.sub(r"\1***@", segments[-1])[:300] if segments else ""
    return "other", detail


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


# Which protocols an input may use, by its scheme. Nested resources (HLS segments and
# keys, RTSP media) must be named too, or ffmpeg refuses them. `file` is deliberately
# absent: a playlist that names a local file must not read it (audit 2026-11-24 L2).
_PROTOCOL_WHITELISTS = {
    "rtsp": "rtsp,rtp,srtp,tcp,udp",
    "rtmp": "rtmp,rtmpt,ffrtmphttp,tcp,tls,crypto",
    "http": "http,https,httpproxy,tcp,tls,crypto",
    "https": "http,https,httpproxy,tcp,tls,crypto",
}


def _ffmpeg_args(url: str) -> list[str]:
    """What ffmpeg is told to read the stream at url and write MJPEG to its stdout."""
    # An option of the RTSP reader alone. Given it with any other input, ffmpeg stops at
    # "Option rtsp_transport not found": http, https and rtmp streams never played.
    scheme = urlparse(url).scheme
    transport = ["-rtsp_transport", "tcp"] if scheme == "rtsp" else []
    whitelist = _PROTOCOL_WHITELISTS.get(scheme, "rtsp,rtp,srtp,tcp,udp")
    return [
        *transport,
        "-protocol_whitelist",
        whitelist,
        "-i",
        url,
        "-f",
        "mjpeg",
        "-q:v",
        "5",
        "-r",
        "15",
        "-an",
        "pipe:1",
    ]


@router.get("/api/video")
async def video_stream(url: str = "", stream: str = ""):
    """Proxy RTSP/video stream as MJPEG for browser display."""
    if not url:
        return {"error": "No video URL provided"}
    # getaddrinfo is synchronous: on the event loop a slow resolver stalls every
    # websocket push and request until it returns. Off it, as the NTRIP start
    # already is (post-release review 2026-11-18).
    url_err = await asyncio.to_thread(_validate_video_url, url)
    if url_err:
        return {"error": f"Invalid video URL: {url_err}"}
    # Residual (audit 2026-11-16 L4): ffmpeg resolves the name again when it
    # connects, so a name re-resolved between this check and the connection
    # can hand the stream to an address that was never checked. Pinning it is
    # not possible without breaking streams: https needs the name for SNI and
    # the certificate, and rewriting the host in rtsp/http URLs breaks
    # name-based virtual hosts. The operator types the address, as with the
    # vehicle link.
    if not _ffmpeg_available():
        return {"error": "ffmpeg not installed on server"}

    with _proc_lock:
        if _active_proc is not None:
            try:
                # A deliberate stop, not a failure: the generator reads this flag.
                _active_proc._argus_stopped = True  # type: ignore[attr-defined]
                _active_proc.kill()
                _active_proc.wait(timeout=3)
            except OSError:
                pass

    async def generate():
        global _active_proc, _last_error  # noqa: PLW0603
        proc = subprocess.Popen(
            # The program is named here, where a reader and CodeQL can see that no request sets it.
            ["ffmpeg", *_ffmpeg_args(url)],
            # Its own, or it reads the keys typed into the console the server runs in.
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        tail = _StderrTail(proc.stderr) if proc.stderr is not None else None
        if tail is not None:
            tail.start()
        with _proc_lock:
            _active_proc = proc
        loop = asyncio.get_running_loop()
        try:
            buf = b""
            # If the upstream isn't MJPEG (e.g. mis-configured URL), the
            # JPEG markers never appear and `buf += chunk` grows forever.
            # Cap at ~8MB and reset to recover.
            _MAX_BUF = 8 * 1024 * 1024
            while True:
                chunk = await loop.run_in_executor(
                    None,
                    proc.stdout.read,
                    4096,  # type: ignore[union-attr]
                )
                if not chunk:
                    break
                buf += chunk
                if len(buf) > _MAX_BUF:
                    # Keep only the trailing 64KB in case a partial header
                    # is in there.
                    buf = buf[-65536:]
                # Extract complete JPEG frames (FF D8 … FF D9).
                while True:
                    start = buf.find(b"\xff\xd8")
                    end = buf.find(b"\xff\xd9", start + 2) if start >= 0 else -1
                    if start >= 0 and end >= 0:
                        frame = buf[start : end + 2]
                        buf = buf[end + 2 :]
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
                    else:
                        break
        finally:
            try:
                proc.kill()
            except OSError:
                pass
            rc = proc.wait()
            intentional = bool(getattr(proc, "_argus_stopped", False))
            if tail is not None:
                # The reader may still be draining the pipe; its tail is the reason.
                tail.join(timeout=2)
                # Only a process that ended on its own with a failure code has a reason
                # to report. A page's Stop kills ffmpeg without letting it say anything,
                # and a stream that ended cleanly is not a failure either.
                if not intentional and rc not in (0, None):
                    code, detail = _classify_ffmpeg_error(tail.tail())
                    # "other" without a line says nothing; an empty message would read
                    # as a failure with no reason.
                    if code != "other" or detail:
                        with _last_error_lock:
                            _last_error = {
                                "at": time.time(),
                                "stream": stream,
                                "code": code,
                                "detail": detail,
                            }
            with _proc_lock:
                if _active_proc is proc:
                    _active_proc = None

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/api/video/stop")
async def video_stop():
    """Stop active video stream."""
    global _active_proc  # noqa: PLW0603
    with _proc_lock:
        if _active_proc is not None:
            try:
                _active_proc._argus_stopped = True  # type: ignore[attr-defined]
                _active_proc.kill()
                _active_proc.wait(timeout=3)
            except OSError:
                pass
            _active_proc = None
    return {"ok": True}


@router.get("/api/video/validate")
async def video_validate(url: str = ""):
    """Check a URL and ffmpeg without opening a stream.

    The panel used to fetch the streaming route just to read its headers, which
    starts a second ffmpeg and can hold a camera's single RTSP session. This
    route only validates; the one streaming request is the <img> itself.
    """
    if not url:
        return {"ok": False, "error": "No video URL provided"}
    err = await asyncio.to_thread(_validate_video_url, url)
    if err:
        return {"ok": False, "error": f"Invalid video URL: {err}"}
    if not _ffmpeg_available():
        return {"ok": False, "error": "ffmpeg not installed on server"}
    return {"ok": True}


@router.get("/api/video/last_error")
async def video_last_error(stream: str = ""):
    """Why the last stream ended, for the panel to say more than "load failed".

    Keyed by the id the panel put on its stream: an error belongs to the page that
    started it, and an id is required. The detail can name the stream's host and
    path, so an empty id must not hand it to whoever asks.
    """
    with _last_error_lock:
        err = dict(_last_error) if _last_error else None
    if err is None or not stream or err.get("stream") != stream:
        return {"ok": True, "error": None}
    return {"ok": True, "error": {"code": err["code"], "detail": err["detail"]}}


@router.get("/api/video/capabilities")
async def video_capabilities():
    """Report video streaming capabilities."""
    return {
        "mjpeg": _ffmpeg_available(),
        "webrtc": False,
        "protocols": ["rtsp", "rtmp", "http"] if _ffmpeg_available() else [],
    }
