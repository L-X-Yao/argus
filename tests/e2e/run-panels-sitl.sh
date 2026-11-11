#!/bin/bash
# Drives the panels of the built app with the mouse against real ArduCopter SITL through
# the backend, and reads the results back from the firmware on a port of its own.
#
# Boots what it needs. Needs ~/sitl/arducopter and ~/sitl/copter.parm, and Python with
# pymavlink for the log comparison. Each group gets a fresh SITL and backend.
#
# SITL_INSTANCE shifts the ports (5760 + 10 * instance, SERIAL1 2 above), and
# SITL_BACKEND_PORT the backend, to run beside another session.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SITL_DIR="${SITL_DIR:-$HOME/sitl}"
INSTANCE="${SITL_INSTANCE:-0}"
SPEEDUP="${SITL_SPEEDUP:-5}"
PORT="${SITL_BACKEND_PORT:-8300}"
SERIAL0=$((5760 + 10 * INSTANCE))
RUN_DIR="$(mktemp -d)"
SITL_PID=""
BACKEND_PID=""

stop() {
  if [ -n "$SITL_PID" ]; then
    pkill -P "$SITL_PID" 2>/dev/null || true
    kill "$SITL_PID" 2>/dev/null || true
    wait "$SITL_PID" 2>/dev/null || true
    SITL_PID=""
  fi
  if [ -n "$BACKEND_PID" ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
    BACKEND_PID=""
  fi
}
trap stop EXIT

# See run-webserial-sitl.sh for --serial0 tcp:0, the bash parent and the wait on the log.
start() {
  local model="$1" name="$2" dir="$RUN_DIR/$2"
  mkdir -p "$dir"
  (
    cd "$dir"
    setsid nohup bash -c "'$SITL_DIR/arducopter' --model '$model' --speedup $SPEEDUP -w -I $INSTANCE \
      --serial0 tcp:0 --defaults '$SITL_DIR/copter.parm,$REPO/tests/e2e/sitl-panels.parm' \
      --home -35.363261,149.165230,584,353 >> sitl.log 2>&1; \
      echo \"=== SITL exited with status \$?\" >> sitl.log" < /dev/null &
    echo $! > pid
  )
  SITL_PID="$(cat "$dir/pid")"
  for _ in $(seq 1 60); do
    grep -q 'SERIAL2 on TCP port' "$dir/sitl.log" 2>/dev/null && break
    sleep 1
  done
  grep -q 'SERIAL2 on TCP port' "$dir/sitl.log" || { echo "SITL never came up"; cat "$dir/sitl.log"; exit 1; }
  sleep 3

  ARGUS_NO_BROWSER=1 python3 "$REPO/run.py" --port "$PORT" > "$dir/backend.log" 2>&1 &
  BACKEND_PID=$!
  for _ in $(seq 1 30); do
    curl -sf "http://127.0.0.1:$PORT/health" > /dev/null && break
    sleep 1
  done
  curl -sf "http://127.0.0.1:$PORT/health" > /dev/null || { echo "backend never came up"; cat "$dir/backend.log"; exit 1; }
  export SITL_RUN_DIR="$dir"
}

chmod +x "$SITL_DIR/arducopter"
cd "$REPO"
npm run build > /dev/null

export ARGUS_URL="http://127.0.0.1:$PORT"
export SITL_TCP="127.0.0.1:$SERIAL0"
export SITL_PROBE_TCP="127.0.0.1:$((SERIAL0 + 2))"
PLAYWRIGHT=(npx playwright test --config=tests/playwright.sitl.config.ts)

start + setup
"${PLAYWRIGHT[@]}" tests/e2e/panels-sitl-params.spec.ts tests/e2e/panels-sitl-setup.spec.ts
stop

start + mission
"${PLAYWRIGHT[@]}" tests/e2e/panels-sitl-mission.spec.ts
stop

# One SITL for both: the tools read the log of the flight.
start + flight
"${PLAYWRIGHT[@]}" tests/e2e/panels-sitl-flight.spec.ts tests/e2e/panels-sitl-tools.spec.ts
stop

# The firmware's own fit on simulated samples can fail on a busy runner. The backend then
# reports the failure and accepts nothing, which is right, the offsets stay as they were, and
# the spec fails on that. A user would run the calibration again, and so does this, once, on a
# fresh vehicle: tests/e2e/webserial-sitl-cal.spec.ts does the same inside its test.
start calibration compass
if ! "${PLAYWRIGHT[@]}" tests/e2e/panels-sitl-compass.spec.ts; then
  echo "=== the compass spec failed: once more on a fresh vehicle. What the first one logged last:"
  tail -n 15 "$SITL_RUN_DIR/sitl.log" || true
  stop
  start calibration compass-again
  "${PLAYWRIGHT[@]}" tests/e2e/panels-sitl-compass.spec.ts
fi
