"""backend/firmware_flash.py and the flashing command: APJ, CRC, protocol, guards, worker."""

import base64
import json
import struct
import threading
import time
import zlib
from types import SimpleNamespace
from unittest import mock

import pytest

from backend import firmware_flash as fw
from backend.commands import _firmware as cmd
from backend.drone_link import DroneLink


def make_apj(tmp_path, image=b"\x01\x02\x03\x04\x05", board_id=9, image_size=None, extf_size=0, extf_image=b""):
    desc = {"board_id": board_id, "image": base64.b64encode(zlib.compress(image)).decode()}
    if image_size is not None:
        desc["image_size"] = image_size
    if extf_size or extf_image:
        desc["extf_image"] = base64.b64encode(zlib.compress(extf_image)).decode()
        desc["extf_image_size"] = extf_size
    path = tmp_path / "fw.apj"
    path.write_text(json.dumps(desc), encoding="utf-8")
    return path


class TestApj:
    def test_decodes_pads_and_keeps_the_declared_size(self, tmp_path):
        apj = fw.load_apj(make_apj(tmp_path, image=b"\x01\x02\x03\x04\x05", image_size=5))
        assert apj.board_id == 9
        assert apj.image == b"\x01\x02\x03\x04\x05\xff\xff\xff"
        assert apj.image_size == 5

    def test_refuses_a_real_external_flash_image(self, tmp_path):
        with pytest.raises(fw.FlashError, match="external"):
            fw.load_apj(make_apj(tmp_path, extf_size=3, extf_image=b"ext"))

    def test_accepts_the_empty_external_flash_key_ardupilot_writes(self, tmp_path):
        # The official .apj files carry "extf_image": "eNoDAAAAAAE=" with
        # extf_image_size 0; the key alone is not an external image.
        apj = fw.load_apj(make_apj(tmp_path, extf_size=0, extf_image=b""))
        assert apj.board_id == 9
        assert apj.image

    def test_refuses_a_truncated_image(self, tmp_path):
        packed = zlib.compress(b"x" * 1000)
        path = tmp_path / "truncated.apj"
        path.write_text(
            json.dumps({"board_id": 9, "image": base64.b64encode(packed[:8]).decode()}),
            encoding="utf-8",
        )
        with pytest.raises(fw.FlashError, match="truncated"):
            fw.load_apj(path)

    def test_refuses_an_empty_image(self, tmp_path):
        path = tmp_path / "empty.apj"
        path.write_text(
            json.dumps({"board_id": 9, "image": base64.b64encode(zlib.compress(b"")).decode()}),
            encoding="utf-8",
        )
        with pytest.raises(fw.FlashError, match="empty"):
            fw.load_apj(path)

    def test_refuses_an_image_that_is_not_base64(self, tmp_path):
        path = tmp_path / "bad.apj"
        path.write_text(json.dumps({"board_id": 9, "image": "not base64!"}), encoding="utf-8")
        with pytest.raises(fw.FlashError, match="base64"):
            fw.load_apj(path)

    def test_refuses_a_file_without_a_board_id(self, tmp_path):
        path = tmp_path / "bad.apj"
        path.write_text(json.dumps({"image": base64.b64encode(zlib.compress(b"x")).decode()}), encoding="utf-8")
        with pytest.raises(fw.FlashError, match="board_id"):
            fw.load_apj(path)


class TestCrc:
    def test_matches_the_uploader(self):
        # Values computed with ArduPilot Tools/scripts/uploader.py's crc32.
        assert fw.crc32(b"123456789") == 0x2DFD2D88
        assert fw.crc32(b"\x01\x02\x03\x04") == 0x977824D1
        assert fw.crc_for_flash(b"\x01\x02\x03\x04", 16) == 0x7A7A56A8


class TestBoardCheck:
    def test_accepts_the_board_and_the_compatible_id(self):
        apj = SimpleNamespace(board_id=9, image_size=4, image=b"\x01\x02\x03\x04")
        fw.check_apj(apj, SimpleNamespace(board_id=9, flash_size=1024))
        fw.check_apj(apj, SimpleNamespace(board_id=33, flash_size=1024))

    def test_refuses_another_board(self):
        apj = SimpleNamespace(board_id=9, image_size=4, image=b"\x01\x02\x03\x04")
        with pytest.raises(fw.FlashError, match="board"):
            fw.check_apj(apj, SimpleNamespace(board_id=50, flash_size=1024))

    def test_refuses_an_image_that_does_not_fit(self):
        apj = SimpleNamespace(board_id=9, image_size=8, image=b"\x01\x02\x03\x04\x05\x06\x07\x08")
        with pytest.raises(fw.FlashError, match="fit"):
            fw.check_apj(apj, SimpleNamespace(board_id=9, flash_size=4))


class TestHeartbeatProbe:
    def test_accepts_a_valid_heartbeat(self):
        header = bytes([9, 0, 0, 0, 1, 1, 0, 0, 0])
        payload = bytes(9)
        frame = b"\xfd" + header + payload + struct.pack("<H", fw.mc(header + payload, 50))
        assert fw._heartbeat_in(bytearray(frame))

    def test_rejects_other_bytes(self):
        assert not fw._heartbeat_in(bytearray(b"\x00" * 20))


class FakeSerial:
    """The bootloader side of the protocol, in memory. One command at a time."""

    def __init__(
        self, bl_rev=5, flash_size=1024, crc_ok=True, erase_answers=True, bad_silicon=False, fail_program=False
    ):
        self.info = {1: bl_rev, 2: 9, 3: 1, 4: flash_size, 6: 0}
        self.flash_size = flash_size
        self.crc_ok = crc_ok
        self.erase_answers = erase_answers
        self.bad_silicon = bad_silicon
        self.fail_program = fail_program
        self.inbuf = bytearray()
        self.out = bytearray()
        self.image = bytearray()
        self.read_pos = 0
        self.closed = False
        self.timeout = 2.0

    def _reply(self, body: bytes = b"", status: bytes = b"\x12\x10") -> None:
        self.out += body + status

    def write(self, data):
        self.inbuf += data
        self._parse()

    def _parse(self):
        while self.inbuf:
            command = self.inbuf[0]
            if command == 0x21:  # GET_SYNC + EOC
                if len(self.inbuf) < 2:
                    return
                del self.inbuf[:2]
                self._reply()
            elif command == 0x22:  # GET_DEVICE + param + EOC
                if len(self.inbuf) < 3:
                    return
                param = self.inbuf[1]
                del self.inbuf[:3]
                self._reply(struct.pack("<I", self.info.get(param, 0)))
            elif command == 0x23:  # CHIP_ERASE + EOC
                if len(self.inbuf) < 2:
                    return
                del self.inbuf[:2]
                if self.bad_silicon:
                    self.out += b"\x12\x14"
                elif self.erase_answers:
                    self._reply()
            elif command == 0x27:  # PROG_MULTI + len + data + EOC
                if len(self.inbuf) < 2:
                    return
                count = self.inbuf[1]
                if len(self.inbuf) < 2 + count + 1:
                    return
                self.image += self.inbuf[2 : 2 + count]
                del self.inbuf[: 2 + count + 1]
                if self.fail_program:
                    self.out += b"\x12\x11"
                else:
                    self._reply()
            elif command == 0x29:  # GET_CRC + EOC
                if len(self.inbuf) < 2:
                    return
                del self.inbuf[:2]
                value = fw.crc_for_flash(bytes(self.image), self.flash_size) if self.crc_ok else 0
                self._reply(struct.pack("<I", value))
            elif command == 0x24:  # CHIP_VERIFY + EOC (rev 2)
                if len(self.inbuf) < 2:
                    return
                del self.inbuf[:2]
                self.read_pos = 0
                self._reply()
            elif command == 0x28:  # READ_MULTI + len + EOC (rev 2)
                if len(self.inbuf) < 3:
                    return
                count = self.inbuf[1]
                del self.inbuf[:3]
                body = bytes(self.image[self.read_pos : self.read_pos + count])
                self.read_pos += count
                self._reply(body)
            elif command == 0x30:  # REBOOT + EOC
                if len(self.inbuf) < 2:
                    return
                del self.inbuf[:2]
                self._reply()
            else:
                del self.inbuf[0]

    def read(self, count=1):
        body = bytes(self.out[:count])
        del self.out[:count]
        return body

    def flush(self):
        pass

    def reset_input_buffer(self):
        pass

    def close(self):
        self.closed = True


def bootloader(monkeypatch, fake):
    import serial

    monkeypatch.setattr(serial, "Serial", lambda *args, **kwargs: fake)
    return fw.Bootloader("COM1")


class TestBootloader:
    def test_identify_reads_the_device_info(self, monkeypatch):
        fake = FakeSerial(bl_rev=5, flash_size=2048)
        bl = bootloader(monkeypatch, fake)
        bl.identify()
        assert (bl.bl_rev, bl.board_id, bl.flash_size) == (5, 9, 2048)

    def test_program_and_crc_verify(self, monkeypatch):
        fake = FakeSerial()
        bl = bootloader(monkeypatch, fake)
        bl.identify()
        image = b"\x01\x02\x03\x04" * 10
        bl.erase()
        bl.program(image)
        bl.verify(image)
        assert bytes(fake.image) == image

    def test_a_wrong_crc_fails_the_verify(self, monkeypatch):
        fake = FakeSerial(crc_ok=False)
        bl = bootloader(monkeypatch, fake)
        bl.identify()
        image = b"\x01\x02\x03\x04"
        bl.program(image)
        with pytest.raises(fw.FlashError, match="CRC"):
            bl.verify(image)

    def test_rev2_verifies_by_read_back(self, monkeypatch):
        fake = FakeSerial(bl_rev=2)
        bl = bootloader(monkeypatch, fake)
        bl.identify()
        image = b"\x05\x06\x07\x08" * 5
        bl.program(image)
        bl.verify(image)

    def test_erase_times_out(self, monkeypatch):
        fake = FakeSerial(erase_answers=False)
        bl = bootloader(monkeypatch, fake)
        bl.identify()

        clock = SimpleNamespace(now=0.0)

        class Clock:
            @staticmethod
            def monotonic():
                return clock.now

            @staticmethod
            def sleep(seconds):
                clock.now += seconds

        monkeypatch.setattr(fw, "time", Clock)
        with pytest.raises(fw.FlashError, match="erase"):
            bl.erase()

    def test_bad_silicon_is_reported_not_erased_again(self, monkeypatch):
        fake = FakeSerial(bad_silicon=True)
        bl = bootloader(monkeypatch, fake)
        bl.identify()
        with pytest.raises(fw.FlashError, match="silicon"):
            bl.erase()

    def test_a_failed_program_is_reported(self, monkeypatch):
        fake = FakeSerial(fail_program=True)
        bl = bootloader(monkeypatch, fake)
        bl.identify()
        with pytest.raises(fw.FlashError, match="failure"):
            bl.program(b"\x01\x02\x03\x04")


class TestPauseForFlash:
    def test_refuses_while_the_link_is_reconnecting(self):
        link = DroneLink()
        link._reconnecting = True
        sent = []
        assert link.pause_for_flash(lambda: sent.append(1)) is False
        assert sent == []

    def test_closes_the_port_and_resets_the_session(self):
        link = DroneLink()
        link._ser = mock.MagicMock()
        link._thread = None
        link.connected = True
        assert link.pause_for_flash() is True
        assert link._ser is None
        assert link.connected is False

    def test_the_reboot_command_goes_out_after_the_loop_stopped_and_before_the_port_closes(self):
        link = DroneLink()
        order = []
        link._thread = SimpleNamespace(
            is_alive=lambda: "joined" not in order,
            join=lambda timeout: order.append("joined"),
        )
        link._ser = mock.MagicMock()
        link._ser.close.side_effect = lambda: order.append("closed")
        assert link.pause_for_flash(lambda: order.append("sent")) is True
        assert order == ["joined", "sent", "closed"]

    def test_a_loop_that_does_not_stop_sends_nothing_and_leaves_the_link_as_it_was(self):
        link = DroneLink()
        link._thread = SimpleNamespace(is_alive=lambda: True, join=lambda timeout: None)
        link._ser = mock.MagicMock()
        link._running = True
        sent = []
        assert link.pause_for_flash(lambda: sent.append(1)) is False
        assert sent == []
        assert link._running is True and link._reconnect_enabled is True
        link._ser.close.assert_not_called()

    def test_a_loop_that_ends_while_the_pause_waits_for_it_lets_the_pause_go_on(self):
        # The thread ends right after the join timed out. It has stopped, so the command
        # goes out and the port closes: no state is left between running and paused.
        link = DroneLink()
        checks = []
        link._thread = SimpleNamespace(
            is_alive=lambda: checks.append(1) or len(checks) < 3,  # alive twice, then ended
            join=lambda timeout: None,
        )
        link._ser = mock.MagicMock()
        sent = []
        assert link.pause_for_flash(lambda: sent.append(1)) is True
        assert sent == [1]
        assert link._ser is None and link._running is False

    def test_nothing_of_the_links_is_written_after_the_command_by_a_running_loop(self):
        # The link's own thread, running: its heartbeat is on the port, then the command
        # is the last thing written.
        link = DroneLink()
        writes = []

        class Port:
            in_waiting = 0

            def read(self, count):
                time.sleep(0.02)  # the port's read timeout
                return b""

            def write(self, data):
                writes.append(bytes(data))

            def close(self):
                pass

        link._ser = Port()
        link._running = True
        link._thread = threading.Thread(target=link._loop, daemon=True)
        link._thread.start()
        try:
            deadline = time.monotonic() + 2
            while not writes and time.monotonic() < deadline:
                time.sleep(0.01)
            assert writes
            assert link.pause_for_flash(lambda: link.send(b"the reboot command")) is True
        finally:
            link._running = False
            link._thread.join(timeout=3)
        assert writes[-1] == b"the reboot command"
        assert not link._thread.is_alive()

    def test_a_command_that_cannot_be_sent_still_closes_the_port(self):
        link = DroneLink()
        link._ser = mock.MagicMock()
        link._thread = None

        def broken():
            raise RuntimeError("write failed")

        assert link.pause_for_flash(broken) is True
        assert link._ser is None

    def test_ntrip_and_the_rtcm_injector_are_stopped_before_the_command_goes_out(self):
        # Both write through send() from threads of their own; the reboot command is the
        # last MAVLink frame the port sees.
        link = DroneLink()
        link._ser = mock.MagicMock()
        link._thread = None
        link.ntrip_stop = threading.Event()
        link.rtcm_inject_stop = threading.Event()
        seen = {}

        def command():
            seen.update(ntrip=link.ntrip_stop.is_set(), rtcm=link.rtcm_inject_stop.is_set())

        assert link.pause_for_flash(command) is True
        assert seen == {"ntrip": True, "rtcm": True}

    def test_a_stop_event_cleared_by_its_thread_while_the_pause_runs_is_no_error(self, monkeypatch):
        # The NTRIP thread clears ntrip_stop when it ends. A check of the attribute and a
        # second read of it for set() can trip over that.
        link = DroneLink()
        link._ser = mock.MagicMock()
        link._thread = None
        stop = threading.Event()
        reads = []

        def cleared_after_the_first_read():
            reads.append(1)
            return stop if len(reads) == 1 else None

        monkeypatch.setattr(
            DroneLink, "ntrip_stop", mock.PropertyMock(side_effect=cleared_after_the_first_read), raising=False
        )
        sent = []
        assert link.pause_for_flash(lambda: sent.append(1)) is True
        assert sent == [1] and stop.is_set()
        assert link._ser is None

    def test_a_new_session_drops_the_ports_from_before_the_reboot(self, monkeypatch):
        link = DroneLink()
        link.fw_ports_before = frozenset({"COM1"})
        monkeypatch.setattr(link, "_open_port", lambda port, baud: mock.MagicMock())
        monkeypatch.setattr(link, "_start_log", lambda: None)
        monkeypatch.setattr(link, "_stop_log", lambda: None)
        monkeypatch.setattr(link, "_loop", lambda: None)
        try:
            assert link.connect("COM1") is True
            assert link.fw_ports_before is None
        finally:
            link.disconnect()


class FakeFlashLink:
    def __init__(self):
        self._state_lock = threading.RLock()
        self.fw_flash = {
            "active": False,
            "phase": "",
            "done": 0,
            "total": 0,
            "file": "",
            "port": "",
            "error": "",
        }
        self.fw_thread = None
        self.fw_stop = None
        self.fw_ports_before = None
        self.vehicle = SimpleNamespace(armed=False)
        self.connected = True
        self._last_port = "COM1"
        self._last_baud = 57600
        self._reconnecting = False
        self.locale = "en"
        self.events = []
        self.paused = False
        self.reconnected_to = []

    def add_event(self, text, event_type="", **kwargs):
        self.events.append((event_type, text))

    def pause_for_flash(self, before_close=None):
        # As DroneLink.pause_for_flash: a refusal comes before anything is sent.
        if self._reconnecting:
            return False
        if before_close is not None:
            before_close()
        self.paused = True
        self.connected = False
        return True

    def connect(self, port, baud):
        self.reconnected_to.append((port, baud))
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False


class FakeBootloader:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.calls = []
        self.programmed = b""
        self.port_name = "COM2"

    def identify(self):
        self.calls.append("identify")

    def erase(self):
        self.calls.append("erase")
        if self.fail_on == "erase":
            raise fw.FlashError("erase failed")

    def program(self, image, progress):
        self.calls.append("program")
        self.programmed = image
        if self.fail_on == "program":
            raise fw.FlashError("program failed")
        progress(len(image), len(image))

    def verify(self, image):
        self.calls.append("verify")
        if self.fail_on == "verify":
            raise fw.FlashError("verify failed")

    def reboot(self):
        self.calls.append("reboot")

    def close(self):
        self.calls.append("close")


class TestFlashJob:
    def run_job(self, tmp_path, monkeypatch, boot, reconnect=True):
        link = FakeFlashLink()
        path = make_apj(tmp_path)
        monkeypatch.setattr(cmd, "load_apj", fw.load_apj)
        monkeypatch.setattr(cmd, "send_cmd", lambda *args, **kwargs: None)
        monkeypatch.setattr(cmd, "_current_ports", lambda: set())
        monkeypatch.setattr(cmd, "discover_bootloader", lambda *args, **kwargs: boot)
        monkeypatch.setattr(cmd, "check_apj", lambda apj, bl: None)

        def reconnect_link(target, before):
            target.reconnected_to.append("reconnect")
            return reconnect

        monkeypatch.setattr(cmd, "_reconnect", reconnect_link)
        cmd._flash_job(link, path, threading.Event())
        return link

    def test_a_complete_run_writes_verifies_and_reconnects(self, tmp_path, monkeypatch):
        boot = FakeBootloader()
        link = self.run_job(tmp_path, monkeypatch, boot)
        assert link.fw_flash["phase"] == "done"
        assert link.fw_flash["active"] is False
        assert link.paused is True
        assert boot.calls == ["identify", "erase", "program", "verify", "reboot", "close"]
        assert boot.programmed
        assert link.reconnected_to

    def test_a_failed_program_does_not_reboot_or_reconnect(self, tmp_path, monkeypatch):
        boot = FakeBootloader(fail_on="program")
        link = self.run_job(tmp_path, monkeypatch, boot)
        assert link.fw_flash["phase"] == "failed"
        assert "program failed" in link.fw_flash["error"]
        assert "reboot" not in boot.calls
        assert link.reconnected_to == []

    def test_a_failed_erase_does_not_reboot_a_possibly_blank_chip(self, tmp_path, monkeypatch):
        boot = FakeBootloader(fail_on="erase")
        link = self.run_job(tmp_path, monkeypatch, boot)
        assert link.fw_flash["phase"] == "failed"
        assert "erase failed" in link.fw_flash["error"]
        assert "reboot" not in boot.calls
        assert link.reconnected_to == []

    def test_a_refusal_before_erase_reboots_the_intact_image(self, tmp_path, monkeypatch):
        boot = FakeBootloader()
        link = FakeFlashLink()
        path = make_apj(tmp_path)
        monkeypatch.setattr(cmd, "load_apj", fw.load_apj)
        monkeypatch.setattr(cmd, "send_cmd", lambda *args, **kwargs: None)
        monkeypatch.setattr(cmd, "_current_ports", lambda: set())
        monkeypatch.setattr(cmd, "discover_bootloader", lambda *args, **kwargs: boot)
        monkeypatch.setattr(cmd, "check_apj", lambda apj, bl: (_ for _ in ()).throw(fw.FlashError("wrong board")))
        monkeypatch.setattr(cmd, "_reconnect", lambda target, before: target.reconnected_to.append("yes"))
        cmd._flash_job(link, path, threading.Event())
        assert link.fw_flash["phase"] == "failed"
        assert "reboot" in boot.calls
        assert link.reconnected_to

    def test_an_armed_vehicle_refuses_before_the_port_list(self, tmp_path, monkeypatch):
        link = FakeFlashLink()
        link.vehicle.armed = True
        sent = []
        monkeypatch.setattr(cmd, "load_apj", fw.load_apj)
        monkeypatch.setattr(cmd, "send_cmd", lambda *args, **kwargs: sent.append(args))
        monkeypatch.setattr(cmd, "_current_ports", lambda: (_ for _ in ()).throw(AssertionError("port list read")))
        cmd._flash_job(link, make_apj(tmp_path), threading.Event())
        assert link.fw_flash["phase"] == "failed"
        assert "armed" in link.fw_flash["error"]
        assert sent == [] and link.paused is False

    def test_an_arm_after_the_queue_refuses_before_the_reboot_command(self, tmp_path, monkeypatch):
        link = FakeFlashLink()
        sent = []
        monkeypatch.setattr(cmd, "load_apj", fw.load_apj)
        monkeypatch.setattr(cmd, "send_cmd", lambda target, command, **kwargs: sent.append(command))
        monkeypatch.setattr(cmd, "_current_ports", lambda: set())
        monkeypatch.setattr(cmd, "_reconnect", lambda target, before: target.reconnected_to.append("reconnect"))

        def armed_pause(before_close=None):
            # As the real pause_for_flash: a callback exception is swallowed, and the
            # pause still returns True. The worker, not the callback, must report arming.
            link.vehicle.armed = True
            try:
                before_close()
            except Exception:
                pass
            return True

        monkeypatch.setattr(link, "pause_for_flash", armed_pause)
        cmd._flash_job(link, make_apj(tmp_path), threading.Event())
        assert link.fw_flash["phase"] == "failed"
        assert "armed" in link.fw_flash["error"]
        assert sent == []
        assert link.reconnected_to == ["reconnect"]

    def test_a_link_that_begins_reconnecting_sends_no_reboot_command(self, tmp_path, monkeypatch):
        # Reading the port list takes a moment on Windows. If the link's own loop marks the
        # link lost in that moment the pause is refused. Before, the reboot command had gone
        # out first, and the loop then went on writing MAVLink into the bootloader.
        link = FakeFlashLink()
        sent = []

        def slow_port_list():
            link._reconnecting = True  # the loop's link-lost check fires meanwhile
            return set()

        monkeypatch.setattr(cmd, "_current_ports", slow_port_list)
        monkeypatch.setattr(cmd, "send_cmd", lambda target, command, **kwargs: sent.append(command))
        monkeypatch.setattr(cmd, "_reconnect", lambda target, before: None)
        cmd._flash_job(link, make_apj(tmp_path), threading.Event())
        assert sent == []
        assert link.fw_flash["phase"] == "failed"
        assert "did not stop" in link.fw_flash["error"]
        assert "Nothing was sent" in link.fw_flash["error"]
        # No reboot, so no port list from before one is kept for a retry.
        assert link.fw_ports_before is None


class FakeBootloaderPort:
    """What opening a serial port finds, for the real discover_bootloader."""

    def __init__(self, port, timeout=2.0):
        if port not in WORLD.present:
            raise OSError(f"could not open port {port}")
        self.port_name = port
        WORLD.opened.append(port)

    def sync(self):
        if not (WORLD.answering and self.port_name == WORLD.bootloader):
            raise fw.FlashError(f"{self.port_name}: the bootloader did not answer INSYNC")

    def identify(self):
        pass

    def erase(self):
        pass

    def program(self, image, progress):
        progress(len(image), len(image))

    def verify(self, image):
        pass

    def reboot(self):
        pass

    def close(self):
        pass


WORLD = SimpleNamespace(present={"COM1"}, bootloader="COM2", answering=False, opened=[])


class TestRetryAfterADiscoveryFailure:
    """The real _flash_job, discover_bootloader and port_candidates; the ports are faked."""

    def patch(self, monkeypatch, reconnect=True):
        import serial.tools.list_ports as list_ports

        # The Windows branch of port_candidates and of _current_ports.
        monkeypatch.setattr(cmd.sys, "platform", "win32")
        monkeypatch.setattr(
            list_ports,
            "comports",
            lambda: [SimpleNamespace(device=p, description="USB Serial Device") for p in sorted(WORLD.present)],
        )
        monkeypatch.setattr(fw, "Bootloader", FakeBootloaderPort)
        real_discover = fw.discover_bootloader
        monkeypatch.setattr(
            cmd, "discover_bootloader", lambda original, before=None: real_discover(original, before, 0.05)
        )
        monkeypatch.setattr(cmd, "check_apj", lambda apj, bootloader: None)
        if reconnect:
            monkeypatch.setattr(cmd, "_reconnect", lambda link, before: True)

    def retry_with_another_vehicle_plugged_in(self, tmp_path, monkeypatch, refuse):
        """Run 1 fails in its discovery. COM7, another vehicle with a heartbeat, is plugged in
        before run 2. Run 2 flashes and brings the link back; this board is slow to boot."""
        real_reconnect = cmd._reconnect
        WORLD.present, WORLD.bootloader, WORLD.answering, WORLD.opened = {"COM1"}, "COM2", False, []
        self.patch(monkeypatch, reconnect=False)
        link = FakeFlashLink()

        def reboot(target, command, **kwargs):
            WORLD.present = {"COM2"}

        monkeypatch.setattr(cmd, "send_cmd", reboot)
        monkeypatch.setattr(cmd, "_reconnect", lambda link, before: False)
        path = make_apj(tmp_path)
        cmd._flash_job(link, path, threading.Event())
        assert link.fw_flash["phase"] == "failed"

        WORLD.answering, WORLD.present = True, {"COM2", "COM7"}
        if refuse:
            wrong_board = lambda apj, bootloader: (_ for _ in ()).throw(fw.FlashError("wrong board"))  # noqa: E731
            monkeypatch.setattr(cmd, "check_apj", wrong_board)
        monkeypatch.setattr(FakeBootloaderPort, "reboot", lambda self: setattr(WORLD, "present", {"COM1", "COM7"}))
        probed = []

        def heartbeat(port, baud):
            probed.append(port)
            return port == "COM7" or probed.count("COM1") >= 3

        monkeypatch.setattr(cmd, "probe_mavlink_heartbeat", heartbeat)
        monkeypatch.setattr(cmd, "time", SimpleNamespace(monotonic=time.monotonic, sleep=lambda seconds: None))
        monkeypatch.setattr(cmd, "_reconnect", real_reconnect)
        cmd._flash_job(link, path, threading.Event())
        return link, probed

    def test_a_retry_does_not_link_to_a_vehicle_plugged_in_before_it(self, tmp_path, monkeypatch):
        # The list from before the reboot finds the bootloader (COM2 is new to it), but it
        # must not also decide where the link comes back: COM7 was there when the retry
        # began, and a link to it would send the next command to that vehicle.
        link, probed = self.retry_with_another_vehicle_plugged_in(tmp_path, monkeypatch, refuse=False)
        assert link.fw_flash["phase"] == "done", link.fw_flash["error"]
        assert [port for port, _baud in link.reconnected_to] == ["COM1"]
        assert "COM7" not in probed

    def test_a_retry_refused_before_erase_does_not_link_to_that_vehicle_either(self, tmp_path, monkeypatch):
        link, probed = self.retry_with_another_vehicle_plugged_in(tmp_path, monkeypatch, refuse=True)
        assert link.fw_flash["phase"] == "failed"
        assert [port for port, _baud in link.reconnected_to] == ["COM1"]
        assert "COM7" not in probed

    def test_an_empty_recorded_list_is_still_the_list_from_before_the_reboot(self, tmp_path, monkeypatch):
        # No port could be listed before the reboot (the port list failed then). That is the
        # "nothing was there" the first run worked from, not "no list".
        WORLD.present, WORLD.bootloader, WORLD.answering, WORLD.opened = {"COM1", "COM2"}, "COM2", True, []
        self.patch(monkeypatch)
        link = FakeFlashLink()
        link.connected = False
        link.fw_ports_before = frozenset()
        cmd._flash_job(link, make_apj(tmp_path), threading.Event())
        assert link.fw_flash["phase"] == "done", link.fw_flash["error"]
        assert link.fw_flash["port"] == "COM2"

    def test_a_retry_finds_a_bootloader_that_came_up_on_another_port(self, tmp_path, monkeypatch):
        # The board leaves COM1 for its bootloader's COM2 and is not answering there yet when
        # the first run looks (a slow enumeration, a driver being installed). The second run
        # must still count COM2 as new: a port list taken then has it among the old ones.
        WORLD.present, WORLD.bootloader, WORLD.answering, WORLD.opened = {"COM1"}, "COM2", False, []
        self.patch(monkeypatch)
        link = FakeFlashLink()
        sent = []

        def reboot(target, command, **kwargs):
            sent.append(command)
            WORLD.present = {"COM2"}

        monkeypatch.setattr(cmd, "send_cmd", reboot)
        path = make_apj(tmp_path)
        cmd._flash_job(link, path, threading.Event())
        assert link.fw_flash["phase"] == "failed"
        assert "No bootloader answered" in link.fw_flash["error"]
        assert sent == [246]

        WORLD.answering = True
        WORLD.opened.clear()
        cmd._flash_job(link, path, threading.Event())
        assert link.fw_flash["phase"] == "done", link.fw_flash["error"]
        assert WORLD.opened == ["COM2"]
        assert link.fw_flash["port"] == "COM2"
        # The port list is the link's to keep: fw_flash goes to every page.
        assert set(link.fw_flash) == {"active", "phase", "done", "total", "file", "port", "error"}

    def test_with_no_port_list_from_before_the_reboot_only_the_known_port_is_opened(self, tmp_path, monkeypatch):
        # A board put in its bootloader by hand, after another session: nothing says which
        # port is new, so COM2 (there before this run) is not this run's to open.
        WORLD.present, WORLD.answering, WORLD.opened = {"COM1", "COM2"}, True, []
        self.patch(monkeypatch)
        link = FakeFlashLink()
        link.connected = False
        monkeypatch.setattr(cmd, "send_cmd", lambda *args, **kwargs: None)
        cmd._flash_job(link, make_apj(tmp_path), threading.Event())
        assert link.fw_flash["phase"] == "failed"
        assert WORLD.opened == ["COM1"]


class TestCommandGuards:
    def link(self, tmp_path, monkeypatch):
        link = FakeFlashLink()
        monkeypatch.setattr(cmd.firmware, "FIRMWARE_DIR", tmp_path)
        make_apj(tmp_path)
        monkeypatch.setattr(cmd, "_flash_job", lambda *args, **kwargs: None)
        return link

    def test_starts_a_flash_for_a_stored_file(self, tmp_path, monkeypatch):
        link = self.link(tmp_path, monkeypatch)
        assert cmd.cmd_firmware_flash(link, None, {"file": "fw.apj"}) == {"ok": True, "started": True}

    def test_refuses_an_armed_vehicle(self, tmp_path, monkeypatch):
        link = self.link(tmp_path, monkeypatch)
        link.vehicle.armed = True
        result = cmd.cmd_firmware_flash(link, None, {"file": "fw.apj"})
        assert result["ok"] is False and "Disarm" in result["error"]

    def test_refuses_a_tcp_link(self, tmp_path, monkeypatch):
        link = self.link(tmp_path, monkeypatch)
        link._last_port = "tcp:127.0.0.1:5760"
        result = cmd.cmd_firmware_flash(link, None, {"file": "fw.apj"})
        assert result["ok"] is False and "backend serial" in result["error"]

    def test_refuses_a_second_flash(self, tmp_path, monkeypatch):
        link = self.link(tmp_path, monkeypatch)
        link.fw_flash["active"] = True
        result = cmd.cmd_firmware_flash(link, None, {"file": "fw.apj"})
        assert result["ok"] is False and "already running" in result["error"]

    def test_refuses_a_second_flash_before_it_marks_active(self, tmp_path, monkeypatch):
        link = self.link(tmp_path, monkeypatch)
        link.fw_thread = SimpleNamespace(is_alive=lambda: True)
        result = cmd.cmd_firmware_flash(link, None, {"file": "fw.apj"})
        assert result["ok"] is False and "already running" in result["error"]

    def test_refuses_a_path_outside_the_firmware_folder(self, tmp_path, monkeypatch):
        link = self.link(tmp_path, monkeypatch)
        result = cmd.cmd_firmware_flash(link, None, {"file": "../fw.apj"})
        assert result["ok"] is False

    def test_can_flash_a_known_serial_port_without_a_heartbeat(self, tmp_path, monkeypatch):
        # A board already in its bootloader has no MAVLink heartbeat but is exactly what we
        # want to flash; the bootloader sync, not link.connected, decides.
        link = self.link(tmp_path, monkeypatch)
        link.connected = False
        assert cmd.cmd_firmware_flash(link, None, {"file": "fw.apj"}) == {"ok": True, "started": True}

    def test_a_failed_flash_can_retry_without_a_live_link(self, tmp_path, monkeypatch):
        link = self.link(tmp_path, monkeypatch)
        link.connected = False
        link.fw_flash["phase"] = "failed"
        assert cmd.cmd_firmware_flash(link, None, {"file": "fw.apj"}) == {"ok": True, "started": True}
