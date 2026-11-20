"""Write an ArduPilot .apj to a board over its bootloader protocol.

Read-only apart from the serial port it opens. The protocol is ArduPilot's, as implemented by
Tools/scripts/uploader.py (fetched 2026-11-20): APJ decoding at lines 163-200, the command and
reply bytes at 209-253, sync at 342-406, identify at 729-760, erase/program/verify/reboot at
467-700, and upload() at 924-990. Keep this file in step with that one.

Only the bootloader over a direct serial port is supported: a radio cannot carry the protocol,
and a browser cannot reopen the port after the flight controller re-enumerates.
"""

from __future__ import annotations

import base64
import binascii
import glob
import json
import struct
import sys
import threading
import time
import zlib
from dataclasses import dataclass
from pathlib import Path

from .config import cfg
from .crc_extras import CRC_EXTRA
from .mavlink_frame import mc


class FlashError(Exception):
    """The flash cannot go on; the message names the phase that failed."""


@dataclass(frozen=True)
class Apj:
    name: str
    board_id: int
    image: bytes
    image_size: int


def load_apj(path: Path) -> Apj:
    """The board id and the decoded image, with the 4-byte padding the bootloader writes.

    The image is zlib-compressed base64 in the JSON (uploader.py:170-190). A decompression
    bomb is stopped at the same cap the upload route uses.
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            desc = json.load(fh)
    except (OSError, ValueError) as exc:
        raise FlashError(f"Cannot read {path.name}: {exc}") from exc
    if not isinstance(desc, dict):
        raise FlashError(f"{path.name} is not an ArduPilot .apj.")
    if desc.get("extf_image"):
        raise FlashError("This .apj carries an external-flash image, which Argus does not write yet.")
    raw = desc.get("image")
    if not isinstance(raw, str) or not raw:
        raise FlashError(f"{path.name} has no image field.")
    try:
        packed = base64.b64decode(raw, validate=True)
        stream = zlib.decompressobj()
        image = bytearray(stream.decompress(packed, cfg.FIRMWARE_MAX_SIZE + 1))
        if len(image) > cfg.FIRMWARE_MAX_SIZE or stream.unconsumed_tail:
            raise FlashError(f"The image in {path.name} is larger than {cfg.FIRMWARE_MAX_SIZE // 1024 // 1024} MB.")
        image += stream.flush()
    except (binascii.Error, zlib.error, ValueError) as exc:
        raise FlashError(f"The image in {path.name} is not base64 zlib: {exc}") from exc
    if len(image) > cfg.FIRMWARE_MAX_SIZE:
        raise FlashError(f"The image in {path.name} is larger than {cfg.FIRMWARE_MAX_SIZE // 1024 // 1024} MB.")
    board_id = desc.get("board_id")
    if not isinstance(board_id, int) or isinstance(board_id, bool):
        raise FlashError(f"{path.name} has no board_id.")
    image += b"\xff" * (-len(image) % 4)
    declared = desc.get("image_size")
    image_size = (
        declared if isinstance(declared, int) and not isinstance(declared, bool) and declared > 0 else len(image)
    )
    return Apj(path.name, board_id, bytes(image), image_size)


def _crc_table() -> tuple[int, ...]:
    # crc_crc32 in AP_Math/crc.cpp, the table uploader.py:120-161 carries.
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if crc & 1 else crc >> 1
        table.append(crc)
    return tuple(table)


_CRC_TABLE = _crc_table()


def crc32(data: bytes, state: int = 0) -> int:
    for byte in data:
        state = _CRC_TABLE[(state ^ byte) & 0xFF] ^ (state >> 8)
    return state


def crc_for_flash(image: bytes, flash_size: int) -> int:
    """The CRC the bootloader compares against: the image, then 0xFF to its flash size.

    uploader.py:194-200 pads with four bytes at a time; flash sizes are multiples of 4 on every
    board this runs on.
    """
    if flash_size <= 0:
        raise FlashError("The bootloader did not report a firmware region.")
    state = crc32(image, 0)
    pad = b"\xff\xff\xff\xff"
    for _ in range(len(image), flash_size - 1, 4):
        state = crc32(pad, state)
    return state


# Protocol bytes, uploader.py:209-253.
INSYNC = b"\x12"
EOC = b"\x20"
OK = b"\x10"
FAILED = b"\x11"
INVALID = b"\x13"
BAD_SILICON_REV = b"\x14"
NOP = b"\x00"
GET_SYNC = b"\x21"
GET_DEVICE = b"\x22"
CHIP_ERASE = b"\x23"
CHIP_VERIFY = b"\x24"
PROG_MULTI = b"\x27"
READ_MULTI = b"\x28"
GET_CRC = b"\x29"
REBOOT = b"\x30"
INFO_BL_REV = b"\x01"
INFO_BOARD_ID = b"\x02"
INFO_BOARD_REV = b"\x03"
INFO_FLASH_SIZE = b"\x04"
INFO_EXTF_SIZE = b"\x06"
PROG_MULTI_MAX = 252
READ_MULTI_MAX = 252
BL_REV_MIN = 2
BL_REV_MAX = 5
# uploader.py:150: a board whose firmware id differs but is compatible.
COMPATIBLE_IDS = {33: 9}
BOOTLOADER_BAUD = 115200


class Bootloader:
    """The serial side of the protocol; open() happens in __init__, close() is the caller's."""

    def __init__(self, port: str, timeout: float = 2.0):
        import serial

        self.port_name = port
        self.port = serial.Serial(port, BOOTLOADER_BAUD, timeout=timeout, write_timeout=timeout)
        self.bl_rev = 0
        self.board_id = 0
        self.board_rev = 0
        self.flash_size = 0
        self.extf_size = 0

    def close(self) -> None:
        try:
            self.port.close()
        except OSError:
            pass

    def _write(self, data: bytes) -> None:
        try:
            self.port.write(data)
        except OSError as exc:
            raise FlashError(f"{self.port_name}: write failed: {exc}") from exc

    def _read(self, count: int) -> bytes:
        try:
            data = self.port.read(count)
        except OSError as exc:
            raise FlashError(f"{self.port_name}: read failed: {exc}") from exc
        if len(data) < count:
            raise FlashError(f"{self.port_name}: timeout waiting for {count} bytes")
        return data

    def _flush_output(self) -> None:
        try:
            self.port.flush()
        except OSError:
            pass

    def _flush_input(self) -> None:
        try:
            self.port.reset_input_buffer()
        except AttributeError:
            try:
                self.port.flushInput()
            except AttributeError:
                pass

    def _get_sync(self) -> None:
        self._flush_output()
        if self._read(1) != INSYNC:
            raise FlashError(f"{self.port_name}: the bootloader did not answer INSYNC")
        reply = self._read(1)
        if reply == INVALID:
            raise FlashError(f"{self.port_name}: the bootloader rejected the operation")
        if reply == FAILED:
            raise FlashError(f"{self.port_name}: the bootloader reported failure")
        if reply != OK:
            raise FlashError(f"{self.port_name}: unexpected reply 0x{reply[0]:02x}")

    def sync(self) -> None:
        self._flush_input()
        self._write(GET_SYNC + EOC)
        self._get_sync()

    def _try_sync(self) -> bool:
        try:
            self._flush_output()
            first = self._read(1)
            if first != INSYNC:
                return False
            reply = self._read(1)
            if reply == BAD_SILICON_REV:
                raise FlashError("Programming is not supported on this silicon revision.")
            return reply == OK
        except FlashError:
            return False

    def info(self, param: bytes) -> int:
        self._write(GET_DEVICE + param + EOC)
        value = struct.unpack("<I", self._read(4))[0]
        self._get_sync()
        return value

    def identify(self) -> None:
        self.sync()
        self.bl_rev = self.info(INFO_BL_REV)
        if self.bl_rev < BL_REV_MIN or self.bl_rev > BL_REV_MAX:
            raise FlashError(
                f"Unsupported bootloader protocol {self.bl_rev} (Argus supports {BL_REV_MIN}-{BL_REV_MAX})."
            )
        try:
            self.extf_size = self.info(INFO_EXTF_SIZE)
        except FlashError:
            # uploader.py:739-746: old bootloaders have no external-flash info.
            self.extf_size = 0
            self.sync()
        self.board_id = self.info(INFO_BOARD_ID)
        self.board_rev = self.info(INFO_BOARD_REV)
        self.flash_size = self.info(INFO_FLASH_SIZE)
        if self.flash_size <= 0:
            raise FlashError("The bootloader reported no firmware region.")

    def erase(self) -> None:
        self._write(CHIP_ERASE + EOC)
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if self._try_sync():
                return
            time.sleep(0.05)
        raise FlashError("Timed out waiting for the erase to finish.")

    def program(self, image: bytes, progress=None) -> None:
        for start in range(0, len(image), PROG_MULTI_MAX):
            chunk = image[start : start + PROG_MULTI_MAX]
            self._write(PROG_MULTI + bytes([len(chunk)]) + chunk + EOC)
            self._get_sync()
            if progress:
                progress(min(start + len(chunk), len(image)), len(image))

    def _verify_v2(self, image: bytes) -> None:
        self._write(CHIP_VERIFY + EOC)
        self._get_sync()
        for start in range(0, len(image), READ_MULTI_MAX):
            chunk = image[start : start + READ_MULTI_MAX]
            self._write(READ_MULTI + bytes([len(chunk)]) + EOC)
            self._flush_output()
            if self._read(len(chunk)) != chunk:
                raise FlashError("Verification failed: the bootloader read back different bytes.")
            self._get_sync()

    def _verify_v3(self, image: bytes) -> None:
        self._write(GET_CRC + EOC)
        old = self.port.timeout
        self.port.timeout = 10.0
        try:
            reported = struct.unpack("<I", self._read(4))[0]
        finally:
            self.port.timeout = old
        self._get_sync()
        expected = crc_for_flash(image, self.flash_size)
        if reported != expected:
            raise FlashError(f"Verification failed: CRC 0x{reported:08x}, expected 0x{expected:08x}.")

    def verify(self, image: bytes) -> None:
        if self.bl_rev == 2:
            self._verify_v2(image)
        else:
            self._verify_v3(image)

    def reboot(self) -> None:
        self._write(REBOOT + EOC)
        self._flush_output()
        if self.bl_rev >= 3:
            try:
                self._get_sync()
            except FlashError:
                # The board may reboot before answering; discovery is the real check.
                pass


def check_apj(apj: Apj, bootloader: Bootloader) -> None:
    if bootloader.board_id != apj.board_id and COMPATIBLE_IDS.get(bootloader.board_id) != apj.board_id:
        raise FlashError(
            f"Firmware is for board {apj.board_id}, but the bootloader reports board {bootloader.board_id}."
        )
    if apj.image_size > bootloader.flash_size or len(apj.image) > bootloader.flash_size:
        raise FlashError(f"Firmware does not fit: {len(apj.image)} bytes into {bootloader.flash_size}.")


def _heartbeat_in(buf: bytearray) -> bool:
    """True when buf holds a complete, CRC-valid MAVLink HEARTBEAT (msgid 0)."""
    while len(buf) >= 8:
        if buf[0] == 0xFD:
            length = buf[1]
            need = 12 + length
            if len(buf) < need:
                return False
            msgid = buf[8] | (buf[9] << 8) | (buf[10] << 16)
            if msgid == 0:
                header = bytes(buf[1:10])
                payload = bytes(buf[10 : 10 + length])
                crc = struct.unpack("<H", bytes(buf[10 + length : need]))[0]
                if mc(header + payload, CRC_EXTRA[0]) == crc:
                    return True
            del buf[0]
        elif buf[0] == 0xFE:
            length = buf[1]
            need = 8 + length
            if len(buf) < need:
                return False
            if buf[5] == 0:  # MAVLink 1 has a one-byte message id.
                body = bytes(buf[1 : 6 + length])
                crc = struct.unpack("<H", bytes(buf[6 + length : need]))[0]
                if mc(body, CRC_EXTRA[0]) == crc:
                    return True
            del buf[0]
        else:
            del buf[0]
    return False


def probe_mavlink_heartbeat(port: str, baud: int, timeout: float = 4.0) -> bool:
    """Read only: is this port the flight controller rather than a bootloader?

    The reconnect uses it so no MAVLink frame is ever written into a bootloader, where a byte
    in the payload could otherwise be read as a command.
    """
    import serial

    try:
        ser = serial.Serial(port, baud, timeout=0.3, write_timeout=0.3)
    except OSError:
        return False
    try:
        deadline = time.monotonic() + timeout
        buf = bytearray()
        while time.monotonic() < deadline:
            try:
                buf += ser.read(4096)
            except OSError:
                return False
            if _heartbeat_in(buf):
                return True
        return False
    finally:
        try:
            ser.close()
        except OSError:
            pass


def port_candidates(original: str, before: set[str] | None = None) -> list[str]:
    """The original port first, then the ports a bootloader may have re-enumerated as."""
    before = before or set()
    out: list[str] = []

    def add(port: str) -> None:
        if port and port not in out:
            out.append(port)

    add(original)
    if sys.platform.startswith("win"):
        try:
            from serial.tools import list_ports

            ports = list(list_ports.comports())
        except Exception:  # pyserial missing, or the platform has no port list
            ports = []
        # A bootloader's USB product string usually carries "BL"; a newly appeared COM port
        # comes next. Opening a port and sending the sync is harmless.
        ports.sort(key=lambda p: (0 if "BL" in (p.description or "").upper() else 1, p.device))
        for port in ports:
            description = (port.description or "").upper()
            if port.device == original or port.device not in before or "BL" in description:
                add(port.device)
    else:
        for pattern in ("/dev/serial/by-id/*_BL_*", "/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*"):
            for port in sorted(glob.glob(pattern)):
                add(port)
    return out


def discover_bootloader(
    original: str,
    before: set[str] | None = None,
    timeout: float = 15.0,
    stop: threading.Event | None = None,
) -> Bootloader:
    """Open the first port that answers the bootloader sync. Raises FlashError."""
    deadline = time.monotonic() + timeout
    last = "no candidate"
    while time.monotonic() < deadline:
        if stop is not None and stop.is_set():
            raise FlashError("The flash was cancelled.")
        for port in port_candidates(original, before):
            try:
                candidate = Bootloader(port, timeout=0.4)
            except OSError as exc:
                last = str(exc)
                continue
            try:
                candidate.sync()
                return candidate
            except FlashError as exc:
                last = str(exc)
                candidate.close()
        time.sleep(0.2)
    raise FlashError(f"No bootloader answered on {original} or another port ({last}).")
