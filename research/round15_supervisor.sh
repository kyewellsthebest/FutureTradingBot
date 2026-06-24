#!/bin/bash
# Round 15 supervisor — restart on any non-zero exit.
set -u
SCRIPT="/home/user/HFTBot/research/round15_search.py"
CHECKPOINT="/home/user/HFTBot/research/round15_checkpoint.pkl"
RESULTS="/home/user/HFTBot/research/round15_results.md"
RUN_LOG="/tmp/round15_run.log"
MAX_BACKOFF_S=60

attempt=0
backoff=2
while true; do
    attempt=$((attempt + 1))
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: starting attempt #$attempt" >> "$RUN_LOG"
    if [ -f "$CHECKPOINT" ]; then
        sz=$(stat -c%s "$CHECKPOINT" 2>/dev/null || echo "?")
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: checkpoint exists (${sz} bytes) — resuming" >> "$RUN_LOG"
    fi
    python3 -u "$SCRIPT" >> "$RUN_LOG" 2>&1
    rc=$?
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: process exited code=$rc" >> "$RUN_LOG"
    if [ ! -f "$CHECKPOINT" ] && [ -f "$RESULTS" ]; then
        age=$(( $(date +%s) - $(stat -c%Y "$RESULTS" 2>/dev/null || echo 0) ))
        if [ "$age" -lt 600 ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: results fresh, exiting" >> "$RUN_LOG"
            exit 0
        fi
    fi
    sleep "$backoff"
    if [ "$backoff" -lt "$MAX_BACKOFF_S" ]; then
        backoff=$((backoff * 2))
        [ "$backoff" -gt "$MAX_BACKOFF_S" ] && backoff=$MAX_BACKOFF_S
    fi
done
