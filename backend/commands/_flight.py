from __future__ import annotations

from typing import TYPE_CHECKING

from ..locale_text import lt
from ._helpers import send_cmd, send_set_mode

if TYPE_CHECKING:
    from ..drone_link import DroneLink


def cmd_arm(link: DroneLink, param, data: dict):
    link.add_event(lt('arm_send', link.locale), 'arm_send')
    send_cmd(link, 400, p1=1.0)


def cmd_disarm(link: DroneLink, param, data: dict):
    link.add_event(lt('disarm_send', link.locale), 'disarm_send')
    send_cmd(link, 400, p1=0)


def cmd_force_disarm(link: DroneLink, param, data: dict):
    link.add_event(lt('force_disarm', link.locale), 'force_disarm')
    send_cmd(link, 400, p1=0, p2=21196)


def cmd_rtl(link: DroneLink, param, data: dict):
    rm = 21 if link.is_plane() else 6
    link.add_event(lt('rtl', link.locale) % rm, 'rtl')
    send_set_mode(link, rm)


def cmd_mode(link: DroneLink, param, data: dict):
    if param is None:
        return None
    from ..constants import COPTER_MODES, PLANE_MODES
    md = PLANE_MODES if link.is_plane() else COPTER_MODES
    link.add_event(lt('mode_to', link.locale) % md.get(int(param), str(param)), 'mode_to')
    send_set_mode(link, int(param))


def cmd_takeoff(link: DroneLink, param, data: dict):
    alt = float(data.get('alt', 30))
    if not 1 <= alt <= 1000:
        return {'ok': False, 'error': 'Takeoff altitude must be 1-1000m'}
    link.add_event(lt('takeoff', link.locale) % alt, 'takeoff')
    send_cmd(link, 22, p7=alt)


def cmd_drop(link: DroneLink, param, data: dict):
    link.add_event(lt('drop_on', link.locale), 'drop_on')
    send_cmd(link, 181, p1=0, p2=0)


def cmd_drop_stop(link: DroneLink, param, data: dict):
    link.add_event(lt('drop_off', link.locale), 'drop_off')
    send_cmd(link, 181, p1=0, p2=1)
