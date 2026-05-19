"""
Shared fixtures: simulator + backend + WebSocket client.
"""
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import websockets

V3_DIR = Path(__file__).resolve().parent.parent
GS_DIR = V3_DIR.parent
SIM_SCRIPT = GS_DIR / 'sim_pllink.py'

SIM_PORT = 15770
BACKEND_PORT = 18100


@pytest.fixture(scope='session')
def sim_process():
    proc = subprocess.Popen(
        [sys.executable, str(SIM_SCRIPT), str(SIM_PORT)],
        cwd=str(GS_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(1.5)
    yield proc
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope='session')
def backend_process(sim_process):
    proc = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'backend.app:app',
         '--host', '127.0.0.1', '--port', str(BACKEND_PORT),
         '--log-level', 'warning'],
        cwd=str(V3_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(2)
    yield proc
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope='session')
def backend_url(backend_process):
    return f'http://127.0.0.1:{BACKEND_PORT}'


@pytest.fixture(scope='session')
def ws_url(backend_process):
    return f'ws://127.0.0.1:{BACKEND_PORT}/ws'


@pytest.fixture
def sim_port():
    return SIM_PORT
