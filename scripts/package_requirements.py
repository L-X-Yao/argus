#!/usr/bin/env python3
"""List what a release zip bundles, as pip requirements: one `name==version` per line.

For pip-audit, so that a release is checked on what it ships, which is not what the
build machine has installed: the package brings its own Python and its own wheels.

Usage: python scripts/package_requirements.py release/Argus_GCS_v3.7.8_amd64.zip
"""

import re
import sys
import zipfile


def bundled(zip_path: str) -> list[str]:
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
    found = {
        match.groups()
        for name in names
        if (match := re.search(r"site-packages/([^/]+)-([^/-]+)\.dist-info/METADATA$", name))
    }
    return sorted("%s==%s" % pair for pair in found)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    requirements = bundled(sys.argv[1])
    if not requirements:
        raise SystemExit("no bundled packages found in %s" % sys.argv[1])
    print("\n".join(requirements))
