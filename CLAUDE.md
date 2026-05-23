# Argus GCS

Universal web-based ground control station for MAVLink drones.
Repo: `github.com/L-X-Yao/argus`, branch: `main`, version: `3.4.0`

## Tech Stack

- **Frontend**: Svelte 5 (runes) + TypeScript 6 + Vite 8 + Tailwind CSS 4 + Leaflet + MapLibre GL
- **Backend**: Python 3.10+ + FastAPI + uvicorn + pyserial + websockets
- **Protocol**: MAVLink v2 (standard + PL-Link wrapper), ArduPilot + PX4
- **Tests**: pytest (backend, 946 tests), vitest 4 (frontend, 400 tests), Playwright (E2E, 19 specs)
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
npx vitest run                 # Frontend tests (400)
python -m pytest tests/test_unit_*.py -v  # Backend tests (929)
ruff check backend/ scripts/ tests/       # Python lint
```

## Project Structure

```
argus/
├── backend/                  # Python FastAPI backend (23 modules, 3.5K lines)
│   ├── app.py                # FastAPI routes + lifespan
│   ├── drone_link.py         # Drone connection + main loop
│   ├── state.py              # 9 domain state dataclasses
│   ├── commands/             # Command dispatch package (46 commands)
│   │   ├── __init__.py       # execute() dispatcher + dispatch table
│   │   ├── _flight.py        # arm, disarm, rtl, mode, takeoff, drop
│   │   ├── _mission.py       # mission upload/download/clear, fence, rally
│   │   ├── _setup.py         # calibration, params, logs
│   │   ├── _hardware.py      # vehicle, system, RC, motor, gimbal, camera
│   │   └── _helpers.py       # MAVLink wire helpers (send_cmd, heartbeat, etc.)
│   ├── ws_manager.py         # WebSocket client manager (delta push)
│   ├── mavlink_handlers.py   # 27 MAVLink message handlers
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
