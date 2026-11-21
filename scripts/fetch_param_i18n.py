#!/usr/bin/env python3
"""Download and verify the parameter translation pack named by param_i18n.lock.

The pack is data only: JSON metadata and translations. It is pinned by version and SHA-256 so
a release is reproducible from the data repository's immutable asset.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCK = ROOT / "param_i18n.lock"
DEFAULT_DEST = ROOT / "param_i18n"
MAX_BYTES = 100 * 1024 * 1024
CHUNK = 1024 * 1024


class FetchError(RuntimeError):
    pass


def read_lock(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FetchError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise FetchError(f"{path}: unsupported schema")
    return data


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Argus-GCS-param-i18n/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        length = resp.headers.get("Content-Length")
        if length and int(length) > MAX_BYTES:
            raise FetchError(f"asset is larger than {MAX_BYTES // (1024 * 1024)} MiB")
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise FetchError(f"asset is larger than {MAX_BYTES // (1024 * 1024)} MiB")
    return data


def _safe_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = archive.getmembers()
    for member in members:
        name = Path(member.name)
        if name.is_absolute() or ".." in name.parts:
            raise FetchError(f"archive member escapes the pack: {member.name}")
        if member.issym() or member.islnk():
            raise FetchError(f"archive member is a link: {member.name}")
    return members


def extract_archive(data: bytes, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=dest.name + ".", dir=dest.parent))
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            members = _safe_members(archive)
            try:
                archive.extractall(staging, members=members, filter="data")
            except TypeError:
                # Python 3.11 has no extraction filter; _safe_members already refused links
                # and paths that leave the staging directory.
                archive.extractall(staging, members=members)
        # The archive has one top-level directory; accept both that and a flat pack.
        roots = list(staging.iterdir())
        source = roots[0] if len(roots) == 1 and roots[0].is_dir() else staging
        if not (source / "manifest.json").is_file():
            raise FetchError("pack has no manifest.json")
        if dest.exists():
            shutil.rmtree(dest)
        shutil.move(str(source), str(dest))
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def check(dest: Path, lock: dict) -> None:
    manifest = dest / "manifest.json"
    if not manifest.is_file():
        raise FetchError(f"{dest} has no manifest.json; run without --check first")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FetchError(f"cannot read {manifest}: {exc}") from exc
    if data.get("schema") != lock.get("schema"):
        raise FetchError(f"{manifest}: schema {data.get('schema')} != lock {lock.get('schema')}")
    if data.get("data_version") != lock.get("version"):
        raise FetchError(f"{manifest}: data_version {data.get('data_version')} != lock {lock.get('version')}")
    print(f"OK: {dest} is {lock['version']}, schema {lock['schema']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--asset", type=Path, help="local archive instead of downloading the lock URL")
    parser.add_argument("--check", action="store_true", help="verify an existing pack against the lock")
    args = parser.parse_args(argv)

    try:
        lock = read_lock(args.lock)
        if args.check:
            check(args.dest, lock)
            return 0
        version = str(lock.get("version", ""))
        expected = str(lock.get("sha256", ""))
        if version in ("", "unreleased") or not expected:
            raise FetchError("param_i18n.lock is a placeholder; pin a data release first")
        if args.asset:
            data = args.asset.read_bytes()
        else:
            url = str(lock.get("url", ""))
            if not url:
                raise FetchError("param_i18n.lock has no url")
            data = download(url)
        actual = _sha256(data)
        if actual != expected:
            raise FetchError(f"sha256 mismatch: expected {expected}, got {actual}")
        extract_archive(data, args.dest)
        check(args.dest, lock)
        print(f"Extracted {args.dest}")
        return 0
    except (FetchError, OSError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
