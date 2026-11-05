## Summary

<!-- What does this PR do and why? -->

## Checklist

- [ ] `npx vitest run` — frontend tests pass
- [ ] `python -m pytest tests/test_unit_*.py tests/test_contract_*.py` — backend tests pass
- [ ] `npx svelte-check` — 0 errors, 0 warnings
- [ ] `ruff check backend/ scripts/ tests/` — lint clean
- [ ] Commit messages follow `<type>: <description>` convention
- [ ] FC-coupled code cites upstream ArduPilot/PX4 source `file:line`
- [ ] Changes to what goes to or comes from the FC land on both links, or `docs/VERIFICATION.md` shows `n/a`
- [ ] `docs/VERIFICATION.md` matches what was actually run
