"""The Windows installer: scripts/installer.iss and scripts/build_installer.py.

The installer itself is built and installed on the Windows jobs of ci.yml and release.yml
(scripts/smoke_package.py). What can be checked without Windows is checked here.
"""

import re
import struct
from pathlib import Path

import pytest

from scripts.build_installer import ICON, SCRIPT, png_to_ico, version_of
from scripts.smoke_package import UNINSTALL_KEY

ISS = SCRIPT.read_text(encoding="utf-8-sig")
BUILD_PACKAGE = (Path(__file__).resolve().parent.parent / "scripts" / "build_package.py").read_text(encoding="utf-8")


def section(name: str) -> list[str]:
    """The entries of one [Section] of the script, without comments."""
    lines = ISS.split(f"[{name}]\n", 1)[1].split("\n[", 1)[0].splitlines()
    return [line for line in lines if line.strip() and not line.startswith(";")]


class TestIcon:
    def test_holds_the_png_as_it_is(self):
        png = ICON.read_bytes()
        ico = png_to_ico(png)
        reserved, kind, count = struct.unpack("<HHH", ico[:6])
        width, height, _, _, planes, bits, size, offset = struct.unpack("<BBBBHHII", ico[6:22])
        assert (reserved, kind, count) == (0, 1, 1)
        assert (width, height, planes, bits) == (192, 192, 1, 32)
        assert ico[offset : offset + size] == png

    def test_a_side_of_256_is_written_as_0(self):
        png = ICON.read_bytes()
        big = png[:16] + struct.pack(">II", 256, 256) + png[24:]
        assert png_to_ico(big)[6:8] == b"\x00\x00"

    def test_refuses_what_does_not_fit_or_is_no_png(self):
        png = ICON.read_bytes()
        with pytest.raises(ValueError):
            png_to_ico(png[:16] + struct.pack(">II", 512, 512) + png[24:])
        with pytest.raises(ValueError):
            png_to_ico(b"GIF89a" + png[6:])


class TestVersion:
    def test_from_the_name_of_the_zip(self):
        assert version_of(Path("release/Argus_GCS_v3.9.0_amd64.zip")) == "3.9.0"

    def test_a_zip_named_otherwise_is_refused(self):
        with pytest.raises(SystemExit):
            version_of(Path("release/argus.zip"))


class TestScript:
    def test_inno_setup_reads_its_chinese_names(self):
        # Without the byte order mark ISCC reads the script in the system code page.
        assert SCRIPT.read_bytes()[:3] == b"\xef\xbb\xbf"

    def test_the_smoke_test_reads_the_uninstall_entry_of_this_app(self):
        app_id = re.search(r"^AppId=\{\{([0-9A-F-]{36})\}$", ISS, re.MULTILINE).group(1)
        assert UNINSTALL_KEY.endswith("\\{" + app_id + "}_is1")

    def test_installs_for_this_user_without_administrator_rights(self):
        # Argus writes its logs, caches and token beside its program.
        assert re.search(r"^PrivilegesRequired=lowest$", ISS, re.MULTILINE)
        assert not re.search(r"^PrivilegesRequiredOverridesAllowed", ISS, re.MULTILINE)

    @pytest.mark.parametrize("name", ["InstallDelete", "UninstallDelete"])
    def test_never_deletes_flight_logs_or_map_files(self, name):
        for entry in section(name):
            assert not re.search(r"\{app\}\\(logs|mbtiles)\b", entry), entry

    def test_an_upgrade_clears_only_program_folders(self):
        cleared = {re.search(r'Name: "\{app\}\\([^"]+)"', entry).group(1) for entry in section("InstallDelete")}
        assert cleared == {"backend", "dist", "python", "LICENSES"}

    def test_shortcuts_start_the_launchers_the_package_has(self):
        targets = re.findall(r'(?<![A-Za-z])Filename: "\{app\}\\([^"]+)"', "\n".join(section("Icons")))
        assert targets
        for target in targets:
            assert f'"{target}"' in BUILD_PACKAGE, target
