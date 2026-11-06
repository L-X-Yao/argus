#!/bin/bash
# Flies real ArduCopter firmware in SITL for SOAK_MINUTES (default 60) with the built app
# open in a browser, and writes memory samples to soak.csv. Run it before a release that
# touched the link, the stores or the map. Needs `npm run build` and ~/sitl.
#
# SITL_INSTANCE shifts SITL's ports, and SOAK_PORT is the backend's.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SITL_DIR="${SITL_DIR:-$HOME/sitl}"
INSTANCE="${SITL_INSTANCE:-0}"
PORT="${SOAK_PORT:-8100}"
SERIAL0=$((5760 + 10 * INSTANCE))
RUN_DIR="$(mktemp -d)"
SITL_PID=""
BACKEND_PID=""

stop_all() {
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  if [ -n "$SITL_PID" ]; then
    pkill -P "$SITL_PID" 2>/dev/null || true
    kill "$SITL_PID" 2>/dev/null || true
  fi
}
trap stop_all EXIT

cd "$RUN_DIR"
setsid nohup bash -c "'$SITL_DIR/arducopter' --model + --speedup ${SITL_SPEEDUP:-5} -w -I $INSTANCE \
  --serial0 tcp:0 --defaults '$SITL_DIR/copter.parm' --home -35.363261,149.165230,584,353 >> sitl.log 2>&1" \
  < /dev/null > /dev/null 2>&1 &
SITL_PID=$!
for _ in $(seq 1 60); do
  grep -q 'SERIAL2 on TCP port' sitl.log 2>/dev/null && break
  sleep 1
done
sleep 3

cd "$REPO"
ARGUS_NO_BROWSER=1 ARGUS_PORT="$PORT" python3 -m uvicorn backend.app:app --host 127.0.0.1 --port "$PORT" --log-level warning &
BACKEND_PID=$!
for _ in $(seq 1 30); do
  curl -sf --noproxy '*' "http://127.0.0.1:$PORT/health" > /dev/null && break
  sleep 1
done

SOAK_MINUTES="${SOAK_MINUTES:-60}" SOAK_BACKEND="127.0.0.1:$PORT" SOAK_BACKEND_PID="$BACKEND_PID" \
  SOAK_FC="127.0.0.1:$SERIAL0" SOAK_OUT="${SOAK_OUT:-$REPO/soak.csv}" \
  npx playwright test --config=tests/playwright.config.ts --project=chromium --retries=0 tests/e2e/soak.spec.ts
