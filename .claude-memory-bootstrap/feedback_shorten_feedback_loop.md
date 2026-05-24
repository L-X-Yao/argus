---
name: feedback-shorten-feedback-loop
description: "Development bottleneck is feedback latency (code→hardware→observe), not test count — prioritize faster iteration loops"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 52be3f31-8ffd-4a54-93e8-029daa4fd798
---

Argus's real development bottleneck is the feedback loop: code → build → connect hardware → operate → observe. Single round takes minutes. Adding more tests doesn't help if the bug class (e.g., UI reactivity, $effect lifecycle) can only surface during real interaction.

**Why:** User pointed out that compass calibration bug was found only after 7 calibration attempts on real hardware. No amount of MAVLink protocol tests or contract checks would have caught it — it was a pure UI state management bug ($effect cursor accumulation + events array trim).

**How to apply:** When proposing quality measures, ask "does this shorten the time from writing wrong code to discovering it?" SITL automation (run calibration sequence → check event stream in seconds) and structured dev-mode tracing (ring buffer, not console.log) are higher ROI than "add another test layer." See [[feedback-argus-is-gcs]].
