# Argus GCS

Universal web-based ground control station for MAVLink drones.
Repo: `github.com/L-X-Yao/argus`, branch: `main`

## Tech Stack

- **Frontend**: Svelte 5 (runes) + TypeScript + Vite + Tailwind CSS + Leaflet + MapLibre GL
- **Backend**: Python + FastAPI + uvicorn + pyserial + websockets
- **Protocol**: MAVLink v2 (standard + PL-Link wrapper), ArduPilot + PX4
- **Tests**: pytest (backend), vitest (frontend), Playwright (E2E)

## Quick Start

```bash
npm install                    # Frontend dependencies
pip install -e .               # Backend dependencies (pyproject.toml)
python run.py --sim            # Start everything (backend + simulator)
npm run dev                    # Or: separate frontend dev server on :5173
```

## Build

```bash
npm run build                  # Production build → dist/
npx svelte-check               # Type check (must be 0 errors 0 warnings)
npx vitest run                 # Frontend tests
python -m pytest tests/test_unit_*.py -v  # Backend tests
```

## Project Structure

```
argus/
├── backend/                # Python FastAPI backend
│   ├── app.py              # FastAPI routes + lifespan
│   ├── drone_link.py       # Drone connection + main loop
│   ├── state.py            # 9 domain state dataclasses
│   ├── pllink_proto.py     # PL-Link protocol codec
│   ├── server.py           # Tauri sidecar entry point
│   ├── ws_manager.py       # WebSocket client manager (delta push)
│   ├── mavlink_handlers.py # 30+ MAVLink message handlers
│   ├── commands.py         # Command execution dispatcher
│   └── ...                 # config, auth, video, param_manager, etc.
├── src/                    # Svelte 5 frontend
│   ├── components/         # UI components (11 subdirectories)
│   │   ├── core/           # MapView, StatusBar, ControlPanel, EventLog
│   │   ├── telemetry/      # RcPanel, ServoPanel, VibrationPanel, EkfPanel
│   │   ├── mission/        # MissionPanel, SurveyPanel, FencePanel
│   │   ├── setup/          # CalibrationPanel, SetupWizard, MotorTestPanel
│   │   ├── params/         # ParamPanel, PidPanel, FlightModePanel
│   │   ├── tools/          # InspectorPanel, ConsolePanel, LogPanel
│   │   ├── map/            # Map3DView, AirspacePanel, OfflineMapPanel
│   │   ├── vehicle/        # FleetDashboard, GimbalPanel, VideoOverlay
│   │   ├── planning/       # AiPlannerPanel, SchedulerPanel
│   │   ├── shared/         # CommandPalette, ConfirmDialog, SettingsPanel
│   │   └── layers/         # DroneLayer, WaypointLayer (map overlays)
│   ├── lib/                # Shared libraries
│   │   ├── panels.svelte.ts  # Panel registry (lazy-loaded via LazyPanelHost)
│   │   ├── stores.svelte.ts  # App state (Svelte 5 runes)
│   │   ├── ws.ts             # WebSocket client (typed protocol)
│   │   ├── locales/          # i18n translation files (10 languages)
│   │   ├── mavlink/          # TypeScript MAVLink v2 codec
│   │   └── fc/               # Flight controller adapters (ArduPilot/PX4)
│   └── main.ts            # Entry point
├── tests/                  # pytest + vitest + playwright
├── scripts/                # Build & dev tools
│   ├── sim_pllink.py       # MAVLink vehicle simulator
│   ├── build_package.py    # Windows packaging script
│   └── build_desktop.sh    # Tauri desktop build
├── public/                 # Static assets (leaflet, icons, manifest, sw.js)
├── src-tauri/              # Tauri desktop packaging config
├── run.py                  # One-click launcher (sole entry point)
└── README.md
```

## Commit Convention

Format: `<type>: <imperative description>`

Types: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`, `chore:`

## Key Design Decisions

- **State architecture**: `backend/state.py` — 9 domain dataclasses (AttitudeState, BatteryState, VehicleState, etc.), protected by `_state_lock` RLock
- **Panel system**: `panels.svelte.ts` registry + `LazyPanelHost.svelte` — all 42 panels lazy-loaded on open
- **Delta push**: WebSocket sends only changed fields, full sync every 10th push
- **i18n**: zh/en eager-loaded, 8 other locales lazy-loaded from `src/lib/locales/`
- **Dual connection**: Backend proxy (WebSocket) + WebSerial direct (browser USB)
- **FC adapter**: `src/lib/fc/` — ArduPilot and PX4 share the same UI code
- **Config**: `backend/config.py` centralized constants + `ARGUS_*` env var overrides
- **White-label**: `branding.ts` drives app name/theme
