#!/bin/bash
# Watchdog for pattern_miner_v6. Auto-restarts on crash. Survives session
# recycles. Saves progress every 25 strategies via the miner itself.
set -u
cd "$(dirname "$0")"

LOG=/tmp/v6_watchdog.log
MAX_ATTEMPTS=50
DELAY=20

attempt=0
while [ $attempt -lt $MAX_ATTEMPTS ]; do
    attempt=$((attempt + 1))
    echo "===== watchdog: attempt $attempt at $(date -u) =====" >> "$LOG"
    python3 -u -m research.pattern_miner_v6 >> /tmp/v6.log 2>&1
    rc=$?
    echo "===== miner exited code=$rc at $(date -u) =====" >> "$LOG"

    # If the miner wrote the final output, we're done
    if [ -f "data/mined_v6_patterns.json" ] && \
       python3 -c "
import json, sys
d = json.load(open('data/mined_v6_patterns.json'))
sys.exit(0 if d.get('n_strategies', 0) > 100 else 1)
" 2>/dev/null; then
        echo "===== watchdog: miner finished cleanly =====" >> "$LOG"
        exit 0
    fi

    echo "watchdog: miner died (rc=$rc), waiting ${DELAY}s before retry..." >> "$LOG"
    sleep $DELAY
done

echo "===== watchdog: GAVE UP after $MAX_ATTEMPTS attempts =====" >> "$LOG"
exit 1
