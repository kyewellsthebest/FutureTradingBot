#!/usr/bin/env bash
# The container is being reclaimed every ~10 minutes tonight, so progress has
# to come in units small enough to finish between deaths. Each feature cache
# is one such unit: ~3 minutes, and once written it persists on disk through
# any number of reboots. Build the missing ones one at a time, then sweep.
set -u
cd "$(dirname "$0")"
find /home/user/FutureTradingBot/data/fcache -name "*_v3.npz" -size -40M -delete 2>/dev/null
for cn in NQU4 NQZ4 NQH5 NQM5 NQU5 NQZ5 NQH6 NQM6; do
  [ -f "/home/user/FutureTradingBot/data/fcache/${cn}_K500_v3.npz" ] && continue
  echo "building $cn $(date -u +%H:%M:%S)"
  python -c "import sys;sys.path.insert(0,'.');import vsearch as V;V.cached('$cn',500)" || exit 1
done
echo "all caches present, sweeping $(date -u +%H:%M:%S)"
MAXCOMBO=1500000 ARITY=5 PERTYPE=22 WORKERS=4 MIN_TPW=200 exec python -u fsearch.py
