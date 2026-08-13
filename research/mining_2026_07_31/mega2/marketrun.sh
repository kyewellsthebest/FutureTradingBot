#!/usr/bin/env bash
# Every non-NQ market through the same validated engine, one market at a
# time. Reboot-proof by construction: feature caches are one-quarter durable
# units, the search checkpoints every 100k combos inside a quarter and every
# 2k candidates inside a validation quarter, and a completed market leaves
# its FSEARCH_<M>.md behind, so a dead container resumes by re-running this
# script -- it skips everything already finished.
#
# Economics are the MICRO contract of each market, priced as TAKERS
# (MAKER=0): no queue-edge measurement exists outside NQ, so no credit is
# taken. NQ joins the satellite set for every centre, replacing the centre's
# own symbol.
set -u
cd "$(dirname "$0")"

FC="/home/user/FutureTradingBot/data/fcache"

run_market() {
  local M="$1" TVv="$2" TPXv="$3" RNDv="$4" GREEN="$5" CONS="$6"
  local DONE="/home/user/FutureTradingBot/research/FSEARCH_${M}.md"
  if [ -f "$DONE" ] && grep -q "survived every other quarter" "$DONE"; then
    echo "=== $M already complete, skipping"
    return 0
  fi
  echo "=== $M caches $(date -u '+%H:%M:%S')"
  find "$FC" -name "*_K500_v3.npz" -size -5M -delete 2>/dev/null
  local cn
  for cn in ${CONS//,/ }; do
    [ -f "$FC/${cn}_K500_v3.npz" ] && continue
    echo "  building $cn $(date -u '+%H:%M:%S')"
    ROUND="$RNDv" python -c "import vsearch as V; V.cached('$cn',500)" \
      || return 1
  done
  echo "=== $M sweep $(date -u '+%H:%M:%S')"
  CONTRACTS="$CONS" TV="$TVv" TPX="$TPXv" COST=1.24 MAKER=0 ROUND="$RNDv" \
  MIN_GREEN="$GREEN" MIN_TPW=100 MAXCOMBO=1500000 ARITY=5 PERTYPE=22 \
  WORKERS=4 \
  STATE_JSON="/home/user/FutureTradingBot/data/fsearch_state_${M}.json" \
  OUT_MD="$DONE" \
  python -u fsearch.py
}

#          market  $/tick tick   round green contracts (chronological)
run_market ES      1.25   0.25   25    4 "ESZ4,ESH5,ESU5,ESZ5,ESH6,ESM6"
run_market YM      0.50   1.0    100   5 "YMU4,YMZ4,YMH5,YMM5,YMU5,YMZ5,YMH6,YMM6"
run_market RTY     0.50   0.10   10    5 "RTYU4,RTYZ4,RTYH5,RTYM5,RTYU5,RTYZ5,RTYH6,RTYM6"
run_market CL      1.00   0.01   1     5 "CLU4,CLZ4,CLH5,CLM5,CLU5,CLZ5,CLH6,CLM6"
echo "=== all markets done $(date -u '+%H:%M:%S')"
