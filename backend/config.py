"""Centralized configuration — all tunable constants in one place."""
from __future__ import annotations

import os


def _env(key: str, default, cast=None):
    val = os.environ.get(key)
    if val is None:
        return default
    return (cast or type(default))(val)


class Config:
    HOST: str = _env('ARGUS_HOST', '127.0.0.1')
    PORT: int = _env('ARGUS_PORT', 8100)

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

    # Tile cache
    TILE_CACHE_MAX: int = 50000
    TILE_DOWNLOAD_TIMEOUT: float = 10.0

    # Param metadata
    PARAM_CACHE_TTL: int = 86400 * 7
    PARAM_DOWNLOAD_TIMEOUT: float = 15.0

    # Mission
    MISSION_START_DELAY: float = 0.3
    STREAM_REQUEST_SPACING: float = 0.01
    PARAM_LOAD_SPACING: float = 0.02

    # Git version
    GIT_HASH_TIMEOUT: float = 2.0


cfg = Config()
