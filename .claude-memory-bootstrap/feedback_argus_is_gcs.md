---
name: feedback-argus-is-gcs
description: "Argus is a GCS (display/control), not a flight controller — don't overdramatize safety risk or recommend heavy-weight processes"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 52be3f31-8ffd-4a54-93e8-029daa4fd798
---

Argus is a Ground Control Station, not a flight controller. The FC has its own safety loops. Calling Argus a "safety-critical control system" leads to over-engineering (mutation testing, aerospace-grade processes).

**Why:** User corrected my analysis that framed GCS bugs as "causing crashes." A wrong altitude display affects operator judgment but the FC independently maintains flight safety. The risk profile is real but not flight-critical.

**How to apply:** When analyzing Argus bugs or proposing quality measures, frame risk accurately (operator confusion, not vehicle crash). Don't recommend heavy processes (mutation testing, formal verification) — prefer lightweight, high-ROI measures. See [[feedback-fail-loud-first]] and [[feedback-shorten-feedback-loop]].
