# Argus

[中文](README.zh.md) | **English**

> Web-based ground control station for ArduPilot vehicles.

[![CI](https://github.com/L-X-Yao/argus/actions/workflows/ci.yml/badge.svg)](https://github.com/L-X-Yao/argus/actions/workflows/ci.yml)
![Version](https://img.shields.io/github/v/tag/L-X-Yao/argus?label=version&color=blue)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Tests](https://img.shields.io/badge/tests-3000%2B%20passing-brightgreen.svg)
![i18n](https://img.shields.io/badge/i18n-10%20languages-orange.svg)

<p align="center"><img src="docs/screenshots/hero.png" alt="Argus GCS — map, HUD, and telemetry" width="900"></p>

## What & Why

Argus is a **web GCS** for ArduPilot: one browser interface on desktop, tablet and phone, in 10 languages. There is no hosted version: run the Python backend yourself, or unzip the Windows package (Python included), then open it in a browser.

> **Status**: ArduPilot is verified on ArduCopter SITL in CI and on a real flight controller on the bench, but Argus has not been through proper flight testing. [docs/VERIFICATION.md](docs/VERIFICATION.md) lists what has been tested and how, feature by feature. PX4 is not supported: a command for a PX4 vehicle is refused with an error.
>
> **Maintenance only since November 2026**: bugs and security problems get fixed, and no new features are planned. See [Project Status](#project-status).

Why another GCS: Argus runs in a browser tab, so the device in your hand needs nothing installed, and it can reach a flight controller straight over USB (WebSerial).

| Existing GCS | How it differs |
|---|---|
| [QGroundControl](https://qgroundcontrol.com/) | A native application to install on each device |
| [Mission Planner](https://ardupilot.org/planner/) | A Windows application |
| Cloud platforms such as FlytBase | Closed source, tied to one vendor |

To fly real missions today, use QGroundControl or Mission Planner: both are flight proven and actively developed, and Argus is neither.

## Features

| Category | Features |
|---|---|
| **Connections** | TCP / UDP / Serial / WebSerial (browser-direct USB, no backend needed for telemetry + basic control) |
| **Protocols** | MAVLink v2, ArduPilot only (verified on SITL and on the bench, not flight-tested) |
| **Vehicles** | Copter, Plane, VTOL, Rover, Sub |
| **Map** | 8 tile sources (Amap, Google, OSM, Esri, CartoDB; Tianditu with a key of your own), each under [its own terms](#map-data) + 3D terrain (MapLibre GL) + offline mbtiles |
| **Mission** | WP / Spline / Loiter / Survey grid / Crosshatch / Spiral / Orbit + terrain profile with clearance check |
| **Formats** | `.waypoints` (MP) / `.plan` (QGC) / `.gpx` / `.kml` import & export |
| **Parameters** | Metadata-driven UI (desc/range/units/enum/bitmask), tree view, diff export, default reset |
| **Calibration** | Compass, accel, gyro, level, baro wizards with real-time progress |
| **RTK** | NTRIP client with HTTP/1.0 + ICY-200 negotiation, streaming RTCM injection |
| **Firmware** | Store `.apj` files on the backend, online firmware browser, reboot to bootloader (no built-in flashing) |
| **Fleet** | Multi-vehicle dashboard with live telemetry per vehicle |
| **Video** | RTSP, HTTP and RTMP streams through ffmpeg on the backend, AR waypoint overlay, screenshot capture |
| **HUD** | PFD (attitude/speed/altitude/compass/wind), real-time charts, EKF status |
| **Audio** | Localized voice callouts (mode, battery, altitude, waypoints) in all 10 languages |
| **i18n** | 10 languages (zh, en, ja, ko, de, fr, es, pt, ru, ar) + RTL |
| **Offline** | PWA with service worker, mbtiles support, tile caching (5000-entry LRU) |
| **Desktop** | A Tauri v2 config is in `src-tauri/`. It has never been built: no icons, no CI job, and none planned |
| **Security** | Token auth, cross-site and DNS-rebinding request blocking, SSRF + path-traversal guards, statustext filtering |

## Install

### Windows package

For Windows 10 and 11, x64. Python and every library are inside the zip, and nothing is installed.

1. Download `Argus_GCS_vX.Y.Z_amd64.zip` and `SHA256SUMS.txt` from the [latest release](https://github.com/L-X-Yao/argus/releases/latest).
2. Check the download, because the zip is not code-signed:

   ```powershell
   $want = (Get-Content SHA256SUMS.txt).Split(' ')[0]
   (Get-FileHash Argus_GCS_vX.Y.Z_amd64.zip -Algorithm SHA256).Hash -eq $want   # True when the download is intact
   gh attestation verify Argus_GCS_vX.Y.Z_amd64.zip --repo L-X-Yao/argus       # optional, needs the GitHub CLI, signed in
   ```

3. Unzip it and double-click `Argus地面站.bat` ("Argus ground station"). A browser opens `http://127.0.0.1:8100`.

`启动仿真器.bat` ("start simulator") starts the built-in simulator. `README.txt` in the zip repeats these steps.

### From source

For Linux, macOS and Windows. Needs Python 3.10 or newer and Node.js. CI runs on Node 24 and Python 3.14, which is also the Python the Windows package bundles. Video needs `ffmpeg` on the PATH.

```bash
git clone https://github.com/L-X-Yao/argus && cd argus
npm install && npm run build   # the web interface, into dist/
pip install -e .               # the backend and its dependencies
python run.py                  # serves everything at http://127.0.0.1:8100
```

## Connect

Argus listens on this machine only. To reach it from another device, read [SECURITY.md](SECURITY.md) first: that needs a token.

### Real hardware

Plug the flight controller in, open `http://127.0.0.1:8100`, and pick the serial port from the dropdown. A network link takes an address instead, such as `tcp:192.168.1.10:5760` or `udp:14550`.

### ArduPilot SITL

```bash
sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550
python run.py
# Open the UI, click the "SITL" quick-connect button
```

### Built-in simulator (no FC, no SITL)

```bash
python run.py --sim            # Starts backend + simulator.py together
# Connect to "tcp:localhost:5770"
```

The simulator (`scripts/simulator.py`) emits realistic telemetry (GPS, attitude, battery drain, heartbeat) and responds to arm/disarm/mode commands.

### WebSerial (direct USB)

Open Argus in Chrome/Edge, click the **USB** button, pick your flight controller. Telemetry, arm/disarm/mode/RTL, param read+write, mission upload/download/clear, fence upload, log list/download, and all 5 calibration types flow directly via WebSerial and the built-in TypeScript MAVLink v2 codec. Map tiles, terrain profiles, parameter descriptions, video, and firmware file storage still use the Python backend; without it, new map tiles cannot load. RTK (NTRIP) and the MAVLink console need the FC connected through the backend, so they are unavailable over WebSerial.

### Map data

Map tiles, terrain heights and ArduPilot's firmware and parameter lists are not part of Argus. Argus fetches them from other parties' servers when you use the feature, under the terms of each server: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) lists them.

- The map shows the credit of the server it comes from. The backend names itself to the servers it asks (`Argus-GCS/<version>`). The terrain of the 3D view is read by the browser itself.
- The AutoNavi (Amap) source, which is the default, and the Google sources are not published APIs: they are the addresses those companies' own web maps read. Choose another source in Settings if that matters to you.
- OpenStreetMap forbids bulk download from its tile server, so the Offline Maps panel does not offer it. A map file of your own (`.mbtiles` in `mbtiles/`) works without any server.

## Architecture

```
+------------------------------------------+
|  Browser (Svelte 5 + TypeScript 6)       |
|  80 components, 27K lines                |
|  MAVLink v2 codec (pure TS)              |
|  WebSerial direct USB connection         |
|  41 lazy-loaded panels + view splitting  |
+------------------------------------------+
|          WebSocket (JSON delta push)     |
+------------------------------------------+
|  Python Backend (FastAPI + uvicorn)      |
|  31 modules, 7.1K lines                  |
|  MAVLink dispatch + 35 message handlers  |
|  53 commands, tile/video/firmware API    |
+------------------------------------------+
|          MAVLink v2                      |
|  TCP / UDP / Serial                      |
+------------------------------------------+
|  Flight Controller (ArduPilot)           |
+------------------------------------------+
```

### Key modules

| Module | Description |
|---|---|
| `src/lib/mavlink/` | Pure TypeScript MAVLink v2 encoder/decoder with CRC validation |
| `src/lib/fc/` | Flight controller adapter (ArduPilot wired; PX4 mode tables exist, not imported in production) |
| `src/lib/transport.ts` | Dual-mode transport (WebSocket backend vs WebSerial direct) |
| `src/lib/serial.ts` | Web Serial API wrapper with FC USB vendor filters |
| `src/lib/terrain.ts` | SRTM elevation queries for terrain-following missions |
| `src/lib/missionIO.ts` | Mission import/export (`.waypoints` / `.plan` / `.gpx`) |
| `src/lib/survey.ts` | Survey patterns (grid, crosshatch, spiral, orbit) |
| `src/lib/i18n.svelte.ts` | 10-language i18n with RTL support |
| `backend/drone_link.py` | MAVLink connection, frame parsing, state management |
| `backend/commands/` | 53 command handlers (arm, mode, mission, calibration, gimbal, NTRIP, etc.) |
| `backend/config.py` | Centralized configuration (all timeouts/ports/rates) |

## Development

Install the development tools with `pip install -e '.[dev]'`. `npm run dev` serves the interface at `http://127.0.0.1:5173` with hot reload and passes API calls on to a backend started with `python run.py`.

> **Windows / recent Node note**: Node ≥17 may resolve `localhost` to IPv6 `::1`, while the backend binds IPv4-only `127.0.0.1` — use `127.0.0.1` in dev URLs.

```bash
# Backend unit + contract tests
python -m pytest tests/test_unit_*.py tests/test_contract_*.py -v

# Frontend unit tests
npx vitest run

# Type check (must be 0 errors, 0 warnings)
npx svelte-check --tsconfig ./tsconfig.json

# Python lint
ruff check backend/ scripts/ tests/

# Formatting (npm run format fixes it)
npm run format:check

# Integration tests (start their own backend and simulator)
make test-integration

# Production build
npm run build

# E2E (needs the production build; starts its own backend)
npm run test:e2e -- --project=chromium
```

**Git hooks** (enable once per clone with `git config core.hooksPath .githooks`):
- **pre-commit**: ruff + svelte-check
- **pre-push**: vitest + pytest unit and contract tests

**Deeper docs**:

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — development rules: CI limits, both links, tests, review, releases
- [`CLAUDE.md`](CLAUDE.md) — project conventions, PX4 status, protocol-coupling discipline
- [`docs/VERIFICATION.md`](docs/VERIFICATION.md) — how far every feature has been verified
- [`SECURITY.md`](SECURITY.md) — how to run it safely, and how to report a vulnerability
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — work of others in the repository and the package, and the servers Argus reads
- [`docs/FEATURE_CHECKLIST.md`](docs/FEATURE_CHECKLIST.md) — feature snapshot from v3.4, frozen
- [`docs/protocol_design.md`](docs/protocol_design.md) — load-bearing design decisions
- [`docs/audits/`](docs/audits/) — archived audit reports

## Release

```bash
bash scripts/make-release.sh X.Y.Z
```

This command bumps the version everywhere it is stored, runs the frontend, unit and contract tests, commits, tags, and pushes. GitHub Actions then repeats lint and those tests, builds the Windows package, generates a changelog, and publishes a GitHub Release with artifacts. The Windows package is also checked by hand before and after: see [CONTRIBUTING.md](CONTRIBUTING.md#releases).

Alternatively, to generate a changelog preview locally:

```bash
bash scripts/changelog.sh v3.5.0   # Changes since v3.5.0
```

## Project Status

Argus is in maintenance since November 2026. Bugs and security problems get fixed. No new features are planned.

**Built**

- Rally points: map editing, upload and clear on both links
- Terrain profile panel with clearance visualization
- In-flight waypoint jump (MISSION_SET_CURRENT)
- WebSerial mission upload/download/clear + fence upload
- WebSerial log list + binary download
- WebSerial all 5 calibration types (compass, accel, gyro, level, baro)
- 3D map waypoint editing, fence drawing, distance/area measure
- NTRIP RTK client (HTTP/1.0 + ICY-200, RTCM streaming)
- Compass/accel/gyro calibration with binary progress
- Multi-language UI (10 locales + RTL)
- Dual-transport mutex (WS backend / WebSerial)
- Gimbal pitch/yaw control
- Tag-triggered release workflow with auto-changelog

**No longer planned**

These were on the roadmap and will not be built here:

- Firmware flashing (APJ parsing + bootloader protocol)
- PX4 end-to-end support (the backend reads `HEARTBEAT.autopilot` and refuses PX4; the frontend holds a mode table only)
- WebRTC video streaming (replace the ffmpeg proxy)
- MQTT cloud relay for fleet management
- MAVLink FTP for firmware upload and Lua script management
- MSP protocol support (BetaFlight / iNav)

What Argus does not do, and what has never been tested, is listed in [docs/VERIFICATION.md](docs/VERIFICATION.md) and [SECURITY.md](SECURITY.md).

## Contributing

Bug reports and fixes are welcome. A feature request is unlikely to be picked up: see [Project Status](#project-status). Before sending a PR:

1. Tests pass locally: `npx vitest run && python -m pytest tests/test_unit_*.py tests/test_contract_*.py`
2. Type check is clean: `npx svelte-check` (0 errors, 0 warnings)
3. Python lint is clean: `ruff check backend/ scripts/ tests/`
4. Commit convention: `<type>: <imperative description>` (types: `feat`, `fix`, `perf`, `refactor`, `test`, `docs`, `ci`, `chore`)
5. For FC-coupled code (MAVLink commands, ACK handling, calibration), cite upstream ArduPilot/PX4 source `file:line` in a comment — see `CLAUDE.md ## Protocol Code Discipline`

## Acknowledgments

Argus stands on the shoulders of:

- [ArduPilot](https://ardupilot.org/) — the flight controller firmware that defines the protocol semantics this GCS targets
- [pymavlink](https://github.com/ArduPilot/pymavlink) — reference MAVLink codec used to validate our pure-TS implementation
- [MAVLink](https://mavlink.io/) — the messaging protocol itself
- [Svelte](https://svelte.dev/), [FastAPI](https://fastapi.tiangolo.com/), [Leaflet](https://leafletjs.com/), [MapLibre GL](https://maplibre.org/), [Tauri](https://tauri.app/) — the application stack
- [QGroundControl](https://github.com/mavlink/qgroundcontrol) — the six calibration pictures come from it (Apache-2.0)
- QGroundControl, Mission Planner, MAVProxy — for showing what's possible

## License

MIT — see [LICENSE](LICENSE). Work of others in the repository and in the Windows package keeps its own license: see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
