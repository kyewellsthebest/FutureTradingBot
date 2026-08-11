#!/usr/bin/env bash
# Commit the search state on a timer, because the disk is not durable.
#
# The container running this search has already been reclaimed twice today,
# mid-run, taking everything on local disk with it. A supervisor restarts the
# process after a crash but cannot survive the machine going away. Git can.
# So the state file and the report are pushed every INTERVAL seconds, and the
# worst a container loss can cost is one interval of work instead of all of it.
set -u
cd /home/user/FutureTradingBot
END="${END_TS:?need END_TS}"
INT="${INTERVAL:-1200}"
while [ "$(date +%s)" -lt "$END" ]; do
  sleep "$INT"
  git add -A data/mega6_state.json data/mega6.log research/MEGA6.md 2>/dev/null
  if ! git diff --staged --quiet; then
    n=$(python3 -c "
import json
try: print(f\"{len(json.load(open('data/mega6_state.json'))['rows']):,}\")
except Exception: print('?')" 2>/dev/null)
    git commit -q -m "search checkpoint: $n scored, $(date -u '+%H:%M UTC')"
    for i in 1 2 3 4; do
      git push -q origin claude/hello-vc2ivo 2>/dev/null && break
      sleep $((2**i))
    done
  fi
done
