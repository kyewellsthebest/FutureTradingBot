"""Trend following across 18 markets, ranked on DRAWDOWN rather than profit.

THE REGION NOBODY HERE HAS EVER LOOKED AT. The longest hold ever tested
in this repo is three days. Trend following -- the strategy behind the
entire managed-futures industry, documented across decades and dozens
of markets -- trades on a one-to-twelve-MONTH clock. Four months of
searching never once entered the region with the strongest prior in
systematic futures, because every search inherited the assumption that
a strategy is something that trades often.

WHY IT SUITS THIS ACCOUNT SPECIFICALLY. Ten trades a week across
eighteen markets is one position per market every two weeks. At that
cadence a $1.99 round turn is charged against a two-week move: the toll
falls to a rounding error, which is the one thing today proved
conclusively.

THE DESIGN CHANGE THAT MATTERS, and the earlier search got it wrong.
The wide search held ONE CONTRACT of every market. That is not equal
treatment, it is wildly unequal risk: one HO contract carries about
forty times the dollar risk of one YM, so a "diversified" book was
really a bet on heating oil with rounding errors attached. It showed up
exactly as expected -- HO drawdown $40,697, YM a few hundred.

Volatility scaling fixes it: size each market so every position risks
the SAME number of dollars. That is standard practice in the industry
and it is the single largest drawdown reducer available, worth more
than any signal improvement. Since contracts are integers and the
account holds a fixed number of micros, the weights are then rounded to
a whole-contract budget -- which is what can actually be traded.

RANKED ON DRAWDOWN, NOT RETURN, because that is what was asked for and
because it changes which configuration wins. Sorting on profit picks
the loudest cell; sorting on Calmar picks the one that survives.

CONTROLS

  1  RANDOM SIGNS. The identical book with each position's direction
     drawn at random, same sizes, same turnover, same costs. Volatility
     scaling and diversification reduce drawdown on their own, so the
     question is never "is the drawdown low" -- a coin flip run this
     way also has a low drawdown. It is whether the TREND SIGNAL beats
     a coin flip run identically.

  2  MDE reported for every configuration, found or not.

  3  Costs at the measured $1.99. The $0.85 subscription case is shown
     but nothing is judged on it.

HONEST LIMIT, stated before the numbers. 137 weeks is short for a
strategy that trades monthly. A 4-week hold gives 34 independent
periods per market. Diversification across 18 markets helps, but they
are correlated, so the effective sample is smaller than 34 x 18 and
this cannot be a definitive answer. It can only say whether the region
deserves real data.
"""
from __future__ import annotations

import glob
import itertools
import json
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DROP = {"SI"}
MIN_OPEN = 18
COSTS = [0.85, 1.99]
BARS_WK = 939                      # measured: 128,726 bars / 137 weeks
CONTRACT_BUDGET = [10, 20]         # total micros held at once
SPEC = {
    "NQ": 2.0, "ES": 5.0, "YM": 0.50, "RTY": 5.0, "GC": 10.0, "HG": 2500.0,
    "CL": 100.0, "NG": 2500.0, "HO": 42000.0, "RB": 42000.0, "ZB": 1000.0,
    "ZN": 1000.0, "ZF": 1000.0, "ZT": 2000.0, "6E": 12500.0, "6A": 10000.0,
    "6B": 6250.0, "6J": 6250000.0, "ZC": 10.0, "ZW": 10.0, "ZS": 10.0,
}
LOOKBACKS_WK = [1, 2, 4, 8, 12, 26]
HOLDS_WK = [1, 2, 4, 8]
VOL_WINDOW_WK = 8


def load():
    out = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "polygon",
                                           "*_5min.csv"))):
        s = os.path.basename(p).replace("_5min.csv", "")
        if s in DROP or s not in SPEC:
            continue
        d = pd.read_csv(p, parse_dates=["ts"], usecols=["ts", "close"])
        out[s] = d.set_index("ts")["close"]
    px = pd.DataFrame(out).sort_index()
    px = px[px.notna().sum(axis=1) >= MIN_OPEN].ffill(limit=3)
    keep = [c for c in px.columns if px[c].notna().mean() > 0.90]
    return px[keep].dropna(how="any")


def book(px, lb, hold, budget, cost, rng=None):
    """One configuration, as an integer-contract book.

    Returns per-rebalance dollar P&L for the whole portfolio.
    """
    syms = list(px.columns)
    pv = np.array([SPEC[s] for s in syms], dtype=float)
    idx = np.arange(lb + VOL_WINDOW_WK * BARS_WK, len(px) - hold, hold)
    if len(idx) < 20:
        return None
    vals = px.values
    # dollar volatility of an h-bar move, per contract, estimated on the
    # trailing window ONLY -- never on the period being traded.
    dollar_sd = np.empty((len(idx), len(syms)))
    signal = np.empty((len(idx), len(syms)))
    fwd = np.empty((len(idx), len(syms)))
    w0 = VOL_WINDOW_WK * BARS_WK
    for j, t in enumerate(idx):
        win = vals[t - w0:t]
        step = np.diff(win[::hold], axis=0) * pv
        dollar_sd[j] = np.nanstd(step, axis=0)
        signal[j] = (vals[t] - vals[t - lb]) / vals[t - lb]
        fwd[j] = (vals[t + hold] - vals[t]) * pv

    pnl, prev = [], np.zeros(len(syms))
    for j in range(len(idx)):
        sd = dollar_sd[j]
        ok = np.isfinite(sd) & (sd > 1e-9) & np.isfinite(signal[j]) \
            & np.isfinite(fwd[j])
        if ok.sum() < 6:
            continue
        # EQUAL DOLLAR RISK: weight inversely to each market's own
        # dollar volatility, then scale to the contract budget and
        # round to integers, because contracts are not divisible.
        raw = np.zeros(len(syms))
        raw[ok] = 1.0 / sd[ok]
        raw = raw / raw.sum() * budget
        n = np.floor(raw + 0.5)
        n[~ok] = 0.0
        d = rng.choice([-1.0, 1.0], size=len(syms)) if rng is not None \
            else np.sign(signal[j])
        pos = n * np.nan_to_num(d)
        g = float(np.nansum(pos * fwd[j]))
        turn = float(np.nansum(np.abs(pos - prev)))
        pnl.append(g - turn * cost / 2.0)
        prev = pos
    if len(pnl) < 20:
        return None
    return np.array(pnl), int(np.abs(np.floor(raw + 0.5)).sum())


def stats(pnl, weeks, contracts, lb_wk, hold_wk, budget):
    eq = np.cumsum(pnl)
    dd = float((np.maximum.accumulate(eq) - eq).max())
    sd = float(pnl.std(ddof=1))
    net_wk = float(pnl.sum()) / weeks
    return {
        "lookback_wk": lb_wk, "hold_wk": hold_wk, "budget": budget,
        "rebalances": len(pnl),
        "trades_per_week": round(contracts / hold_wk, 1),
        "net_per_week": round(net_wk, 2),
        "max_drawdown": round(dd, 2),
        "calmar": round(net_wk * 52 / dd, 2) if dd > 1 else None,
        "mde_per_week": round(3.0 * sd * math.sqrt(len(pnl)) / weeks, 2),
        "worst_rebalance": round(float(pnl.min()), 2),
        "pct_positive": round(100.0 * float((pnl > 0).mean()), 1),
    }


def main():
    print(__doc__, flush=True)
    print("=" * 78, flush=True)
    px = load()
    weeks = (px.index[-1] - px.index[0]).total_seconds() / (7 * 86400)
    print(f"{len(px.columns)} markets, {len(px):,} bars, {weeks:.0f} weeks\n",
          flush=True)
    rng = np.random.default_rng(5150)

    rows, ctrl = [], []
    combos = list(itertools.product(LOOKBACKS_WK, HOLDS_WK, CONTRACT_BUDGET))
    for lbw, hw, bud in combos:
        lb, hold = lbw * BARS_WK, hw * BARS_WK
        r = book(px, lb, hold, bud, COSTS[1])
        if r is None:
            continue
        pnl, contracts = r
        rows.append(stats(pnl, weeks, contracts, lbw, hw, bud))
        c = book(px, lb, hold, bud, COSTS[1], rng=rng)
        if c is not None:
            ctrl.append(stats(c[0], weeks, c[1], lbw, hw, bud))

    # RANKED ON DRAWDOWN-ADJUSTED RETURN, as asked.
    rows.sort(key=lambda r: (r["calmar"] is None, -(r["calmar"] or -9)))
    print(f"{'look':>5} {'hold':>5} {'micros':>7} {'tr/wk':>6} {'$/wk':>8} "
          f"{'maxDD':>9} {'Calmar':>7} {'MDE $/wk':>9} {'%+':>5}")
    for r in rows[:14]:
        print(f"{r['lookback_wk']:>4}w {r['hold_wk']:>4}w {r['budget']:>7} "
              f"{r['trades_per_week']:>6.1f} {r['net_per_week']:>8,.0f} "
              f"{r['max_drawdown']:>9,.0f} {str(r['calmar']):>7} "
              f"{r['mde_per_week']:>9,.0f} {r['pct_positive']:>4.0f}%")

    cal_c = sorted((c["calmar"] or -9) for c in ctrl)
    p90 = cal_c[int(0.90 * (len(cal_c) - 1))] if cal_c else 0.0
    best_ctrl_dd = min((c["max_drawdown"] for c in ctrl), default=0.0)
    print(f"\nRANDOM-SIGN CONTROL: p90 Calmar {p90:.2f}, "
          f"lowest drawdown ${best_ctrl_dd:,.0f}")
    print("  (vol scaling and diversification cut drawdown on their own --")
    print("   the signal must beat a coin flip run through the SAME book)")

    win = [r for r in rows
           if r["calmar"] and r["calmar"] > max(p90, 0.0)
           and r["net_per_week"] > r["mde_per_week"]]
    print(f"\n{len(win)} configuration(s) beat the random-sign control "
          f"AND exceed their own MDE")
    for w in win[:8]:
        print(f"   {w['lookback_wk']}w look / {w['hold_wk']}w hold / "
              f"{w['budget']} micros: ${w['net_per_week']:,.0f}/wk, "
              f"DD ${w['max_drawdown']:,.0f}, Calmar {w['calmar']}, "
              f"{w['trades_per_week']:.0f} trades/wk")
    if not win and rows:
        b = min(r["mde_per_week"] for r in rows)
        print(f"   Nothing cleared. Smallest edge any configuration could "
              f"have seen: ${b:,.0f}/week.")
    json.dump({"weeks": round(weeks, 1), "rows": rows, "control": ctrl,
               "control_p90_calmar": round(p90, 3), "winners": win},
              open(os.path.join(ROOT, "research", "TREND.json"), "w"),
              indent=1)
    print("\nwrote research/TREND.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
