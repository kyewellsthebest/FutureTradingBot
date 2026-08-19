"""Minimum drawdown first. Revenue is whatever survives that choice.

THE INSTRUCTION, taken at face value: prioritise the least drawdown.
Taken literally it has a trivial answer -- hold nothing, draw down
nothing, earn nothing -- so what it must mean is: for each level of
drawdown actually achievable, what is the most revenue available, and
where does that curve stop being worth trading. That curve is what this
prints.

THE LEVER THAT HAS NOT BEEN USED, and it is the largest one left.
Every previous run sized markets at 1/volatility, which treats each
market as an independent bet. They are not. ES, NQ, YM and RTY are
close to a single position wearing four names; ZB, ZN, ZF and ZT are
another. An inverse-volatility book across 23 markets is really a
handful of large correlated bets, and its drawdown is set by that
concentration rather than by the market count.

Correlation-aware sizing fixes it. The trailing covariance of dollar
moves is estimated, and each market is weighted so that its
contribution to PORTFOLIO risk is equal -- not its standalone risk.
A cluster of four near-identical markets then shares one market's worth
of risk between them instead of taking four.

    equal standalone risk   ->  4 correlated markets carry 4 units
    equal PORTFOLIO risk    ->  the same 4 carry ~1 unit between them

THE SECOND LEVER: TARGET THE BOOK, NOT THE CONTRACTS. Fixing the
contract count fixes the size and lets the drawdown fall where it may,
which is how "20 micros" and "$2,000 drawdown" turned out to be
incompatible. Targeting a portfolio dollar volatility inverts that: the
risk is chosen, the contract count is whatever delivers it, and
drawdown becomes an input rather than an outcome. Sweeping that target
traces the frontier.

WHAT IS REPORTED. For each risk target: realised drawdown, revenue,
contracts actually held, and the MDE. A point on the frontier that
earns less than its own MDE is drawn but marked, because a low drawdown
achieved by not really trading is not an achievement.

THE CONTROL, unchanged and necessary: the same book with random
directions. Correlation-aware sizing and volatility targeting lower
drawdown ON THEIR OWN -- a coin flip run through this machinery will
also look calm -- so only beating that coin flip means anything.
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
COST = 1.99
SPEC = {
    "NQ": 2.0, "ES": 5.0, "YM": 0.50, "RTY": 5.0, "GC": 10.0, "HG": 2500.0,
    "CL": 100.0, "NG": 2500.0, "HO": 42000.0, "RB": 42000.0, "ZB": 1000.0,
    "ZN": 1000.0, "ZF": 1000.0, "ZT": 2000.0, "6E": 12500.0, "6A": 10000.0,
    "6B": 6250.0, "6J": 6250000.0, "ZC": 10.0, "ZW": 10.0, "ZS": 10.0,
    "ETH": 0.10, "MBT": 0.10,
}
# target dollar volatility of the whole book, per rebalance
RISK_TARGETS = [50, 100, 200, 400, 800, 1600]
LOOKBACK_D = [20, 40, 60, 120]
HOLD_D = [5, 10, 20]
THRESH = [0.0, 1.0]
COVWIN_D = 120
MAX_CONTRACTS = 40


def load_daily():
    out = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "polygon",
                                           "*_5min.csv"))):
        s = os.path.basename(p).replace("_5min.csv", "")
        if s in DROP or s not in SPEC:
            continue
        d = pd.read_csv(p, parse_dates=["ts"], usecols=["ts", "close"])
        out[s] = d.set_index("ts")["close"].resample("1D").last()
    px = pd.DataFrame(out).sort_index().ffill(limit=3).dropna(how="all")
    return px[[c for c in px.columns if px[c].notna().sum() > 400]]


def weights(cov, active, target):
    """Contracts such that each ACTIVE market contributes equal risk to
    the portfolio, scaled so total book volatility equals `target`.

    Marginal risk contribution is w_i * (Cov w)_i. Solving that exactly
    needs an optimiser; one Newton-ish pass from an inverse-volatility
    start gets most of the benefit and cannot diverge, which matters
    more here than the last few percent.
    """
    idx = np.flatnonzero(active)
    if len(idx) < 3:
        return None
    C = cov[np.ix_(idx, idx)]
    sd = np.sqrt(np.clip(np.diag(C), 1e-12, None))
    w = 1.0 / sd
    for _ in range(3):
        mrc = C @ w
        rc = w * mrc
        rc = np.where(rc <= 1e-12, 1e-12, rc)
        w = w * (rc.mean() / rc) ** 0.5
        w = np.clip(w, 0, None)
    pv = float(np.sqrt(max(w @ C @ w, 1e-12)))
    if not np.isfinite(pv) or pv <= 0:
        return None
    w = w * (target / pv)
    # A singular or degenerate covariance can produce non-finite
    # weights, and one NaN contract silently poisons the whole book's
    # P&L. Refuse the rebalance rather than trade an undefined size.
    if not np.isfinite(w).all():
        return None
    out = np.zeros(cov.shape[0])
    out[idx] = w
    return out


def simulate(px, lb, hold, thresh, target, rng=None):
    syms = list(px.columns)
    pv = np.array([SPEC[s] for s in syms], dtype=float)
    V = px.values
    start = max(lb, COVWIN_D) + hold
    idx = np.arange(start, len(px) - hold, hold)
    if len(idx) < 15:
        return None
    pnl, prev, held = [], np.zeros(len(syms)), []
    for t in idx:
        win = V[t - COVWIN_D:t]
        step = np.diff(win, axis=0) * pv * math.sqrt(hold)
        good = np.isfinite(step).all(axis=0)
        cov = np.cov(np.where(np.isfinite(step), step, 0.0), rowvar=False)
        cov = np.nan_to_num(cov)
        sig = (V[t] - V[t - lb]) / V[t - lb]
        nz = np.nanstd(np.diff(win, axis=0) / win[:-1], axis=0) * math.sqrt(lb)
        z = np.divide(sig, nz, out=np.zeros_like(sig), where=nz > 1e-12)
        fwd = (V[t + hold] - V[t]) * pv
        act = good & np.isfinite(z) & np.isfinite(fwd) & (np.abs(z) >= thresh)
        pos = np.zeros(len(syms))
        w = weights(cov, act, target) if act.sum() >= 3 else None
        if w is not None:
            n = np.floor(np.clip(np.nan_to_num(w), 0, MAX_CONTRACTS) + 0.5)
            d = (rng.choice([-1.0, 1.0], size=len(syms)) if rng is not None
                 else np.sign(z))
            pos = n * d
        g = float(np.nansum(pos * np.nan_to_num(fwd)))
        turn = float(np.nansum(np.abs(pos - prev)))
        pnl.append(g - turn * COST / 2.0)
        held.append(float(np.abs(np.nan_to_num(pos)).sum()))
        prev = pos
    pnl = np.array(pnl)
    if len(pnl) < 15 or not np.isfinite(pnl).all():
        return None
    weeks = (px.index[-1] - px.index[0]).days / 7.0
    eq = np.cumsum(pnl)
    dd = float((np.maximum.accumulate(eq) - eq).max())
    sd = float(pnl.std(ddof=1))
    return {"lookback_d": lb, "hold_d": hold, "thresh": thresh,
            "risk_target": target, "rebalances": len(pnl),
            "avg_contracts": round(float(np.mean(held)), 1),
            "max_contracts": int(np.max(held)),
            "net_per_week": round(float(pnl.sum()) / weeks, 2),
            "net_per_fortnight": round(2 * float(pnl.sum()) / weeks, 2),
            "max_drawdown": round(dd, 2),
            "mde_per_week": round(3.0 * sd * math.sqrt(len(pnl)) / weeks, 2),
            "pct_positive": round(100.0 * float((pnl > 0).mean()), 1),
            "trades_per_week": round(float(np.mean(held)) / (hold / 5.0), 1)}


def main():
    print(__doc__, flush=True)
    print("=" * 78, flush=True)
    px = load_daily()
    yrs = (px.index[-1] - px.index[0]).days / 365
    print(f"{len(px.columns)} markets, {len(px)} daily bars, {yrs:.1f} years\n",
          flush=True)
    rng = np.random.default_rng(1234)
    rows, ctrl = [], []
    for lb, hold, th, tg in itertools.product(LOOKBACK_D, HOLD_D, THRESH,
                                              RISK_TARGETS):
        if lb < hold:
            continue
        r = simulate(px, lb, hold, th, tg)
        if r:
            rows.append(r)
        c = simulate(px, lb, hold, th, tg, rng=rng)
        if c:
            ctrl.append(c)

    print(f"{len(rows)} configurations\n")
    print("THE FRONTIER -- best revenue available at each drawdown level")
    print(f"{'maxDD <=':>10} {'$/wk':>8} {'$/fortnight':>12} {'micros':>7} "
          f"{'tr/wk':>6} {'MDE $/wk':>9} {'ctrl $/wk':>10} {'real?':>6}")
    for cap in (500, 1000, 2000, 4000, 8000, 16000, 40000):
        under = [r for r in rows if r["max_drawdown"] <= cap]
        cu = [c["net_per_week"] for c in ctrl if c["max_drawdown"] <= cap]
        if not under:
            print(f"{cap:>10,}  -- nothing achieves this --")
            continue
        b = max(under, key=lambda r: r["net_per_week"])
        cbest = max(cu) if cu else 0.0
        real = (b["net_per_week"] > b["mde_per_week"]
                and b["net_per_week"] > cbest)
        print(f"{cap:>10,} {b['net_per_week']:>8,.0f} "
              f"{b['net_per_fortnight']:>12,.0f} {b['avg_contracts']:>7.1f} "
              f"{b['trades_per_week']:>6.1f} {b['mde_per_week']:>9,.0f} "
              f"{cbest:>10,.0f} {'YES' if real else 'no':>6}")

    lowest = min(rows, key=lambda r: r["max_drawdown"])
    print(f"\nAbsolute lowest drawdown found: ${lowest['max_drawdown']:,.0f} "
          f"(earns ${lowest['net_per_week']:,.0f}/wk on "
          f"{lowest['avg_contracts']:.1f} micros)")
    json.dump({"years": round(yrs, 2), "markets": list(px.columns),
               "rows": rows, "control": ctrl},
              open(os.path.join(ROOT, "research", "MINDD.json"), "w"), indent=1)
    print("wrote research/MINDD.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
