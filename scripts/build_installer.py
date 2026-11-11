#!/usr/bin/env python3
"""Build the Windows installer from a release zip: Argus_GCS_vX.Y.Z_amd64_setup.exe beside it.

The installer holds exactly what the zip holds, plus the icon, so the zip that was tested is
the program that gets installed. scripts/installer.iss says how it installs.

Usage: python scripts/build_installer.py release/Argus_GCS_v3.9.0_amd64.zip

Windows only: it runs ISCC.exe, the compiler of Inno Setup 6, which the GitHub Windows runners
carry. Set ISCC to its path when it is somewhere else.
"""

import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "installer.iss"
ICON = ROOT / "public" / "images" / "icon-192.png"
ISCC_PLACES = [
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def version_of(package: Path) -> str:
    found = re.search(r"_v(\d+\.\d+\.\d+)_", package.name)
    if not found:
        raise SystemExit(f"{package.name} is not named like a release zip (Argus_GCS_vX.Y.Z_amd64.zip)")
    return found.group(1)


def png_to_ico(png: bytes) -> bytes:
    """An .ico that holds one PNG image, which Windows reads since Vista. The format keeps a
    side in one byte, 0 meaning 256, so the image may be at most 256 pixels on each side."""
    if png[:8] != PNG_SIGNATURE:
        raise ValueError("not a PNG image")
    width, height = struct.unpack(">II", png[16:24])
    if not (0 < width <= 256 and 0 < height <= 256):
        raise ValueError(f"a {width}x{height} image does not fit in an icon")
    directory = struct.pack("<HHH", 0, 1, 1)  # reserved, type 1 (icon), one image
    entry = struct.pack("<BBBBHHII", width % 256, height % 256, 0, 0, 1, 32, len(png), 6 + 16)
    return directory + entry + png


def find_iscc() -> str:
    for candidate in (os.environ.get("ISCC"), shutil.which("ISCC"), *ISCC_PLACES):
        if candidate and Path(candidate).is_file():
            return candidate
    raise SystemExit("ISCC.exe not found: install Inno Setup 6, or set ISCC to its path")


def build(package: Path) -> Path:
    version = version_of(package)
    out_dir = package.parent
    setup = out_dir / f"Argus_GCS_v{version}_amd64_setup.exe"
    setup.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(package) as z:
            z.extractall(tmp)
        source = next(Path(tmp).iterdir())
        (source / "argus.ico").write_bytes(png_to_ico(ICON.read_bytes()))
        subprocess.run(
            [
                find_iscc(),
                "/Q",
                f"/DAppVersion={version}",
                f"/DSourceDir={source}",
                f"/DOutputDir={out_dir}",
                str(SCRIPT),
            ],
            check=True,
        )
    if not setup.is_file():
        raise SystemExit(f"ISCC finished without {setup.name}")
    return setup


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    setup = build(Path(sys.argv[1]).resolve())
    print(f"Output: {setup} ({setup.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
