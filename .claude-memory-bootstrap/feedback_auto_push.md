---
name: feedback-auto-push
description: "After committing, push to origin without asking — same agency as auto-commit"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2fc6fac5-ef50-46a5-9821-8f991a74a72d
---

When local work is committed, push to origin automatically. Don't pause to confirm.

**Why:** User explicitly granted this on 2026-05-23 after a 20-commit session — they value momentum and dislike round-trips for routine git ops. Pairs with the existing [[feedback-auto-commit]] memory: commit when done, push when committed.

**How to apply:** After every `git commit`, immediately `git push origin <branch>` (typically `main`). Still confirm before destructive operations (`--force`, `--force-with-lease`, branch deletion). For branches without an upstream, use `-u` to set it on first push. If the push fails (rejected by remote, hook block), report the error and stop — don't retry blindly or force.
