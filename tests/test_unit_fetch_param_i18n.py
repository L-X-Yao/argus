"""scripts/fetch_param_i18n.py: verify, extract and refuse a bad parameter data pack."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile

import pytest

from scripts.fetch_param_i18n import FetchError, extract_archive, main


def _archive(tmp_path, members: dict[str, bytes]) -> tuple[bytes, str]:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    raw = buf.getvalue()
    return raw, hashlib.sha256(raw).hexdigest()


def _lock(tmp_path, version: str, sha: str) -> object:
    path = tmp_path / "param_i18n.lock"
    path.write_text(
        json.dumps({"schema": 1, "version": version, "asset": "pack.tar.gz", "sha256": sha, "url": ""}),
        encoding="utf-8",
    )
    return path


def test_extracts_a_verified_pack_and_checks_it(tmp_path):
    raw, sha = _archive(
        tmp_path,
        {
            "pack/manifest.json": json.dumps({"schema": 1, "data_version": "2026.11.1"}).encode(),
            "pack/tm/zh.json": b"{}",
        },
    )
    archive = tmp_path / "pack.tar.gz"
    archive.write_bytes(raw)
    lock = _lock(tmp_path, "2026.11.1", sha)
    dest = tmp_path / "param_i18n"
    assert main(["--lock", str(lock), "--dest", str(dest), "--asset", str(archive)]) == 0
    assert (dest / "manifest.json").is_file()
    assert (dest / "tm" / "zh.json").is_file()
    assert main(["--lock", str(lock), "--dest", str(dest), "--check"]) == 0


def test_refuses_a_hash_mismatch(tmp_path):
    raw, _ = _archive(tmp_path, {"pack/manifest.json": b"{}"})
    archive = tmp_path / "pack.tar.gz"
    archive.write_bytes(raw)
    lock = _lock(tmp_path, "2026.11.1", "0" * 64)
    assert main(["--lock", str(lock), "--dest", str(tmp_path / "out"), "--asset", str(archive)]) == 1


def test_refuses_a_placeholder_lock(tmp_path):
    lock = _lock(tmp_path, "unreleased", "")
    assert main(["--lock", str(lock), "--dest", str(tmp_path / "out")]) == 1


def test_refuses_a_member_that_escapes_the_destination(tmp_path):
    raw, _ = _archive(
        tmp_path,
        {"pack/manifest.json": b"{}", "pack/../../evil": b"x"},
    )
    with pytest.raises(FetchError, match="escapes"):
        extract_archive(raw, tmp_path / "out")


def test_check_reports_a_version_mismatch(tmp_path, capsys):
    raw, sha = _archive(tmp_path, {"pack/manifest.json": json.dumps({"schema": 1, "data_version": "old"}).encode()})
    archive = tmp_path / "pack.tar.gz"
    archive.write_bytes(raw)
    lock = _lock(tmp_path, "2026.11.1", sha)
    dest = tmp_path / "param_i18n"
    assert main(["--lock", str(lock), "--dest", str(dest), "--asset", str(archive)]) == 1
    assert "data_version" in capsys.readouterr().err
