#!/bin/bash
# Round 19 supervisor: restart the search up to N times if it dies.
set -u
cd /home/user/HFTBot
LOG=/home/user/HFTBot/research/round19.log
ERR=/home/user/HFTBot/research/round19.err
RESULTS=/home/user/HFTBot/research/round19_results.md

MAX_RESTARTS=8
i=0
while [ $i -lt $MAX_RESTARTS ]; do
    if [ -f "$RESULTS" ]; then
        echo "[supervisor] Results file exists. Exiting." | tee -a "$LOG"
        exit 0
    fi
    echo "[supervisor] Attempt $((i+1))/$MAX_RESTARTS at $(date)" | tee -a "$LOG"
    /usr/bin/env python3 /home/user/HFTBot/research/round19_search.py \
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
