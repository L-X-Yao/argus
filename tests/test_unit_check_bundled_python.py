"""scripts/check_bundled_python.py: is the Python the Windows package bundles behind its line?"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import check_bundled_python as check  # noqa: E402


def test_reads_the_version_of_the_build_script():
    source = (Path(check.__file__).with_name("build_package.py")).read_text(encoding="utf-8")
    major, minor, patch = check.bundled_version(source)
    assert (major, minor) >= (3, 11)
    assert f'PY_VER = "{major}.{minor}.{patch}"' in source


def test_no_version_is_an_error():
    with pytest.raises(SystemExit):
        check.bundled_version("PY_VERSION = '3.14'\n")


@pytest.mark.parametrize(
    ("bundled", "running", "expected"),
    [
        ((3, 14, 10), (3, 14, 11), True),
        ((3, 14, 10), (3, 14, 10), False),
        ((3, 14, 11), (3, 14, 10), False),  # the runner's image lags python.org by days
        ((3, 14, 10), (3, 15, 0), False),  # another line says nothing about this one
        ((3, 14, 9), (3, 14, 10), True),  # compared as numbers: "9" sorts after "10" as text
    ],
)
def test_behind_only_within_one_line(bundled, running, expected):
    assert check.behind(bundled, running) is expected


def test_fails_on_an_older_patch_release(tmp_path, monkeypatch, capsys):
    here = sys.version_info
    script = tmp_path / "build_package.py"
    script.write_text(f'PY_VER = "{here.major}.{here.minor}.{max(here.micro - 1, 0)}"\n', encoding="utf-8")
    code = check.main(["check_bundled_python.py", str(script)])
    assert code == (1 if here.micro > 0 else 0)
    if here.micro > 0:
        assert "::error::" in capsys.readouterr().out


def test_passes_on_the_same_release_and_on_another_line(tmp_path, capsys):
    here = sys.version_info
    script = tmp_path / "build_package.py"
    script.write_text(f'PY_VER = "{here.major}.{here.minor}.{here.micro}"\n', encoding="utf-8")
    assert check.main(["check_bundled_python.py", str(script)]) == 0
    script.write_text(f'PY_VER = "{here.major}.{here.minor + 1}.0"\n', encoding="utf-8")
    assert check.main(["check_bundled_python.py", str(script)]) == 0
    assert "::warning::" in capsys.readouterr().out
