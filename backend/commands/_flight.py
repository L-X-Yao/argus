from __future__ import annotations

from typing import TYPE_CHECKING

from ..locale_text import lt
from ._helpers import send_cmd, send_set_mode

if TYPE_CHECKING:
    from ..drone_link import DroneLink


def cmd_arm(link: DroneLink, param, data: dict):
    link.add_event(lt("arm_send", link.locale), "arm_send")
    send_cmd(link, 400, p1=1.0)


def cmd_disarm(link: DroneLink, param, data: dict):
    link.add_event(lt("disarm_send", link.locale), "disarm_send")
    send_cmd(link, 400, p1=0)


def cmd_force_disarm(link: DroneLink, param, data: dict):
    link.add_event(lt("force_disarm", link.locale), "force_disarm")
    send_cmd(link, 400, p1=0, p2=21196)


def cmd_rtl(link: DroneLink, param, data: dict):
    # Plane RTL = mode 11 (standard NAV_RTL); mode 21 is Q-RTL (QuadPlane only).
    # ArduPilot ArduPlane/mode.h `enum class Number`: RTL=11, QRTL=21.
    # On QuadPlane with Q_RTL_MODE=1 the FC promotes RTL→QRTL within RTL_RADIUS of home automatically.
    rm = link.special_mode("rtl")
    if rm is None:
        return {"ok": False, "error": lt("err_no_rtl", link.locale)}
    link.add_event(lt("rtl", link.locale) % rm, "rtl")
    send_set_mode(link, rm)


def cmd_mode(link: DroneLink, param, data: dict):
    if param is None:
        return None
    md = link._get_vehicle_info()[0]
    link.add_event(lt("mode_to", link.locale) % md.get(int(param), str(param)), "mode_to")
    send_set_mode(link, int(param))


def cmd_takeoff(link: DroneLink, param, data: dict):
    alt = float(data.get("alt", 30))
    if not 1 <= alt <= 1000:
        return {"ok": False, "error": lt("err_bad_coord", link.locale)}
    # GUIDED first, on what can take off. QuadPlane.do_user_takeoff (quadplane.cpp:3948)
    # refuses MAV_CMD_NAV_TAKEOFF outside it. Copter takes it in a few modes only
    # (ArduCopter/takeoff.cpp:27 has_user_takeoff): not in STABILIZE, which it boots in, and
    # in LOITER a stick left low brings it straight back down. There is no button for GUIDED.
    # On the ground only: in the air it refuses the takeoff (takeoff.cpp:23), and the switch
    # alone would stop an AUTO, an RTL or a LAND where it is.
    kind = link.vehicle_kind()
    if kind == "plane" or (kind == "copter" and link.vehicle.landed):
        send_set_mode(link, link.special_mode("guided"))
    link.add_event(lt("takeoff", link.locale) % alt, "takeoff")
    send_cmd(link, 22, p7=alt)


def cmd_drop(link: DroneLink, param, data: dict):
    # MAV_CMD_DO_SET_RELAY (181): p1=relay instance, p2=state. AP source:
    # GCS_Common.cpp:5848 → AP_ServoRelayEvents::do_set_relay
    # (AP_ServoRelayEvents.cpp:70). Drop rig on relay 0, active-low.
    link.add_event(lt("drop_on", link.locale), "drop_on")
    send_cmd(link, 181, p1=0, p2=0)


def cmd_drop_stop(link: DroneLink, param, data: dict):
    link.add_event(lt("drop_off", link.locale), "drop_off")
    send_cmd(link, 181, p1=0, p2=1)
