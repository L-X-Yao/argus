#!/usr/bin/env python3
"""Standalone entry point for PL-Link GCS backend (used by Tauri sidecar).

When packaged with PyInstaller, this becomes the single-file executable that
Tauri spawns as a sidecar process.  It starts the FastAPI/uvicorn server on
the given port (default 8100) and serves both the REST API and the WebSocket
endpoint that the Tauri webview connects to.
"""
import argparse
import sys
from pathlib import Path

# Ensure the parent directory is in path so that `backend` package and
# `pllink_proto` (one level up) are importable regardless of CWD.
_here = Path(__file__).resolve().parent
sys.path.insert(0, str(_here))
sys.path.insert(0, str(_here.parent))

import uvicorn


def main():
    parser = argparse.ArgumentParser(description='PL-Link GCS backend')
    parser.add_argument('--port', type=int, default=8100)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()

    uvicorn.run(
        'backend.app:app',
        host=args.host,
        port=args.port,
        log_level='warning',
    )


if __name__ == '__main__':
    main()
