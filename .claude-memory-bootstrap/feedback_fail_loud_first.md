---
name: feedback-fail-loud-first
description: Prefer fail-loud runtime checks (log+drop unknown) over adding tests — cheapest way to surface protocol bugs
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 52be3f31-8ffd-4a54-93e8-029daa4fd798
---

When proposing quality improvements, always consider fail-loud runtime checks before adding tests or CI scripts. Example: drone_link.py CRC check silently passes unknown msg IDs (crc_extra==0 → accept frame). Changing to log+drop costs 30 minutes and catches "msg ID not in table" bugs at first run, no tests needed.

**Why:** User pointed out that the CRC_EXTRA dict missing entries for msg 191/192 would have been caught immediately if unknown msg IDs logged a warning instead of silently passing. This is cheaper than any CI check.

**How to apply:** When analyzing bugs or proposing fixes, always ask "could a runtime assertion/warning have caught this earlier?" before reaching for test infrastructure. Prioritize P0: fail-loud > P0: CI contract checks > P1: codegen > P2: property tests.
