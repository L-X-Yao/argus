#!/bin/bash
# Runs the WebSerial specs against real ArduCopter SITL: a full flight, a vehicle that
# is not system 1 losing its USB in the air, then the two interactive calibrations on
# the `calibration` vehicle model.
#
# Needs ~/sitl/arducopter and ~/sitl/copter.parm, and the Vite dev server on
# VITE_URL (default http://localhost:5173). The specs reach the page's own modules
# through it, so restart Vite after editing anything under src/: a hot update gives
# the app a second copy of a module, and the specs then talk to the wrong one.
#
# SITL_INSTANCE shifts the ports (5760 + 10 * instance) to run beside another SITL.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SITL_DIR="${SITL_DIR:-$HOME/sitl}"
INSTANCE="${SITL_INSTANCE:-0}"
SPEEDUP="${SITL_SPEEDUP:-5}"
SERIAL0=$((5760 + 10 * INSTANCE))
SERIAL1=$((SERIAL0 + 2))
RUN_DIR="$(mktemp -d)"
SITL_PID=""

stop_sitl() {
  if [ -n "$SITL_PID" ]; then
    pkill -P "$SITL_PID" 2>/dev/null || true
    kill "$SITL_PID" 2>/dev/null || true
    wait "$SITL_PID" 2>/dev/null || true
    SITL_PID=""
  fi
}
trap stop_sitl EXIT

# --serial0 tcp:0, not the default tcp:0:wait: boot must not gate on the first
# client (libraries/AP_HAL_SITL/UARTDriver.cpp:117). The bash parent keeps SITL
# alive on hosted runners, and the log, not a TCP probe, tells when it is up:
# see sitl-smoke in .github/workflows/ci.yml.
start_sitl() {
  local model="$1" defaults="$2" dir="$RUN_DIR/$1"
  mkdir -p "$dir"
  (
    cd "$dir"
    setsid nohup bash -c "'$SITL_DIR/arducopter' --model '$model' --speedup $SPEEDUP -w -I $INSTANCE \
      --serial0 tcp:0 --defaults '$defaults' --home -35.363261,149.165230,584,353 >> sitl.log 2>&1; \
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
}

chmod +x "$SITL_DIR/arducopter"
cd "$REPO"
export SITL_TCP="127.0.0.1:$SERIAL0"
PLAYWRIGHT=(npx playwright test --config=tests/playwright.config.ts --project=chromium)

start_sitl + "$SITL_DIR/copter.parm,$REPO/tests/e2e/sitl-gimbal.parm"
"${PLAYWRIGHT[@]}" tests/e2e/webserial-sitl.spec.ts
stop_sitl

start_sitl + "$SITL_DIR/copter.parm,$REPO/tests/e2e/sitl-sysid.parm"
"${PLAYWRIGHT[@]}" tests/e2e/webserial-sitl-link.spec.ts
stop_sitl

start_sitl calibration "$SITL_DIR/copter.parm"
SITL_DRIVER_TCP="127.0.0.1:$SERIAL1" "${PLAYWRIGHT[@]}" tests/e2e/webserial-sitl-cal.spec.ts
