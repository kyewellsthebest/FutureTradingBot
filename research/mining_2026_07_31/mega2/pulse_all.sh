#!/usr/bin/env bash
# Whatever pulse work is incomplete, resume it (checkpointed per quarter).
cd "$(dirname "$0")"
FINE=1 python -u pulse.py >> /home/user/FutureTradingBot/data/pulse_fine.log 2>&1
FINE=1 PSYM=ES PSCALE=0.3 PTV=5.0 python -u pulse.py >> /home/user/FutureTradingBot/data/pulse_fine_es.log 2>&1
