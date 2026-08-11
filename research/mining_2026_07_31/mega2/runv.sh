#!/usr/bin/env bash
# Six hours of validated searching, whatever happens to the process.
#
# The deadline is computed ONCE and passed in as an absolute timestamp, so a
# relaunch after a crash resumes toward the original finish time rather than
# granting itself a fresh six hours.
set -u
cd "$(dirname "$0")"

HRS="${HRS:-6}"
END="${END_TS:-$(( $(date +%s) + $(python3 -c "print(int($HRS*3600))") ))}"
LOG="${LOG:-/home/user/FutureTradingBot/data/vsearch.log}"

echo "=== supervisor: finish at $(date -u -d "@$END" '+%H:%M:%S UTC'), pid $$" | tee -a "$LOG"

tries=0
while [ "$(date +%s)" -lt "$END" ]; do
  tries=$((tries + 1))
  echo "--- attempt $tries, $(( END - $(date +%s) ))s remaining, $(date -u '+%H:%M:%S')" | tee -a "$LOG"

  END_TS="$END" \
  KBAR="${KBAR:-500,250}" ARITY="${ARITY:-5}" PERTYPE="${PERTYPE:-10}" \
  MIN_TPW="${MIN_TPW:-400}" MIN_DOL="${MIN_DOL:-2.00}" \
  MIN_RR="${MIN_RR:-1.1}" MAX_RR="${MAX_RR:-3.0}" \
  MIN_WIN="${MIN_WIN:-0.28}" MAX_WIN="${MAX_WIN:-0.80}" \
  MAX_DD_PCT="${MAX_DD_PCT:-0.10}" MIN_EDGE_REL="${MIN_EDGE_REL:-0.10}" \
  MIN_EDGE_PP="${MIN_EDGE_PP:-0.02}" MAX_FIRE="${MAX_FIRE:-0.90}" \
  PROBE="${PROBE:-0.04}" \
  TRAIN="${TRAIN:-0.60}" MIN_GREEN="${MIN_GREEN:-5}" \
  MIN_OOS_DOL="${MIN_OOS_DOL:-0.50}" MAX_CAND="${MAX_CAND:-400}" \
  STATE_JSON="${STATE_JSON:-/home/user/FutureTradingBot/data/vsearch_state.json}" \
  OUT_MD="${OUT_MD:-/home/user/FutureTradingBot/research/VSEARCH.md}" \
  python -u vsearch.py >> "$LOG" 2>&1

  echo "--- exited rc=$? after attempt $tries" | tee -a "$LOG"
  [ "$(date +%s)" -ge "$END" ] && break
  sleep 5
done

echo "=== supervisor finished at $(date -u '+%H:%M:%S UTC') after $tries attempt(s)" | tee -a "$LOG"
