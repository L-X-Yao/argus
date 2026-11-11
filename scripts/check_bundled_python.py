#!/usr/bin/env python3
"""Fail when the Python the Windows package bundles is behind the newest of its line.

The package brings a Python of its own, named by PY_VER in scripts/build_package.py, and
nothing else says when a newer patch release is out. Run this on the newest Python of that
line, which is what actions/setup-python gives for "3.14": it compares the two.

Usage: python scripts/check_bundled_python.py [path to a build_package.py]

The path is for the audit of a published release, which reads the file as its tag has it.
Standard library only.
"""

import platform
import re
import sys
from pathlib import Path


def bundled_version(source: str) -> tuple[int, int, int]:
    found = re.search(r'^PY_VER = "(\d+)\.(\d+)\.(\d+)"', source, re.MULTILINE)
    if not found:
        raise SystemExit("no PY_VER in the build script")
    return tuple(int(part) for part in found.groups())


def behind(bundled: tuple[int, int, int], running: tuple[int, int, int]) -> bool:
    """True when both are of one line (3.14) and the bundled one is the older."""
    return bundled[:2] == running[:2] and bundled < running


def main(argv: list[str]) -> int:
    script = Path(argv[1]) if len(argv) > 1 else Path(__file__).with_name("build_package.py")
    bundled = bundled_version(script.read_text(encoding="utf-8"))
    running = tuple(int(part) for part in platform.python_version_tuple()[:3])
    print("bundles %d.%d.%d, this Python is %d.%d.%d" % (bundled + running))
    if bundled[:2] != running[:2]:
        print("::warning::not the same line: nothing to compare. Run this on Python %d.%d" % bundled[:2])
        return 0
    if behind(bundled, running):
        print("::error::Python %d.%d.%d is out: move PY_VER and PY_SHA256 in scripts/build_package.py" % running)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
