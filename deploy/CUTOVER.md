# Cutover: the two validated pulse cells (2026-08-14)

The bot host runs `live_runner.py` -> FibRuntime (the impulse-pullback
executor). One service per market. Old paper account/trade history/stats
files are deleted from the repo; runtime copies start fresh at boot.

## Service 1 (existing) -- MNQ
Set env and redeploy:
    TRADOVATE_SYMBOL=MNQ   BOT_SHADOW_MODE=0
    STRAT_IMPULSE_PTS=5.0  STRAT_IMPULSE_BARS=6  STRAT_PULL_PCT=0.618
    STRAT_STOP_PTS=10.0    STRAT_TARGET_PTS=20.0 STRAT_COOLDOWN_SECS=60
    FIB_N_MNQ=1

## Service 2 (duplicate the service) -- MES
    TRADOVATE_SYMBOL=MES   BOT_SHADOW_MODE=0
    STRAT_IMPULSE_PTS=1.5  STRAT_IMPULSE_BARS=6  STRAT_PULL_PCT=0.618
    STRAT_STOP_PTS=3.0     STRAT_TARGET_PTS=6.0  STRAT_COOLDOWN_SECS=60
    FIB_N_MNQ=1

Code defaults now equal the validated MNQ cell, so a bare redeploy of
service 1 already trades the right parameters. Account: DEMO, reset $4,000.
Shadow week: compare every live fill vs model before trusting size-ups.
