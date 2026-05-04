#!/bin/bash
# Watchdog wrapper for pipeline_orchestrator.
# Restarts the python process up to MAX_RESTARTS times if it exits non-zero
# OR if it dies from a signal. Each restart waits 30s.
# Designed to survive the kind of session-recycle / transient OOM kills
# that took down our earlier overnight runs.

set -u
cd "$(dirname "$0")"

MAX_RESTARTS=20
RESTART_DELAY=30
LOG=/tmp/pipeline.log
STATE=data/pipeline_state.json

attempt=0
while [ $attempt -lt $MAX_RESTARTS ]; do
    attempt=$((attempt + 1))
    echo "===== supervisor: attempt $attempt of $MAX_RESTARTS at $(date -u) =====" \
        | tee -a "$LOG"

    # Run orchestrator in foreground of THIS shell — if it dies, we loop.
    python3 -u -m research.pipeline_orchestrator >> "$LOG" 2>&1
    exit_code=$?
    echo "===== supervisor: orchestrator exited with code $exit_code =====" \
        | tee -a "$LOG"

    # If state file says all phases ok, we're done.
    if [ -f "$STATE" ] && python3 -c "
import json, sys
s = json.load(open('$STATE'))
phases = s.get('phases', {})
needed = ['raw_validate', 'apply_raw_survivors', 'live_sim_raw_survivors', 'final_report']
done = all(phases.get(p, {}).get('status') in ('ok', 'skip') for p in needed)
sys.exit(0 if done else 1)
"; then
        echo "===== supervisor: all critical phases complete — exiting clean =====" \
            | tee -a "$LOG"
        exit 0
    fi

    echo "supervisor: waiting ${RESTART_DELAY}s before retry…" | tee -a "$LOG"
    sleep $RESTART_DELAY
done

echo "===== supervisor: GAVE UP after $MAX_RESTARTS attempts =====" | tee -a "$LOG"
exit 1
