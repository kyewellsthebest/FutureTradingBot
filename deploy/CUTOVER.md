# Cutover: the three validated pulse cells (2026-08-14, rev 2)

## Why rev 2

The first cutover pushed clean code and the host kept trading the old
system (basket sleeves on ZBU6/ZNU6, 318-trade history intact). Two
mechanisms defeated it:

1. **Railway Volume shadowing** — the volume mounted at `/app/data`
   shadows the repo's `data/` dir. Deleting state files from git never
   touches the host; the old history/stats lived on the volume.
2. **Stale service env vars** — Railway env vars override code defaults
   and survive every redeploy. Plus the basket engine was ON by default
   in code, independent of the pulse changes.

Rev 2 makes the entrypoint self-enforcing. On boot, `live_runner.py` now:

- **Force-writes** every strategy-critical env var (engine=mirror,
  shadow=0, basket=0, symbol=MNQ, the validated MNQ params). Whatever
  stale values the service has are stomped and logged.
- **Wipes the data volume once** (marker file `pulse_reset_v1.done`):
  all old trade history, statistics, basket state, paper accounts are
  deleted, then bundled config re-seeds. Restarts after that keep state.
- The basket engine's own default is now OFF (retired).

**No env configuration is needed on the existing service.** A redeploy of
the new commit IS the cutover. The only knobs are the new `PULSE_*`
overrides below, which old deploys cannot possess.

## Verify the deploy actually happened

In Railway → service → Deployments, the newest deploy's commit must be
the rev-2 commit. If it still shows an old commit, the service is not
auto-deploying from `claude/transfer-trading-bot-GiNxs` — trigger a
manual deploy or fix the tracked branch/repo. Then confirm in deploy
logs:

    stale env BROKER_ENGINE=... overridden -> 'pulse'
    PULSE RESET: purged N entries from /app/data
    [acct 1] starting Fib 50% bot (LIVE mode)

and that the dashboard no longer shows the Bonds/Notes basket bots or
the 318-trade history.

## Service 1 (existing) — MNQ

Zero env vars needed. Code forces the validated cell:
impulse 5.0pt / 6 bars, pullback 0.618, stop 10, target 20, 1 micro,
engine mirror, shadow OFF, basket OFF, symbol MNQ.
Validated: +$20,701 held-out, 142 tr/wk, 8/8 quarters green, DD $393.

## Service 2 (duplicate the service) — MES

Overrides use the NEW `PULSE_*` names (plain `STRAT_*` etc. are stomped):

    PULSE_TRADOVATE_SYMBOL=MES    PULSE_POLYGON_CONTRACT=MES
    PULSE_STRAT_IMPULSE_PTS=1.5   PULSE_STRAT_STOP_PTS=3.0
    PULSE_STRAT_TARGET_PTS=6.0

Validated: +$5,976 held-out, 136 tr/wk, 6/6 green, DD $340.

## Service 3 (duplicate the service) — MYM

    PULSE_TRADOVATE_SYMBOL=MYM    PULSE_POLYGON_CONTRACT=MYM
    PULSE_STRAT_IMPULSE_PTS=16.0  PULSE_STRAT_STOP_PTS=20.0
    PULSE_STRAT_TARGET_PTS=40.0   PULSE_STRAT_TICK_SIZE=1.0

Validated: +$3,212 held-out (125/wk, 7/8 green, DD $398) at honest
1-point tick slippage; placebo null loses -$97k at 20% WR — the edge is
the signal. `PULSE_STRAT_TICK_SIZE=1.0` is REQUIRED (YM order prices
round to full points; 0.25 offsets get rejected by the exchange).

MES/MYM services need their own Tradovate creds envs as usual
(TRADOVATE_USER/PASS/CID/SEC are not stomped) and a POLYGON key. Give
each service its own volume (or none) — a fresh volume also gets the
one-time wipe marker.

Account: DEMO 46293485, user resets balance to $4,000 at cutover.
Shadow week: compare every live fill vs the model before trusting
size-ups. Both PULSE_* names and the forced list live at the top of
`live_runner.py` (`PULSE_FORCED_ENV`).
