# Argus

Universal web-based ground control station for MAVLink drones.

## Vision

Argus aims to be the first truly universal **web GCS** — one interface that works with any MAVLink vehicle (ArduPilot, PX4), on any platform (browser, desktop, tablet), in any language (10 supported). No install, no native dependencies, just open a URL and fly.

### Why another GCS?

| Existing GCS | Limitation |
|---|---|
| QGroundControl | Native app, heavy install, no web version |
| Mission Planner | Windows-only, legacy UI |
| Cloud platforms (FlytBase, ADOS) | Vendor lock-in, closed source |

Argus fills the gap: **open-source + web-native + protocol-agnostic + white-label ready**.

## Features

| Category | Features |
|---|---|
| **Connections** | TCP / UDP / Serial / WebSerial (browser-direct USB) |
| **Protocols** | ArduPilot + PX4 (auto-detect via FC adapter layer) |
| **Vehicles** | Copter, Plane, VTOL, Rover, Sub |
| **Map** | 8 tile sources (Amap, Google, OSM, Esri, CartoDB, Tianditu) + 3D terrain (MapLibre GL) |
| **Mission** | WP / Spline / Loiter / Survey grid / Crosshatch / Spiral / Orbit |
| **Formats** | .waypoints (MP) / .plan (QGC) / .gpx / .kml import & export |
| **Parameters** | Metadata (desc/range/units/enum/bitmask), tree view, diff export, default reset |
| **Calibration** | Compass, accel, gyro, level, baro wizards |
| **Firmware** | Upload .apj, online firmware browser, reboot to bootloader |
| **RTK** | NTRIP client panel with fix status display |
| **Fleet** | Multi-vehicle dashboard with live telemetry per vehicle |
| **Video** | RTSP → MJPEG proxy, screenshot capture |
| **HUD** | PFD (attitude/speed/altitude/compass/wind), real-time charts, EKF status |
| **Audio** | Bilingual voice callouts (mode, battery, altitude, waypoints) |
| **i18n** | 10 languages (zh, en, ja, ko, de, fr, es, pt, ru, ar) + RTL |
| **Offline** | PWA with service worker, mbtiles support, tile caching |
| **Desktop** | Tauri v2 packaging (Windows MSI/NSIS installer) |
| **Security** | Token auth, statustext filtering (hides ArduPilot internals) |

## Quick Start

### 1. Browser (development)

```bash
# Frontend
npm install
npm run dev          # http://localhost:5173

# Backend
pip install fastapi uvicorn pyserial websockets
python run.py        # API at http://localhost:8100
```

### 2. With simulator

```bash
python scripts/sim_pllink.py 5770  # Start MAVLink simulator
python run.py                      # Start backend
npm run dev                        # Start frontend
# Browser → type "tcp:localhost:5770" → Connect
```

### 3. With ArduPilot SITL

```bash
sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550
# In Argus: type "udp:14550" → protocol "Standard" → Connect
# Or click the "SITL" quick-connect button
```

### 4. WebSerial (no backend needed)

Open Argus in Chrome/Edge → click the **USB** button → select your flight controller from the browser prompt. Telemetry flows directly via WebSerial + the built-in TypeScript MAVLink v2 codec.

### 5. Production build

```bash
npm run build        # Output: dist/
python run.py        # Serves dist/ + API on :8100
```

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
│  23 modules, 3.5K lines                │
│  MAVLink dispatch + 27 message handlers │
│  46 commands, tile/video/firmware API   │
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
| `src/lib/fc/` | Flight controller adapter (ArduPilot + PX4 mode/command mapping) |
| `src/lib/transport.ts` | Dual-mode transport (WebSocket backend vs WebSerial direct) |
| `src/lib/serial.ts` | Web Serial API wrapper with FC USB vendor filters |
| `src/lib/terrain.ts` | SRTM elevation queries for terrain-following missions |
| `src/lib/missionIO.ts` | Mission import/export (.waypoints / .plan / .gpx) |
| `src/lib/survey.ts` | Survey patterns (grid, crosshatch, spiral, orbit) |
| `src/lib/i18n.svelte.ts` | 10-language i18n with RTL support |
| `backend/drone_link.py` | MAVLink connection, frame parsing, state management |
| `backend/commands/` | 46 command handlers (arm, mode, mission, calibration, gimbal, etc.) |
| `backend/config.py` | Centralized configuration (all timeouts/ports/rates) |

## Simulator

`scripts/sim_pllink.py` is a MAVLink vehicle simulator for development and testing:

```bash
python scripts/sim_pllink.py 5770           # TCP, standard MAVLink
python scripts/sim_pllink.py 5770 --pllink  # TCP, PL-Link wrapped
python scripts/sim_pllink.py 14550 --udp    # UDP
```

It generates realistic telemetry: GPS position (Xi'an), attitude, battery drain, heartbeat, and responds to arm/disarm/mode commands.

## Tests

```bash
# Backend unit tests (929 tests)
python -m pytest tests/test_unit_*.py -v

# Frontend unit tests (400 tests)
npx vitest run

# Type check (0 errors, 0 warnings)
npx svelte-check --tsconfig ./tsconfig.json

# Python lint
ruff check backend/ scripts/ tests/

# E2E (requires dev server)
npx playwright test
```

## Build Stats

| Metric | Value |
|---|---|
| Frontend components | 144 |
| Frontend lines | 21,000 |
| Backend modules | 23 |
| Backend lines | 3,500 |
| MAVLink handlers | 27 |
| Commands | 46 |
| Tests | 1,329 (929 pytest + 400 vitest) |
| Languages | 10 |
| Bundle (main) | 207 KB (65 KB gzip) |
| Bundle (3D map) | 1,028 KB (lazy loaded) |
| Tile sources | 8 |
| Mission formats | 4 (.waypoints, .plan, .gpx, .kml) |

## Roadmap

- [ ] WebSerial command routing (mission upload, param management via browser USB)
- [ ] 3D map feature parity with 2D (waypoint editing, fences, measurement)
- [ ] WebRTC video streaming (replace RTSP→MJPEG proxy)
- [ ] MQTT cloud relay for fleet management
- [ ] MAVLink FTP for firmware upload and Lua script management
- [ ] MSP protocol support (BetaFlight / iNav)

## License

MIT
