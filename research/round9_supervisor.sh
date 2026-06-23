#!/bin/bash
# Supervisor for the round9 strategy search.
# Restarts the python process whenever it dies, resuming from checkpoint.
# Usage:
#   nohup ./research/round9_supervisor.sh [offset] [suffix] [max_days] > /tmp/round9_supervisor.log 2>&1 &
# Stop:
#   pkill -f round9_supervisor.sh && pkill -f round9_search.py
set -u

SCRIPT="/home/user/HFTBot/research/round9_search.py"
OFFSET="${1:-7820974790}"
SUFFIX="${2:-}"
MAX_DAYS="${3:-60}"
RESULTS="/home/user/HFTBot/research/round9_results${SUFFIX}.md"
CHECKPOINT="/home/user/HFTBot/research/round9_checkpoint${SUFFIX}.pkl"
RUN_LOG="/tmp/round9_run${SUFFIX}.log"
MAX_BACKOFF_S=60

attempt=0
backoff=2

while true; do
    attempt=$((attempt + 1))
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: starting attempt #$attempt offset=$OFFSET suffix=$SUFFIX max_days=$MAX_DAYS"
    if [ -f "$CHECKPOINT" ]; then
        ckpt_size=$(stat -c%s "$CHECKPOINT" 2>/dev/null || echo "?")
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: checkpoint exists (${ckpt_size} bytes) - search will resume from it"
    fi

    python3 -u "$SCRIPT" --offset "$OFFSET" --ckpt-suffix "$SUFFIX" --max-days "$MAX_DAYS" >> "$RUN_LOG" 2>&1
    rc=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: process exited with code $rc"

    if [ ! -f "$CHECKPOINT" ] && [ -f "$RESULTS" ]; then
        results_age=$(( $(date +%s) - $(stat -c%Y "$RESULTS" 2>/dev/null || echo 0) ))
        if [ "$results_age" -lt 600 ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: round9 completed successfully. Exiting."
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
