---
name: test-real-data-flow
description: "Always test with real input types from the actual caller, not just config/schema validation"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 52be3f31-8ffd-4a54-93e8-029daa4fd798
---

Test the actual data path, not just that config values exist. When adding validation at a system boundary (e.g. WebSocket message parsing), test with the real types the caller sends — HTML select produces strings, JSON numbers may arrive as float, etc. Extract validation into pure testable functions rather than inlining in async methods.

**Why:** Added `isinstance(baud, int)` validation but only tested that `cfg.VALID_BAUD_RATES` contained correct values. Frontend `<select>` sends baud as string `"57600"`, which failed the isinstance check silently. Bug shipped and broke serial connections.

**How to apply:** When writing input validation, always include tests with the actual types the upstream sends (string from HTML, float from JSON, None for missing fields). Extract validation logic into standalone pure functions testable without mocking the full async context.
