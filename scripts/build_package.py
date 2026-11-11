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
import tomllib
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

# What the licenses of Argus and of the work in it ask to go along with every copy.
LICENSE_FILES = ["LICENSE", "THIRD_PARTY_NOTICES.md"]
# A wheel brings its license text in its .dist-info. This one does not, so LICENSES/ holds it.
OWN_LICENSE_TEXT = {"pyserial": "BSD-3-Clause-pyserial.txt"}

# In every web build. A list without them means the build no longer sees what it bundles.
WEB_LIBRARIES = ["svelte", "maplibre-gl"]

README_TXT = """Argus GCS v{version}
https://github.com/L-X-Yao/argus

Start:      double-click "Argus地面站.bat". A browser opens http://127.0.0.1:8100
Simulator:  double-click "启动仿真器.bat", then connect to tcp:localhost:5770
Stop:       close the window, or press Ctrl+C in it

Argus has not been flight tested. Read docs/VERIFICATION.md and SECURITY.md
in the repository before you fly with it.

启动：双击"Argus地面站.bat"，浏览器会打开 http://127.0.0.1:8100
仿真器：双击"启动仿真器.bat"，然后在地面站里连接 tcp:localhost:5770
停止：关闭窗口，或在窗口里按 Ctrl+C

Argus 没有经过飞行测试。飞行前请先看仓库里的 docs/VERIFICATION.md 和 SECURITY.md。

Licenses: LICENSE (Argus, MIT). THIRD_PARTY_NOTICES.md and LICENSES/ (work of others).
"""


def allowed_versions() -> list[str]:
    """What pyproject.toml allows of each dependency, as pip constraints: the package ships
    what the tests ran against, and none of the versions it rules out. Without the extras,
    which a constraint cannot carry."""
    project = tomllib.loads((SCRIPT_DIR / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return [re.sub(r"\[[^\]]*\]", "", dep) for dep in project["dependencies"]]


def download(url, desc):
    print("  Downloading %s ..." % desc)
    req = urllib.request.Request(url, headers={"User-Agent": "argus-builder/1.0"})
    resp = urllib.request.urlopen(req, timeout=120)
    data = resp.read()
    print("    Done (%.1f KB)" % (len(data) / 1024))
    return data


def python_embeddable(arch: str) -> bytes:
    """The embeddable zip of PY_VER: from the cache beside the scripts, or from python.org.
    Checked against PY_SHA256 before it is cached. A download cut short used to be kept,
    and failed every build after it until someone deleted the file."""
    cache = SCRIPT_DIR / f"python-{PY_VER}-embed-{arch}.zip"
    if cache.exists():
        data = cache.read_bytes()
        if hashlib.sha256(data).hexdigest() == PY_SHA256[arch]:
            print("  Using cached %s" % cache.name)
            return data
        print("  Cached %s is not the file PY_SHA256 names: downloading it again" % cache.name)
    data = download(PY_BASE_URL.format(ver=PY_VER, arch=arch), f"Python {PY_VER} ({arch})")
    if hashlib.sha256(data).hexdigest() != PY_SHA256[arch]:
        print("  ERROR: what python.org sent for %s is not the file PY_SHA256 names" % cache.name)
        sys.exit(1)
    cache.write_bytes(data)
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

    for name in LICENSE_FILES:
        shutil.copy2(SCRIPT_DIR / name, build_dir / name)
    shutil.copytree(SCRIPT_DIR / "LICENSES", build_dir / "LICENSES")
    # utf-8-sig and CRLF: Notepad on an older Windows reads Chinese wrongly without the mark.
    (build_dir / "README.txt").write_text(README_TXT.format(version=_VERSION), encoding="utf-8-sig", newline="\r\n")


def web_libraries_missing(notices: str) -> list[str]:
    """Libraries every web build bundles that dist/THIRD-PARTY-LICENSES.txt does not list."""
    return [name for name in WEB_LIBRARIES if f"\n{name}@" not in notices]


def unlicensed(site_packages: Path) -> list[str]:
    """Libraries in the package that come with no license text: none in their wheel, and none
    kept in LICENSES/. Their licenses ask for the text to go along with every copy."""
    missing = []
    for info in sorted(site_packages.glob("*.dist-info")):
        name = re.split(r"-\d", info.name)[0].lower().replace("_", "-")
        texts = [p for p in info.rglob("*") if p.is_file() and re.search(r"licen[cs]e|copying|notice", p.name, re.I)]
        if not texts and name not in OWN_LICENSE_TEXT:
            missing.append(name)
    return missing


def build(arch: str = "amd64"):
    pip_platform = f"win_{arch}"

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
    notices = dist_src / "THIRD-PARTY-LICENSES.txt"
    if not notices.exists():
        print("  ERROR: the build wrote no dist/THIRD-PARTY-LICENSES.txt (see vite.config.ts)")
        sys.exit(1)
    missing = web_libraries_missing(notices.read_text(encoding="utf-8"))
    if missing:
        print("  ERROR: dist/THIRD-PARTY-LICENSES.txt does not list %s (see vite.config.ts)" % ", ".join(missing))
        sys.exit(1)
    shutil.copytree(dist_src, build_dir / "dist")
    print("  Frontend built")

    # ── 2. Download Python embeddable ──
    print("[2/5] Python embeddable")
    py_data = python_embeddable(arch)

    py_dir = build_dir / "python"
    py_dir.mkdir()
    with zipfile.ZipFile(io.BytesIO(py_data)) as zf:
        zf.extractall(py_dir)

    ver_short = PY_VER.rsplit(".", 1)[0].replace(".", "")
    pth = py_dir / ("python%s._pth" % ver_short)
    # Without it the packaged Python finds neither the backend nor its libraries.
    if not pth.exists():
        print("  ERROR: %s is not in the embedded Python: its layout has changed" % pth.name)
        sys.exit(1)
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
    missing = unlicensed(site_pkg)
    if missing:
        print("  ERROR: no license text for %s: add it to LICENSES/ and OWN_LICENSE_TEXT" % ", ".join(missing))
        sys.exit(1)

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
