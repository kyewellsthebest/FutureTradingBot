#!/bin/bash
# Round 17 supervisor: restarts the search if it dies.
set -u
cd /home/user/HFTBot
LOG=/home/user/HFTBot/research/round17.log
ERR=/home/user/HFTBot/research/round17.err
RESULTS=/home/user/HFTBot/research/round17_results.md

MAX_RESTARTS=20
i=0
while [ $i -lt $MAX_RESTARTS ]; do
    if [ -f "$RESULTS" ]; then
        echo "[supervisor] Results file exists. Exiting." | tee -a "$LOG"
        exit 0
    fi
    echo "[supervisor] Attempt $((i+1))/$MAX_RESTARTS at $(date)" | tee -a "$LOG"
    /usr/bin/env python3 /home/user/HFTBot/research/round17_search.py \
        >>"$LOG" 2>>"$ERR"
    rc=$?
    echo "[supervisor] Exit code: $rc" | tee -a "$LOG"
    if [ $rc -eq 0 ]; then
        echo "[supervisor] Clean exit. Done." | tee -a "$LOG"
        exit 0
    fi
    i=$((i+1))
    sleep 5
done
echo "[supervisor] Max restarts reached." | tee -a "$LOG"
exit 1
