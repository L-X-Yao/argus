from __future__ import annotations

import struct
import threading
import time
from typing import TYPE_CHECKING

from ..config import cfg
from ..crc_extras import CRC_EXTRA
from ..locale_text import lt
from ..mavlink_frame import bm
from ._helpers import send_cmd, send_fence_count, send_mission_count, send_set_mode

if TYPE_CHECKING:
    from ..drone_link import DroneLink

_mission_timer: threading.Timer | None = None
_timer_lock = threading.Lock()


def cmd_mission_start(link: DroneLink, param, data: dict):
    global _mission_timer
    am = link.special_mode("auto")
    link.add_event(lt("mission_start", link.locale), "mission_start")
    send_set_mode(link, am)

    def _delayed():
        try:
            send_cmd(link, 300)
        except OSError:
            link.add_event(lt("err_mission_start", link.locale), "cmd_ack_fail")

    with _timer_lock:
        if _mission_timer:
            _mission_timer.cancel()
        _mission_timer = threading.Timer(cfg.MISSION_START_DELAY, _delayed)
        _mission_timer.daemon = True
        _mission_timer.start()


def cmd_mission_set_current(link: DroneLink, param, data: dict):
    # MISSION_SET_CURRENT (msg 41, CRC_EXTRA 28): jump to waypoint seq during flight.
    # ArduPilot: GCS_MAVLINK::handle_mission_set_current (GCS_Common.cpp)
    # Frontend sends wp_index (0-based waypoint position). We resolve to
    # the actual MAVLink seq via _seq_to_wp reverse lookup, falling back to
    # index+2 (home=0, takeoff=1, first nav=2) when no upload mapping exists.
    wp_index = int(data.get("wp_index", param if param is not None else 0))
    seq = wp_index + 2
    for s, idx in link.mission._seq_to_wp.items():
        if idx == wp_index:
            seq = s
            break
    link.send(bm(41, struct.pack("<HBB", seq, link.vehicle.sysid, 1), link.sq, CRC_EXTRA[41]))
    link.add_event(lt("mission_set_current", link.locale) % (wp_index + 1), "mission_set_current")


def cmd_mission_clear(link: DroneLink, param, data: dict):
    link.send(bm(45, bytes([link.vehicle.sysid, 1, 0]), link.sq, CRC_EXTRA[45]))
    link.mission._mission_items = []
    link.mission._seq_to_wp = {}
    link.mission._mission_pending = False
    link.mission._mission_ul_start_time = 0.0
    link.add_event(lt("mission_clear", link.locale), "mission_clear")


def cmd_fence_clear(link: DroneLink, param, data: dict):
    # MISSION_CLEAR_ALL with mission_type=1 (MAV_MISSION_TYPE_FENCE): AP routes
    # it by type (GCS_Common.cpp:805 handle_mission_clear_all) and wipes the
    # stored polygon with write_fence(nullptr, 0) (MissionItemProtocol_Fence.cpp:226).
    # Non-mission types need MAVLink 2 (MissionItemProtocol.cpp:41), which bm sends.
    # The outcome comes from the MISSION_ACK (MissionItemProtocol.cpp:38), see
    # handle_mission_ack: the FC can refuse, so nothing is reported until it answers.
    if link.mission._fence_pending:
        return {"ok": False, "error": lt("err_fence_busy", link.locale)}
    link.mission._fence_clear_pending = True
    link.mission._fence_clear_start_time = time.time()
    link.send(bm(45, bytes([link.vehicle.sysid, 1, 1]), link.sq, CRC_EXTRA[45]))


def cmd_mission_upload(link: DroneLink, param, data: dict):
    wps = data.get("waypoints", [])
    takeoff_alt = float(data.get("takeoff_alt", 30))
    if not wps:
        return {"ok": False, "error": lt("err_no_wp", link.locale)}
    if len(wps) > 500:
        return {"ok": False, "error": lt("err_mission_too_large", link.locale)}
    # ArduPlane rejects MAV_CMD_NAV_SPLINE_WAYPOINT with
    # MAV_MISSION_UNSUPPORTED (AP_Mission.cpp:1153-1158); the partial mission
    # would be discarded. Reject the whole upload here so the user gets a
    # clear error rather than a confusing FC ack failure.
    if link.is_plane() and any(wp.get("type") == "spline" for wp in wps):
        return {"ok": False, "error": lt("err_spline_plane", link.locale)}
    # Sub::start_command refuses a waypoint above home (ArduSub/commands_logic.cpp:13), so
    # the upload would read as a success and the vehicle would never dive. NAV_TAKEOFF
    # means nothing there, and a positive altitude on it only earns the same warning.
    if link.vehicle_kind() == "sub":
        takeoff_alt = 0.0
        if any(float(wp.get("alt") or 0) > 0 for wp in wps):
            return {"ok": False, "error": lt("err_sub_depth", link.locale)}
    for wp in wps:
        try:
            lat, lon = float(wp.get("lat", 0)), float(wp.get("lon", 0))
        except (TypeError, ValueError):
            return {"ok": False, "error": lt("err_bad_coord", link.locale)}
        if abs(lat) < 0.001 or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            return {"ok": False, "error": lt("err_bad_coord", link.locale)}
        try:
            alt = float(wp.get("alt", 0))
        except (TypeError, ValueError):
            return {"ok": False, "error": lt("err_bad_coord", link.locale)}
        if not (-500 <= alt <= 100000):
            return {"ok": False, "error": lt("err_bad_coord", link.locale)}
    _upload_mission(link, wps, takeoff_alt)


def cmd_fence_upload(link: DroneLink, param, data: dict):
    # An ack carries only the store's type, so the clear's would finish this upload.
    # STORE_CLEAR_TIMEOUT ends a clear the FC never answers.
    if link.mission._fence_clear_pending:
        return {"ok": False, "error": lt("err_clear_busy", link.locale)}
    polygon = data.get("polygon", [])
    if len(polygon) < 3 or len(polygon) > 200:
        return {"ok": False, "error": lt("err_fence_min", link.locale)}
    items = []
    for i, pt in enumerate(polygon):
        items.append(
            {
                "seq": i,
                "cmd": 5001,
                "lat": pt["lat"],
                "lon": pt["lon"],
                "alt": 0,
                "p1": len(polygon),
                "p2": 0,
            }
        )
    link.mission._fence_items = items
    link.mission._fence_pending = True
    link.mission._fence_ul_start_time = time.time()
    send_fence_count(link, len(items))
    link.add_event(lt("fence_upload", link.locale) % len(polygon), "fence_upload")


def cmd_mission_download(link: DroneLink, param, data: dict):
    link.mission._dl_pending = True
    link.mission._dl_total = 0
    link.mission._dl_items = []
    link.mission._dl_start_time = time.time()
    link.add_event(lt("mission_dl", link.locale), "mission_dl")
    link.send(bm(43, struct.pack("<BBB", link.vehicle.sysid, 1, 0), link.sq, CRC_EXTRA[43]))


def check_mission_dl_timeout(link: DroneLink) -> None:
    m = link.mission
    now = time.time()
    timeout = cfg.MISSION_DL_TIMEOUT
    if m._dl_pending and m._dl_start_time > 0:
        if now - m._dl_start_time > timeout:
            m._dl_pending = False
            m._dl_start_time = 0.0
            link.add_event(lt("mission_dl_timeout", link.locale), "mission_dl_timeout")
    # Upload watchdogs: if the FC never requests the next item, the pending
    # flag would zombie forever (and a follow-up upload would be misrouted).
    if m._mission_pending and m._mission_ul_start_time > 0 and now - m._mission_ul_start_time > timeout:
        m._mission_pending = False
        m._mission_ul_start_time = 0.0
        link.add_event(lt("mission_ack_fail", link.locale) % 99, "mission_ack_fail")
    if m._fence_pending and m._fence_ul_start_time > 0 and now - m._fence_ul_start_time > timeout:
        m._fence_pending = False
        m._fence_ul_start_time = 0.0
        link.add_event(lt("fence_ack_fail", link.locale) % 99, "fence_ack_fail")
    if m._rally_pending and m._rally_ul_start_time > 0 and now - m._rally_ul_start_time > timeout:
        m._rally_pending = False
        m._rally_ul_start_time = 0.0
        link.add_event(lt("rally_ack_fail", link.locale) % 99, "rally_ack_fail")
    # A clear gets one MISSION_ACK or nothing: 99 is the same no-answer code as above.
    if m._fence_clear_pending and now - m._fence_clear_start_time > cfg.STORE_CLEAR_TIMEOUT:
        m._fence_clear_pending = False
        link.add_event(lt("fence_clear_fail", link.locale) % 99, "fence_clear_fail")
    if m._rally_clear_pending and now - m._rally_clear_start_time > cfg.STORE_CLEAR_TIMEOUT:
        m._rally_clear_pending = False
        link.add_event(lt("rally_clear_fail", link.locale) % 99, "rally_clear_fail")


def cmd_rally_upload(link: DroneLink, param, data: dict):
    if link.mission._rally_clear_pending:  # see cmd_fence_upload
        return {"ok": False, "error": lt("err_clear_busy", link.locale)}
    points = data.get("points", [])
    if not points:
        return None
    # The FC refuses these one item in (MissionItemProtocol_Rally.cpp:63-66 for the
    # coordinates, :69 for an altitude outside int16), so catch them before starting.
    for pt in points:
        lat, lon, alt = float(pt.get("lat", 0)), float(pt.get("lon", 0)), float(pt.get("alt", 100))
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180) or not (-32768 <= alt <= 32767):
            return {"ok": False, "error": lt("err_bad_coord", link.locale)}
    _upload_rally(link, points)
    return None


def cmd_rally_clear(link: DroneLink, param, data: dict):
    # MISSION_CLEAR_ALL with mission_type=2 (MAV_MISSION_TYPE_RALLY): AP routes it by
    # type (GCS_Common.cpp:805) and truncates the store (MissionItemProtocol_Rally.cpp:52).
    # As with the fence, nothing is reported until the FC's MISSION_ACK says so
    # (MissionItemProtocol.cpp:38), see handle_mission_ack.
    if link.mission._rally_pending:
        return {"ok": False, "error": lt("err_rally_busy", link.locale)}
    link.mission._rally_clear_pending = True
    link.mission._rally_clear_start_time = time.time()
    link.send(bm(45, bytes([link.vehicle.sysid, 1, 2]), link.sq, CRC_EXTRA[45]))


def _upload_mission(link: DroneLink, waypoints: list, takeoff_alt: float) -> None:
    items = []
    items.append({"seq": 0, "cmd": 16, "lat": 0, "lon": 0, "alt": 0, "p1": 0, "p2": 0})
    items.append({"seq": 1, "cmd": 22, "lat": 0, "lon": 0, "alt": takeoff_alt, "p1": 0, "p2": 0})
    seq = 2
    for wp in waypoints:
        spd = float(wp.get("speed", 0))
        if spd > 0:
            items.append({"seq": seq, "cmd": 178, "lat": 0, "lon": 0, "alt": 0, "p1": 1, "p2": spd})
            seq += 1
        wtype = wp.get("type", "wp")
        if wtype == "loiter_turns":
            nav_cmd = 18
            p1_val = float(wp.get("loiter_param", 3))
        elif wtype == "loiter_time":
            nav_cmd = 19
            p1_val = float(wp.get("loiter_param", 10))
        elif wtype == "spline":
            nav_cmd = 82
            p1_val = float(wp.get("delay", 0))
        else:
            nav_cmd = 16
            p1_val = float(wp.get("delay", 0))
        items.append(
            {
                "seq": seq,
                "cmd": nav_cmd,
                "lat": float(wp["lat"]),
                "lon": float(wp["lon"]),
                "alt": float(wp.get("alt", takeoff_alt)),
                "p1": p1_val,
                "p2": 0,
            }
        )
        seq += 1
        servo = wp.get("cmd_servo")
        if servo:
            items.append(
                {
                    "seq": seq,
                    "cmd": 183,
                    "lat": 0,
                    "lon": 0,
                    "alt": 0,
                    "p1": int(servo.get("num", 1)),
                    "p2": float(servo.get("pwm", 1500)),
                }
            )
            seq += 1
        roi = wp.get("cmd_roi")
        if roi:
            items.append(
                {
                    "seq": seq,
                    "cmd": 201,
                    "lat": float(roi.get("lat", 0)),
                    "lon": float(roi.get("lon", 0)),
                    "alt": float(roi.get("alt", 0)),
                    "p1": 0,
                    "p2": 0,
                }
            )
            seq += 1
        cam = wp.get("cmd_cam_trig")
        if cam:
            items.append(
                {"seq": seq, "cmd": 206, "lat": 0, "lon": 0, "alt": 0, "p1": float(cam.get("dist", 0)), "p2": 0}
            )
            seq += 1
        yaw = wp.get("cmd_yaw")
        if yaw:
            items.append(
                {
                    "seq": seq,
                    "cmd": 115,
                    "lat": 0,
                    "lon": 0,
                    "alt": 0,
                    "p1": float(yaw.get("deg", 0)),
                    "p2": 0,
                    "p3": float(yaw.get("dir", 1)),
                    "p4": 0,
                }
            )
            seq += 1
        vtol = wp.get("cmd_vtol")
        if vtol:
            items.append(
                {"seq": seq, "cmd": 3000, "lat": 0, "lon": 0, "alt": 0, "p1": int(vtol.get("mode", 4)), "p2": 0}
            )
            seq += 1
        if wp.get("drop"):
            items.append({"seq": seq, "cmd": 181, "lat": 0, "lon": 0, "alt": 0, "p1": 0, "p2": 0})
            seq += 1
    # Sub cannot run RTL as an item, whatever frame it arrives in: it is not stored with a
    # location (AP_Mission.cpp:897), so Sub::start_command reads an absolute frame and answers
    # "Bad alt frame" (ArduSub/commands_logic.cpp:13). Its mission ends in a loiter by itself.
    if link.vehicle_kind() != "sub":
        items.append({"seq": seq, "cmd": 20, "lat": 0, "lon": 0, "alt": 0, "p1": 0, "p2": 0})
    m = link.mission
    m._mission_items = items
    m._seq_to_wp = {}
    s2 = 2
    for i, wp in enumerate(waypoints):
        if float(wp.get("speed", 0)) > 0:
            s2 += 1
        m._seq_to_wp[s2] = i
        s2 += 1
        if wp.get("cmd_servo"):
            s2 += 1
        if wp.get("cmd_roi"):
            s2 += 1
        if wp.get("cmd_cam_trig"):
            s2 += 1
        if wp.get("cmd_yaw"):
            s2 += 1
        if wp.get("cmd_vtol"):
            s2 += 1
        if wp.get("drop"):
            s2 += 1
    m._mission_pending = True
    m._mission_ul_start_time = time.time()
    send_mission_count(link, len(items))
    drop_n = sum(1 for w in waypoints if w.get("drop"))
    link.add_event(lt("mission_upload", link.locale) % (len(waypoints), drop_n, takeoff_alt))


def _upload_rally(link: DroneLink, points: list) -> None:
    # AP_Mission requires the GCS to follow the proper request/response
    # handshake: COUNT -> wait for REQUEST -> ITEM -> ... -> ACK. The previous
    # implementation blasted all items immediately after COUNT, which AP
    # rejected as MAV_MISSION_INVALID_SEQUENCE. Stash items on the link and
    # let handle_mission_request stream them out one at a time.
    items: list[dict] = []
    for i, pt in enumerate(points):
        items.append(
            {
                "seq": i,
                "cmd": 5100,  # MAV_CMD_NAV_RALLY_POINT
                "lat": float(pt.get("lat", 0)),
                "lon": float(pt.get("lon", 0)),
                "alt": float(pt.get("alt", 100)),
                "p1": 0,
                "p2": 0,
            }
        )
    m = link.mission
    m._rally_items = items
    m._rally_pending = True
    m._rally_ul_start_time = time.time()
    count = len(items)
    link.send(bm(44, struct.pack("<HBB", count, link.vehicle.sysid, 1) + bytes([2]), link.sq, CRC_EXTRA[44]))
    link.add_event(lt("rally_uploading", link.locale) % count, "rally_uploading")
