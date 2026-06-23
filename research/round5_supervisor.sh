#!/bin/bash
# Supervisor for the round5 strategy search.
#
# Restarts the python process whenever it dies (non-zero exit OR signal),
# resuming from the last checkpoint written by round5_search.py. Exits
# cleanly when the search reports successful completion.
#
# Detection of success: round5_search.py removes its checkpoint file on
# clean completion AND writes research/round5_results<suffix>.md. The
# supervisor checks for either signal.
#
# Usage:
#   nohup ./research/round5_supervisor.sh [offset] [suffix] > /tmp/round5_supervisor.log 2>&1 &
#
# Stop:
#   pkill -f round5_supervisor.sh && pkill -f round5_search.py
#
set -u

SCRIPT="/home/user/HFTBot/research/round5_search.py"
OFFSET="${1:-7820974790}"
SUFFIX="${2:-}"
RESULTS="/home/user/HFTBot/research/round5_results${SUFFIX}.md"
CHECKPOINT="/home/user/HFTBot/research/round5_checkpoint${SUFFIX}.pkl"
RUN_LOG="/tmp/round5_run${SUFFIX}.log"
MAX_BACKOFF_S=60

attempt=0
backoff=2

while true; do
    attempt=$((attempt + 1))
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: starting attempt #$attempt offset=$OFFSET suffix=$SUFFIX"
    if [ -f "$CHECKPOINT" ]; then
        ckpt_size=$(stat -c%s "$CHECKPOINT" 2>/dev/null || echo "?")
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: checkpoint exists (${ckpt_size} bytes) - search will resume from it"
    fi

    python3 -u "$SCRIPT" --offset "$OFFSET" --ckpt-suffix "$SUFFIX" >> "$RUN_LOG" 2>&1
    rc=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: process exited with code $rc"

    if [ ! -f "$CHECKPOINT" ] && [ -f "$RESULTS" ]; then
        results_age=$(( $(date +%s) - $(stat -c%Y "$RESULTS" 2>/dev/null || echo 0) ))
        if [ "$results_age" -lt 600 ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: round5 completed successfully. Exiting."
            exit 0
        fi
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: restarting in ${backoff}s..."
    sleep "$backoff"
    if [ "$backoff" -lt "$MAX_BACKOFF_S" ]; then
        backoff=$((backoff * 2))
        if [ "$backoff" -gt "$MAX_BACKOFF_S" ]; then
            backoff=$MAX_BACKOFF_S
        fi
    fi
done
