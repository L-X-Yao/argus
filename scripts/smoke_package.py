#!/usr/bin/env python3
"""Smoke-test a release zip: step 2 of Releases in CONTRIBUTING.md.

Extracts the zip, starts the packaged backend and simulator with the packaged Python,
and checks what a release must do. Windows only, like the package.

Usage: python scripts/smoke_package.py release/Argus_GCS_v3.7.4_amd64.zip

Standard library only, so it runs from any Python. The websocket check runs on the
packaged Python, which is also what proves the bundled websockets works. Exits with the
number of failures.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

PORT = 8123
TOKEN_PORT = 8124
SIM_PORT = 5771
TOKEN = "smoke-token-123456"

WS_CHECK = """
import asyncio, json, sys
import websockets

async def main():
    async with websockets.connect('ws://127.0.0.1:%d/ws') as ws:
        await ws.send(json.dumps({'type': 'connect', 'port': 'tcp:localhost:%d', 'baud': 57600}))
        for _ in range(400):
            m = json.loads(await asyncio.wait_for(ws.recv(), 15))
            if m.get('type') == 'state' and m.get('connected') and m.get('gps_sats', 0) > 0:
                await ws.send(json.dumps({'type': 'disconnect'}))
                return 0
    return 1

sys.exit(asyncio.run(main()))
""" % (PORT, SIM_PORT)

failures = 0


def record(name: str, ok: bool, detail: object = "") -> None:
    global failures
    failures += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {name}  {detail}", flush=True)


def request(url: str, data: bytes | None = None, headers: dict | None = None) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def wait_healthy(port: int) -> bool:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if request(f"http://127.0.0.1:{port}/health")[0] == 200:
                return True
        except OSError:
            time.sleep(0.5)
    return False


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    zip_path = Path(sys.argv[1]).resolve()
    version = re.search(r"v(\d+\.\d+\.\d+)", zip_path.name).group(1)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        root = next(Path(tmp).iterdir())
        python = str(root / "python" / "python.exe")
        server = [python, r"backend\server.py", "--host", "127.0.0.1", "--no-browser", "--port"]
        env = {k: v for k, v in os.environ.items() if k.upper() != "GCS_AUTH_TOKEN"}
        procs = [
            subprocess.Popen([*server, str(PORT)], cwd=root, env=env),
            subprocess.Popen([python, "simulator.py", str(SIM_PORT)], cwd=root, env=env, stdout=subprocess.DEVNULL),
            subprocess.Popen([*server, str(TOKEN_PORT)], cwd=root, env={**env, "GCS_AUTH_TOKEN": TOKEN}),
        ]
        try:
            base = f"http://127.0.0.1:{PORT}"
            record("the backend starts", wait_healthy(PORT))

            got = json.loads(request(f"{base}/api/version")[2]).get("version")
            record("version", got == version, got)
            record("index", request(f"{base}/")[0] == 200)

            worker = next((root / "dist" / "assets").glob("maplibre-gl-worker*")).name
            status, headers, _ = request(f"{base}/assets/{worker}")
            content_type = headers.get("content-type", headers.get("Content-Type", ""))
            record("map worker is served as a script", status == 200 and "javascript" in content_type, content_type)

            foreign = {"Origin": "http://evil.example", "Content-Type": "text/plain"}
            record("POST from another site", request(f"{base}/api/tile_cache_clear", b"{}", foreign)[0] == 403)
            own = {"Origin": f"http://localhost:{PORT}", "Content-Type": "application/json"}
            record("POST from itself", request(f"{base}/api/tile_cache_clear", b"{}", own)[0] == 200)
            image = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Dest": "image"}
            record("image from another site", request(f"{base}/api/video/stop", None, image)[0] == 403)

            ws = subprocess.run([python, "-c", WS_CHECK], cwd=root, env=env, timeout=120)
            record("live telemetry over the websocket", ws.returncode == 0)

            token = f"http://127.0.0.1:{TOKEN_PORT}"
            record("the backend with a token starts", wait_healthy(TOKEN_PORT))
            record("no login, no data", request(f"{token}/api/ports")[0] == 401)
            login = request(
                f"{token}/api/auth/login",
                json.dumps({"token": TOKEN}).encode(),
                {"Origin": token, "Content-Type": "application/json"},
            )
            record("login", login[0] == 200)
            cookie = login[1].get("set-cookie", login[1].get("Set-Cookie", "")).split(";")[0]
            record("logged in, data", request(f"{token}/api/ports", None, {"Cookie": cookie})[0] == 200)
        finally:
            for proc in procs:
                proc.kill()
            for proc in procs:
                proc.wait(timeout=10)
    print(f"{failures} failed", flush=True)
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
