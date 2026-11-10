"""scripts/build_package.py: the Windows package must start outside the repo."""

import re
import subprocess
import sys

import pytest

from backend.config import VERSION
from scripts.build_package import _VERSION, PIP_DEPS, allowed_versions, copy_app_files
from scripts.package_requirements import bundled


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


@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib")
def test_package_ships_inside_what_pyproject_allows():
    allowed = allowed_versions()
    assert "websockets>=14.0,<17.0" in allowed
    # pip refuses a constraint with extras, and uvicorn[standard] asks for uvloop: no Windows build.
    assert not any("[" in line for line in allowed)
    constrained = {re.split(r"[<>=!~ ]", line, maxsplit=1)[0] for line in allowed}
    only_on_windows = {"typing_extensions", "colorama"}
    assert set(PIP_DEPS) - only_on_windows <= constrained


def test_lists_what_a_zip_bundles(tmp_path):
    import zipfile

    path = tmp_path / "Argus_GCS_v0.0.0_amd64.zip"
    with zipfile.ZipFile(path, "w") as z:
        site = "Argus_GCS_v0.0.0/python/Lib/site-packages/"
        z.writestr(site + "starlette-1.10.0.dist-info/METADATA", "")
        z.writestr(site + "starlette-1.10.0.dist-info/RECORD", "")
        z.writestr(site + "pydantic_core-2.50.4.dist-info/METADATA", "")
        z.writestr(site + "starlette/__init__.py", "")
        z.writestr("Argus_GCS_v0.0.0/backend/app.py", "")
    assert bundled(str(path)) == ["pydantic_core==2.50.4", "starlette==1.10.0"]
