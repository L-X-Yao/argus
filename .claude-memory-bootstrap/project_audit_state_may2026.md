---
name: project-audit-state-may2026
description: "Snapshot of the 2026-05-23 multi-agent protocol-layer audit — what was found, what's fixed, what's still open"
metadata: 
  node_type: memory
  type: project
  originSessionId: 2fc6fac5-ef50-46a5-9821-8f991a74a72d
---

A multi-agent audit pass on 2026-05-23 swept the Argus GCS MAVLink/ArduPilot interaction layer. ~35 commits landed; **all critical findings** in the audit reports at `docs/audits/` were fixed. Canonical feature/verification status now lives in `docs/FEATURE_CHECKLIST.md` (updated by this audit); design rationale for non-obvious code in `docs/protocol_design.md`.

**Why:** The user requested "0-cost verification" — verify everything possible before real-hardware testing, without optimizing for engineering hours. Parallel agents audited mission/log/param/drone_link/modules/edges/encoders/webserial/px4_pllink/frontend, each citing the local ArduPilot mount (`/home/plkj/samba/filght/ardupilot`) or pymavlink for ground truth.

**How to apply:** When the user asks "what's the state of X" or returns from a compressed-context session:
1. The repo at `github.com/L-X-Yao/argus` branch `main` is current — never assume any single fix from the audit is missing; check `docs/audits/README.md` for the per-area scorecard.
2. Notable load-bearing decisions that came out of this audit and are unlikely to be re-justified later:
   - The `_pad(p, n)` helper in `backend/mavlink_handlers.py` exists because MAVLink 2 zero-trim breaks every handler's offset reads when trailing fields are zero — see [[feedback-protocol-discipline]] for the supporting rule.
   - The accel cal ACK uses `command=0, result=MAV_RESULT_TEMPORARILY_REJECTED(1)` — a private ArduPilot semantic that contradicts the MAVLink spec. Cited at `backend/commands/_setup.py:cmd_cal_accel_next`. Do NOT "fix" it to look more like a normal ACK.
   - Disconnect cleanup (`_reset_session_state` in `drone_link.py`) clears _everything_ session-scoped; that's intentional because the in-loop silent reconnect would otherwise leak pending uploads + a 100MB log buffer.
   - The frontend `src/components/params/*.svelte` panels were untracked because `.gitignore` had `params/` (no leading slash). Fixed in commit `ea9fa58` — anchor to `/params/`.
3. PX4 support is essentially fictional — the `CLAUDE.md ## PX4 Status` section is the authoritative statement.
4. `tests/test_integration.py` failures were triaged in `docs/audits/audit_remaining.md` (categories A-D, mostly fixed; remainder is pre-existing xfail). Don't re-categorize from scratch.
5. The contract tests `test_contract_*.py` enforce: command-name parity, state-shape parity, handler↔CRC parity, pymavlink byte-level, locale completeness, encoder/decoder symmetry. If one of them fails, treat the diff as the source of truth — the test isn't paranoid, it caught real bugs every time it was added.
