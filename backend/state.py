from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AttitudeState:
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    lat: float = 0.0
    lon: float = 0.0
    alt_rel: float = 0.0
    alt_msl: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    gs: float = 0.0
    hdg: float = 0.0
    home_lat: float = 0.0
    home_lon: float = 0.0
    dist_home: float = 0.0
    _prev_pos: tuple | None = None


@dataclass
class BatteryState:
    voltage: float = 0.0
    current: float = 0.0
    remaining: int = -1
    _bat_history: list[tuple[float, int]] = field(default_factory=list)
    bat_time_remaining: int = -1
    _bat_start_pct: int = -1
    battery_cells: list[float] = field(default_factory=list)


@dataclass
class GpsState:
    gps_fix: int = 0
    gps_sats: int = 0


@dataclass
class VehicleState:
    mode: int = 0
    armed: bool = False
    armed_time: float = 0.0
    vtype_raw: int = 0
    force_plane: bool | None = None
    sysid: int = 1
    fw_version: str = ''
    fw_git: str = ''
    board_id: int = 0
    flight_summary: dict | None = None
    max_alt: float = 0.0
    max_speed: float = 0.0
    total_dist: float = 0.0


@dataclass
class MissionState:
    wp_seq: int = 0
    _mission_items: list[dict] = field(default_factory=list)
    _mission_pending: bool = False
    _seq_to_wp: dict[int, int] = field(default_factory=dict)
    _fence_items: list[dict] = field(default_factory=list)
    _fence_pending: bool = False
    _dl_pending: bool = False
    _dl_total: int = 0
    _dl_items: list = field(default_factory=list)
    _dl_messages: list[dict] = field(default_factory=list)


@dataclass
class DiagnosticState:
    vibe_x: float = 0.0
    vibe_y: float = 0.0
    vibe_z: float = 0.0
    vibe_clip0: int = 0
    vibe_clip1: int = 0
    vibe_clip2: int = 0
    ekf_vel_var: float = 0.0
    ekf_pos_h_var: float = 0.0
    ekf_pos_v_var: float = 0.0
    ekf_compass_var: float = 0.0
    ekf_terrain_var: float = 0.0
    ekf_flags: int = 0
    wind_dir: float = 0.0
    wind_speed: float = 0.0
    terrain_alt: float = -1.0


@dataclass
class RcServoState:
    rc_channels: list[int] = field(default_factory=lambda: [0] * 16)
    rc_rssi: int = 0
    servo_out: list[int] = field(default_factory=lambda: [0] * 16)


@dataclass
class LogState:
    _log_list: list[dict] = field(default_factory=list)
    _log_download_id: int = -1
    _log_download_data: bytearray = field(default_factory=bytearray)
    _log_download_size: int = 0
    _log_download_ofs: int = 0
    _log_messages: list[dict] = field(default_factory=list)


@dataclass
class TrafficState:
    _adsb_vehicles: dict[int, dict] = field(default_factory=dict)
