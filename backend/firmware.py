"""Firmware upload, listing, online search, and download."""

from __future__ import annotations

import ipaddress
import logging
import re
import socket as _socket
import urllib.error
import urllib.request as urlreq
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Request, UploadFile

from .config import FAKE_IP_RANGE, ROOT_DIR, USER_AGENT, aio_download, cfg, json_object

router = APIRouter()

FIRMWARE_DIR = ROOT_DIR / "firmware"

_FW_BASE = "https://firmware.ardupilot.org/"

_BOARD_MAP = {
    9: ("Copter", "Pixhawk1"),
    50: ("Copter", "Pixhawk4"),
}


@router.post("/api/firmware/upload")
async def api_firmware_upload(file: UploadFile):
    if not file.filename or not file.filename.endswith(".apj"):
        return {"ok": False, "error": "Only .apj files accepted"}
    safe_name = Path(file.filename).name
    if not safe_name[:-4]:
        return {"ok": False, "error": "Only .apj files accepted"}
    FIRMWARE_DIR.mkdir(exist_ok=True)
    dest = (FIRMWARE_DIR / safe_name).resolve()
    try:
        dest.relative_to(FIRMWARE_DIR.resolve())
    except ValueError:
        return {"ok": False, "error": "Invalid filename"}
    tmp = dest.with_suffix(".apj.tmp")
    total = 0
    too_large = False
    try:
        with tmp.open("wb") as fh:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > cfg.FIRMWARE_MAX_SIZE:
                    too_large = True
                    break
                fh.write(chunk)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    if too_large:
        tmp.unlink(missing_ok=True)
        return {"ok": False, "error": f"File too large (max {cfg.FIRMWARE_MAX_SIZE // 1024 // 1024} MB)"}
    tmp.rename(dest)
    return {"ok": True, "filename": safe_name, "size": total}


@router.get("/api/firmware/list")
async def api_firmware_list():
    if not FIRMWARE_DIR.exists():
        return {"files": []}
    files = []
    for f in sorted(FIRMWARE_DIR.glob("*.apj")):
        files.append({"name": f.name, "size": f.stat().st_size})
    return {"files": files}


def _read_url(url: str, limit: int) -> str:
    req = urlreq.Request(url, headers={"User-Agent": USER_AGENT})
    resp = urlreq.urlopen(req, timeout=cfg.FIRMWARE_LIST_TIMEOUT)
    return resp.read(limit).decode("utf-8", errors="replace")


def _fetch_online_versions(board_id: int) -> dict:
    board_info = _BOARD_MAP.get(board_id)
    if not board_info:
        return {"versions": [], "error": "Unknown board_id"}
    vehicle, board_name = board_info
    # One build per board and channel, named after the vehicle (arducopter.apj). Only
    # firmware-version.txt says which: "4.7.2-FIRMWARE_VERSION_TYPE_OFFICIAL".
    url = "%s%s/stable/%s/" % (_FW_BASE, vehicle, board_name)
    try:
        html = _read_url(url, cfg.FIRMWARE_HTML_MAX)
        version = _read_url(url + "firmware-version.txt", 128).split("-")[0].strip()
    except (OSError, urllib.error.URLError) as e:
        logging.getLogger("gcs").warning("firmware online fetch failed: %s", e)
        return {"versions": [], "error": "Cannot reach firmware server"}
    names = sorted({href.rsplit("/", 1)[-1] for href in re.findall(r'href="([^"]*\.apj)"', html)})
    return {"versions": [{"version": version, "date": "", "url": url + name, "size": 0} for name in names]}


@router.get("/api/firmware/online")
async def api_firmware_online(board_id: int = 0):
    return await aio_download(_fetch_online_versions, board_id)


def _download_firmware(fw_url: str, filename: str) -> dict:
    # Every URL the firmware panel is offered comes from there. Any other server could also
    # get past the address check below with a redirect, which urlopen follows.
    if not isinstance(fw_url, str) or not fw_url.startswith(_FW_BASE):
        return {"ok": False, "error": "Only the ArduPilot firmware server is allowed"}
    try:
        addrs = _socket.getaddrinfo(urlparse(fw_url).hostname, None)
    except _socket.gaierror:
        return {"ok": False, "error": "Cannot resolve host"}
    for _fam, *_rest, sockaddr in addrs:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip in FAKE_IP_RANGE:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return {"ok": False, "error": "Refusing to fetch from internal address"}
    try:
        req = urlreq.Request(fw_url, headers={"User-Agent": USER_AGENT})
        resp = urlreq.urlopen(req, timeout=cfg.FIRMWARE_DOWNLOAD_TIMEOUT)
        FIRMWARE_DIR.mkdir(exist_ok=True)
        target = (FIRMWARE_DIR / filename).resolve()
        try:
            target.relative_to(FIRMWARE_DIR.resolve())
        except ValueError:
            return {"ok": False, "error": "Invalid filename"}
        tmp = target.with_suffix(".tmp")
        total = 0
        try:
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > cfg.FIRMWARE_MAX_SIZE:
                        raise ValueError("too large")
                    f.write(chunk)
            tmp.rename(target)
        except ValueError:
            tmp.unlink(missing_ok=True)
            return {"ok": False, "error": "File too large (max %d MB)" % (cfg.FIRMWARE_MAX_SIZE // 1024 // 1024)}
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        return {"ok": True, "filename": filename, "size": total}
    except (OSError, urllib.error.URLError) as e:
        logging.getLogger("gcs").warning("firmware download failed: %s", e)
        return {"ok": False, "error": "Download failed (check server logs)"}


@router.post("/api/firmware/download")
async def api_firmware_download(request: Request):
    body = await json_object(request)
    fw_url = body.get("url", "")
    raw_filename = body.get("filename", "firmware.apj")
    if not fw_url or not isinstance(raw_filename, str):
        return {"ok": False, "error": "Invalid params"}
    filename = Path(raw_filename).name
    if not filename.endswith(".apj") or filename in ("", ".", ".."):
        return {"ok": False, "error": "Invalid params"}
    return await aio_download(_download_firmware, fw_url, filename)
