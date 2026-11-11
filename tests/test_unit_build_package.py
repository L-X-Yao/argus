"""scripts/build_package.py: the Windows package must start outside the repo."""

import re
import subprocess
import sys

import pytest

from backend.config import VERSION
from scripts.build_package import (
    _VERSION,
    OWN_LICENSE_TEXT,
    PIP_DEPS,
    SCRIPT_DIR,
    allowed_versions,
    copy_app_files,
    unlicensed,
)
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


class TestLicenseTexts:
    """The licenses of Argus and of the work inside it ask for their text in every copy.
    Until v3.7.9 the package held neither Argus's own license nor any notice of the rest."""

    def test_the_package_carries_them(self, tmp_path):
        copy_app_files(tmp_path)
        for name in [
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
            "LICENSES/Apache-2.0.txt",
            "LICENSES/BSD-2-Clause-Leaflet.txt",
        ]:
            assert (tmp_path / name).is_file(), name
        for name in OWN_LICENSE_TEXT.values():
            assert (tmp_path / "LICENSES" / name).is_file(), name

    def test_the_package_says_how_to_start_it_in_a_form_notepad_reads(self, tmp_path):
        copy_app_files(tmp_path)
        raw = (tmp_path / "README.txt").read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        assert f"Argus GCS v{VERSION}" in text and "Argus地面站.bat" in text
        assert "\r\n" in text and "\n" not in text.replace("\r\n", "")

    def test_a_library_without_a_license_text_is_named(self, tmp_path):
        (tmp_path / "fastapi-0.1.dist-info" / "licenses").mkdir(parents=True)
        (tmp_path / "fastapi-0.1.dist-info" / "licenses" / "LICENSE").write_text("MIT")
        (tmp_path / "old_style-2.0.dist-info").mkdir()
        (tmp_path / "old_style-2.0.dist-info" / "LICENSE.txt").write_text("BSD")
        (tmp_path / "python_nothing-1.2.3.dist-info").mkdir()
        (tmp_path / "python_nothing-1.2.3.dist-info" / "METADATA").write_text("License: MIT")
        assert unlicensed(tmp_path) == ["python-nothing"]

    def test_a_library_whose_text_the_repo_keeps_is_covered(self, tmp_path):
        (tmp_path / "pyserial-3.5.dist-info").mkdir()
        (tmp_path / "pyserial-3.5.dist-info" / "METADATA").write_text("License: BSD")
        assert unlicensed(tmp_path) == []

    def test_the_notices_name_what_the_repo_holds_of_others(self):
        notices = (SCRIPT_DIR / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        vendored = [f"public/lib/{d.name}/" for d in (SCRIPT_DIR / "public" / "lib").iterdir() if d.is_dir()]
        for path in [*vendored, "public/images/cal/"]:
            assert path in notices, path
        for text in (SCRIPT_DIR / "LICENSES").iterdir():
            assert f"LICENSES/{text.name}" in notices, text.name

    def test_the_calibration_pictures_are_the_ones_the_notices_credit(self):
        """A picture added to the folder would carry a credit that is not its own."""
        pictures = sorted(p.name for p in (SCRIPT_DIR / "public" / "images" / "cal").iterdir())
        assert pictures == [
            "VehicleDown.png",
            "VehicleLeft.png",
            "VehicleNoseDown.png",
            "VehicleRight.png",
            "VehicleTailDown.png",
            "VehicleUpsideDown.png",
        ]


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


class TestPythonEmbeddable:
    GOOD = b"the file python.org serves"

    @pytest.fixture
    def here(self, tmp_path, monkeypatch):
        import hashlib

        import scripts.build_package as build

        monkeypatch.setattr(build, "SCRIPT_DIR", tmp_path)
        monkeypatch.setitem(build.PY_SHA256, "amd64", hashlib.sha256(self.GOOD).hexdigest())
        return build, tmp_path / f"python-{build.PY_VER}-embed-amd64.zip"

    def test_a_download_that_matches_is_cached(self, here, monkeypatch):
        build, cache = here
        monkeypatch.setattr(build, "download", lambda url, desc: self.GOOD)
        assert build.python_embeddable("amd64") == self.GOOD
        assert cache.read_bytes() == self.GOOD

    def test_a_download_that_does_not_match_stops_the_build_and_is_not_kept(self, here, monkeypatch):
        build, cache = here
        monkeypatch.setattr(build, "download", lambda url, desc: self.GOOD[:10])
        with pytest.raises(SystemExit):
            build.python_embeddable("amd64")
        assert not cache.exists()

    def test_a_cached_file_that_matches_is_used_without_a_download(self, here, monkeypatch):
        build, cache = here
        cache.write_bytes(self.GOOD)
        monkeypatch.setattr(build, "download", lambda url, desc: pytest.fail("downloaded"))
        assert build.python_embeddable("amd64") == self.GOOD

    def test_a_cached_file_that_does_not_match_is_replaced(self, here, monkeypatch):
        build, cache = here
        cache.write_bytes(self.GOOD[:10])
        monkeypatch.setattr(build, "download", lambda url, desc: self.GOOD)
        assert build.python_embeddable("amd64") == self.GOOD
        assert cache.read_bytes() == self.GOOD
