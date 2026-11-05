# Argus + ArduPilot — Development Workflow

All development happens in one checkout inside WSL2. Windows provides the browser and the USB port the flight controller is plugged into; it does not hold a second clone.

## TL;DR — Where each task lives

| Task | Where | Why |
| - | - | - |
| Write Argus code, run lint/tests | **WSL2** | CI is Ubuntu; ruff / pytest / vitest / svelte-check are all native |
| Run Argus against ArduPilot SITL | **WSL2** | SITL is Linux; one host, zero glue |
| Real FC over WebSerial | **Windows browser**, servers in WSL2 | The FC stays on Windows, no usbipd needed |
| Real FC over backend serial, firmware upload | **WSL2 + usbipd** | The backend needs a local serial device |
| Flash FC firmware with vendor tools | **Windows** | FC uploader / Mission Planner are Windows tools |
| Edit ArduPilot fork (C++) | **WSL2** | waf, SITL build, fork maintenance — Linux-first ecosystem |
| Build ArduPilot SITL or firmware APJ | **WSL2** | Same |

## WSL2 — development environment

Already set up. See `docs/MIGRATION_TO_WSL.md` for the bootstrap.

**Daily commands**:

```bash
cd ~/project/argus

# Run against the built-in simulator
python run.py --sim                          # backend on :8100, simulator on tcp:5770
npm run dev                                  # Vite on :5173

# Pre-commit gate
ruff check backend/ scripts/ tests/
python -m pytest tests/test_unit_*.py tests/test_contract_*.py -v
npx vitest run
npx svelte-check --tsconfig ./tsconfig.json
npm run build                                # only when shipping
```

Enable the git hooks once per clone: `git config core.hooksPath .githooks`.

## Session record / replay — hardware sessions as offline assets

Every live connection automatically records every **validated** MAVLink frame
(both directions) to `logs/argus_*.tlog` alongside the telemetry CSV. The
format is standard tlog (8-byte big-endian µs timestamp per message) —
readable by pymavlink `mavlogdump.py` and Mission Planner. Frames that fail
CRC or carry unknown msg ids are dropped before recording (they surface in
`parse_errors` / the unknown-id log instead) — the tlog captures exactly what
drove state, not the raw wire noise.

This shrinks the code→hardware→observe loop: an FC quirk captured once on real
hardware replays forever, no hardware attached.

**Replay into the running UI** — connect with a `replay:` port (optional
`@speed` suffix); commands are discarded, the session loops at end-of-log:

```
replay:logs/argus_20260712_213300.tlog@10
```

**Replay into tests** — drive the real parse→dispatch→state path offline:

```python
from backend.replay import replay_into
link = DroneLink()
replay_into(link, "tests/fixtures/that_weird_calibration.tlog")
assert link.get_state()["..."] == ...
```

When a hardware session exposes a bug, scrub its tlog with
`scripts/scrub_tlog.py`, copy it into `tests/fixtures/` and pin the fixed
behavior with a replay test. Only do this with recordings from hardware you
own and may publish. Frame builders for synthetic sessions live in
`tests/frame_builders.py`.

### Calibration fixtures — recorded from real-firmware SITL

`tests/fixtures/{magcal,accelcal}_sitl.tlog` are full calibration handshakes
(onboard compass cal incl. accept; 6-position accel cal) recorded against the
prebuilt ArduPilot SITL using its special `calibration` vehicle model, driven
end-to-end through the backend's own command path.
`tests/test_contract_calibration_replay.py` replays them every CI run — the
offline regression for the calibration protocol, no hardware or SITL needed.

Regenerate after changing anything FC-coupled in the calibration flow:

```bash
python tests/sitl_calibrate.py   # self-contained: boots SITL + backend, ~3 min
```

The recorder is also a live integration test — it dies loudly if any step of
either handshake stalls (that is how the missing MAG_CAL_PROGRESS stream
subscription was found).

## Real flight controller

The FC is plugged into Windows. Both routes run the servers in WSL.

**WebSerial (default).** Keep the FC on Windows and do not attach it with usbipd.

1. In WSL, start the backend (`python run.py`) and Vite (`npm run dev`). WebSerial still needs the backend: map tiles and parameter metadata come from it.
2. In a Windows browser (Chrome or Edge), open `http://localhost:5173` and click **USB**. Use `localhost`, not the WSL IP: WebSerial requires a secure context.

**Backend serial or firmware upload.** Forward the FC into WSL from an admin PowerShell, then connect to `/dev/ttyACM0` from the UI:

```powershell
usbipd list                                  # find the busid
usbipd attach --wsl --busid=<busid>
```

Detach it afterwards so WebSerial can see the device again: `usbipd detach --busid=<busid>`. See `docs/MIGRATION_TO_WSL.md` Phase 4 for first-time setup.

## ArduPilot fork — WSL only

```bash
# One-time
git clone --recursive https://github.com/ArduPilot/ardupilot.git ~/ardupilot
cd ~/ardupilot
git checkout master                          # or checkout your target branch/commit
Tools/environment_install/install-prereqs-ubuntu.sh -y
. ~/.profile

# Build SITL (for Argus protocol-layer development)
./waf configure --board sitl
./waf copter
# → build/sitl/bin/arducopter

# Build flashable firmware
./waf configure --board <your-board-name>
./waf copter
# → build/<your-board>/bin/arducopter.apj
```

**Flashing the FC**: build the APJ in WSL, copy it to Windows, flash from Windows:

```
# In Windows Explorer
\\wsl.localhost\Ubuntu\home\administrator\ardupilot\build\<your-board>\bin\arducopter.apj
→ copy to C:\firmware\
→ flash with FC uploader / Mission Planner over COM6
```

Cross-boundary file copy is acceptable here because it is low-frequency (a flash, not a build).

## Why this is the shape

- **CI is Ubuntu** — developing on the same platform catches Linux-only regressions in the dev loop, not at PR time
- **ArduPilot maintainers are on Linux** — fork patches and SITL stay in the most-supported toolchain
- **One checkout** — there is nothing to keep in sync, and `venv` and `node_modules` hold native binaries that cannot be shared across the WSL/Windows boundary anyway
