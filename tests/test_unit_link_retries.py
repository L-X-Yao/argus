"""One lost frame must not end a transfer or swallow a click: see send_cmd and _resend_stalled."""

import struct
import time
from unittest.mock import MagicMock, patch

from backend.commands import check_commands, execute
from backend.commands._mission import check_mission_dl_timeout
from backend.config import cfg
from backend.drone_link import DroneLink
from backend.mavlink_handlers import handle_command_ack, handle_mission_ack


def make_link():
    link = DroneLink()
    link._ser = MagicMock()
    link.connected = True
    link.vehicle.vtype_raw = 2
    return link


def msg_ids(link):
    frames = [c.args[0] for c in link._ser.write.call_args_list]
    return [f[7] | (f[8] << 8) | (f[9] << 16) for f in frames]


def later(link, seconds, check):
    """Runs a check as if the seconds had gone by. All the modules share one time module."""
    real = time.time()
    with patch.object(time, "time", return_value=real + seconds):
        check(link)


def ack(link, command, result=0):
    handle_command_ack(struct.pack("<HB", command, result), 3, link)


class TestCommands:
    def confirmations(self, link):
        frames = [c.args[0] for c in link._ser.write.call_args_list]
        return [f[10 + 32] for f in frames if f[7] == 76]

    def test_a_mode_change_goes_out_again_and_then_reports_no_answer(self):
        link = make_link()
        execute("mode", 4, link)
        assert self.confirmations(link) == [0]
        later(link, 1.1, check_commands)
        assert self.confirmations(link) == [0, 1]
        later(link, 2.2, check_commands)
        assert self.confirmations(link) == [0, 1, 2]
        assert not [e for e in link.events if e["event_type"] == "cmd_ack_fail"]
        later(link, 3.3, check_commands)
        assert self.confirmations(link) == [0, 1, 2]
        failed = [e for e in link.events if e["event_type"] == "cmd_ack_fail"]
        assert len(failed) == 1
        assert "无应答" in failed[0]["text"]

    def test_an_answer_ends_it(self):
        link = make_link()
        execute("mode", 4, link)
        ack(link, 176)
        later(link, 5, check_commands)
        assert self.confirmations(link) == [0]

    def test_a_refusal_is_an_answer(self):
        link = make_link()
        execute("mode", 4, link)
        ack(link, 176, result=4)
        assert link._cmd_pending == {}

    def test_an_accept_goes_out_again(self):
        # Nobody clicked it, so nobody would notice the compasses left unsaved.
        link = make_link()
        execute("cal_compass_accept", None, link)
        later(link, 1.1, check_commands)
        assert self.confirmations(link) == [0, 1]

    def test_what_must_not_run_twice_is_not_repeated_but_still_reported(self):
        link = make_link()
        execute("motor_test", None, link, data={"motor": 0, "throttle": 5, "duration": 1})
        later(link, 1.1, check_commands)
        later(link, 2.2, check_commands)
        assert self.confirmations(link) == [0]
        assert not [e for e in link.events if e["event_type"] == "cmd_ack_fail"]
        later(link, 3.3, check_commands)
        assert [e for e in link.events if e["event_type"] == "cmd_ack_fail"]

    def test_a_reboot_expects_no_answer(self):
        link = make_link()
        execute("reboot", None, link)
        assert link._cmd_pending == {}

    def test_a_calibration_answers_when_it_is_done(self):
        link = make_link()
        execute("cal_gyro", None, link)
        assert link._cmd_pending == {}

    def test_a_link_reset_forgets_what_was_waiting(self):
        link = make_link()
        execute("mode", 4, link)
        link._reset_session_state()
        assert link._cmd_pending == {}


class TestNoLink:
    """A key pressed with no vehicle must not wait for the next one that connects."""

    def test_a_command_with_no_port_is_refused_and_not_kept(self):
        link = DroneLink()
        result = execute("arm", None, link)
        assert result["ok"] is False
        assert link._cmd_pending == {}

    def test_so_is_one_before_a_vehicle_has_been_heard(self):
        link = make_link()
        link.connected = False  # a port open is not a vehicle: after a loss on UDP, say
        assert execute("rtl", None, link)["ok"] is False
        assert link._ser.write.call_count == 0

    def test_a_cancel_always_gets_through(self):
        link = DroneLink()
        assert execute("cal_cancel", None, link) is None

    def test_an_upload_is_refused_too(self):
        link = DroneLink()
        result = execute("mission_upload", None, link, data={"waypoints": [{"lat": 30.0, "lon": 120.0, "alt": 50}]})
        assert result["ok"] is False
        assert link.mission._mission_pending is False

    def test_what_only_touches_the_gcs_still_works(self):
        link = DroneLink()
        assert execute("clear_summary", None, link) is None

    def test_connecting_starts_with_nothing_waiting(self):
        link = make_link()
        link._cmd_pending[400] = {"sent": 0, "tries": 1, "resend": None}
        link._ser = None
        with patch.object(link, "_open_port", return_value=MagicMock(in_waiting=0)), patch("threading.Thread"):
            link.connect("tcp:127.0.0.1:5760")
        assert link._cmd_pending == {}


class TestMissionTransfers:
    WPS = [{"lat": 30.0, "lon": 120.0, "alt": 50}]

    def test_asks_for_the_mission_list_again(self):
        link = make_link()
        execute("mission_download", None, link)
        assert msg_ids(link).count(43) == 1
        later(link, cfg.MISSION_RETRY_INTERVAL + 0.1, check_mission_dl_timeout)
        assert msg_ids(link).count(43) == 2

    def test_asks_again_for_the_item_that_went_missing(self):
        link = make_link()
        execute("mission_download", None, link)
        link.mission._dl_total = 3
        link.mission._dl_items = [{"seq": 0}, None, None]
        later(link, cfg.MISSION_RETRY_INTERVAL + 0.1, check_mission_dl_timeout)
        frame = link._ser.write.call_args[0][0]
        assert frame[7] == 51
        assert struct.unpack_from("<H", frame, 10)[0] == 1

    def test_the_download_still_gives_up(self):
        link = make_link()
        execute("mission_download", None, link)
        later(link, cfg.MISSION_DL_TIMEOUT + 1, check_mission_dl_timeout)
        assert link.mission._dl_pending is False

    def test_sends_the_count_of_an_upload_again(self):
        link = make_link()
        execute("mission_upload", None, link, data={"waypoints": self.WPS})
        assert msg_ids(link).count(44) == 1
        later(link, cfg.MISSION_UPLOAD_RETRY - 0.5, check_mission_dl_timeout)
        assert msg_ids(link).count(44) == 1
        later(link, cfg.MISSION_UPLOAD_RETRY + 0.1, check_mission_dl_timeout)
        assert msg_ids(link).count(44) == 2

    def test_an_fc_at_work_is_left_alone(self):
        link = make_link()
        execute("mission_upload", None, link, data={"waypoints": self.WPS})
        link.mission._mission_ul_start_time += 100  # it just asked for an item
        later(link, cfg.MISSION_UPLOAD_RETRY + 0.1, check_mission_dl_timeout)
        assert msg_ids(link).count(44) == 1

    def test_the_counts_of_the_other_stores_go_out_again_with_their_type(self):
        link = make_link()
        polygon = [{"lat": 30.0, "lon": 120.0}, {"lat": 30.1, "lon": 120.0}, {"lat": 30.1, "lon": 120.1}]
        execute("fence_upload", None, link, data={"polygon": polygon})
        later(link, cfg.MISSION_UPLOAD_RETRY + 0.1, check_mission_dl_timeout)
        frame = link._ser.write.call_args[0][0]
        assert (frame[7], frame[10 + 4]) == (44, 1)

        link = make_link()
        execute("rally_upload", None, link, data={"points": [{"lat": 30.0, "lon": 120.0, "alt": 50}]})
        later(link, cfg.MISSION_UPLOAD_RETRY + 0.1, check_mission_dl_timeout)
        frame = link._ser.write.call_args[0][0]
        assert (frame[7], frame[10 + 4]) == (44, 2)

    def test_a_clear_goes_out_again_before_it_gives_up(self):
        link = make_link()
        execute("fence_clear", None, link)
        later(link, cfg.STORE_CLEAR_TIMEOUT / 2 + 0.1, check_mission_dl_timeout)
        assert msg_ids(link).count(45) == 2


class TestMissionClear:
    def test_goes_out_again_and_reports_only_what_the_fc_said(self):
        link = make_link()
        execute("mission_clear", None, link)
        assert not [e for e in link.events if e["event_type"] == "mission_clear"]
        later(link, cfg.STORE_CLEAR_TIMEOUT / 2 + 0.1, check_mission_dl_timeout)
        assert msg_ids(link).count(45) == 2
        handle_mission_ack(bytes([255, 190, 0, 0]), 4, link)
        assert link.mission._mission_clear_pending is False
        assert [e for e in link.events if e["event_type"] == "mission_clear"]

    def test_no_answer_is_a_failure(self):
        link = make_link()
        execute("mission_clear", None, link)
        later(link, cfg.STORE_CLEAR_TIMEOUT + 1, check_mission_dl_timeout)
        assert [e for e in link.events if e["event_type"] == "mission_clear_fail"]

    def test_a_refused_clear_leaves_the_jump_table_alone(self):
        """The FC refuses it while flying the mission, and a jump must still find its item."""
        link = make_link()
        link.mission._seq_to_wp = {2: 0, 4: 1}
        execute("mission_clear", None, link)
        assert link.mission._seq_to_wp == {2: 0, 4: 1}
        handle_mission_ack(bytes([255, 190, 1, 0]), 4, link)
        assert link.mission._seq_to_wp == {2: 0, 4: 1}
        assert [e for e in link.events if e["event_type"] == "mission_clear_fail"]

    def test_an_accepted_clear_empties_it(self):
        link = make_link()
        link.mission._seq_to_wp = {2: 0}
        execute("mission_clear", None, link)
        handle_mission_ack(bytes([255, 190, 0, 0]), 4, link)
        assert link.mission._seq_to_wp == {}

    def test_an_upload_waits_for_it(self):
        link = make_link()
        execute("mission_clear", None, link)
        wps = [{"lat": 30.0, "lon": 120.0, "alt": 50}]
        assert execute("mission_upload", None, link, data={"waypoints": wps})["ok"] is False


class TestParamSet:
    def test_goes_out_again_until_the_fc_echoes_it(self):
        link = make_link()
        link.param_mgr.set_param("RTL_ALT", 3000)
        later(link, 1.1, lambda _l: link.param_mgr.check_timeout())
        assert msg_ids(link).count(23) == 2
        echo = struct.pack("<fHH", 3000, 100, 5) + b"RTL_ALT".ljust(16, b"\x00") + bytes([9])
        link.param_mgr.handle_param_value(echo, len(echo))
        later(link, 5, lambda _l: link.param_mgr.check_timeout())
        assert msg_ids(link).count(23) == 2

    def test_silence_is_reported(self):
        link = make_link()
        link.param_mgr.set_param("RTL_ALT", 3000)
        for seconds in (1.1, 2.2, 3.3):
            later(link, seconds, lambda _l: link.param_mgr.check_timeout())
        assert [e for e in link.events if e["event_type"] == "param_set_fail"]


class TestRetriedMissionStart:
    def test_a_mode_change_also_stops_the_one_about_to_go_out(self):
        link = make_link()
        with patch("backend.commands._mission.cfg.MISSION_START_DELAY", 0.05):
            execute("mission_start", None, link)
            execute("mode", 6, link)
            time.sleep(0.15)
        frames = [c.args[0] for c in link._ser.write.call_args_list]
        assert not [f for f in frames if f[7] == 76 and struct.unpack_from("<H", f, 10 + 28)[0] == 300]

    def test_a_mode_change_cancels_it(self):
        link = make_link()
        execute("mission_start", None, link)
        link._cmd_pending[300] = {"sent": 0, "tries": 1, "resend": lambda n: None}
        execute("mode", 6, link)
        assert 300 not in link._cmd_pending


class TestLinkLostDuringUpload:
    def test_is_reported(self):
        link = make_link()
        execute("mission_upload", None, link, data={"waypoints": [{"lat": 30.0, "lon": 120.0, "alt": 50}]})
        link._reset_session_state()
        assert [e for e in link.events if e["event_type"] == "mission_ack_fail"]
