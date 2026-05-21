#!/usr/bin/env python3
"""
Argus GCS — one-click launcher.
Starts simulator + backend on a single port, opens browser.

Usage:
    python run.py              (backend only, connect real hardware)
    python run.py --sim        (start simulator for testing)
"""
import argparse
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SIM_SCRIPT = ROOT_DIR / 'scripts' / 'sim_pllink.py'


def main():
    parser = argparse.ArgumentParser(description='Argus GCS')
    parser.add_argument('--sim', action='store_true', help='Start simulator on port 5770')
    parser.add_argument('--host', default='0.0.0.0', help='Bind address (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8100, help='HTTP port (default: 8100)')
    args = parser.parse_args()

    sim_proc = None
    if args.sim:
        print('[SIM] Starting simulator on port 5770...')
        sim_proc = subprocess.Popen(
            [sys.executable, str(SIM_SCRIPT), '5770'],
            cwd=str(ROOT_DIR),
        )
        time.sleep(1)

    print('=' * 50)
    print('  Argus GCS')
    print('  http://localhost:%d' % args.port)
    if args.sim:
        print('  Simulator: tcp:localhost:5770')
    print('  Ctrl+C to stop')
    print('=' * 50)

    webbrowser.open('http://localhost:%d' % args.port)

    try:
        import uvicorn
        uvicorn.run(
            'backend.app:app',
            host=args.host,
            port=args.port,
            log_level='warning',
        )
    except KeyboardInterrupt:
        pass
    finally:
        if sim_proc:
            sim_proc.terminate()
            sim_proc.wait()


if __name__ == '__main__':
    main()
