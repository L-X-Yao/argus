"""Centralized configuration — all tunable constants in one place."""

from __future__ import annotations

import asyncio
import ipaddress
import os
import re
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# The benchmarking range, where proxy tools in fake-IP mode put every host they resolve.
# Nothing internal lives there, and the internal-address guards would refuse every public
# server behind such a tool.
FAKE_IP_RANGE = ipaddress.ip_network("198.18.0.0/15")
VERSION = re.search(r'^version = "([^"]+)"', (ROOT_DIR / "pyproject.toml").read_text(), re.MULTILINE).group(1)


def off_limits(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for an address a camera or caster URL may not name: this machine, link-local
    (where a cloud host keeps its metadata service), multicast and the reserved blocks.
    A private address passes. A vehicle's camera and an RTK base live on one, and the
    vehicle link already connects to whatever address the operator names."""
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved


async def json_object(request) -> dict:
    """The body of a request as a JSON object, and {} for anything else, which a route then
    answers as it answers a missing field. Each one used to fail with a 500 on a body that
    was not JSON, or was JSON but a list."""
    try:
        body = await request.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


async def aio(fn, *args):
    """Run a blocking function in the default executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(fn, *args) if args else fn)


# Downloads get their own threads. A dead uplink holds each one for a full
# timeout, and link connect and disconnect run on the default executor, which
# has only cpu_count + 4 threads.
_download_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="argus-download")


async def aio_download(fn, *args):
    """Run a blocking network download off the default executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_download_pool, partial(fn, *args) if args else fn)


def _env(key: str, default, cast=None):
    val = os.environ.get(key)
    # A blank `ARGUS_HOST=` line counts as unset: host "" binds every interface.
    if not val:
        return default
    cast_fn = cast or type(default)
    try:
        return cast_fn(val)
    except (ValueError, TypeError):
        # Bad env var (e.g. ARGUS_PORT=abc) used to crash at module import
        # before logging was configured, leaving the operator with a bare
        # traceback. Fall back to the default and log a warning so the
        # process still starts.
        import logging

        logging.getLogger("gcs").warning(
            "Invalid value for %s=%r; falling back to default %r",
            key,
            val,
            default,
        )
        return default


class Config:
    HOST: str = _env("ARGUS_HOST", "127.0.0.1")
    PORT: int = _env("ARGUS_PORT", 8100)
    # Tianditu serves nothing without a key of your own (console.tianditu.gov.cn).
    TIANDITU_KEY: str = _env("ARGUS_TIANDITU_KEY", "")

    # Connection
    TCP_CONNECT_TIMEOUT: float = 5.0
    TCP_READ_TIMEOUT: float = 0.1
    UDP_READ_TIMEOUT: float = 0.1
    SERIAL_READ_TIMEOUT: float = 0.1
    SERIAL_BAUD: int = 57600

    # Heartbeat / link management
    HEARTBEAT_INTERVAL: float = 0.5
    LINK_LOST_TIMEOUT: float = 5.0
    RECONNECT_DELAY: float = 3.0
    MAIN_LOOP_SLEEP: float = 0.02

    # WebSocket push rates
    WS_PUSH_INTERVAL_CONNECTED: float = 0.2
    WS_PUSH_INTERVAL_IDLE: float = 1.0

    # Logging
    LOG_WRITE_INTERVAL: float = 0.25
    LOG_DIR: Path = ROOT_DIR / "logs"

    # Tile cache
    TILE_CACHE_MAX: int = 50000
    TILE_DOWNLOAD_TIMEOUT: float = 10.0
    TILE_RETRY_AFTER: float = 30.0

    # SRTM terrain
    SRTM_CACHE_MAX: int = 500
    SRTM_DOWNLOAD_TIMEOUT: float = 10.0
    SRTM_FILE_MAX: int = 30 * 1024 * 1024  # 30 MB

    # Firmware
    FIRMWARE_MAX_SIZE: int = 50 * 1024 * 1024  # 50 MB
    FIRMWARE_HTML_MAX: int = 1024 * 1024  # 1 MB
    FIRMWARE_LIST_TIMEOUT: float = 10.0
    FIRMWARE_DOWNLOAD_TIMEOUT: float = 60.0

    # Param metadata
    PARAM_META_MAX: int = 50 * 1024 * 1024  # 50 MB: each file is about 3
    PARAM_CACHE_TTL: int = 86400 * 7
    PARAM_DOWNLOAD_TIMEOUT: float = 15.0
    PARAM_FETCH_TIMEOUT: float = 60.0
    # If no PARAM_VALUE has been seen for this many seconds during a fetch,
    # but total_count > received, assume packet loss and start re-requesting
    # missing indices individually via PARAM_REQUEST_READ (msg 20).
    PARAM_GAP_FILL_DELAY: float = 2.0

    # Mission
    MISSION_START_DELAY: float = 0.3
    MISSION_DL_TIMEOUT: float = 30.0
    # A lost frame stalls a transfer, as each side waits for the other. Asked again after:
    MISSION_RETRY_INTERVAL: float = 1.5
    # An upload: the FC asks again for an item by itself every second
    # (MissionItemProtocol::update), so this much silence means its count or ack went missing.
    MISSION_UPLOAD_RETRY: float = 3.0
    CMD_RETRY_INTERVAL: float = 1.0
    CMD_TRIES: int = 3
    STORE_CLEAR_TIMEOUT: float = 3.0
    STREAM_REQUEST_SPACING: float = 0.01
    PARAM_LOAD_SPACING: float = 0.02

    # Git version
    GIT_HASH_TIMEOUT: float = 2.0

    # Validation
    VALID_BAUD_RATES: tuple = (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600)
    VIDEO_URL_MAX_LEN: int = 2048


cfg = Config()

if not 1 <= cfg.PORT <= 65535:
    import logging

    logging.getLogger("gcs").warning(
        "ARGUS_PORT=%d out of range 1-65535; using default 8100",
        cfg.PORT,
    )
    cfg.PORT = 8100
