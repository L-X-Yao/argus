# PL-Link GCS

A modern, web-based ground control station for autonomous vehicles.

## Features

| Feature | Description |
|---------|-------------|
| **Standard MAVLink** | Connect to any ArduPilot/PX4 vehicle via UDP, TCP, or serial |
| **Protocol Auto-detect** | Automatically identifies standard MAVLink or PL-Link framing |
| **Multi-vehicle** | Track and display multiple vehicles on the map simultaneously |
| **4 Vehicle Types** | Full support for Copter, Plane, Rover, and Sub with dedicated mode maps |
| **Bilingual UI** | Chinese/English locale switching — all panels, buttons, alerts, and audio |
| **Mission Planning** | Waypoints, circle patterns, survey grids, KML import/export, altitude profile |
| **Parameter Metadata** | Descriptions, ranges, units, enum values from upstream XML definitions |
| **Parameter Diff** | Instantly see which parameters differ from defaults, one-click reset |
| **Geofence** | Polygon geofence upload with map visualization |
| **Sensor Calibration** | Compass, accelerometer, gyroscope, level, barometer wizards |
| **PFD** | Primary Flight Display with attitude, speed/altitude tapes, compass, wind |
| **Real-time Charts** | Altitude, speed, vertical speed, voltage, current, vibration |
| **EKF Status** | Navigation filter variance bars and status flags |
| **Gamepad Control** | Joystick/gamepad via browser Gamepad API with RC override |
| **Audio Alerts** | Bilingual voice callouts for mode, battery, altitude, waypoints |
| **Video Overlay** | RTSP video feed with size presets |
| **Flight Report** | Post-flight summary with export |
| **Global Maps** | China (Amap/GCJ-02) and international (OSM/ArcGIS/WGS-84) tile sources |
| **PWA** | Installable web app with offline-capable architecture |
| **Dark Mode** | Full dark/light theme with optimized map tile rendering |
| **Log Download** | Browse, download, and replay onboard flight logs |

## Quick Start

### Browser (development)

```bash
# Install dependencies
npm install
pip install -r requirements.txt  # or: pip install fastapi uvicorn pyserial

# Start
python run.py --sim   # backend + simulator
# Open http://localhost:8100
```

### Windows Package (zero-install)

```bash
python build_package.py
# Output: release/PLLink_GCS_v3.1.zip
# Extract → double-click "PL-Link地面站.bat"
```

### Connect to SITL

```bash
# Start ArduPilot SITL
sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550

# In GCS: type "udp:14550" → select "Standard" protocol → Connect
# Or click the "SITL" quick-connect button
```

## Architecture

```
Browser (Svelte 5 + TypeScript + Tailwind)
    ↕ WebSocket (JSON)
Python Backend (FastAPI + uvicorn)
    ↕ MAVLink v2 (TCP/UDP/Serial)
Flight Controller
```

- **Frontend**: 33 Svelte 5 components + 6 composable map layers, 335KB JS (gzip 103KB)
- **Backend**: 15 Python modules, MAVLink dispatch + handler architecture
- **Tests**: 216 automated tests (unit + integration)
- **i18n**: 345+ bilingual string pairs, locale-aware backend events

## Connection Types

| Type | Format | Example |
|------|--------|---------|
| TCP | `tcp:host:port` | `tcp:localhost:5770` |
| UDP | `udp:port` | `udp:14550` |
| Serial | `/dev/ttyUSB0` or `COM3` | `/dev/ttyUSB0` |

Protocol (Standard MAVLink or PL-Link) is auto-detected from the first received bytes.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /api/version` | Version, protocols, vehicles, features |
| `GET /api/ports` | Available serial ports |
| `GET /api/param_meta?vehicle=copter` | Parameter metadata (cached from upstream XML) |
| `GET /api/tile_sources` | Available map tile configurations |
| `GET /api/tile/{style}/{z}/{x}/{y}` | Tile proxy with disk cache |
| `GET /api/log` | Download active connection log (CSV) |
| `WS /ws` | WebSocket for telemetry, commands, events |

## Tech Stack

- **Frontend**: Svelte 5 (runes), TypeScript, Vite, Tailwind CSS, shadcn/ui, Leaflet
- **Backend**: Python, FastAPI, uvicorn, pyserial
- **Protocol**: MAVLink v2 (standard + PL-Link wrapper)
- **Tests**: pytest, Playwright (screenshots), httpx

## License

Proprietary — PengLiKeJi Technology Co., Ltd.
