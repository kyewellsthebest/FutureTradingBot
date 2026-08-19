"""The h=400 model on one micro, with a stop the account can survive.

WHY. The candidate cleared its permutation test (p = 0.048, IC three
empirical standard errors from zero) and then failed on two practical
grounds: a maximum drawdown near the whole $4,100 account, and a
position that was fractional -- routinely long a third of a contract,
which nobody can trade.

Both failures share a cause: nothing ever bounded the loss. The
backtest sized by confidence and rode every position for the full 18
hours no matter how far it went against. That is a sizing choice, not a
market fact, and it is testable.

WHAT THIS RUNS. The same predictions -- same features, same purged CV,
same model, no refitting of anything that could be tuned to the answer
-- traded as ONE MICRO with a hard dollar stop, walking the position
bar by bar inside each 18-hour block and closing it the moment
cumulative loss crosses the cap.

    no stop        the original, for reference
    stop $200      5% of the account
    stop $400      10%
    stop $800      20%

THE QUESTION IT ANSWERS, and either answer is worth having:

  If the edge SURVIVES a stop, the strategy becomes something a $4,100
  account can actually carry, and the drawdown objection dissolves.

  If the edge DIES, then it only ever worked by riding losses of
  thousands of dollars to recovery -- which is not an edge a small
  account can harvest, and the last live lane closes honestly.

A stop is not free and the accounting says so: stopping out locks in
the loss and forfeits any recovery that would have come. A strategy
whose profit depends on that recovery will show it here as a large drop
in net, and that is the finding rather than a flaw in the test.

THE CONTROL. The same stop logic on the shuffled target. A stop changes
the return distribution on its own -- it truncates the left tail -- so
"net improved with a stop" has to beat what a stop does to noise.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cadence as C                                          # noqa: E402

H = int(os.environ.get("H", "400"))
NTREE = int(os.environ.get("NTREE", "200"))
NFOLD = int(os.environ.get("NFOLD", "4"))
STOPS = [None, 200.0, 400.0, 800.0]
ACCOUNT = 4100.0


def walk(pos_block, y1_block, stop):
    """One 18-hour block, bar by bar, with a hard dollar stop.

    Returns (realised P&L, whether it stopped, bars actually held).
    """
    if pos_block == 0.0:
        return 0.0, False, 0
    run = 0.0
    for i, r in enumerate(y1_block):
        if not np.isfinite(r):
            continue
        run += pos_block * r
        if stop is not None and run <= -stop:
            return -stop, True, i + 1
    return run, False, len(y1_block)


def simulate(pos, y1, h, stop, cost_rt, weeks):
    n = (len(pos) // h) * h
    P = pos[:n].reshape(-1, h)[:, 0]
    Y = y1[:n].reshape(-1, h)
    pnl, stopped, held, prev = [], 0, [], 0.0
    for k in range(len(P)):
        p = P[k]
        g, hit, bars = walk(p, Y[k], stop)
        # Cost: turnover between the position we ended flat/at and the
        # next one. A stop-out means we are flat, so the next entry is
        # a full entry rather than an adjustment.
        end_pos = 0.0 if hit else p
        turn = abs(p - prev)
        pnl.append(g - turn * cost_rt / 2.0)
        prev = end_pos
        stopped += int(hit)
        held.append(bars)
    pnl = np.array(pnl)
    eq = np.cumsum(pnl)
    dd = float((np.maximum.accumulate(eq) - eq).max()) if len(eq) else 0.0
    active = P != 0
    wins = pnl[active] > 0
    return {
        "stop": stop, "blocks": len(P),
        "net_per_week": round(float(pnl.sum()) / weeks, 2),
        "total": round(float(pnl.sum()), 2),
        "max_drawdown": round(dd, 2),
        "dd_pct_of_account": round(100 * dd / ACCOUNT, 1),
        "stopped_out_pct": round(100 * stopped / max(len(P), 1), 1),
        "avg_hold_hours": round(float(np.mean(held)) * C.BAR_MIN / 60.0, 1),
        "win_rate_pct": round(100 * float(wins.mean()), 1) if active.any() else 0.0,
        "worst_block": round(float(pnl.min()), 2),
        "best_block": round(float(pnl.max()), 2),
        "trades_per_week": round(float(active.sum()) / weeks, 1),
    }


def main():
    print(__doc__, flush=True)
    print("=" * 74, flush=True)
    t0 = time.time()
    X, names, cls, ts = C.load()
    n_bars = len(X)
    weeks = n_bars * C.BAR_MIN / (60 * 24 * 7)
    yh, y1 = C.targets(cls, H)
    ok = np.isfinite(yh) & np.isfinite(y1)
    Xo, yo, y1o = X[ok], yh[ok], y1[ok]

    import lightgbm as lgb

    def fit(target, seed):
        preds = np.full(len(target), np.nan)
        for tr, te in C.purged_cv(len(target), NFOLD, H):
            m = lgb.LGBMRegressor(
                n_estimators=NTREE, learning_rate=0.05, num_leaves=31,
                min_child_samples=500, subsample=0.7, subsample_freq=1,
                colsample_bytree=0.5, reg_lambda=10.0, verbose=-1,
                n_jobs=4, random_state=seed)
            m.fit(Xo[tr], target[tr])
            preds[te] = m.predict(Xo[te])
        return preds

    rng = np.random.default_rng(77)
    results = {}
    for tag, target, seed in (("real", yo, 0),
                              ("SHUFFLED", rng.permutation(yo), 1)):
        preds = fit(target, seed)
        v = np.isfinite(preds)
        ic = float(np.corrcoef(preds[v], target[v])[0, 1])
        s = preds[v] / (np.nanstd(preds[v]) + 1e-12)
        s = s - np.nanmean(s)
        # ONE MICRO. -1, 0, +1 -- the only positions this account has.
        pos = np.sign(s) * (np.abs(s) >= 0.5)
        print(f"\n--- {tag}   IC {ic:+.4f}   "
              f"in a position {100*np.mean(pos!=0):.0f}% of blocks "
              f"({time.time()-t0:.0f}s)", flush=True)
        print(f"{'stop':>8} {'$/wk':>8} {'maxDD':>9} {'DD%acct':>8} "
              f"{'stopped':>8} {'hold h':>7} {'win%':>6} {'worst':>8}")
        rows = []
        for stop in STOPS:
            r = simulate(pos, y1o[v], H, stop, C.COST_MEASURED, weeks)
            rows.append(r)
            lbl = "none" if stop is None else f"${stop:.0f}"
            print(f"{lbl:>8} {r['net_per_week']:>8.0f} "
                  f"{r['max_drawdown']:>9,.0f} "
                  f"{r['dd_pct_of_account']:>7.0f}% "
                  f"{r['stopped_out_pct']:>7.0f}% "
                  f"{r['avg_hold_hours']:>7.1f} "
                  f"{r['win_rate_pct']:>5.0f}% "
                  f"{r['worst_block']:>8,.0f}", flush=True)
        results[tag] = {"ic": round(ic, 4), "rows": rows}

    print("\n" + "=" * 74)
    print("VERDICT -- does the edge survive being risk-capped?")
    for stop in STOPS:
        lbl = "none" if stop is None else f"${stop:.0f}"
        rr = [r for r in results["real"]["rows"] if r["stop"] == stop][0]
        ss = [r for r in results["SHUFFLED"]["rows"] if r["stop"] == stop][0]
        survivable = rr["max_drawdown"] <= 0.25 * ACCOUNT
        beats = rr["net_per_week"] > max(0.0, ss["net_per_week"])
        verd = ("TRADEABLE" if (survivable and beats)
                else "drawdown too big" if beats and not survivable
                else "edge gone")
        print(f"  stop {lbl:>5}: real ${rr['net_per_week']:>6.0f}/wk  "
              f"shuffled ${ss['net_per_week']:>6.0f}/wk  "
              f"DD ${rr['max_drawdown']:>6,.0f}  ->  {verd}")
    p = os.path.join(C.ROOT, "research", "RISKCAP.json")
    json.dump({"account": ACCOUNT, "weeks": round(weeks, 1),
               "results": results}, open(p, "w"), indent=1)
    print(f"\nwrote {p}  ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
