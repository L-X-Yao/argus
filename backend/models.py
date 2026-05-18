from __future__ import annotations
from pydantic import BaseModel


class DroneState(BaseModel):
    connected: bool = False
    frames: int = 0
    mode: str = '---'
    mode_id: int = 0
    armed: bool = False
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    lat: float = 0.0
    lon: float = 0.0
    alt_rel: float = 0.0
    alt_msl: float = 0.0
    gs: float = 0.0
    vz: float = 0.0
    hdg: float = 0.0
    dist_home: float = 0.0
    flight_time: int = 0
    voltage: float = 0.0
    current: float = 0.0
    remaining: int = -1
    gps_fix: str = '---'
    gps_sats: int = 0
    wp: int = 0
    vtype: str = ''
    vtype_raw: int = 0
    mode_btns: list = []
    link_age: float = -1.0
    bat_time: int = -1
    home_lat: float = 0.0
    home_lon: float = 0.0
    parse_errors: int = 0


class Event(BaseModel):
    time: str
    text: str
