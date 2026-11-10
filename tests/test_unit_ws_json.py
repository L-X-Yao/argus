"""What goes to the page must be JSON that the page can parse.

json.dumps writes a NaN as the bare word NaN, and JSON.parse throws on it. An FC sends NaN
for real: the variances of an estimator that has diverged, an attitude nobody measured.
"""

import asyncio
import json
import struct
from unittest.mock import MagicMock

import pytest

from backend.drone_link import _CRC_EXTRA, DroneLink
from backend.ws_manager import WSManager, dumps

NAN, INF = float("nan"), float("inf")

# src/lib/ws.test.ts feeds the page this same text.
DIVERGED = (
    '{"type": "state", "connected": true, "roll": null, "pitch": 1.5, "vibe": [0.1, null, null], "ekf_vel": null, '
    '"_nonfinite": [["roll", "NaN"], ["vibe", 1, "Infinity"], ["vibe", 2, "-Infinity"], ["ekf_vel", "NaN"]]}'
)


def strict(text: str) -> dict:
    """Parse as a browser does: NaN, Infinity and -Infinity are syntax errors there."""

    def refuse(word):
        raise ValueError(f"{word} is not JSON")

    return json.loads(text, parse_constant=refuse)


def frame(link: DroneLink, msg_id: int, payload: bytes) -> bytes:
    header = bytes([len(payload), 0, 0, 0, 1, 1, msg_id & 0xFF, (msg_id >> 8) & 0xFF, (msg_id >> 16) & 0xFF])
    crc = link._mavlink_crc16(header + payload + bytes([_CRC_EXTRA[msg_id]]))
    return b"\xfd" + header + payload + struct.pack("<H", crc)


def linked() -> DroneLink:
    link = DroneLink()
    link._ser = MagicMock()
    link._record_tlog = lambda frame: None
    link.feed(frame(link, 0, struct.pack("<IBBBBB", 0, 2, 3, 81, 4, 3)))  # a Copter heartbeat
    return link


class TestDumps:
    def test_a_message_of_finite_numbers_goes_out_as_it_is(self):
        msg = {"type": "state", "roll": 1.5, "vibe": [0.1, 0.2], "mode": "LOITER", "summary": None}
        assert dumps(msg) == json.dumps(msg)
        assert "_nonfinite" not in dumps(msg)

    def test_nan_and_infinity_go_as_null_with_where_they_were(self):
        msg = {"type": "state", "connected": True, "roll": NAN, "pitch": 1.5, "vibe": [0.1, INF, -INF], "ekf_vel": NAN}
        assert dumps(msg) == DIVERGED
        assert strict(dumps(msg))["roll"] is None

    def test_the_message_given_is_left_alone(self):
        msg = {"type": "state", "vibe": [NAN]}
        dumps(msg)
        assert "_nonfinite" not in msg and msg["vibe"][0] != msg["vibe"][0]

    def test_it_reaches_into_lists_of_objects(self):
        msg = {"type": "mission_downloaded", "waypoints": [{"alt": 30.0, "p4": NAN}, {"alt": NAN, "p4": 0.0}]}
        sent = strict(dumps(msg))
        assert sent["waypoints"] == [{"alt": 30.0, "p4": None}, {"alt": None, "p4": 0.0}]
        assert sent["_nonfinite"] == [["waypoints", 0, "p4", "NaN"], ["waypoints", 1, "alt", "NaN"]]

    def test_a_null_of_the_message_itself_is_not_listed(self):
        sent = strict(dumps({"type": "state", "flight_summary": None, "roll": NAN}))
        assert sent["_nonfinite"] == [["roll", "NaN"]]


class TestTelemetryThatIsNoNumber:
    """Every message that the probe of all 67 handled ones found able to do it."""

    @pytest.mark.parametrize(
        "msg_id, keys",
        [
            (30, {"roll", "pitch", "yaw"}),  # ATTITUDE
            (74, {"airspeed", "climb"}),  # VFR_HUD
            (168, {"wind_dir", "wind_speed"}),  # WIND
            (193, {"ekf_vel", "ekf_pos_h", "ekf_pos_v", "ekf_compass"}),  # EKF_STATUS_REPORT
            (241, {"vibe"}),  # VIBRATION
            (285, {"gimbal_pitch", "gimbal_yaw"}),  # GIMBAL_DEVICE_ATTITUDE_STATUS
        ],
    )
    @pytest.mark.parametrize("value", [NAN, INF])
    def test_the_state_stays_json_and_says_which_values(self, msg_id, keys, value):
        link = linked()
        link.feed(frame(link, msg_id, (struct.pack("<f", value) * 64)[:200]))
        sent = strict(dumps(link.get_state()))
        marked = {mark[0] for mark in sent["_nonfinite"]}
        # An angle worked out from an infinite quaternion can come out finite: any of them will do.
        assert marked and marked <= keys
        assert all(sent[key] is None or None in sent[key] for key in marked)

    def test_a_downloaded_mission_with_nan_in_it_stays_json(self):
        from backend.commands import execute

        link = linked()
        execute("mission_download", None, link)
        link.feed(frame(link, 44, struct.pack("<HBBB", 2, 255, 190, 0)))
        for seq in (0, 1):  # item 0 is home, which the download leaves out
            item = struct.pack(
                "<ffffiifHHBBBBBB", 0, 0, 0, NAN, -353600000, 1491600000, 30.0, seq, 16, 255, 190, 3, 0, 1, 0
            )
            link.feed(frame(link, 73, item))
        (downloaded,) = [m for m in link.mission._dl_messages if m["type"] == "mission_downloaded"]
        sent = strict(dumps(downloaded))
        assert sent["waypoints"][0]["p4"] is None
        assert sent["_nonfinite"] == [["waypoints", 0, "p4", "NaN"]]

    def test_a_parameter_that_holds_nan_stays_json(self):
        from backend.commands import execute

        link = linked()
        execute("param_request_all", None, link)
        link.feed(frame(link, 22, struct.pack("<fHH16sB", NAN, 1, 0, b"TEST_NAN".ljust(16, b"\x00"), 9)))
        batch = {"type": "param_batch", "params": [m for m in link.param_mgr._messages if m["type"] == "param_value"]}
        sent = strict(dumps(batch))
        assert sent["params"][0]["name"] == "TEST_NAN" and sent["params"][0]["value"] is None


class TestPushLoop:
    def test_what_the_page_is_sent_parses_after_the_estimator_diverges(self):
        """The whole path: frame, state, push loop, text on the socket."""
        link = linked()
        link.feed(frame(link, 193, struct.pack("<ffffHf", NAN, NAN, NAN, NAN, 0, NAN)))
        sent: list[str] = []

        class Page:
            async def send_text(self, text):
                sent.append(text)
                if len(sent) >= 3:
                    raise RuntimeError("enough")

        async def run():
            manager = WSManager(link)
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr("backend.ws_manager.cfg.WS_PUSH_INTERVAL_CONNECTED", 0)
                patch.setattr("backend.ws_manager.cfg.WS_PUSH_INTERVAL_IDLE", 0)
                await manager._push_loop(Page())

        asyncio.run(run())
        states = [strict(text) for text in sent]
        assert len(states) == 3
        # NaN never equals itself, so the variance is in every push, the short ones included.
        assert all(state["ekf_vel"] is None and ["ekf_vel", "NaN"] in state["_nonfinite"] for state in states)
