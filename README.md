# Argus

> Universal web-based ground control station for MAVLink drones.

[![CI](https://github.com/L-X-Yao/argus/actions/workflows/ci.yml/badge.svg)](https://github.com/L-X-Yao/argus/actions/workflows/ci.yml)
![Version](https://img.shields.io/badge/version-3.4.0-blue.svg)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Tests](https://img.shields.io/badge/tests-1480%20passing-brightgreen.svg)
![i18n](https://img.shields.io/badge/i18n-10%20languages-orange.svg)

<!-- TODO: add a hero screenshot (map + HUD + telemetry overlay).
     Drop a PNG at docs/screenshots/hero.png and uncomment the line below.
<p align="center"><img src="docs/screenshots/hero.png" alt="Argus screenshot" width="900"></p>
-->

## What & Why

Argus is a universal **web GCS** — one browser interface for MAVLink drones, on any platform (desktop, tablet, mobile), in 10 languages. No install, no native dependencies, just open a URL and fly.

> **Status**: ArduPilot is production-tested today. PX4 has frontend adapter scaffolding in `src/lib/fc/` but is not yet wired end-to-end — see `CLAUDE.md ## PX4 Status`.

Why another GCS:

| Existing GCS | Limitation |
|---|---|
| QGroundControl | Native app, heavy install, no first-class web build |
| Mission Planner | Windows-only, legacy UI |
| Cloud platforms (FlytBase, ADOS) | Vendor lock-in, closed source |

Argus fills the gap: **open-source + web-native + protocol-agnostic + white-label ready**.

## Features

| Category | Features |
|---|---|
| **Connections** | TCP / UDP / Serial / WebSerial (browser-direct USB, no backend needed for telemetry + basic control) |
| **Protocols** | MAVLink v2 (ArduPilot production-tested; PX4 adapter scaffolded, unwired) |
| **Vehicles** | Copter, Plane, VTOL, Rover, Sub |
| **Map** | 8 tile sources (Amap, Google, OSM, Esri, CartoDB, Tianditu) + 3D terrain (MapLibre GL) + offline mbtiles |
| **Mission** | WP / Spline / Loiter / Survey grid / Crosshatch / Spiral / Orbit |
| **Formats** | `.waypoints` (MP) / `.plan` (QGC) / `.gpx` / `.kml` import & export |
| **Parameters** | Metadata-driven UI (desc/range/units/enum/bitmask), tree view, diff export, default reset |
| **Calibration** | Compass, accel, gyro, level, baro wizards with real-time progress |
| **RTK** | NTRIP client with HTTP/1.0 + ICY-200 negotiation, streaming RTCM injection |
| **Firmware** | Upload `.apj`, online firmware browser, reboot to bootloader |
| **Fleet** | Multi-vehicle dashboard with live telemetry per vehicle |
| **Video** | RTSP → MJPEG proxy, AR waypoint overlay, screenshot capture |
| **HUD** | PFD (attitude/speed/altitude/compass/wind), real-time charts, EKF status |
| **Audio** | Bilingual voice callouts (mode, battery, altitude, waypoints) |
| **i18n** | 10 languages (zh, en, ja, ko, de, fr, es, pt, ru, ar) + RTL |
| **Offline** | PWA with service worker, mbtiles support, tile caching (5000-entry LRU) |
| **Desktop** | Tauri v2 packaging (Windows MSI/NSIS installer) |
| **Security** | Token auth, SSRF + path-traversal guards, statustext filtering |

## Quick Start

One-time setup:

```bash
npm install        # Frontend dependencies
pip install -e .   # Backend (uses pyproject.toml — pulls all required deps)
```

### Option 1 — Real hardware (USB to Pixhawk)

```bash
python run.py                  # Backend at http://localhost:8100
# In another shell:
npm run dev                    # Dev server at http://localhost:5173
# Open the URL, plug in USB, pick your serial port from the dropdown
```

For production: `npm run build` builds the bundle into `dist/`, then `python run.py` serves it on `:8100`.

### Option 2 — ArduPilot SITL

```bash
sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550
python run.py
# Open the UI, click the "SITL" quick-connect button
```

### Option 3 — Built-in MAVLink simulator (no FC, no SITL)

```bash
python run.py --sim            # Starts backend + sim_pllink.py together
# Connect to "tcp:localhost:5770"
```

The simulator (`scripts/sim_pllink.py`) emits realistic telemetry (GPS at Xi'an, attitude, battery drain, heartbeat) and responds to arm/disarm/mode commands.

### WebSerial (no backend at all)

Open Argus in Chrome/Edge → click the **USB** button → pick your flight controller. Telemetry + arm/disarm/mode/RTL/param-read+write + **mission upload** flow directly via WebSerial and the built-in TypeScript MAVLink v2 codec. For mission download, calibration wizards, firmware upload, and log download, run the Python backend.

## Architecture

```
┌─────────────────────────────────────────┐
│  Browser (Svelte 5 + TypeScript 6)      │
│  144 components, 21K lines              │
│  MAVLink v2 codec (pure TS)             │
│  WebSerial direct USB connection        │
│  42 lazy-loaded panels + view splitting │
├─────────────────────────────────────────┤
│          ↕ WebSocket (JSON delta push)  │
├─────────────────────────────────────────┤
│  Python Backend (FastAPI + uvicorn)     │
│  24 modules, 3.5K lines                 │
│  MAVLink dispatch + 31 message handlers │
│  50 commands, tile/video/firmware API   │
├─────────────────────────────────────────┤
│          ↕ MAVLink v2                   │
│  TCP / UDP / Serial / PL-Link           │
├─────────────────────────────────────────┤
│  Flight Controller (ArduPilot / PX4)    │
└─────────────────────────────────────────┘
```

### Key modules

| Module | Description |
|---|---|
| `src/lib/mavlink/` | Pure TypeScript MAVLink v2 encoder/decoder with CRC validation |
| `src/lib/fc/` | Flight controller adapter (ArduPilot wired; PX4 mode tables exist but production code does not import them yet) |
| `src/lib/transport.ts` | Dual-mode transport (WebSocket backend vs WebSerial direct) |
| `src/lib/serial.ts` | Web Serial API wrapper with FC USB vendor filters |
| `src/lib/terrain.ts` | SRTM elevation queries for terrain-following missions |
| `src/lib/missionIO.ts` | Mission import/export (`.waypoints` / `.plan` / `.gpx`) |
| `src/lib/survey.ts` | Survey patterns (grid, crosshatch, spiral, orbit) |
| `src/lib/i18n.svelte.ts` | 10-language i18n with RTL support |
| `backend/drone_link.py` | MAVLink connection, frame parsing, state management |
| `backend/commands/` | 50 command handlers (arm, mode, mission, calibration, gimbal, NTRIP, etc.) |
| `backend/config.py` | Centralized configuration (all timeouts/ports/rates) |

## Development

```bash
# Backend unit + contract tests (1,037 tests)
python -m pytest tests/test_unit_*.py tests/test_contract_*.py -v

# Frontend unit tests (443 tests)
npx vitest run

# Type check (must be 0 errors, 0 warnings)
npx svelte-check --tsconfig ./tsconfig.json

# Python lint
ruff check backend/ scripts/ tests/

# E2E (requires dev server)
npx playwright test

# Production build
npm run build
```

**Deeper docs**:

- [`CLAUDE.md`](CLAUDE.md) — project conventions, PX4 status, protocol-coupling discipline (read this first if you're contributing FC-coupled code)
- [`docs/FEATURE_CHECKLIST.md`](docs/FEATURE_CHECKLIST.md) — single source of truth for feature verification status
- [`docs/protocol_design.md`](docs/protocol_design.md) — load-bearing design decisions (the "looks-wrong-but-is-correct" cases)
- [`docs/audits/`](docs/audits/) — archived audit reports

## Roadmap

**✅ Recently shipped**

- WebSerial direct USB connection (telemetry + arm/disarm/mode/RTL/param)
- WebSerial mission upload (MISSION_COUNT/REQUEST/ITEM/ACK state machine in transport.ts)
- NTRIP RTK client (HTTP/1.0 + ICY-200, RTCM streaming via msg 233)
- Compass / accel / gyro calibration with binary progress (MAG_CAL_PROGRESS / REPORT)
- Multi-language UI (10 locales + RTL)
- Tauri v2 desktop packaging
- Dual-transport mutex (WS backend ↔ WebSerial, defended at the store layer)
- Gimbal pitch/yaw via MAV_CMD_DO_GIMBAL_MANAGER_PITCHYAW (angle + rate + retract/neutral)

**🚧 In progress / partial**

- WebSerial command coverage expansion (calibration wizards, firmware, log download)
- 3D map feature parity with 2D (waypoint editing, fences, measurement)
- PX4 end-to-end wiring (frontend adapter exists; backend never reads HEARTBEAT.autopilot byte)
- Real-hardware verification sweep for the remaining calibration types (level, baro, simple-accel)

**📋 Future**

- WebRTC video streaming (replace RTSP → MJPEG proxy)
- MQTT cloud relay for fleet management
- MAVLink FTP for firmware upload and Lua script management
- MSP protocol support (BetaFlight / iNav)

## Contributing

Issues and PRs welcome. Before sending a PR:

1. Tests pass locally: `npx vitest run && python -m pytest tests/test_unit_*.py tests/test_contract_*.py`
2. Type check is clean: `npx svelte-check` (0 errors, 0 warnings)
3. Python lint is clean: `ruff check backend/ scripts/ tests/`
4. Use the commit convention from `CLAUDE.md`: `<type>: <imperative description>` (types: `feat`, `fix`, `refactor`, `test`, `docs`, `ci`, `chore`)
5. For flight-controller-coupled code (MAVLink commands, ACK handling, calibration handshakes), cite the upstream ArduPilot/PX4 source `file:line` in a comment — see `CLAUDE.md ## Protocol Code Discipline`. Unit tests that mock the FC will pass either way; only the real source pins the truth.

## Acknowledgments

Argus stands on the shoulders of:

- [ArduPilot](https://ardupilot.org/) — the flight controller firmware that defines the protocol semantics this GCS targets
- [pymavlink](https://github.com/ArduPilot/pymavlink) — reference MAVLink codec used to validate our pure-TS implementation
- [MAVLink](https://mavlink.io/) — the messaging protocol itself
- [Svelte](https://svelte.dev/), [FastAPI](https://fastapi.tiangolo.com/), [Leaflet](https://leafletjs.com/), [MapLibre GL](https://maplibre.org/), [Tauri](https://tauri.app/) — the application stack
- The MAVLink GCS that came before — QGroundControl, Mission Planner, MAVProxy — for showing what's possible and where there's room to do better on the web

## License

MIT — see [LICENSE](LICENSE).
