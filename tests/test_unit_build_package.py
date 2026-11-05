"""scripts/build_package.py: the Windows package must start outside the repo."""

import subprocess
import sys

from backend.config import VERSION
from scripts.build_package import _VERSION, copy_app_files


def test_version_matches_the_backend():
    assert _VERSION == VERSION


def test_packaged_backend_imports_without_the_repo(tmp_path):
    copy_app_files(tmp_path)
    result = subprocess.run(
        [sys.executable, "-c", "import backend.config as c; print(c.VERSION)"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == VERSION
