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
pip install fastapi uvicorn pyserial websockets  # Backend dependencies
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
├── backend/          # Python FastAPI backend (17 modules)
├── src/              # Svelte 5 frontend
│   ├── components/   # 75 UI components
│   ├── lib/          # Shared libraries (mavlink/, fc/, stores, i18n, etc.)
│   └── main.ts       # Entry point
├── tests/            # pytest + vitest + playwright
├── public/           # Static assets (leaflet, icons, manifest, sw.js)
├── src-tauri/        # Tauri desktop packaging config
├── sim_pllink.py     # MAVLink vehicle simulator
├── pllink_proto.py   # PL-Link protocol codec (used by backend)
├── run.py            # One-click launcher
└── README.md
```

## Commit Convention

Format: `<type>: <imperative description>`

Types: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`, `chore:`

## Key Design Decisions

- Frontend decoupled from backend locale — uses `event_type` + numeric IDs, not Chinese strings
- `branding.ts` drives white-label — change appName there, not in components
- `src/lib/fc/` adapter pattern — ArduPilot and PX4 share the same UI code
- `src/lib/mavlink/` — pure TypeScript MAVLink v2 codec for WebSerial direct connection
- All hardcoded values centralized in `backend/config.py`
- i18n fallback chain: selected locale → zh → key string
