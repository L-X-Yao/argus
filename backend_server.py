#!/usr/bin/env python3
"""Standalone entry point for PL-Link GCS backend (used by Tauri sidecar).

When packaged with PyInstaller, this becomes the single-file executable that
Tauri spawns as a sidecar process.  It starts the FastAPI/uvicorn server on
the given port (default 8100) and serves both the REST API and the WebSocket
endpoint that the Tauri webview connects to.
"""
import argparse
import logging
import sys
import threading
import time
import webbrowser
from pathlib import Path

_here = Path(__file__).resolve().parent
sys.path.insert(0, str(_here))
sys.path.insert(0, str(_here.parent))

import uvicorn


def _open_browser(port: int):
    """Wait for server to be ready, then open browser."""
    import urllib.request
    for _ in range(30):
        time.sleep(0.3)
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/health' % port, timeout=1)
            webbrowser.open('http://localhost:%d' % port)
            return
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description='PL-Link GCS backend')
    parser.add_argument('--port', type=int, default=8100)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()

    if not args.no_browser:
        threading.Thread(target=_open_browser, args=(args.port,), daemon=True).start()

    logging.getLogger('uvicorn.error').setLevel(logging.WARNING)

    uvicorn.run(
        'backend.app:app',
        host=args.host,
        port=args.port,
        log_level='warning',
    )


if __name__ == '__main__':
    main()
