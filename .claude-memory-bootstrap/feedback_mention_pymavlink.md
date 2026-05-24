---
name: feedback-mention-pymavlink
description: "When suggesting MAVLink codegen, first address why not just use pymavlink — the standard library for this"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 52be3f31-8ffd-4a54-93e8-029daa4fd798
---

Before recommending "build a MAVLink code generator," always address pymavlink (mavgen) first — it's the standard library that already does this. The recommendation to "generate from XML" is empty without answering why Argus doesn't use pymavlink directly.

**Why:** User called out that I proposed reinventing codegen without acknowledging the existing standard tool. Real reasons Argus might not use pymavlink include: binary size, PL-Link wrapper protocol, embedded packaging constraints, TypeScript frontend needs. These trade-offs must be stated explicitly.

**How to apply:** When discussing MAVLink tooling, start with pymavlink as the baseline. If recommending alternatives, explain the specific constraint that rules pymavlink out. Don't propose "write a generator" as if it's novel.
