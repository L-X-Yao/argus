# Argus GCS — PX4 Audit

Repo: `github.com/L-X-Yao/argus`, branch `main` @ commit `41b03b0`

---

## Section 1 — PX4 Support

### What's claimed

- `README.md:Argus aims to be the first truly universal web GCS — one interface that works with any MAVLink vehicle (ArduPilot, PX4)`
- `README.md:| Protocols | ArduPilot + PX4 (auto-detect via FC adapter layer) |`
- `README.md:| src/lib/fc/ | Flight controller adapter (ArduPilot + PX4 mode/command mapping) |`
- `CLAUDE.md:Protocol: MAVLink v2 (standard + PL-Link wrapper), ArduPilot + PX4`

### What's actually implemented

`src/lib/fc/` defines an `FcAdapter` abstraction (`interface.ts:17-46`) with `ardupilotAdapter` (`ardupilot.ts:32-77`) and `px4Adapter` (`px4.ts:60-100`). It includes a `detectAdapter(autopilot)` helper (`index.ts:15-20`) that switches on the HEARTBEAT `autopilot` field (3 = ArduPilot, 12 = PX4).

The PX4 adapter handles:
- 24-bit custom_mode decoding `(main << 16) | (sub << 24)` (`px4.ts:8-9, 28-30`)
- Mode names for 14 modes (manual/altctl/posctl/auto sub-modes) (`px4.ts:32-47`)
- Mode buttons (`px4.ts:49-58`)
- RTL / hold / auto / arm-base-mode helpers (`px4.ts:87-90`)

### Gaps

#### G1. The FC adapter is unwired dead code

Nothing outside `src/lib/fc/` ever imports it. Verified by grep across the entire `src/` tree:
- No production file imports `ardupilotAdapter`, `px4Adapter`, `detectAdapter`, or `FcAdapter`.
- Only `src/lib/fc/fc.test.ts` references it (unit test isolated from production).
- `src/lib/types.ts:32` declares `mode_btns: [number, string][]` which is populated **server-side** in `backend/drone_link.py:281,315` via `_get_vehicle_info()`.
- UI components (`ControlPanel.svelte:71,100,133,154`, `MapControls.svelte:42`, `CommandPalette.svelte:171-172`, `App.svelte:202`) read `app.drone.mode_btns` directly from the backend payload.

Result: the `px4Adapter` mode tables, buttons, RTL/HOLD/AUTO IDs are never seen by the running UI.

#### G2. Backend never reads the autopilot field from HEARTBEAT

`backend/mavlink_handlers.py:30-64` (`handle_heartbeat`) reads `p[0..3]` (custom_mode), `p[4]` (type), `p[6]` (base_mode), `p[7]` (system_status), but **never reads `p[5]` (autopilot)**. The vehicle state `backend/state.py:56` only stores `vtype_raw`. There is no field or branch anywhere in the backend that distinguishes ArduPilot from PX4.

#### G3. Backend mode tables are ArduPilot-only

`backend/constants.py:1-7` ("Verified against ArduCopter/mode.h, ArduPlane/mode.h, …") defines COPTER_MODES, PLANE_MODES, ROVER_MODES, SUB_MODES — all using ArduPilot custom_mode integer enumerations.

`backend/drone_link.py:253-274` (`_get_vehicle_info`) selects one of these tables based on `vtype_raw` (MAV_TYPE) alone — never based on autopilot.

If a PX4 vehicle connects, the backend will look up PX4's custom_mode (a packed 32-bit `(sub<<24)|(main<<16)`) in a flat ArduPilot table:
- PX4 POSCTL = `0x00030000` (196608) → falls through to `MODE%d` fallback (`drone_link.py:288`)
- PX4 AUTO/MISSION = `0x04040000` (67371008) → same fallback.

Every PX4 mode appears as `MODE197120` style garbage in the UI.

#### G4. Mode-set commands assume ArduPilot integers

- `backend/commands/_flight.py:28`: `cmd_rtl` sends `send_set_mode(link, 21 if is_plane else 6)`. For PX4 this would set custom_mode=6 (AUTO main_mode=0/sub=0 if PX4 even honored the legacy SET_MODE) — meaningless.
- `backend/commands/_flight.py:36-39`: `cmd_mode` uses ArduPilot's COPTER_MODES / PLANE_MODES for the event-log name; the integer is passed straight through.
- `backend/commands/_hardware.py:34`: `cmd_guided_goto` uses `gm = 15 if is_plane else 4` (ArduPilot Guided mode IDs). PX4 has no equivalent "Guided" mode at id 4.
- `backend/commands/_mission.py:22`: `cmd_mission_start` uses `am = 10 if is_plane else 3` (ArduPilot Auto = 3 copter, 10 plane). For PX4 this is not the Auto/Mission mode bit pattern.

#### G5. `SET_MODE` (msg 11) is deprecated on PX4

`backend/commands/_helpers.py:20-22` (`send_set_mode`) sends MAVLink message 11 (SET_MODE) with `base_mode = 0x01` (MAV_MODE_FLAG_CUSTOM_MODE_ENABLED). PX4 documents SET_MODE as deprecated; the canonical mechanism is `MAV_CMD_DO_SET_MODE` (cmd 176, COMMAND_LONG) with `param1 = base_mode`, `param2 = main_mode`, `param3 = sub_mode`.

The deprecation is informational on recent PX4 builds — they still mostly honor SET_MODE — but the `(custom_mode = u32 enum)` semantic is fundamentally different between the two stacks, so even if PX4 accepts the message, the integer payload is wrong.

#### G6. ArduPilot-private MAVLink messages are registered as common

`backend/drone_link.py:49-57` (`_CRC_EXTRA`) and `backend/mavlink_handlers.py:634-666` (`init_handlers`) treat these messages as if they were common when they are actually in the `ardupilotmega` dialect — verified against pymavlink (these msg IDs are absent from `dialects.v20.common`):

- `158` MOUNT_STATUS — AP only; PX4 uses MOUNT_ORIENTATION (msg 265).
- `163` AHRS — AP only.
- `168` WIND — AP only; PX4 uses WIND_COV (231).
- `178` AHRS2 — AP only.
- `191` MAG_CAL_PROGRESS — AP only.
- `192` MAG_CAL_REPORT — AP only.
- `193` EKF_STATUS_REPORT — AP only; PX4 uses ESTIMATOR_STATUS (230).
- `241` VIBRATION — common (PX4 does send this).

On a PX4 vehicle, none of the AP-private streams arrive, so the Vibration / EKF / Wind / Gimbal panels show only zeros, and accel-cal / mag-cal flows are silent. The CRC_EXTRAs themselves are correct (matched against pymavlink ardupilotmega dialect), so no parsing corruption — just missing data.

#### G7. Calibration ACK semantics are AP-private

`backend/commands/_setup.py:47-58` (`cmd_cal_accel_next`) sends a COMMAND_ACK (msg 77) with `command=0, result=MAV_RESULT_TEMPORARILY_REJECTED(1)` — verbatim from `AP_AccelCal::handle_command_ack` in ArduPilot. PX4 has no equivalent — its accel calibration uses a different orientation-handshake flow (via custom STATUSTEXT / SENSOR_OFFSETS).

`backend/commands/_setup.py:19, 24, 70`: cmds 42424 / 42425 / 42426 (`DO_START_MAG_CAL`, `DO_ACCEPT_MAG_CAL`, `DO_CANCEL_MAG_CAL`) are AP MAVLink extensions; PX4 ignores them.

`backend/commands/_setup.py:29-44`: cmd 241 (`MAV_CMD_PREFLIGHT_CALIBRATION`) is common, but PX4 only honors `p1=1` (gyro) and `p3=1` (baro); PX4's accel cal flow is different.

#### G8. Force-disarm magic value is AP-only

`backend/commands/_flight.py:23-24`: `send_cmd(link, 400, p1=0, p2=21196)`. The magic 21196 is `'L'<<8|'I'` (Land Immediately), checked specifically in `AP_Arming::run_arming_checks`. PX4 ignores p2 — it uses `21196` is not interpreted, and PX4 force-disarm is `param2 = 21196` only honored on AP. To force-disarm on PX4 the command must be a regular `cmd 400, p1=0` from a system_status==CRITICAL state.

#### G9. Motor-test param mapping is AP-only

`backend/commands/_hardware.py:110-125`: cmd 209 `MAV_CMD_DO_MOTOR_TEST` with `p1 = 1-based motor index`. The comment explicitly cites `GCS_MAVLink_Copter.cpp:702`. PX4 uses different motor test semantics (commander module accepts `param5 = motor_id` differently). Even motor numbering differs.

#### G10. WebSerial direct path uses ArduPilot Copter RTL

`src/lib/transport.ts:172-174`: `serialSendRtl()` calls `serialSendMode(11)` with comment "RTL mode for copter". 11 is ArduPlane RTL, not Copter RTL (Copter RTL = 6). For PX4 it's neither (it'd be sub=0 main=0, undefined). This is a freestanding bug compounding the PX4 gap.

#### G11. Heartbeat/vehicle-type fallback assumes AP-style multirotor

`backend/drone_link.py:271-273`: when MAV_TYPE matches none of the explicit branches but `> 0`, the backend defaults to COPTER_MODES. For a PX4 fixed-wing with MAV_TYPE=1 (FIXED_WING) it would hit the plane branch first (`vtype_raw in (1, 19, 20, …)`) — but a PX4 hexarotor (MAV_TYPE=13) wouldn't match either, so it'd silently get ArduCopter's mode names. The fallback assumption is wrong for PX4.

#### G12. AP-specific PreArm string parsing

`backend/mavlink_handlers.py:244`: `if text.startswith('PreArm:') or text.startswith('Arm:')`. ArduPilot prefixes pre-arm failures with `PreArm:` / `Arm:`. PX4 uses different prefixes (e.g. `Preflight Fail:`). Pre-arm messages from PX4 won't be deduplicated/aggregated as designed.

#### G13. `statustext_filter` only knows AP strings

`backend/statustext_filter.py:1-38`: every leak filter is AP/APM/ArduCopter/EKF3/etc. PX4 STATUSTEXTs (e.g. `Commander: …`, `Preflight Fail: …`) get no translation, no brand suppression. (This is more cosmetic but reinforces that PX4 was never exercised.)

#### G14. Stream requests work, but not what we tell PX4 to send

`backend/commands/_helpers.py:86-99`: `request_streams()` uses `MAV_CMD_SET_MESSAGE_INTERVAL` (cmd 511) — universal MAVLink — so this works. But it requests msg 65 (RC_CHANNELS), msg 241 (VIBRATION), msg 74 (VFR_HUD), msg 33 (GLOBAL_POSITION_INT) — most are common. Then cmd 512 with p1=148 (request AUTOPILOT_VERSION) — common. So data flow works for PX4 for the messages PX4 implements.

The WebSerial path (`src/lib/transport.ts:135-150`) however uses deprecated `REQUEST_DATA_STREAM` (msg 66) with stream IDs 1, 2, 3, 6, 10, 11, 12. PX4 stopped supporting that years ago; no telemetry will flow on the WebSerial path with a PX4 vehicle.

### Summary

The PX4 story is: a frontend FC adapter pattern was scaffolded (`src/lib/fc/`) but never wired in. The backend is monolithic ArduPilot end-to-end — mode tables, custom_mode integers, calibration semantics, force-disarm magic, motor test, fence/rally protocols, PreArm parsing, statustext filtering, AP-private message IDs. PX4 connections will see a HEARTBEAT, the backend will display garbled mode names like `MODE197120`, and PX4-private telemetry (EKF, mount, mag-cal) will never reach the UI.

**14 gaps identified.**

---

## Section 2 — Concrete Bug List

### PX4 bugs (in order of severity)

| # | Severity | File:Line | Description |
| - | - | - | - |
| P1 | **Critical** | `src/lib/fc/index.ts:15-20` & all UI | The FC adapter (`px4Adapter`, `ardupilotAdapter`, `detectAdapter`) is **never imported** by any production code. All mode/button data is delivered by the backend in `mode_btns`/`mode` fields. README's "auto-detect via FC adapter layer" is false. |
| P2 | **Critical** | `backend/mavlink_handlers.py:30-64` | `handle_heartbeat` never reads `p[5]` (autopilot field). Backend has no way to detect PX4. |
| P3 | **Critical** | `backend/drone_link.py:253-274`, `backend/constants.py:10-44` | Mode tables are 100% ArduPilot. PX4's packed `(sub<<24)|(main<<16)` custom_mode lookup will always miss → "MODE197120" garbage in UI. |
| P4 | High | `backend/commands/_flight.py:28`, `backend/commands/_hardware.py:34`, `backend/commands/_mission.py:22` | RTL/Guided/Auto mode IDs are hardcoded to ArduPilot integers. Sending these to a PX4 vehicle is meaningless. |
| P5 | High | `backend/commands/_helpers.py:20-22` | `send_set_mode` uses deprecated MAVLink msg 11 (SET_MODE) with ArduPilot custom_mode semantics. PX4 expects `MAV_CMD_DO_SET_MODE` (cmd 176) with `(base_mode, main_mode, sub_mode)` triplet. |
| P6 | High | `backend/commands/_setup.py:23-24, 47-58, 70` | Compass cal (42424/42425/42426) and accel-cal ACK (msg 77 with cmd=0,result=1) are ArduPilot extensions. PX4 ignores them. Calibration flow will silently no-op on PX4. |
| P7 | High | `backend/commands/_flight.py:23-24` | Force-disarm magic `p2=21196` is ArduPilot-only. PX4 force-disarm uses a different mechanism. |
| P8 | Medium | `src/lib/transport.ts:135-150` | WebSerial path uses `REQUEST_DATA_STREAM` (msg 66) which PX4 dropped support for. PX4 vehicles connected via WebSerial direct will receive no telemetry. |
| P9 | Medium | `src/lib/transport.ts:172-174` | `serialSendRtl()` sends mode=11 with comment "RTL mode for copter". Copter RTL = 6, not 11. This is a freestanding bug (independent of PX4) that suggests the WebSerial path is rarely exercised. |
| P10 | Medium | `backend/commands/_hardware.py:110-125` | Motor test uses ArduPilot's 1-based motor index convention. PX4 motor test semantics differ. |
| P11 | Medium | `backend/mavlink_handlers.py:244` | PreArm/Arm prefix matching is ArduPilot-only. PX4 uses different statustext prefixes — dedup/aggregation won't trigger. |
| P12 | Low | `backend/statustext_filter.py:1-38` | All leak filters are ArduPilot strings. PX4's statustext goes through unfiltered. |
| P13 | Low | `backend/drone_link.py:49-57`, registered handlers at `mavlink_handlers.py:634-666` | Handlers registered for AP-only msgs (158 MOUNT_STATUS, 163 AHRS, 168 WIND, 178 AHRS2, 191-192 MAG_CAL_*, 193 EKF_STATUS_REPORT) will never fire on PX4 — but no PX4-equivalent handlers exist (MOUNT_ORIENTATION 265, ESTIMATOR_STATUS 230, WIND_COV 231). UI fields for these are zero-default. |
| P14 | Low | `backend/drone_link.py:271-273` | When `vtype_raw > 0` but not a known plane/rover/sub type, code defaults to COPTER_MODES. For PX4 hexarotor (MAV_TYPE=13) you'd get ArduCopter mode names — correct by accident for some IDs, wrong for most. |

---

## Verdict

- **PX4**: The "ArduPilot + PX4" claim is not delivered. The frontend has scaffolding (a clean `FcAdapter` interface with a working PX4 adapter and unit tests) but it is **dead code** — no UI component or transport layer ever calls it. The backend has no PX4 awareness anywhere, and mode tables, calibration semantics, and mode-set commands are all ArduPilot-specific. A PX4 vehicle would connect (HEARTBEAT decodes fine), then 95% of the UI would be broken (modes garbled, calibration no-ops, EKF/wind/gimbal fields stuck at zero, mode buttons send AP integers PX4 doesn't recognize).
