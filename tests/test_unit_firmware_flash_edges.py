"""Error and edge paths of the firmware flashing code: APJ refusals, broken ports, discovery."""

import json
import struct
import threading
from types import SimpleNamespace

import pytest
from test_unit_firmware_flash import (
    FakeBootloader,
    FakeFlashLink,
    FakeSerial,
    bootloader,
    make_apj,
)

from backend import firmware_flash as fw
from backend.commands import _firmware as cmd


class TestApjEdges:
    def test_a_missing_file_is_refused(self, tmp_path):
        with pytest.raises(fw.FlashError, match="Cannot read"):
            fw.load_apj(tmp_path / "nope.apj")

    def test_json_that_is_not_an_object_is_refused(self, tmp_path):
        path = tmp_path / "list.apj"
        path.write_text("[]", encoding="utf-8")
        with pytest.raises(fw.FlashError, match="not an ArduPilot"):
            fw.load_apj(path)

    def test_an_invalid_extf_size_is_refused(self, tmp_path):
        path = tmp_path / "extf.apj"
        path.write_text(json.dumps({"board_id": 9, "image": "x", "extf_image_size": "big"}), encoding="utf-8")
        with pytest.raises(fw.FlashError, match="extf_image_size"):
            fw.load_apj(path)

    def test_an_apj_without_an_image_is_refused(self, tmp_path):
        path = tmp_path / "noimage.apj"
        path.write_text(json.dumps({"board_id": 9}), encoding="utf-8")
        with pytest.raises(fw.FlashError, match="no image"):
            fw.load_apj(path)

    def test_an_image_over_the_cap_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fw.cfg, "FIRMWARE_MAX_SIZE", 10)
        with pytest.raises(fw.FlashError, match="larger than"):
            fw.load_apj(make_apj(tmp_path, image=b"x" * 100))

    def test_crc_without_a_flash_region_is_refused(self):
        with pytest.raises(fw.FlashError, match="firmware region"):
            fw.crc_for_flash(b"\x01", 0)


class BrokenSerial(FakeSerial):
    def __init__(self, mode: str):
        super().__init__()
        self.mode = mode

    def write(self, data):
        if self.mode == "write":
            raise OSError("boom")
        super().write(data)

    def read(self, count=1):
        if self.mode == "read":
            raise OSError("boom")
        if self.mode == "short":
            return b""
        return super().read(count)

    def flush(self):
        if self.mode == "flush":
            raise OSError("boom")
        super().flush()

    def reset_input_buffer(self):
        if self.mode == "flush_in":
            raise OSError("boom")
        super().reset_input_buffer()

    def close(self):
        if self.mode == "close":
            raise OSError("boom")
        super().close()


class TestBootloaderEdges:
    def test_a_write_error_is_a_flash_error(self, monkeypatch):
        bl = bootloader(monkeypatch, BrokenSerial("write"))
        with pytest.raises(fw.FlashError, match="write failed"):
            bl._write(b"x")

    def test_a_read_error_is_a_flash_error(self, monkeypatch):
        bl = bootloader(monkeypatch, BrokenSerial("read"))
        with pytest.raises(fw.FlashError, match="read failed"):
            bl._read(1)

    def test_a_short_read_is_a_timeout(self, monkeypatch):
        bl = bootloader(monkeypatch, BrokenSerial("short"))
        with pytest.raises(fw.FlashError, match="timeout"):
            bl._read(4)

    def test_flush_errors_are_swallowed(self, monkeypatch):
        bl = bootloader(monkeypatch, BrokenSerial("flush"))
        bl._flush_output()
        bl.close()

    def test_a_flush_input_error_is_reported(self, monkeypatch):
        bl = bootloader(monkeypatch, BrokenSerial("flush_in"))
        with pytest.raises(fw.FlashError, match="cannot flush"):
            bl._flush_input()

    def test_close_ignores_an_oserror(self, monkeypatch):
        bootloader(monkeypatch, BrokenSerial("close")).close()

    def test_get_sync_replies_are_checked(self, monkeypatch):
        fake = FakeSerial()
        bl = bootloader(monkeypatch, fake)
        for reply, message in (
            (b"\x00\x10", "INSYNC"),
            (b"\x12\x13", "rejected"),
            (b"\x12\x11", "failure"),
            (b"\x12\x99", "unexpected"),
        ):
            fake.out = bytearray(reply)
            with pytest.raises(fw.FlashError, match=message):
                bl._get_sync()

    def test_identify_rejects_an_unknown_protocol(self, monkeypatch):
        bl = bootloader(monkeypatch, FakeSerial(bl_rev=1))
        with pytest.raises(fw.FlashError, match="Unsupported bootloader"):
            bl.identify()

    def test_identify_accepts_a_bootloader_without_extf_info(self, monkeypatch):
        bl = bootloader(monkeypatch, FakeSerial())
        monkeypatch.setattr(bl, "sync", lambda: None)
        calls = []

        def info(param):
            if param == fw.INFO_EXTF_SIZE:
                raise fw.FlashError("old bootloader")
            calls.append(param)
            return {fw.INFO_BL_REV: 5, fw.INFO_BOARD_ID: 9, fw.INFO_BOARD_REV: 1, fw.INFO_FLASH_SIZE: 1024}[param]

        monkeypatch.setattr(bl, "info", info)
        bl.identify()
        assert bl.extf_size == 0
        assert (bl.bl_rev, bl.board_id, bl.flash_size) == (5, 9, 1024)

    def test_identify_requires_a_firmware_region(self, monkeypatch):
        bl = bootloader(monkeypatch, FakeSerial())
        monkeypatch.setattr(bl, "sync", lambda: None)
        monkeypatch.setattr(bl, "info", lambda param: 5 if param == fw.INFO_BL_REV else 0)
        with pytest.raises(fw.FlashError, match="firmware region"):
            bl.identify()

    def test_program_reports_progress(self, monkeypatch):
        bl = bootloader(monkeypatch, FakeSerial())
        bl.identify()
        seen = []
        bl.program(b"\x01\x02\x03\x04" * 100, lambda done, total: seen.append((done, total)))
        assert seen and seen[-1] == (400, 400)

    def test_rev2_verify_reports_a_mismatch(self, monkeypatch):
        bl = bootloader(monkeypatch, FakeSerial(bl_rev=2))
        bl.identify()
        monkeypatch.setattr(bl, "_get_sync", lambda: None)
        monkeypatch.setattr(bl, "_read", lambda count: b"\x00" * count)
        with pytest.raises(fw.FlashError, match="different bytes"):
            bl._verify_v2(b"\x01\x02\x03\x04")

    def test_reboot_tolerates_a_lost_ack(self, monkeypatch):
        bl = bootloader(monkeypatch, FakeSerial())
        bl.identify()
        bl.reboot()
        monkeypatch.setattr(bl, "_get_sync", lambda: (_ for _ in ()).throw(fw.FlashError("timeout")))
        bl.reboot()

    def test_check_apj_refuses_an_empty_image(self):
        apj = fw.Apj("x.apj", 9, b"", 0)
        with pytest.raises(fw.FlashError, match="empty"):
            fw.check_apj(apj, SimpleNamespace(board_id=9, flash_size=1024))


class TestPortsAndProbe:
    def test_linux_candidates_keep_only_new_ports(self, monkeypatch):
        monkeypatch.setattr(fw.sys, "platform", "linux")

        def glob(pattern):
            return ["/dev/ttyACM0", "/dev/ttyACM1"] if "ttyACM" in pattern else []

        monkeypatch.setattr(fw.glob, "glob", glob)
        assert fw.port_candidates("/dev/ttyACM0", {"/dev/ttyACM0", "/dev/ttyACM1"}) == ["/dev/ttyACM0"]
        assert fw.port_candidates("/dev/ttyACM0", {"/dev/ttyACM0"}) == ["/dev/ttyACM0", "/dev/ttyACM1"]

    def test_windows_candidates_prefer_a_new_bootloader(self, monkeypatch):
        import serial.tools.list_ports as list_ports

        monkeypatch.setattr(fw.sys, "platform", "win32")
        ports = [
            SimpleNamespace(device="COM1", description="USB Serial"),
            SimpleNamespace(device="COM3", description="Other"),
            SimpleNamespace(device="COM2", description="BL"),
        ]
        monkeypatch.setattr(list_ports, "comports", lambda: ports)
        assert fw.port_candidates("COM1", {"COM1", "COM3"}) == ["COM1", "COM2"]

    def test_windows_without_a_port_list_returns_the_original(self, monkeypatch):
        import serial.tools.list_ports as list_ports

        monkeypatch.setattr(fw.sys, "platform", "win32")
        monkeypatch.setattr(list_ports, "comports", lambda: (_ for _ in ()).throw(RuntimeError("no list")))
        assert fw.port_candidates("COM1", set()) == ["COM1"]

    def test_probe_accepts_a_heartbeat(self, monkeypatch):
        import serial

        header = bytes([9, 0, 0, 0, 1, 1, 0, 0, 0])
        payload = bytes(9)
        frame = b"\xfd" + header + payload + struct.pack("<H", fw.mc(header + payload, 50))

        class OneFrame:
            def __init__(self):
                self.sent = False

            def read(self, count):
                if self.sent:
                    return b""
                self.sent = True
                return frame

            def close(self):
                pass

        monkeypatch.setattr(serial, "Serial", lambda *args, **kwargs: OneFrame())
        assert fw.probe_mavlink_heartbeat("COM1", 57600) is True

    def test_probe_returns_false_on_a_read_error(self, monkeypatch):
        import serial

        class Broken:
            def read(self, count):
                raise OSError("unplugged")

            def close(self):
                pass

        monkeypatch.setattr(serial, "Serial", lambda *args, **kwargs: Broken())
        assert fw.probe_mavlink_heartbeat("COM1", 57600) is False

    def test_probe_times_out_without_a_heartbeat(self, monkeypatch):
        import serial

        class Silent:
            def read(self, count):
                return b""

            def close(self):
                pass

        ticks = [0]

        class Clock:
            @staticmethod
            def monotonic():
                ticks[0] += 1
                return ticks[0]

            @staticmethod
            def sleep(seconds):
                ticks[0] += seconds

        monkeypatch.setattr(serial, "Serial", lambda *args, **kwargs: Silent())
        monkeypatch.setattr(fw, "time", Clock)
        assert fw.probe_mavlink_heartbeat("COM1", 57600) is False

    def test_probe_returns_false_when_the_port_will_not_open(self, monkeypatch):
        import serial

        monkeypatch.setattr(serial, "Serial", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("busy")))
        assert fw.probe_mavlink_heartbeat("COM1", 57600) is False

    def test_heartbeat_in_handles_a_truncated_frame(self):
        assert fw._heartbeat_in(bytearray(b"\xfd\xc8" + b"\x00" * 10)) is False

    def test_heartbeat_in_discards_non_frames(self):
        assert fw._heartbeat_in(bytearray(b"\x00" * 12)) is False

    def test_discover_returns_the_first_bootloader(self, monkeypatch):
        class Client:
            def __init__(self, port, timeout):
                self.port = port

            def sync(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(fw, "port_candidates", lambda original, before=None: ["COM1"])
        monkeypatch.setattr(fw, "Bootloader", Client)
        assert fw.discover_bootloader("COM1").port == "COM1"

    def test_discover_times_out(self, monkeypatch):
        monkeypatch.setattr(fw, "port_candidates", lambda original, before=None: [])
        ticks = [0]

        class Clock:
            @staticmethod
            def monotonic():
                ticks[0] += 10
                return ticks[0]

            @staticmethod
            def sleep(seconds):
                pass

        monkeypatch.setattr(fw, "time", Clock)
        with pytest.raises(fw.FlashError, match="No bootloader"):
            fw.discover_bootloader("COM1")

    def test_discover_honours_the_stop_event(self):
        stop = threading.Event()
        stop.set()
        with pytest.raises(fw.FlashError, match="cancelled"):
            fw.discover_bootloader("COM1", stop=stop)

    def test_discover_skips_a_port_that_will_not_open(self, monkeypatch):
        class Client:
            def __init__(self, port, timeout):
                raise OSError("busy")

        monkeypatch.setattr(fw, "port_candidates", lambda original, before=None: ["COM1"])
        monkeypatch.setattr(fw, "Bootloader", Client)
        ticks = [0]

        class Clock:
            @staticmethod
            def monotonic():
                ticks[0] += 10
                return ticks[0]

            @staticmethod
            def sleep(seconds):
                pass

        monkeypatch.setattr(fw, "time", Clock)
        with pytest.raises(fw.FlashError, match="No bootloader"):
            fw.discover_bootloader("COM1")


class TestOrchestrationEdges:
    def test_current_ports_reads_the_port_list_and_globs(self, monkeypatch):
        import serial.tools.list_ports as list_ports

        monkeypatch.setattr(cmd.sys, "platform", "linux")
        monkeypatch.setattr(list_ports, "comports", lambda: [SimpleNamespace(device="/dev/ttyACM0")])
        monkeypatch.setattr(cmd.glob, "glob", lambda pattern: ["/dev/ttyACM0"] if "ttyACM" in pattern else [])
        assert "/dev/ttyACM0" in cmd._current_ports()

    def test_current_ports_survives_a_missing_port_list(self, monkeypatch):
        import serial.tools.list_ports as list_ports

        monkeypatch.setattr(cmd.sys, "platform", "linux")
        monkeypatch.setattr(list_ports, "comports", lambda: (_ for _ in ()).throw(RuntimeError("no list")))
        monkeypatch.setattr(cmd.glob, "glob", lambda pattern: [])
        assert cmd._current_ports() == set()

    def test_reconnect_returns_true_when_a_heartbeat_is_found(self, monkeypatch):
        link = FakeFlashLink()
        monkeypatch.setattr(cmd, "port_candidates", lambda original, before=None: ["COM1"])
        monkeypatch.setattr(cmd, "probe_mavlink_heartbeat", lambda port, baud: True)
        assert cmd._reconnect(link, set()) is True
        assert link.reconnected_to

    def test_reconnect_returns_false_on_timeout(self, monkeypatch):
        link = FakeFlashLink()
        monkeypatch.setattr(cmd, "port_candidates", lambda original, before=None: ["COM1"])
        monkeypatch.setattr(cmd, "probe_mavlink_heartbeat", lambda port, baud: False)
        ticks = [0]

        class Clock:
            @staticmethod
            def monotonic():
                ticks[0] += 10
                return ticks[0]

            @staticmethod
            def sleep(seconds):
                pass

        monkeypatch.setattr(cmd, "time", Clock)
        assert cmd._reconnect(link, set()) is False

    def test_a_load_failure_does_not_touch_a_live_link(self, tmp_path, monkeypatch):
        link = FakeFlashLink()
        path = make_apj(tmp_path)
        reconnects = []
        monkeypatch.setattr(cmd, "load_apj", lambda p: (_ for _ in ()).throw(fw.FlashError("bad apj")))
        monkeypatch.setattr(cmd, "_reconnect", lambda target, before: reconnects.append(1))
        cmd._flash_job(link, path, threading.Event())
        assert link.fw_flash["phase"] == "failed"
        assert reconnects == []

    def test_a_pause_failure_is_reported(self, tmp_path, monkeypatch):
        link = FakeFlashLink()
        path = make_apj(tmp_path)
        sent = []
        monkeypatch.setattr(cmd, "_current_ports", lambda: set())
        monkeypatch.setattr(cmd, "send_cmd", lambda target, command, **kwargs: sent.append(command))
        monkeypatch.setattr(link, "pause_for_flash", lambda *args, **kwargs: False)
        cmd._flash_job(link, path, threading.Event())
        assert link.fw_flash["phase"] == "failed"
        assert "did not stop" in link.fw_flash["error"]
        # The pause was refused, so the reboot command never went out.
        assert sent == []

    def test_a_discovery_failure_reconnects_the_app(self, tmp_path, monkeypatch):
        link = FakeFlashLink()
        path = make_apj(tmp_path)
        reconnects = []
        monkeypatch.setattr(cmd, "_current_ports", lambda: set())
        monkeypatch.setattr(cmd, "send_cmd", lambda *args, **kwargs: None)
        monkeypatch.setattr(
            cmd, "discover_bootloader", lambda *args, **kwargs: (_ for _ in ()).throw(fw.FlashError("no bl"))
        )
        monkeypatch.setattr(cmd, "_reconnect", lambda target, before: reconnects.append(1))
        cmd._flash_job(link, path, threading.Event())
        assert link.fw_flash["phase"] == "failed"
        assert reconnects == [1]

    def test_an_unexpected_error_before_erase_recovers(self, tmp_path, monkeypatch):
        link = FakeFlashLink()
        boot = FakeBootloader()
        path = make_apj(tmp_path)
        reconnects = []
        monkeypatch.setattr(cmd, "_current_ports", lambda: set())
        monkeypatch.setattr(cmd, "send_cmd", lambda *args, **kwargs: None)
        monkeypatch.setattr(cmd, "discover_bootloader", lambda *args, **kwargs: boot)
        monkeypatch.setattr(cmd, "check_apj", lambda apj, bl: (_ for _ in ()).throw(ValueError("bug")))
        monkeypatch.setattr(cmd, "_reconnect", lambda target, before: reconnects.append(1))
        cmd._flash_job(link, path, threading.Event())
        assert link.fw_flash["phase"] == "failed"
        assert "reboot" in boot.calls
        assert reconnects == [1]

    def test_a_failed_reconnect_after_a_write_is_reported(self, tmp_path, monkeypatch):
        link = FakeFlashLink()
        boot = FakeBootloader()
        path = make_apj(tmp_path)
        monkeypatch.setattr(cmd, "_current_ports", lambda: set())
        monkeypatch.setattr(cmd, "send_cmd", lambda *args, **kwargs: None)
        monkeypatch.setattr(cmd, "discover_bootloader", lambda *args, **kwargs: boot)
        monkeypatch.setattr(cmd, "check_apj", lambda apj, bl: None)
        monkeypatch.setattr(cmd, "_reconnect", lambda target, before: False)
        cmd._flash_job(link, path, threading.Event())
        assert link.fw_flash["phase"] == "failed"
        assert "did not come back" in link.fw_flash["error"]


class TestCommandEdges:
    def link(self, tmp_path, monkeypatch):
        link = FakeFlashLink()
        monkeypatch.setattr(cmd.firmware, "FIRMWARE_DIR", tmp_path)
        make_apj(tmp_path)
        monkeypatch.setattr(cmd, "_flash_job", lambda *args, **kwargs: None)
        return link

    def test_bad_names_are_refused(self, tmp_path, monkeypatch):
        link = self.link(tmp_path, monkeypatch)
        for name in (None, 123, "x.txt", ".apj", "../fw.apj", "sub/fw.apj"):
            result = cmd.cmd_firmware_flash(link, None, {"file": name})
            assert result["ok"] is False, name

    def test_a_missing_file_is_refused(self, tmp_path, monkeypatch):
        link = self.link(tmp_path, monkeypatch)
        assert cmd.cmd_firmware_flash(link, None, {"file": "nope.apj"})["ok"] is False

    def test_a_link_without_a_known_port_is_refused(self, tmp_path, monkeypatch):
        link = self.link(tmp_path, monkeypatch)
        link._last_port = ""
        result = cmd.cmd_firmware_flash(link, None, {"file": "fw.apj"})
        assert result["ok"] is False and "backend serial" in result["error"]

    def test_a_reconnecting_link_is_refused(self, tmp_path, monkeypatch):
        link = self.link(tmp_path, monkeypatch)
        link._reconnecting = True
        result = cmd.cmd_firmware_flash(link, None, {"file": "fw.apj"})
        assert result["ok"] is False and "reconnecting" in result["error"]
