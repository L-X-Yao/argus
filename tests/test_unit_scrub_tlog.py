"""scripts/scrub_tlog.py: what must not survive into a shared recording."""

import struct

from pymavlink.dialects.v20 import ardupilotmega as apm

from scripts.scrub_tlog import _scrub_text, scrub, verify


class TestScrubText:
    def test_board_banner_loses_name_and_uid(self):
        assert _scrub_text("AcmeBoard 0030ABCD 3133510C 38383833") == "board 00000000 00000000 00000000"

    def test_firmware_banner_loses_name_and_keeps_version(self):
        assert _scrub_text("Acme-Copter V1.2.3 (bfec0dc8)") == "firmware V1.2.3 (bfec0dc8)"

    def test_field_elevation_is_zeroed(self):
        assert _scrub_text("Field Elevation Set: 1234m") == "Field Elevation Set: 0000m"

    def test_other_text_is_untouched(self):
        for text in ("EKF3 IMU0 origin set", "ChibiOS: 7c2d922b", "Frame: QUAD/X", "PreArm: RC not found"):
            assert _scrub_text(text) == text


class TestScrubFile:
    def test_board_and_firmware_names_leave_the_file(self, tmp_path):
        mav = apm.MAVLink(None, srcSystem=1, srcComponent=1)
        mav.robust_parsing = True
        msgs = [
            apm.MAVLink_home_position_message(341000000, 1089000000, 400000, 0, 0, 0, [1, 0, 0, 0], 0, 0, 0),
            apm.MAVLink_statustext_message(6, b"AcmeBoard 0030ABCD 3133510C 38383833"),
            apm.MAVLink_statustext_message(6, b"Acme-Copter V1.2.3 (bfec0dc8)"),
        ]
        src = tmp_path / "in.tlog"
        src.write_bytes(b"".join(struct.pack(">Q", i * 1000) + bytes(m.pack(mav)) for i, m in enumerate(msgs)))
        out = tmp_path / "out.tlog"

        scrub(str(src), str(out))
        verify(str(src), str(out))

        blob = out.read_bytes()
        assert b"AcmeBoard" not in blob
        assert b"Acme-Copter" not in blob
        assert b"0030ABCD" not in blob
