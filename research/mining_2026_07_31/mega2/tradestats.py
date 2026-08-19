"""What the h=400 candidate actually does, trade by trade.

Net-per-week is a summary. It hides how often you trade, how often you
are right, how big the losers are, and how deep the account goes
underwater before it recovers -- all of which decide whether a $4,100
account can actually carry the thing.

THE ONE THAT MATTERS MOST, and it is not a statistic. The backtest
holds a CONTINUOUS position, `clip(pred/std, -1, +1)`, so it is
routinely long 0.34 contracts. Nobody can trade 0.34 of a micro. On one
MNQ the only positions that exist are -1, 0 and +1, and rounding to
them is not a cosmetic detail: it changes both the P&L and the
turnover, and it can destroy a result that depended on sizing
proportional to confidence.

So this reports the strategy three ways:

    continuous     what the backtest assumed -- fractional contracts
    rounded        the same signal on ONE micro: -1, 0, +1 only
    threshold      one micro, but only when |signal| is strong enough
                   to be worth a round turn -- flat otherwise

A "trade" here is one rebalance block: the position is set, held for
400 bars (~18 hours), and its P&L is the sum of the bar returns over
that block times the position. That is the unit a person would
recognise as a trade.
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
NJOBS = int(os.environ.get("NJOBS", "2"))     # share the box politely


def blocks(pos, y1, h, cost_rt):
    """Split into rebalance blocks and price each as one trade."""
    n = (len(pos) // h) * h
    p = pos[:n].reshape(-1, h)[:, 0]           # position set at block open
    r = y1[:n].reshape(-1, h).sum(axis=1)      # move over the block
    pnl_gross = p * r
    # Cost: the change in position at each block boundary, in round
    # turns. |dpos| of 2.0 (full flip) is one round turn each way.
    dp = np.abs(np.diff(p, prepend=0.0))
    pnl = pnl_gross - dp * cost_rt / 2.0
    return p, pnl, pnl_gross, dp


def describe(name, pos, y1, h, weeks, cost_rt):
    p, pnl, gross, dp = blocks(pos, y1, h, cost_rt)
    traded = dp > 1e-9
    active = np.abs(p) > 1e-9
    wins = pnl[active] > 0
    eq = np.cumsum(pnl)
    dd = float((np.maximum.accumulate(eq) - eq).max()) if len(eq) else 0.0
    n_blocks = len(p)
    out = {
        "variant": name,
        "blocks": n_blocks,
        "blocks_per_week": round(n_blocks / weeks, 2),
        "blocks_with_a_position": int(active.sum()),
        "rebalances_per_week": round(float(traded.sum()) / weeks, 2),
        "round_turns_per_week": round(float(dp.sum() / 2.0) / weeks, 2),
        "avg_abs_position": round(float(np.abs(p[active]).mean()) if active.any() else 0.0, 3),
        "hold_hours": round(h * C.BAR_MIN / 60.0, 1),
        "win_rate_pct": round(100.0 * wins.mean(), 1) if active.any() else 0.0,
        "avg_win": round(float(pnl[active][wins].mean()), 2) if wins.any() else 0.0,
        "avg_loss": round(float(pnl[active][~wins].mean()), 2) if (~wins).any() else 0.0,
        "best": round(float(pnl.max()), 2),
        "worst": round(float(pnl.min()), 2),
        "net_per_week": round(float(pnl.sum()) / weeks, 2),
        "gross_per_week": round(float(gross.sum()) / weeks, 2),
        "cost_per_week": round(float(dp.sum() / 2.0 * cost_rt) / weeks, 2),
        "total_net": round(float(pnl.sum()), 2),
        "max_drawdown": round(dd, 2),
    }
    return out


def main():
    print(__doc__, flush=True)
    t0 = time.time()
    X, names, cls, ts = C.load()
    n_bars = len(X)
    weeks = n_bars * C.BAR_MIN / (60 * 24 * 7)
    yh, y1 = C.targets(cls, H)
    ok = np.isfinite(yh) & np.isfinite(y1)
    Xo, yo, y1o = X[ok], yh[ok], y1[ok]

    import lightgbm as lgb
    preds = np.full(len(yo), np.nan)
    for k, (tr, te) in enumerate(C.purged_cv(len(yo), NFOLD, H)):
        m = lgb.LGBMRegressor(
            n_estimators=NTREE, learning_rate=0.05, num_leaves=31,
            min_child_samples=500, subsample=0.7, subsample_freq=1,
            colsample_bytree=0.5, reg_lambda=10.0, verbose=-1,
            n_jobs=NJOBS, random_state=0)
        m.fit(Xo[tr], yo[tr])
        preds[te] = m.predict(Xo[te])
        print(f"  fold {k+1}/{NFOLD} ({time.time()-t0:.0f}s)", flush=True)

    v = np.isfinite(preds)
    pv, yv = preds[v], y1o[v]
    ic = float(np.corrcoef(pv, yo[v])[0, 1])
    s = pv / (np.nanstd(pv) + 1e-12)
    s = s - np.nanmean(s)

    cont = np.clip(s, -1.0, 1.0)
    rounded = np.sign(cont) * (np.abs(cont) >= 0.5)          # -1 / 0 / +1
    thresh = np.sign(s) * (np.abs(s) >= 1.0)                 # only strong

    rows = [describe("continuous (what the backtest assumed)", cont, yv, H,
                     weeks, C.COST_MEASURED),
            describe("rounded to 1 micro (-1/0/+1)", rounded, yv, H, weeks,
                     C.COST_MEASURED),
            describe("1 micro, only |z|>=1", thresh, yv, H, weeks,
                     C.COST_MEASURED)]

    print(f"\nIC {ic:+.4f}   {weeks:.0f} weeks of tape\n")
    for r in rows:
        print("=" * 66)
        print(f"  {r['variant']}")
        print(f"    trades (rebalances) per week   {r['rebalances_per_week']}")
        print(f"    round turns per week           {r['round_turns_per_week']}")
        print(f"    hold                           {r['hold_hours']} hours")
        print(f"    avg position size              "
              f"{r['avg_abs_position']} contracts")
        print(f"    win rate                       {r['win_rate_pct']}%")
        print(f"    average win / loss             "
              f"${r['avg_win']} / ${r['avg_loss']}")
        print(f"    best / worst single trade      "
              f"${r['best']} / ${r['worst']}")
        print(f"    gross per week                 ${r['gross_per_week']}")
        print(f"    cost per week                  ${r['cost_per_week']}")
        print(f"    NET PER WEEK                   ${r['net_per_week']}")
        print(f"    total over {r['blocks']} blocks        "
              f"${r['total_net']}")
        print(f"    MAX DRAWDOWN                   ${r['max_drawdown']}")
    p = os.path.join(C.ROOT, "research", f"TRADESTATS_H{H}.json")
    json.dump({"ic": round(ic, 4), "weeks": round(weeks, 1), "rows": rows},
              open(p, "w"), indent=1)
    print(f"\nwrote {p}  ({time.time()-t0:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
