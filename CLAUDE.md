# Argus GCS

Web-based MAVLink ground control station. ArduPilot only (PX4 unwired — see below).

**Maintenance only since 2026-11.** Fix bugs and security problems. Do not add features, and do not start what the README lists under "No longer planned", unless the maintainer asks for it.

## Build & Test

```bash
npm install && pip install -e '.[dev]' # deps
python run.py --sim                    # backend + simulator
npm run dev                            # frontend dev server :5173

npx svelte-check --tsconfig ./tsconfig.json   # 0 errors 0 warnings
npx vitest run                                # frontend tests
python -m pytest tests/test_unit_*.py tests/test_contract_*.py  # backend tests
ruff check backend/ scripts/ tests/           # Python lint
npm run format:check                          # Prettier + ruff format
make test-integration                         # backend + simulator, about 3 min
```

`CONTRIBUTING.md` holds the full rules: CI limits, both links, tests, review, verification status, releases.

## Commit Convention

`<type>: <imperative description>` — types: feat / fix / perf / refactor / test / docs / ci / chore. `scripts/make-release.sh` writes the `release:` commit.

## Protocol Code Discipline

FC-coupled code (MAVLink commands, ACKs, field offsets, CRC extras, calibration handshakes, mode IDs, parameter semantics) **must cite the ArduPilot/PX4 source file:line in a code comment**. Do not infer from the MAVLink XML spec alone — FCs hijack generic fields for private protocols.

Workflow: stop guessing → fetch AP source (`raw.githubusercontent.com/ArduPilot/ardupilot/master/...`) → quote the exact condition → implement to match.

Examples already in the codebase:
- `backend/commands/_setup.py:cmd_cal_accel_next` — AP_AccelCal ACK semantics
- `backend/mavlink_handlers.py:handle_mag_cal_progress` — binary MAG_CAL msgs
- `src/components/params/FailsafeConfigPanel.svelte` — BATT_FS_LOW_ACT values

## PX4 Status

Only ArduPilot is wired end-to-end. The backend and WebSerial both latch the `autopilot` byte from HEARTBEAT and refuse FC-bound commands from any other autopilot (`backend/commands/__init__.py:execute`), so a PX4 vehicle connecting today gets an error, not control. `src/lib/fc/px4.ts` holds a mode table and nothing else is wired. PX4 support is greenfield work — weeks not days.
