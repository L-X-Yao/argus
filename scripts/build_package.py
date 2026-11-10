#!/usr/bin/env python3
"""
Build self-contained Windows package for Argus GCS v3.
Downloads the Python embeddable below, bundles all dependencies offline,
produces a zip that runs on any Windows 10/11 x64 with zero install.

Usage:
    python3 build_package.py              # x64 (default)
    python3 build_package.py --arch arm64 # ARM64 Windows

Run it on the Python version it bundles, as CI does: pip decides which conditional
dependencies to fetch from the interpreter running this script.
"""

import argparse
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

# The launchers have Chinese names, and a Windows console may not take them.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = SCRIPT_DIR / "release"

_VERSION = re.search(r'^version = "([^"]+)"', (SCRIPT_DIR / "pyproject.toml").read_text(), re.MULTILINE).group(1)

# A version python.org still builds for Windows: it stops two years after x.y.0, and
# the fixes after that never reach an embeddable zip (3.10 stayed at 3.10.11 from 2023).
PY_VER = "3.14.10"
PY_BASE_URL = "https://www.python.org/ftp/python/{ver}/python-{ver}-embed-{arch}.zip"
# What python.org served for PY_VER, as its .spdx.json beside the zip states too.
PY_SHA256 = {
    "amd64": "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159",
    "arm64": "bbe116bb1248820359cbf25127ac5c7794ea161869d83686cfbc9a45203ff836",
}

PIP_DEPS = [
    "fastapi",
    "uvicorn",
    "pyserial",
    "websockets",
    "python-multipart",
    # pip evaluates environment markers against the interpreter running this
    # script, not the Windows target, so what the packages above only need on
    # Windows has to be listed by hand.
    "typing_extensions",
    "colorama",
]


def allowed_versions() -> list[str]:
    """What pyproject.toml allows of each dependency, as pip constraints: the package ships
    what the tests ran against, and none of the versions it rules out. Without the extras,
    which a constraint cannot carry."""
    import tomllib  # here, so that Python 3.10 can still import this file for its tests

    project = tomllib.loads((SCRIPT_DIR / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return [re.sub(r"\[[^\]]*\]", "", dep) for dep in project["dependencies"]]


def download(url, desc):
    print("  Downloading %s ..." % desc)
    req = urllib.request.Request(url, headers={"User-Agent": "argus-builder/1.0"})
    resp = urllib.request.urlopen(req, timeout=120)
    data = resp.read()
    print("    Done (%.1f KB)" % (len(data) / 1024))
    return data


def copy_app_files(build_dir: Path) -> None:
    """Copy everything the packaged app reads at runtime, apart from Python and dist/."""
    # Copy the entire backend tree so subpackages (e.g. backend/commands/)
    # are included. The previous `glob('*.py')` only matched top-level .py
    # files, which meant the packaged zip was missing the commands package
    # and the backend crashed at import time inside the .bat launcher.
    shutil.copytree(
        SCRIPT_DIR / "backend", build_dir / "backend", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )

    # backend/config.py reads the version from here at import time.
    shutil.copy2(SCRIPT_DIR / "pyproject.toml", build_dir / "pyproject.toml")

    # simulator.py lives under scripts/, not at the repo root. Without the
    # correct path the sim launcher .bat tried to run a file that wasn't in
    # the zip.
    shutil.copy2(SCRIPT_DIR / "scripts" / "simulator.py", build_dir / "simulator.py")


def build(arch: str = "amd64"):
    pip_platform = f"win_{arch}"
    py_url = PY_BASE_URL.format(ver=PY_VER, arch=arch)

    print(f"=== Argus GCS v3 Package Builder (arch={arch}) ===\n")

    build_dir = SCRIPT_DIR / "_build"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir()

    # ── 1. Build frontend ──
    print("[1/5] Building frontend")
    subprocess.run(
        ["node", "node_modules/vite/bin/vite.js", "build"],
        cwd=str(SCRIPT_DIR),
        check=True,
        capture_output=True,
    )
    dist_src = SCRIPT_DIR / "dist"
    if not dist_src.exists():
        print("  ERROR: dist/ not found after build")
        sys.exit(1)
    shutil.copytree(dist_src, build_dir / "dist")
    print("  Frontend built")

    # ── 2. Download Python embeddable ──
    print("[2/5] Python embeddable")
    cache = SCRIPT_DIR / (f"python-{PY_VER}-embed-{arch}.zip")
    if cache.exists():
        print("  Using cached %s" % cache.name)
        py_data = cache.read_bytes()
    else:
        py_data = download(py_url, f"Python {PY_VER} ({arch})")
        cache.write_bytes(py_data)
    if hashlib.sha256(py_data).hexdigest() != PY_SHA256[arch]:
        print("  ERROR: %s is not the file PY_SHA256 names" % cache.name)
        sys.exit(1)

    py_dir = build_dir / "python"
    py_dir.mkdir()
    with zipfile.ZipFile(io.BytesIO(py_data)) as zf:
        zf.extractall(py_dir)

    ver_short = PY_VER.rsplit(".", 1)[0].replace(".", "")
    pth = py_dir / ("python%s._pth" % ver_short)
    if pth.exists():
        pth.write_text("python%s.zip\n.\n..\\backend\n..\\.\nLib\\site-packages\nimport site\n" % ver_short)

    # ── 3. Download pip wheels ──
    print("[3/5] Downloading dependencies")
    wheels_dir = build_dir / "_wheels"
    wheels_dir.mkdir()
    site_pkg = py_dir / "Lib" / "site-packages"
    site_pkg.mkdir(parents=True, exist_ok=True)

    constraints = build_dir / "_constraints.txt"
    constraints.write_text("\n".join(allowed_versions()) + "\n", encoding="utf-8")
    for dep in PIP_DEPS:
        print("  %s" % dep)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                f"--platform={pip_platform}",
                "--python-version=%s" % PY_VER.rsplit(".", 1)[0],
                "-c",
                str(constraints),
                "-d",
                str(wheels_dir),
                dep,
            ],
            check=True,
            capture_output=True,
        )
    constraints.unlink()

    for whl in wheels_dir.glob("*.whl"):
        with zipfile.ZipFile(whl) as zf:
            zf.extractall(site_pkg)
    shutil.rmtree(wheels_dir)

    # ── 4. Copy backend + protocol ──
    print("[4/5] Copying application files")
    copy_app_files(build_dir)

    # Create launcher bat
    (build_dir / "Argus地面站.bat").write_text(
        "@echo off\r\n"
        'cd /d "%~dp0"\r\n'
        "chcp 65001 >nul\r\n"
        f"title Argus 地面站 v{_VERSION}\r\n"
        "echo ============================================\r\n"
        f"echo   Argus 地面站 v{_VERSION}\r\n"
        "echo ============================================\r\n"
        "echo.\r\n"
        "echo 正在启动，浏览器将自动打开...\r\n"
        "echo 按 Ctrl+C 停止\r\n"
        "echo.\r\n"
        "python\\python.exe backend\\server.py --port 8100\r\n"
        "if errorlevel 1 pause\r\n",
        encoding="utf-8",
    )

    # Sim launcher
    (build_dir / "启动仿真器.bat").write_text(
        "@echo off\r\n"
        'cd /d "%~dp0"\r\n'
        "chcp 65001 >nul\r\n"
        "echo 仿真器运行中 (端口 5770)\r\n"
        "echo 在地面站中连接: tcp:localhost:5770\r\n"
        "python\\python.exe simulator.py 5770\r\n"
        "pause\r\n",
        encoding="utf-8",
    )

    # ── 5. Package ──
    print("[5/5] Creating zip")
    OUTPUT_DIR.mkdir(exist_ok=True)
    zip_name = OUTPUT_DIR / f"Argus_GCS_v{_VERSION}_{arch}.zip"
    if zip_name.exists():
        zip_name.unlink()

    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(build_dir):
            for f in files:
                filepath = Path(root) / f
                arcname = f"Argus_GCS_v{_VERSION}/" + str(filepath.relative_to(build_dir))
                zf.write(filepath, arcname)

    shutil.rmtree(build_dir)

    size_mb = zip_name.stat().st_size / 1024 / 1024
    print("\n=== Done! ===")
    print("Output: %s (%.1f MB)" % (zip_name, size_mb))
    print('Usage: Extract zip, double-click "Argus地面站.bat"')


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build Argus GCS Windows package")
    ap.add_argument(
        "--arch",
        choices=["amd64", "arm64"],
        default="amd64",
        help="Target architecture (default: amd64).",
    )
    args = ap.parse_args()
    build(arch=args.arch)
