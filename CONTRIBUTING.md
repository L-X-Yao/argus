# Contributing to Argus

Thanks for your interest! Here's how to get started.

## Setup

```bash
npm install && pip install -e '.[dev]'
python run.py --sim   # backend + simulator
npm run dev           # frontend dev server at :5173
```

Enable the hooks once per clone with `git config core.hooksPath .githooks`. The pre-commit hook runs lint + type-check; pre-push runs the unit, contract and frontend tests.

## Before Submitting a PR

All five must pass:

```bash
npx svelte-check --tsconfig ./tsconfig.json   # 0 errors 0 warnings
npx vitest run                                # frontend tests
python -m pytest tests/test_unit_*.py tests/test_contract_*.py  # backend tests
ruff check backend/ scripts/ tests/           # Python lint
npm run format:check                          # Prettier + ruff format
```

## What CI Checks

CI runs on every push to `main` and every PR. On top of the five checks above, it requires:

| Check | Requirement |
| --- | --- |
| Generated files | `scripts/sync_modes.py` and `scripts/sync_crc.py` leave no diff |
| Backend coverage | At least 95% |
| Frontend coverage | At least 85% of lines |
| Build | `npm run build` succeeds |
| Bundle size | `dist/assets/` is at most 3 MiB |
| npm audit | No critical issues |
| Integration tests | `tests/test_integration.py`: real backend and simulator over WebSocket. `tests/test_integration_rest.py`: REST routes with real files and the real terrain and firmware servers |
| macOS | Unit and contract tests on `macos-latest`. SITL ships as a Linux binary, so the SITL jobs stay on Linux |
| SITL smoke test | `tests/sitl_verify.py`: a full flight on real ArduCopter firmware in simulation, through the backend |
| WebSerial on SITL | `tests/e2e/run-webserial-sitl.sh`: a full flight and both interactive calibrations, through the browser stack |
| Other vehicles | `tests/sitl_vehicles.py` and `tests/sitl_flights.py`: Plane, QuadPlane, Rover and Sub on real firmware: recognition, mode numbers, parameters, and a whole mission each |
| Links | `tests/sitl_links.py`: what the jobs above leave out, through the backend on real firmware |
| End-to-end tests | Playwright specs in `tests/e2e/` |

`make test-integration` runs the integration tests locally, in about 3 minutes.

CI only runs the specs named in `.github/workflows/ci.yml`, so add a new spec to that list.

## Commit Messages

Format: `<type>: <imperative description>`

Types: `feat` / `fix` / `perf` / `refactor` / `test` / `docs` / `ci` / `chore`

`scripts/make-release.sh` writes the `release:` commit. Release notes are built from commit subjects, so write them for someone reading the changelog.

## Branches

`main` is the only long-lived branch. Contributors open a PR against it; the maintainer can push to it directly. GitHub blocks force pushes to `main` and deleting it, but requires neither a PR nor a passing CI run, so check the run after pushing and fix a red `main` before starting anything else.

## Protocol Code

Code coupled to ArduPilot behavior (MAVLink commands, ACKs, field offsets, mode IDs, parameter semantics) must cite the upstream source in a code comment. See `CLAUDE.md` for details and examples.

## Two Links

Argus reaches the flight controller over two separate stacks: the Python backend (`backend/`) and WebSerial in the browser (`src/lib/serial.ts`, `src/lib/transport.ts`, `src/lib/serialHandlers.ts`). A change to what goes to or comes from the FC has to land in both. If one link cannot support it, `docs/VERIFICATION.md` shows `n/a` for that link.

Contract tests keep the two aligned:

| Test | Compares |
| --- | --- |
| `tests/test_contract_serial_dispatch.py` | Command names. A backend-only command goes in its `_WS_ONLY` list |
| `tests/test_contract_dualstack_parity.py` | Frames both stacks send for the same operation |
| `tests/test_contract_dualstack_state_parity.py` | State both stacks produce from the same frames |

## Tests

- A bug fix comes with a test that fails without the fix.
- Test with what the real caller sends: a `<select>` sends strings, JSON numbers can arrive as floats, fields can be missing.
- When two layers must agree, compare their output (wire bytes, call arguments, resulting state). Matching names do not show that they agree.
- Before adding a test for bad input, ask whether a runtime check that logs and drops it would catch the problem sooner.
- A bug seen only on hardware gets a replay test, see `docs/DEV_WORKFLOW.md`. Only use recordings from hardware you own and may publish, and run them through `scripts/scrub_tlog.py` first.

## Review

Bug fixes and FC-facing changes get a second read before release, from a person or a new AI session that did not write them. Give the reviewer the diff, not your conclusion.

## Verification Status

`docs/VERIFICATION.md` records how far every command, message, REST route, panel and platform feature has been tested.

- `tests/test_contract_verification_doc.py` fails until a new command, message, route or panel has a row and the summary matches the tables.
- Set the level to what actually ran, not to what should work.
- After a session on a real flight controller, update the rows it covered and the dates in the Evidence column. Leave board and firmware names out.

## i18n

All user-visible strings use `t('key')` from `src/lib/i18n.svelte.ts`. Add new keys to `src/lib/locales/zh.ts` and `en.ts`, then run `python scripts/sync_locales.py --write` to propagate to the other 8 locales.

## Formatting

`npm run format` applies Prettier to `src/` and `ruff format` to the Python code, and CI fails on anything it would change. Run it after `scripts/sync_locales.py`, which writes long strings on one line.

## Releases

Versions are `MAJOR.MINOR.PATCH`: PATCH for fixes, MINOR for new features, MAJOR for changes that break existing setups.

Release from `main`, on a commit whose CI run is green. `scripts/make-release.sh` checks the branch and a clean tree, but not CI.

1. Build the Windows package with `python scripts/build_package.py`. It writes a zip to `release/`.
2. Extract the zip on a real Windows machine and start the backend and the simulator. Check the REST API, the WebSocket, that a request from another origin is rejected, and token login.
3. Run `bash scripts/make-release.sh X.Y.Z`. It bumps the version, runs the frontend, unit and contract tests, commits, tags and pushes.
4. The tag starts `.github/workflows/release.yml`, which builds the zip and publishes the GitHub Release.
5. Repeat step 2 on the published zip.

## Reporting Issues

- Bugs and feature requests: [GitHub Issues](https://github.com/L-X-Yao/argus/issues)
- Security vulnerabilities: see `SECURITY.md`
