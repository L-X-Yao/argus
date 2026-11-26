# Field validation plan, 2026-11-26

The next milestone is the first flight of Argus: a full ground calibration, then takeoff, RTL and a short mission on a real vehicle. This plan covers the work around that session; the flight procedure itself, with the roles and the abort calls, is in [FLIGHT_TEST.md](FLIGHT_TEST.md).

## Goal

Move v3.16.10 from bench-verified to verified in flight, and write the result back to [VERIFICATION.md](VERIFICATION.md). Fix and release v3.16.11 only if the session finds a software defect.

## Baseline (2026-11-26)

| Item | Value |
| --- | --- |
| Release | v3.16.10, installed on the field computer |
| Parameter pack | data-v2026.11.6 |
| Code | `main` `8f287d6` (document commits after the release tag `3164a84`); no code change since the release |
| Verified on hardware | arm, disarm and mode; parameters; mission round trip; log download; firmware flash; motor test; gyro and baro calibration; LOG_ERASE over the backend link |
| Not verified | takeoff, RTL and mission start; accelerometer, compass and level calibration; LOG_ERASE and motor test over WebSerial; other vehicles; RTK, gimbal, camera and ADS-B |

## Phases

### P0 Preparation (no vehicle)

1. Check the field computer: the Settings page shows 3.16.10, the parameter pack is data-v2026.11.6, and `logs/` is writable.
2. Re-check the five calibration flows in the panel against the controller firmware in use.
3. Prepare the field record sheet and the evidence list (tlog, screenshots, spotter notes). The filled record stays local; it never goes into the repository.
4. Add the ground calibration steps and abort conditions to FLIGHT_TEST.
5. Equipment: field computer, USB data cable, charged flight battery, level surface, an outdoor calibration spot away from steel.

### P1 Ground calibration (D-1; vehicle and site; no pilot)

The order, completion signals and abort conditions are in the "Ground calibration session" section of [FLIGHT_TEST.md](FLIGHT_TEST.md#ground-calibration-session). In short: gyro, accelerometer (six positions), level, compass (outdoors, away from metal), barometer, then RC only if a receiver is fitted.

- Do not combine P1 with P2. A first flight with freshly calibrated sensors adds a variable nobody can interpret. Recommended: separate days; if both happen on one day, power-cycle the vehicle and complete the P1 checks before the flight.
- Acceptance: every calibration ends on the controller's own acknowledgement or message; every compass reports success and the result is accepted before the reboot; parameters are read and backed up; the calibration rows of VERIFICATION.md get the date and what was seen.

### P2 First flight (D; pilot and spotter)

Follow the "First field flight" and "Abort" sections of [FLIGHT_TEST.md](FLIGHT_TEST.md): a 3D fix and a healthy EKF, takeoff at 10 m, hover, RTL; then a three-waypoint mission, RTL at the second waypoint, the flight summary and clearing the mission.

Evidence: the tlog, the event log, screenshots and the spotter's notes. Keep board names, firmware names, locations and serial numbers out of the repository.

### P3 Wrap-up and release decision (T+1)

| Result | Action |
| --- | --- |
| No software defect | Update the documents only (VERIFICATION, the README status wording, the project log); no release |
| Software defect | Fix through the six-step flow: code review by argus-kimi, evidence audit by argus-glm, a fail-first test, the full gate, then v3.16.11 |
| Feature gap | Record it; a separate decision, not part of this batch |

### P4 Deferred items (not part of this batch)

| Item | Trigger |
| --- | --- |
| Native-speaker review | A native speaker is available; the kit is in the data repository `docs/native-review/` |
| Windows code signing | Distribution outside the maintainer's own computers |
| ArduPilot GCS list entry | A real flight record exists after P2 |
| Upstream confirmation of the PSC alias rename group | The ArduPilot maintainers answer |

## Roles

| Role | Responsibility |
| --- | --- |
| Maintainer | Date, site, aircraft and pilot; flight authority; approve the documents |
| argus-ds (integrator) | P0, step guidance, log analysis, integration and release |
| argus-kimi | Code review of a fix batch |
| argus-glm | Evidence audit of the flight logs and the verification rows |

## Inputs needed before P1

1. Date, site, aircraft and pilot.
2. Link for the session: backend serial (recommended; the backend records a tlog by itself) or WebSerial.
3. Whether P1 and P2 are on separate days (recommended) or one.
