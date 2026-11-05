"""Fuzz tests for the MAVLink parser and frame builder.

Ensures malformed, truncated, and random data does not crash the parser.
"""

import os
import struct

from backend.drone_link import _CRC_EXTRA, DroneLink
from backend.mavlink_frame import bm, mc

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _build_valid_mavlink(link, msg_id=0, payload=b"\x00" * 9, sysid=1, compid=1, seq=0):
    """Build a valid MAVLink v2 frame for comparison / mutation tests."""
    header = bytes(
        [
            len(payload),
            0,
            0,
            seq & 0xFF,
            sysid & 0xFF,
            compid & 0xFF,
            msg_id & 0xFF,
            (msg_id >> 8) & 0xFF,
            (msg_id >> 16) & 0xFF,
        ]
    )
    crc_extra = _CRC_EXTRA.get(msg_id, 0)
    crc = link._mavlink_crc16(header + payload + bytes([crc_extra]))
    return b"\xfd" + header + payload + struct.pack("<H", crc)


# ---------------------------------------------------------------------------
# MAVLink parser fuzz: random / garbage data
# ---------------------------------------------------------------------------


class TestMavlinkParserRandomData:
    """Ensure _parse_mavlink_frame never raises on garbage input."""

    def test_empty_buffer(self):
        link = DroneLink()
        link._buf = b""
        result, skip = link._parse_mavlink_frame()
        assert result is None

    def test_single_byte_zero(self):
        link = DroneLink()
        link._buf = b"\x00"
        result, skip = link._parse_mavlink_frame()
        assert result is None
        assert skip >= 1

    def test_single_byte_magic(self):
        link = DroneLink()
        link._buf = b"\xfd"
        result, skip = link._parse_mavlink_frame()
        assert result is None
        assert skip == 0  # needs more data

    def test_random_bytes_short(self):
        link = DroneLink()
        link._buf = os.urandom(5)
        result, skip = link._parse_mavlink_frame()
        assert result is None

    def test_random_bytes_medium(self):
        link = DroneLink()
        link._buf = os.urandom(64)
        result, skip = link._parse_mavlink_frame()
        assert result is None

    def test_random_bytes_large(self):
        link = DroneLink()
        link._buf = os.urandom(1024)
        result, skip = link._parse_mavlink_frame()
        assert result is None

    def test_all_zeros(self):
        link = DroneLink()
        link._buf = b"\x00" * 100
        result, skip = link._parse_mavlink_frame()
        assert result is None
        assert skip >= 1

    def test_all_ff(self):
        link = DroneLink()
        link._buf = b"\xff" * 100
        result, skip = link._parse_mavlink_frame()
        assert result is None


# ---------------------------------------------------------------------------
# MAVLink parser fuzz: structural malformations
# ---------------------------------------------------------------------------


class TestMavlinkParserMalformed:
    """Test partial / malformed MAVLink frames."""

    def test_magic_then_truncated_header(self):
        link = DroneLink()
        link._buf = b"\xfd\x09\x00\x00"
        result, skip = link._parse_mavlink_frame()
        assert result is None
        assert skip == 0

    def test_wrong_magic_byte(self):
        link = DroneLink()
        link._buf = b"\xfe\x09\x00\x00\x01\x01\x01\x00\x00\x00" + b"\x00" * 11
        result, skip = link._parse_mavlink_frame()
        assert result is None

    def test_invalid_crc(self):
        link = DroneLink()
        frame = bytearray(_build_valid_mavlink(link))
        frame[-1] ^= 0xFF  # flip last CRC byte
        frame[-2] ^= 0xFF  # flip first CRC byte
        link._buf = bytes(frame)
        result, skip = link._parse_mavlink_frame()
        assert result is None
        assert skip == 1

    def test_truncated_payload(self):
        """Payload length says 9, but buffer only has 3 bytes of payload."""
        link = DroneLink()
        link._buf = b"\xfd\x09\x00\x00\x01\x01\x01\x00\x00\x00\x01\x02\x03"
        result, skip = link._parse_mavlink_frame()
        assert result is None
        assert skip == 0  # waiting for more data

    def test_oversized_payload_length(self):
        """Claimed payload length of 255 with insufficient data."""
        link = DroneLink()
        link._buf = b"\xfd\xff\x00\x00\x01\x01\x01\x00\x00\x00" + b"\x00" * 20
        result, skip = link._parse_mavlink_frame()
        assert result is None
        assert skip == 0

    def test_magic_in_middle_garbage_before(self):
        link = DroneLink()
        link._buf = b"\xaa\xbb\xcc\xfd\x00\x00\x00\x01\x01\x00\x00\x00\x00"
        result, skip = link._parse_mavlink_frame()
        assert result is None
        assert skip == 3  # skip to the magic byte

    def test_repeated_magic_bytes(self):
        link = DroneLink()
        link._buf = b"\xfd" * 50
        result, skip = link._parse_mavlink_frame()
        # Should not crash; may find or reject frame
        assert result is None or isinstance(result, bytes)

    def test_zero_length_payload(self):
        link = DroneLink()
        # A heartbeat-like frame with 0-byte payload
        link._buf = b"\xfd\x00\x00\x00\x01\x01\x01\x00\x00\x00\x00\x00"
        result, skip = link._parse_mavlink_frame()
        # Should not crash
        assert result is None or isinstance(result, bytes)


# ---------------------------------------------------------------------------
# MAVLink CRC (mc) fuzz
# ---------------------------------------------------------------------------


class TestMavlinkCrcFuzz:
    """Fuzz mc (MAVLink CRC) with garbage data."""

    def test_empty_data(self):
        crc = mc(b"", 0)
        assert isinstance(crc, int)
        assert 0 <= crc <= 0xFFFF

    def test_random_payload_random_extra(self):
        for _ in range(20):
            data = os.urandom(32)
            extra = int.from_bytes(os.urandom(1), "little")
            crc = mc(data, extra)
            assert 0 <= crc <= 0xFFFF

    def test_large_payload(self):
        data = os.urandom(512)
        crc = mc(data, 50)
        assert 0 <= crc <= 0xFFFF


# ---------------------------------------------------------------------------
# Build MAVLink frame (bm) fuzz
# ---------------------------------------------------------------------------


class TestBuildMavlinkFuzz:
    """Fuzz bm (build MAVLink frame) with edge-case inputs."""

    def test_empty_payload(self):
        frame = bm(0, b"", 0, 50)
        assert frame[0] == 0xFD
        assert frame[1] == 0  # length

    def test_max_msg_id(self):
        frame = bm(0xFFFFFF, b"\x00", 0, 50)
        assert frame[7] == 0xFF
        assert frame[8] == 0xFF
        assert frame[9] == 0xFF

    def test_large_payload(self):
        payload = os.urandom(255)
        frame = bm(0, payload, 0, 50)
        assert frame[1] == 255

    def test_zero_crc_extra(self):
        frame = bm(0, b"\x00" * 9, 0, 0)
        assert isinstance(frame, bytes)
        assert len(frame) == 1 + 9 + 9 + 2
