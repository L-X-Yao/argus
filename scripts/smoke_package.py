#!/usr/bin/env python3
"""Smoke-test a release package: step 2 of Releases in CONTRIBUTING.md.

A zip is extracted. An installer (..._setup.exe) is installed for this user into a folder of
its own and uninstalled at the end, and what it left is checked. Either way the packaged
backend and simulator are started with the packaged Python, and what a release must do is
checked. Windows only, like the package.

Usage: python scripts/smoke_package.py release/Argus_GCS_v3.7.4_amd64.zip
       python scripts/smoke_package.py release/Argus_GCS_v3.9.0_amd64_setup.exe

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
EXPOSED_PORT = 8125
SIM_PORT = 5771
TOKEN = "smoke-token-123456"

# The uninstall entry of an install for this user: AppId in scripts/installer.iss, plus "_is1".
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{2CDE95AA-A33A-4B5A-9B54-5350EAF7C49D}_is1"
# What uninstalling leaves: flight logs, map files of the user's own, firmware uploaded or downloaded.
KEPT = ("logs", "mbtiles", "firmware")
START_MENU = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Argus GCS"

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


def installed_at() -> Path | None:
    """Where the uninstall entry says Argus is installed for this user, if it is."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            return Path(winreg.QueryValueEx(key, "InstallLocation")[0])
    except OSError:
        return None


def run_setup(setup: Path, folder: Path, log: Path) -> int | None:
    """The exit code of a silent install into folder, or None when it took too long."""
    command = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", f"/DIR={folder}"]
    try:
        return subprocess.run([*command, f"/LOG={log}"], timeout=600).returncode
    except subprocess.TimeoutExpired:
        return None


def refuses_a_folder_of_other_things(setup: Path, other: Path) -> None:
    """An upgrade clears folders such as python in the folder it installs to: one that holds
    other things, and no Argus, is refused before anything is touched."""
    (other / "python").mkdir(parents=True)
    (other / "python" / "mine.txt").write_text("mine")
    code = run_setup(setup, other, other.parent / "refused.log")
    kept = (other / "python" / "mine.txt").is_file()
    record(
        "it refuses a folder that holds other things", code not in (0, None) and kept and installed_at() is None, code
    )


def install(setup: Path, root: Path) -> bool:
    if installed_at() is not None:
        raise SystemExit(
            "Argus is installed for this user, and the test would take over its uninstall entry. "
            "Uninstall it first, or run the test on another account."
        )
    refuses_a_folder_of_other_things(setup, root.parent / "Other things")
    log = root.parent / "install.log"
    code = run_setup(setup, root, log)
    record("the installer runs", code == 0, "timed out" if code is None else code)
    if code != 0 and log.is_file():
        print(log.read_text(encoding="utf-8", errors="replace")[-3000:], flush=True)
    where = installed_at()
    record(
        "it installs for this user, with an uninstall entry",
        where is not None and where.is_dir() and where.samefile(root),
        where,
    )
    shortcuts = sorted(p.name for p in START_MENU.glob("*.lnk"))
    record("Start menu shortcuts", len(shortcuts) == 3, shortcuts)
    return code == 0


def uninstall(root: Path) -> None:
    # Files of the user's own beside the program, and some that Argus makes as it runs.
    for name in (*KEPT, "tile_cache", "param_cache"):
        (root / name).mkdir(exist_ok=True)
        (root / name / "smoke.txt").write_text("smoke")
    (root / ".gcs_token").write_text(TOKEN)
    done = subprocess.run([str(root / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=600)
    # The uninstaller hands the work to a copy of itself in TEMP, which may still be at it.
    deadline = time.monotonic() + 120
    while ((root / "unins000.exe").exists() or installed_at() is not None) and time.monotonic() < deadline:
        time.sleep(1)
    record("the uninstaller runs", done.returncode == 0 and not (root / "unins000.exe").exists(), done.returncode)
    left = [
        name
        for name in ("backend", "dist", "python", "tile_cache", "param_cache", ".gcs_token", "Argus地面站.bat")
        if (root / name).exists()
    ]
    record("it removes the program, its caches and the token", not left, left)
    record("it keeps flight logs, map files and firmware", all((root / name / "smoke.txt").is_file() for name in KEPT))
    record("no uninstall entry or shortcuts are left", installed_at() is None and not START_MENU.exists())


def check_package(root: Path, version: str) -> None:
    python = str(root / "python" / "python.exe")
    texts = [
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "README.txt",
        "LICENSES/Apache-2.0.txt",
        "LICENSES/BSD-2-Clause-Leaflet.txt",
        "LICENSES/BSD-3-Clause-pyserial.txt",
        "dist/THIRD-PARTY-LICENSES.txt",
        "python/LICENSE.txt",
    ]
    missing = [name for name in texts if not (root / name).is_file()]
    record("license texts are in the package", not missing, missing or "")
    web = root / "dist" / "THIRD-PARTY-LICENSES.txt"
    listed = web.read_text(encoding="utf-8") if web.is_file() else ""
    record("the web build lists its libraries", all(f"\n{name}@" in listed for name in ("svelte", "maplibre-gl")))
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
        status, headers, _ = request(f"{base}/")
        record("index", status == 200)
        policy = headers.get("content-security-policy", headers.get("Content-Security-Policy", ""))
        record("the page takes scripts from this server only", "script-src 'self';" in policy, policy[:40])

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
        rebound = {"Host": f"evil.example:{PORT}", "Authorization": "x"}
        record("another site's name for this machine", request(f"{base}/api/ports", None, rebound)[0] == 403)

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

        exposed = [python, r"backend\server.py", "--host", "0.0.0.0", "--no-browser", "--port", str(EXPOSED_PORT)]
        try:
            refused = subprocess.run(exposed, cwd=root, env=env, capture_output=True, text=True, timeout=30)
            record("no token, no network", refused.returncode != 0 and "GCS_AUTH_TOKEN" in refused.stderr)
        except subprocess.TimeoutExpired:
            record("no token, no network", False, "it started")
    finally:
        for proc in procs:
            proc.kill()
        for proc in procs:
            proc.wait(timeout=10)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    package = Path(sys.argv[1]).resolve()
    version = re.search(r"_v(\d+\.\d+\.\d+)_", package.name).group(1)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        if package.suffix.lower() == ".exe":
            # A space in the name, as in the default folder under Programs.
            root = Path(tmp) / "Argus GCS"
            try:
                if install(package, root):
                    check_package(root, version)
            finally:
                # Also after a failed or timed-out install that got as far as the uninstaller:
                # its entry and shortcuts would outlive the folder.
                if (root / "unins000.exe").exists():
                    uninstall(root)
        else:
            with zipfile.ZipFile(package) as z:
                z.extractall(tmp)
            check_package(next(Path(tmp).iterdir()), version)
    print(f"{failures} failed", flush=True)
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
