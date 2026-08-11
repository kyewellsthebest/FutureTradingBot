#!/usr/bin/env bash
# Six hours of searching, whatever happens to the process.
#
# The deadline is computed ONCE and passed in as an absolute timestamp, so a
# relaunch after a crash resumes toward the original finish time instead of
# granting itself a fresh six hours. mega.py reloads its state file on start,
# so a restart also keeps every row already scored and -- critically -- the
# RATCHETED bar, which would otherwise reset to the starting value and let the
# search re-find things it had already beaten.
set -u
cd "$(dirname "$0")"

HRS="${HRS:-6}"
END="${END_TS:-$(( $(date +%s) + $(python3 -c "print(int($HRS*3600))") ))}"
LOG="${LOG:-/home/user/FutureTradingBot/data/mega6.log}"

echo "=== supervisor: finish at $(date -u -d "@$END" '+%H:%M:%S UTC'), pid $$" | tee -a "$LOG"

tries=0
while [ "$(date +%s)" -lt "$END" ]; do
  tries=$((tries + 1))
  left=$(( END - $(date +%s) ))
  echo "--- attempt $tries, ${left}s remaining, $(date -u '+%H:%M:%S')" | tee -a "$LOG"

  END_TS="$END" \
  KBAR="${KBAR:-500,250,1000}" ARITY="${ARITY:-5}" PERTYPE="${PERTYPE:-12}" \
  MIN_TPW="${MIN_TPW:-400}" MIN_DOL="${MIN_DOL:-2.00}" \
  MIN_RR="${MIN_RR:-1.1}" MAX_RR="${MAX_RR:-3.0}" \
  MIN_WIN="${MIN_WIN:-0.28}" MAX_WIN="${MAX_WIN:-0.80}" \
  MAX_DD_PCT="${MAX_DD_PCT:-0.10}" MIN_EDGE_REL="${MIN_EDGE_REL:-0.10}" \
  MIN_EDGE_PP="${MIN_EDGE_PP:-0.02}" MAX_FIRE="${MAX_FIRE:-0.90}" \
  PROBE="${PROBE:-0.04}" BEEP="${BEEP:-0.015}" DIG_ROUNDS="${DIG_ROUNDS:-6}" \
  STATE_JSON="${STATE_JSON:-/home/user/FutureTradingBot/data/mega6_state.json}" \
  OUT_MD="${OUT_MD:-/home/user/FutureTradingBot/research/MEGA6.md}" \
  python -u mega.py >> "$LOG" 2>&1

  rc=$?
  echo "--- exited rc=$rc after attempt $tries" | tee -a "$LOG"
  [ "$(date +%s)" -ge "$END" ] && break
  sleep 5
done

echo "=== supervisor finished at $(date -u '+%H:%M:%S UTC') after $tries attempt(s)" | tee -a "$LOG"
