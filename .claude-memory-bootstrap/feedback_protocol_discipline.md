---
name: feedback-protocol-discipline
description: "For FC-coupled code, cite the upstream source file:line in a comment — same rule as CLAUDE.md, mirrored here for memory recall"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2fc6fac5-ef50-46a5-9821-8f991a74a72d
---

Any code that talks to ArduPilot or PX4 — MAVLink commands, ACKs, msg field offsets, CRC extras, calibration handshakes, mode IDs, parameter semantics — must cite the upstream source file:line in a code comment. Do not infer from the MAVLink spec alone.

**Why:** Flight controllers regularly hijack generic MAVLink fields for private protocols. "What the spec says" diverges from "what the FC actually does." This was the root cause of the entire 2026-05-23 audit pass — silent bugs everywhere because code had been written from guesses. Two real examples in this repo:

- `AP_AccelCal::handle_command_ack` requires `command ≤ 6` and `result == 1`, not the MAV_CMD/MAV_RESULT values an unaware reader would write. Cited at `backend/commands/_setup.py:cmd_cal_accel_next`.
- Mag cal progress is binary `MAG_CAL_PROGRESS` (msg 191) / `MAG_CAL_REPORT` (192), not STATUSTEXT. Cited at `backend/mavlink_handlers.py:handle_mag_cal_progress`.

**How to apply:** Workflow when implementing or debugging FC-coupled code:
1. Stop guessing.
2. Fetch the AP/PX4 source — local mount at `/home/plkj/samba/filght/ardupilot` if available, else `raw.githubusercontent.com/ArduPilot/ardupilot/master/...` via WebFetch.
3. Quote the exact condition or field reference in a comment above your implementation.
4. Cross-check against pymavlink (`pip install pymavlink` is set up) for byte-level encoding when wire-format is in question.

The `docs/audits/` folder contains the receipts for protocol claims that have already been verified. Use it before re-auditing the same area.

Same rule lives in CLAUDE.md `## Protocol Code Discipline`. This memory exists so the rule survives a context window flush.
