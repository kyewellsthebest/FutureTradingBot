#!/bin/bash
# Supervisor for the round3 strategy search.
#
# Restarts the python process whenever it dies (non-zero exit OR signal),
# resuming from the last checkpoint written by round3_search.py. Exits
# cleanly when the search reports successful completion.
#
# Detection of success: round3_search.py removes its checkpoint file on
# clean completion AND writes research/round3_results.md. The supervisor
# checks for either signal.
#
# Usage:
#   nohup ./research/round3_supervisor.sh > /tmp/round3_supervisor.log 2>&1 &
#
# Stop:
#   pkill -f round3_supervisor.sh && pkill -f round3_search.py
#
set -u

SCRIPT="/home/user/HFTBot/research/round3_search.py"
RESULTS="/home/user/HFTBot/research/round3_results.md"
CHECKPOINT="/home/user/HFTBot/research/round3_checkpoint.pkl"
RUN_LOG="/tmp/round3_run.log"
MAX_BACKOFF_S=60

attempt=0
backoff=2

while true; do
    attempt=$((attempt + 1))
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: starting attempt #$attempt"
    if [ -f "$CHECKPOINT" ]; then
        ckpt_size=$(stat -c%s "$CHECKPOINT" 2>/dev/null || echo "?")
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: checkpoint exists (${ckpt_size} bytes) — search will resume from it"
    fi

    python3 -u "$SCRIPT" >> "$RUN_LOG" 2>&1
    rc=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: process exited with code $rc"

    # Success path: round3_search.py removed the checkpoint AND wrote the results.
    if [ ! -f "$CHECKPOINT" ] && [ -f "$RESULTS" ]; then
        # Was results recently written? (mtime in last 600s)
        results_age=$(( $(date +%s) - $(stat -c%Y "$RESULTS" 2>/dev/null || echo 0) ))
        if [ "$results_age" -lt 600 ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: round3 completed successfully (results fresh, no checkpoint). Exiting."
            exit 0
        fi
    fi

    # Failure path: restart with backoff (capped). The script's
    # checkpoint, written every 5M ticks, lets the next attempt
    # resume from the last saved offset.
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: restarting in ${backoff}s..."
    sleep "$backoff"
    if [ "$backoff" -lt "$MAX_BACKOFF_S" ]; then
        backoff=$((backoff * 2))
        if [ "$backoff" -gt "$MAX_BACKOFF_S" ]; then
            backoff=$MAX_BACKOFF_S
        fi
    fi
done
