#!/bin/bash
# Watchdog for pattern_miner_v10. Auto-restarts on crash. Runs all night.
set -u
cd "$(dirname "$0")"

LOG=/tmp/v10_watchdog.log
MAX_ATTEMPTS=300
DELAY=15

attempt=0
while [ $attempt -lt $MAX_ATTEMPTS ]; do
    attempt=$((attempt + 1))
    echo "===== watchdog: attempt $attempt at $(date -u) =====" >> "$LOG"
    python3 -u -m research.pattern_miner_v10 >> /tmp/v10.log 2>&1
    rc=$?
    echo "===== miner exited code=$rc at $(date -u) =====" >> "$LOG"

    if [ -f "data/mined_v10_patterns.json" ]; then
        echo "===== watchdog: miner finished cleanly =====" >> "$LOG"
        exit 0
    fi

    echo "watchdog: miner died (rc=$rc), waiting ${DELAY}s..." >> "$LOG"
    sleep $DELAY
done

echo "===== watchdog: GAVE UP after $MAX_ATTEMPTS attempts =====" >> "$LOG"
exit 1
