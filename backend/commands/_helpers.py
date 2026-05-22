from __future__ import annotations

import struct
import time
from typing import TYPE_CHECKING

from ..config import cfg
from ..pllink_proto import bm

if TYPE_CHECKING:
    from ..drone_link import DroneLink


def send_cmd(link: DroneLink, command: int, p1=0, p2=0, p3=0, p4=0, p5=0, p6=0, p7=0) -> None:
    payload = struct.pack('<fffffffHBBB', float(p1), float(p2), float(p3), float(p4),
                          float(p5), float(p6), float(p7), command, link.vehicle.sysid, 1, 0)
    link.send(bm(76, payload, link.sq, 152))


def send_set_mode(link: DroneLink, mode: int) -> None:
    payload = struct.pack('<IBB', mode, link.vehicle.sysid, 0x01)
    link.send(bm(11, payload, link.sq, 89))


def send_mission_count(link: DroneLink, count: int) -> None:
    link.send(bm(44, struct.pack('<HBB', count, link.vehicle.sysid, 1) + bytes([0]), link.sq, 221))


def send_fence_count(link: DroneLink, count: int) -> None:
    link.send(bm(44, struct.pack('<HBB', count, link.vehicle.sysid, 1) + bytes([1]), link.sq, 221))


def send_fence_item_int(link: DroneLink, item: dict) -> None:
    lat7 = int(float(item.get('lat', 0)) * 1e7)
    lon7 = int(float(item.get('lon', 0)) * 1e7)
    p = struct.pack('<ffffiifHHBBBBBB',
                    float(item.get('p1', 0)), float(item.get('p2', 0)), 0.0, 0.0,
                    lat7, lon7, float(item.get('alt', 0)),
                    item['seq'], item['cmd'],
                    link.vehicle.sysid, 1, 3,
                    0, 1, 1)
    link.send(bm(73, p, link.sq, 38))


def send_mission_item_int(link: DroneLink, wp: dict) -> None:
    frame = 3 if wp['cmd'] in (16, 19, 21, 22, 82) else 2
    lat7 = int(float(wp.get('lat', 0)) * 1e7)
    lon7 = int(float(wp.get('lon', 0)) * 1e7)
    p = struct.pack('<ffffiifHHBBBBBB',
                    float(wp.get('p1', 0)), float(wp.get('p2', 0)), 0.0, 0.0,
                    lat7, lon7, float(wp.get('alt', 0)),
                    wp['seq'], wp['cmd'],
                    link.vehicle.sysid, 1, frame,
                    1 if wp['seq'] == 0 else 0, 1, 0)
    link.send(bm(73, p, link.sq, 38))


def send_serial_control(link: DroneLink, text: str) -> None:
    data = (text + '\n').encode('ascii', 'replace')[:70]
    flags = 0x06
    p = struct.pack('<BBHB', 10, flags, 0, len(data))
    p += data + b'\x00' * (70 - len(data))
    link.send(bm(126, p, link.sq, 220))


def send_heartbeat(link: DroneLink) -> None:
    payload = struct.pack('<IBBBBB', 0, 6, 8, 0, 0, 3)
    link.send(bm(0, payload, link.sq, 50))


def request_streams(link: DroneLink) -> None:
    streams = [
        (30, 250000), (33, 250000), (24, 250000),
        (1, 1000000), (42, 1000000),
        (36, 500000), (65, 500000), (241, 1000000),
        (74, 1000000),
    ]
    for mid, interval in streams:
        payload = struct.pack('<fffffffHBBB',
                              float(mid), float(interval), 0, 0, 0, 0, 0,
                              511, link.vehicle.sysid, 1, 0)
        link.send(bm(76, payload, link.sq, 152))
        time.sleep(cfg.STREAM_REQUEST_SPACING)
    send_cmd(link, 512, p1=148.0)
