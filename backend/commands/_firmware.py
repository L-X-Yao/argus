"""Firmware flashing: the command, its guards, and the worker that owns the serial port.

The protocol lives in backend/firmware_flash.py. This module only orchestrates it around the
link: send MAV_CMD_FLASH_BOOTLOADER, stop the link, find the bootloader port, write, then bring
the normal link back. It is backend-serial only; a page that owns the vehicle over WebSerial
cannot flash.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .. import firmware
from ..config import cfg
from ..firmware_flash import (
    Apj,
    Bootloader,
    FlashError,
    check_apj,
    discover_bootloader,
    load_apj,
    port_candidates,
    probe_mavlink_heartbeat,
)
from ..locale_text import lt
from ._helpers import send_cmd

if TYPE_CHECKING:
    from ..drone_link import DroneLink

# MAV_CMD_FLASH_BOOTLOADER, param1=3: "remain in bootloader" (the same command the panel's
# reboot button sends). ArduPilot's GCS_MAVLink/GCS_Common.cpp handles it.
FLASH_BOOTLOADER = 246


def _state(link: DroneLink, **fields) -> None:
    with link._state_lock:
        link.fw_flash.update(fields)


def _refuse(link: DroneLink, key: str, *args) -> dict:
    text = lt(key, link.locale)
    return {"ok": False, "error": text % args if args else text}


def _fail(link: DroneLink, message: str) -> None:
    _state(link, active=False, phase="failed", error=message)
    link.add_event(lt("flash_fail", link.locale) % message, "flash")


def _current_ports() -> set[str]:
    """The serial ports present before the reboot, so a new bootloader port stands out."""
    try:
        from serial.tools import list_ports

        return {port.device for port in list_ports.comports()}
    except Exception:  # pyserial missing or no port list on this platform
        return set()


def _reconnect(link: DroneLink) -> bool:
    """Bring the normal link back on the port the firmware re-enumerated as."""
    original = link._last_port or ""
    baud = link._last_baud or cfg.SERIAL_BAUD
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        for port in port_candidates(original):
            if not probe_mavlink_heartbeat(port, baud):
                continue
            try:
                if not link.connect(port, baud):
                    continue
            except OSError:
                continue
            end = time.monotonic() + 5.0
            while time.monotonic() < end:
                if link.connected:
                    return True
                time.sleep(0.1)
            link.disconnect()
        time.sleep(0.5)
    return False


def _flash_job(link: DroneLink, path: Path, stop: threading.Event) -> None:
    bootloader: Bootloader | None = None
    erased = False
    try:
        apj: Apj = load_apj(path)
        _state(link, active=True, phase="reboot", done=0, total=apj.image_size, file=path.name, error="")
        link.add_event(lt("flash_start", link.locale) % path.name, "flash")

        # A retry starts from an FC that may already be in its bootloader: every port counts.
        before = _current_ports() if link.connected else set()
        if link.connected:
            # The FC reboots into its bootloader on this command; the ACK may never arrive.
            send_cmd(link, FLASH_BOOTLOADER, p1=3)
            time.sleep(0.6)
        if not link.pause_for_flash():
            raise FlashError("The link did not stop for flashing (reconnect in progress?).")

        _state(link, phase="waiting")
        bootloader = discover_bootloader(link._last_port or "", before)
        bootloader.identify()
        check_apj(apj, bootloader)

        _state(link, phase="erase")
        bootloader.erase()
        erased = True

        _state(link, phase="write", done=0, total=len(apj.image))
        marked = [0.0]

        def progress(done: int, total: int) -> None:
            now = time.monotonic()
            if now - marked[0] >= 0.5 or done == total:
                marked[0] = now
                _state(link, done=done, total=total)

        bootloader.program(apj.image, progress)
        _state(link, phase="verify")
        bootloader.verify(apj.image)
        _state(link, phase="reboot")
        bootloader.reboot()
        bootloader.close()
        bootloader = None

        _state(link, phase="reconnecting")
        if not _reconnect(link):
            raise FlashError("Flashed, but the flight controller did not come back on a serial port.")
        _state(link, active=False, phase="done", done=apj.image_size, total=apj.image_size, error="")
        link.add_event(lt("flash_done", link.locale), "flash")
    except FlashError as exc:
        _fail(link, str(exc))
        if bootloader is not None:
            if not erased:
                # Nothing was written: reboot the intact firmware and try to bring the link back.
                try:
                    bootloader.reboot()
                except Exception:
                    pass
            bootloader.close()
        if not erased:
            _reconnect(link)
    except Exception as exc:  # a bad file, a closed port, a bug: never leave the page silent
        _fail(link, f"Unexpected error: {exc}")
        if bootloader is not None:
            bootloader.close()
    finally:
        with link._state_lock:
            if link.fw_thread is threading.current_thread():
                link.fw_thread = None
                link.fw_stop = None


def cmd_firmware_flash(link: DroneLink, param, data: dict):
    """Validate, then hand the write to a worker: the websocket loop must not block."""
    name = data.get("file")
    if not isinstance(name, str) or not name.endswith(".apj") or name in ("", ".apj") or Path(name).name != name:
        return _refuse(link, "flash_bad_file", str(name))
    root = firmware.FIRMWARE_DIR.resolve()
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return _refuse(link, "flash_bad_file", name)
    if not path.is_file():
        return _refuse(link, "flash_bad_file", name)

    with link._state_lock:
        # The worker sets active only after it has parsed the APJ; a second click in that
        # window would otherwise start a second writer on the same port.
        if link.fw_flash.get("active") or (link.fw_thread is not None and link.fw_thread.is_alive()):
            return _refuse(link, "flash_busy")
        if link.vehicle.armed:
            return _refuse(link, "flash_armed")
        port = link._last_port or ""
        if not port or port.startswith(("tcp:", "udp:", "replay:")):
            return _refuse(link, "flash_serial_only")
        if link._reconnecting:
            return _refuse(link, "flash_unstable")
        # A failed run may have left the FC in its bootloader: allow the retry without a live
        # link, because the worker finds and talks to that bootloader first.
        if not link.connected and link.fw_flash.get("phase") != "failed":
            return _refuse(link, "flash_no_link")
        stop = threading.Event()
        thread = threading.Thread(
            target=_flash_job,
            args=(link, path, stop),
            daemon=True,
            name="firmware-flash",
        )
        link.fw_thread = thread
        link.fw_stop = stop
        thread.start()
    return {"ok": True, "started": True}
