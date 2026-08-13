#!/usr/bin/env bash
# The frequency-first re-search: five markets, two bar sizes, the spec
# enforced from the first arithmetic op. K=500 re-searches the old space
# with the fixed bracket selection ($/wk ranking, no first-pass break, no
# edge-only top-3); K=250 doubles the bar resolution -- space never
# searched, and the only place 100+ trades/wk can physically live when
# holds are more than a handful of bars.
#
# Reboot-proof: per-K checkpoint dirs (data/f2_K<K>/fsearch_ck), completed
# reports skipped, one-quarter cache units.
set -u
cd "$(dirname "$0")"
FC=/home/user/FutureTradingBot/data/fcache

run() {
  local M=$1 TVv=$2 TPXv=$3 RNDv=$4 GREEN=$5 K=$6 CONS=$7
  local DONE="/home/user/FutureTradingBot/research/F2_${M}_K${K}.md"
  if [ -f "$DONE" ] && grep -q "survived" "$DONE"; then
    echo "=== $M K$K already done"; return 0
  fi
  echo "=== $M K$K $(date -u '+%H:%M:%S')"
  find "$FC" -name "*_K${K}_v3.npz" -size -2M -delete 2>/dev/null
  local cn
  for cn in ${CONS//,/ }; do
    [ -f "$FC/${cn}_K${K}_v3.npz" ] && continue
    echo "  building $cn K$K $(date -u '+%H:%M:%S')"
    ROUND="$RNDv" python -c "import vsearch as V; V.cached('$cn',$K)" \
      || return 1
  done
  mkdir -p "/home/user/FutureTradingBot/data/f2_K${K}"
  CONTRACTS="$CONS" KBAR=$K TV="$TVv" TPX="$TPXv" COST=1.24 MAKER=0 \
  ROUND="$RNDv" MIN_GREEN="$GREEN" MIN_TPW=100 MIN_OOS_TPW=100 \
  MIN_OOS_WK=150 MAXCOMBO=1500000 ARITY=5 PERTYPE=22 WORKERS=4 \
  STATE_JSON="/home/user/FutureTradingBot/data/f2_K${K}/state_${M}.json" \
  OUT_MD="$DONE" \
  python -u fsearch.py
}

NQC="NQU4,NQZ4,NQH5,NQM5,NQU5,NQZ5,NQH6,NQM6"
ESC="ESZ4,ESH5,ESU5,ESZ5,ESH6,ESM6"
YMC="YMU4,YMZ4,YMH5,YMM5,YMU5,YMZ5,YMH6,YMM6"
RTC="RTYU4,RTYZ4,RTYH5,RTYM5,RTYU5,RTYZ5,RTYH6,RTYM6"
CLC="CLU4,CLZ4,CLH5,CLM5,CLU5,CLZ5,CLH6,CLM6"

# K500 first: caches already exist for four markets, results come fast
run NQ  0.50 0.25 25  5 500 "$NQC"
run ES  1.25 0.25 25  4 500 "$ESC"
run YM  0.50 1.0  100 5 500 "$YMC"
run RTY 0.50 0.10 10  5 500 "$RTC"
# then the new space: 250-tick bars, all five markets (CL only fits here)
run CL  1.00 0.01 1   5 250 "$CLC"
run NQ  0.50 0.25 25  5 250 "$NQC"
run ES  1.25 0.25 25  4 250 "$ESC"
run YM  0.50 1.0  100 5 250 "$YMC"
run RTY 0.50 0.10 10  5 250 "$RTC"
echo "=== sweep2 complete $(date -u '+%H:%M:%S')"
