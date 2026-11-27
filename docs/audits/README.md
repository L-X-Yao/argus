# Audit Reports

This folder holds point-in-time audit reports from several campaigns, starting
with the 2026-05-23 review of Argus GCS. The May reports are the raw agent
output from a single audit pass, preserved so future contributors can see what
was checked, what was found, and what was deliberately deferred. Later reports
carry their own Status, Verification and Accepted-residuals sections.

Each report is dated by the file's mtime in the original /tmp scratch
location; they were copied here verbatim and not re-edited, except that
`audit_px4.md` lost its PL-Link sections when that transport was removed.

PL-Link was removed in v3.7. Other references to it, and to `sim_pllink.py`
(now `simulator.py`), are historical.

## Index

| File | Scope | Result |
|---|---|---|
| `audit_modes.md` | Flight-mode tables vs ArduCopter/Plane/Rover/Sub `mode.h` | Rover ID 5 mislabeled + 32 missing modes. **Fixed.** |
| `audit_log.md` | Log download protocol vs `AP_Logger_MAVLinkLogTransfer.cpp` | 6 critical state-machine bugs. **Fixed.** |
| `audit_param.md` | Parameter protocol vs `GCS_Param.cpp` | 8 critical + 9 partial bugs. **Most fixed.** |
| `audit_mission.md` | Mission upload/download vs `AP_Mission.cpp` | 2 critical + 18 partial. **Critical fixed.** |
| `audit_drone_link.md` | DroneLink main loop / reconnect / locking | 6 critical + 9 warnings. **All critical fixed.** |
| `audit_encoders.md` | Frontend `messages.ts` encoders vs pymavlink | **0 bugs.** Verified byte-perfect. |
| `audit_webserial.md` | Frontend MAVLink codec (WebSerial direct mode) | 1 offset bug, 4 edge gaps, 13 missing decoders. **All fixed.** |
| `audit_px4.md` | PX4 claim vs implementation | PX4 unwired (documented in CLAUDE.md). |
| `audit_modules.md` | connection/ws_manager/app/auth/video sweep | 5 critical (security), 23 medium. **Critical + most medium fixed.** |
| `audit_edges.md` | Specific partial findings (equator, NAV_SPLINE, VTOL takeoff, etc.) | 5 real bugs, 3 fixed in-place, 2 documented. |
| `audit_frontend.md` | Svelte 5 components/stores reactivity + lifecycle | 40+ findings, 10 fixed in-place. |
| `audit_remaining.md` | sim_pllink + build scripts + run.py + test_integration triage + remaining app.py routes | 6 critical + 10 medium + 7 low. **19 fixed in-place** including sim protocol auto-detect, mbtiles path traversal, PyInstaller hidden-import for `backend.commands._*`. |
| `sitl_validation_2026-05-24.md` | End-to-end check against real ArduCopter SITL v4.6.3 — telemetry, mission round-trip, command pipeline, params, fence, Phase P WS propagation, custom-identity FC rendering | **7 PASS, 1 partial (full mission flight), 4 blocked on USB**. Real-AP corroboration for the protocol assertions that the unit suite makes under mocks. |
| `panel_reality_2026-07-13.md` | UI panel reality snapshot: every panel under `src/components/` against the ws commands, routes and telemetry it uses | Superseded by [VERIFICATION.md](../VERIFICATION.md); kept as a historical snapshot. |
| `audit_2026-11-16.md` | Full audit of `3c8945b`: backend auth/network/MCP and frontend XSS/CSP | 2 H / 6 M / 19 L. H1, H2 and M1–M6 fixed in v3.10.5, the remaining lows in v3.10.6; accepted residuals are in the report. |
| `audit_2026-11-24.md` | 165 commits since `6320b4e`: backend external surface, frontend, protocol/AI/data | 0 H / 15 M / 20 L. All 15 M fixed, 18 L fixed, 2 L accepted; shipped in v3.16.9, hardening in v3.16.10. |

## What the May campaign left open (historical)

The 32 integration failures named here were fixed later; the suite passes 69.
NTRIP has since been implemented.

- **PX4 support is non-existent in production.** See `CLAUDE.md ## PX4 Status`.
- Several Svelte components (F-17, F-36, F-39 in `audit_frontend.md`) need
  larger refactors — ack-driven state instead of hard timers.
- The 7 contract-test orphans (NTRIP commands + 5 dead backend handlers) are
  product decisions: implement or delete.

## Accepted residuals (November campaigns)

- 2026-11-16: a chunked upload without Content-Length still reaches multipart
  parsing; ffmpeg resolves the video hostname a second time; a stalled serial
  write can hold the state lock up to 1 s; roles remain a courtesy.
- 2026-11-24: a video URL that redirects to loopback is still followed; a manual
  edit of the parameter pack needs a restart; a log removed during analysis
  returns an internal error; `csv_left` is API-only.

## The discipline this enforces

Every audit cross-references the Argus source against either ArduPilot
source (a local ArduPilot checkout during the session)
or pymavlink (`pip install pymavlink`) as ground truth. The rule in
`CLAUDE.md ## Protocol Code Discipline` says all FC-coupled code must cite
the upstream source file:line in a comment. The audits in this folder are
the receipts for the citations that have already landed.
