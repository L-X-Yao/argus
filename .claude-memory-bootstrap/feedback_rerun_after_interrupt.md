---
name: feedback-rerun-after-interrupt
description: "After a manual interrupt, re-run the test suite before committing — don't assume the pre-interrupt results still cover the post-interrupt state"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2fc6fac5-ef50-46a5-9821-8f991a74a72d
---

After the user manually interrupts a task and then says "continue", do not commit based on test results that ran BEFORE the interrupt — re-run pytest + vitest + svelte-check + ruff before the commit.

**Why:** During Phase P (2026-05-24, commit `c6b9e0d`) the user interrupted mid-task between "all checks green" and the final commit. The work after the interrupt was documentation-only (CLAUDE.md / README / FEATURE_CHECKLIST text edits), and the commit was pushed without re-validation. The user pushed back: "刚刚测试被我手动中断了，你不重新执行？" — they expect the test gate to run immediately before the commit, not from earlier in the session, regardless of whether the post-interrupt edits were "obviously" docs-only. Their reasoning is that interrupt boundaries change the trust state.

**How to apply:** Any time the flow is `[run tests → user interrupt → user says continue → make more edits → commit]`, treat it as if no tests had run. Run the full quick gate again (pytest unit+contract, vitest, svelte-check, ruff) right before `git commit`. The 30 seconds of test time is cheap insurance vs. shipping a regression that the user would otherwise hit on next pull.

Pairs with [[feedback-shorten-feedback-loop]] — the user wants the feedback loop validated at the COMMIT boundary, not somewhere upstream of it.
