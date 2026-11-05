"""Tests for backend.mavlink_frame: MAVLink CRC and frame construction."""

from backend.mavlink_frame import bm, mc


class TestMavlinkCrc:
    def test_returns_uint16(self):
        crc = mc(b"\xfd\x09\x00", 50)
        assert isinstance(crc, int)
        assert 0 <= crc <= 0xFFFF

    def test_deterministic(self):
        data = b"\x09\x00\x00\x01\x01\x01\x00\x00\x00"
        assert mc(data, 50) == mc(data, 50)

    def test_different_crc_extra(self):
        data = b"\x09\x00\x00\x01\x01\x01\x00\x00\x00"
        assert mc(data, 50) != mc(data, 51)


class TestBuildMavlink:
    def test_magic_byte(self):
        frame = bm(0, b"\x00" * 9, 0, 50)
        assert frame[0] == 0xFD

    def test_payload_length(self):
        payload = b"\x00" * 9
        frame = bm(0, payload, 0, 50)
        assert frame[1] == len(payload)

    def test_sysid_compid(self):
        frame = bm(0, b"\x00", 0, 50, sysid=1, compid=190)
        assert frame[5] == 1
        assert frame[6] == 190

    def test_msg_id_encoding(self):
        frame = bm(33, b"\x00" * 28, 0, 104)
        assert frame[7] == 33
        assert frame[8] == 0
        assert frame[9] == 0

    def test_crc_appended(self):
        payload = b"\x00" * 9
        frame = bm(0, payload, 0, 50)
        expected_len = 1 + 9 + len(payload) + 2  # magic + header + payload + crc
        assert len(frame) == expected_len

    def test_default_sysid_compid(self):
        frame = bm(0, b"\x00", 0, 50)
        assert frame[5] == 255  # default sysid
        assert frame[6] == 1  # default compid
