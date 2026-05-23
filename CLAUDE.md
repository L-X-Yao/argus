# Argus GCS

Universal web-based ground control station for MAVLink drones.
Repo: `github.com/L-X-Yao/argus`, branch: `main`, version: `3.4.0`

## Tech Stack

- **Frontend**: Svelte 5 (runes) + TypeScript 6 + Vite 8 + Tailwind CSS 4 + Leaflet + MapLibre GL
- **Backend**: Python 3.10+ + FastAPI + uvicorn + pyserial + websockets
- **Protocol**: MAVLink v2 (standard + PL-Link wrapper). **ArduPilot is the only production-tested target.** PX4 support is partially scaffolded in `src/lib/fc/` but unwired — see `## PX4 Status` below.
- **Tests**: pytest (backend + contract, 1040 tests), vitest 4 (frontend, 487 tests), Playwright (E2E, 19 specs). Current verification status per feature: `docs/FEATURE_CHECKLIST.md`. Don't-refactor decisions: `docs/protocol_design.md`.
- **Lint**: ruff (Python), svelte-check (TypeScript/Svelte)
- **CI**: GitHub Actions — lint → test → type-check → build → E2E

## Quick Start

```bash
npm install                    # Frontend dependencies
pip install -e .               # Backend dependencies (pyproject.toml)
python run.py --sim            # Start everything (backend + simulator)
npm run dev                    # Or: separate frontend dev server on :5173
```

## Build & Verify

```bash
npm run build                  # Production build → dist/
npx svelte-check               # Type check (must be 0 errors 0 warnings)
npx vitest run                 # Frontend tests (487)
python -m pytest tests/test_unit_*.py tests/test_contract_*.py -v  # Backend tests (1040)
ruff check backend/ scripts/ tests/       # Python lint
```

## Project Structure

```
argus/
├── backend/                  # Python FastAPI backend (24 modules, 3.5K lines)
│   ├── app.py                # FastAPI routes + lifespan
│   ├── drone_link.py         # Drone connection + main loop
│   ├── state.py              # 9 domain state dataclasses
│   ├── commands/             # Command dispatch package (50 commands)
│   │   ├── __init__.py       # execute() dispatcher + dispatch table
│   │   ├── _flight.py        # arm, disarm, rtl, mode, takeoff, drop
│   │   ├── _mission.py       # mission upload/download/clear, fence, rally
│   │   ├── _setup.py         # calibration, params, logs
│   │   ├── _hardware.py      # vehicle, system, RC, motor, gimbal, camera
│   │   └── _helpers.py       # MAVLink wire helpers (send_cmd, heartbeat, etc.)
│   ├── ws_manager.py         # WebSocket client manager (delta push)
│   ├── mavlink_handlers.py   # 31 MAVLink message handlers
│   ├── pllink_proto.py       # PL-Link protocol codec
│   └── ...                   # config, auth, video, param_manager, connection, etc.
├── src/                      # Svelte 5 frontend (144 components, 21K lines)
│   ├── components/           # UI components (12 subdirectories)
│   │   ├── core/             # MapView, StatusBar, ConnectionForm, ControlPanel, EventLog
│   │   ├── telemetry/        # RcPanel, ServoPanel, VibrationPanel, EkfPanel
│   │   ├── mission/          # MissionPanel, SurveyPanel, FencePanel
│   │   ├── setup/            # CalibrationPanel, FirmwarePanel, NtripPanel, PositionSourcePanel
│   │   ├── params/           # ParamPanel, PidPanel, FlightModePanel
│   │   ├── tools/            # InspectorPanel, ConsolePanel, LogPanel, FlightReportPanel
│   │   ├── map/              # Map3DView, AirspacePanel, OfflineMapPanel
│   │   ├── vehicle/          # FleetDashboard, GimbalPanel, VideoOverlay
│   │   ├── planning/         # AiPlannerPanel, SchedulerPanel
│   │   ├── shared/           # CommandPalette, ConfirmDialog, SettingsPanel (dialogs only)
│   │   └── layers/           # DroneLayer, WaypointLayer (map overlays)
│   ├── lib/                  # Shared libraries
│   │   ├── panels.svelte.ts  # Panel registry (42 panels, lazy-loaded via LazyPanelHost)
│   │   ├── stores.svelte.ts  # App state (Svelte 5 runes)
│   │   ├── ws.ts             # WebSocket client (typed protocol)
│   │   ├── locales/          # i18n translation files (10 languages)
│   │   ├── mavlink/          # TypeScript MAVLink v2 codec
│   │   └── fc/               # Flight controller adapters (ArduPilot/PX4)
│   ├── App.svelte            # Root component (view-level lazy loading)
│   └── main.ts               # Entry point + SW registration
├── tests/                    # pytest + vitest + playwright
├── scripts/                  # Build & dev tools
│   ├── sim_pllink.py         # MAVLink vehicle simulator
│   ├── build_package.py      # Windows packaging script
│   └── build_desktop.sh      # Tauri desktop build
├── public/                   # Static assets (leaflet, icons, manifest, sw.js)
├── src-tauri/                # Tauri desktop packaging config
├── run.py                    # One-click launcher (sole entry point)
└── README.md
```

## Commit Convention

Format: `<type>: <imperative description>`

Types: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`, `chore:`

## Key Design Decisions

- **State architecture**: `backend/state.py` — 9 domain dataclasses, protected by `_state_lock` RLock
- **Panel system**: `panels.svelte.ts` registry + `LazyPanelHost.svelte` — all 42 panels lazy-loaded on open
- **View lazy loading**: `App.svelte` dynamically imports monitor/plan/params/modal components on first use
- **Delta push**: WebSocket sends only changed fields, full sync every 10th push
- **i18n**: zh/en eager-loaded, 8 other locales lazy-loaded from `src/lib/locales/`
- **Dual connection**: Backend proxy (WebSocket) + WebSerial direct (browser USB)
- **FC adapter**: `src/lib/fc/` — ArduPilot and PX4 share the same UI code
- **Config**: `backend/config.py` centralized constants + `ARGUS_*` env var overrides
- **PWA**: Service worker with app shell precache, tile cache (5000 entries LRU), push notifications
- **White-label**: `branding.ts` drives app name/theme

## PX4 Status

Despite the README's "ArduPilot + PX4" framing, only ArduPilot is wired end-to-end. The frontend `src/lib/fc/` adapter system has working PX4 mode tables and unit tests, but **no production code path imports `px4Adapter`**. As of the 2026-05-24 Phase P commit, the backend DOES read the `autopilot` byte from HEARTBEAT (offset 5) and surfaces it as `vehicle.autopilot` + `drone.autopilot` in the WebSocket state. **That's the only PX4 wiring that exists** — nothing branches on it yet. All flight-mode strings, mode buttons, calibration messages, and parameter behaviors still assume ArduPilot. A real PX4 vehicle connecting today would correctly report `drone.autopilot === 12` to the frontend, but would still render every mode as `MODE%d`, fail every calibration handshake (the magic numbers like `21196`, `42424-42426` are AP-private), and not understand `RTL`/`mission_start`/`takeoff` integer enums.

If the user asks for PX4 support, that is greenfield work — quote weeks not days. The autopilot byte is a foothold, not a feature. Do not assume any PX4 path "should just work."

## Protocol Code Discipline

Anything coupled to ArduPilot/PX4 behavior — MAVLink commands, ACKs, message field offsets, CRC extras, calibration handshakes, mode IDs, parameter semantics — **cite the upstream source file:line in a code comment**. Do not infer from the MAVLink spec alone.

Why: flight controllers regularly hijack generic MAVLink fields for private protocols, and "what the spec says" diverges from "what the FC actually does". Two real examples this repo got bitten by:

- **Accel cal advance ACK**: `AP_AccelCal::handle_command_ack` (libraries/AP_AccelCal/AP_AccelCal.cpp:367-398) overrides COMMAND_ACK's `command` and `result` fields entirely — requires `command ≤ 6` (NOT the MAV_CMD value 42429) and `result == 1 / TEMPORARILY_REJECTED` (NOT ACCEPTED). See `backend/commands/_setup.py:cmd_cal_accel_next` for the citation pattern.
- **Compass cal progress**: Sent via binary MAG_CAL_PROGRESS (msg 191) and MAG_CAL_REPORT (msg 192), not STATUSTEXT. See `backend/mavlink_handlers.py:handle_mag_cal_progress`.

Workflow when implementing or debugging FC-coupled code: report → **stop guessing** → fetch the AP/PX4 source (`raw.githubusercontent.com/ArduPilot/ardupilot/master/...` or via WebFetch) → quote the exact condition in a comment above your implementation → implement to match. Unit tests that mock the FC will pass either way — only the real source pins the truth.
