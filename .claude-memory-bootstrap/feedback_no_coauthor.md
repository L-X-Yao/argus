---
name: feedback-no-coauthor
description: Never add Co-Authored-By trailer to git commit messages
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 52be3f31-8ffd-4a54-93e8-029daa4fd798
---

Do not add "Co-Authored-By: Claude ..." or any co-author trailer to commit messages.

**Why:** User explicitly requested this — they don't want AI attribution in their git history.

**How to apply:** When creating git commits, end the message after the description. Never append Co-Authored-By lines.
