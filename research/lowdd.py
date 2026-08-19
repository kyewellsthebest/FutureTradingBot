"""Maximum revenue subject to a HARD $2,000 drawdown cap. 20 micros.

THE BRIEF, taken literally and treated as a constraint rather than a
preference:

    max drawdown < $2,000          -- hard, a configuration that breaks
                                      it is not ranked, it is excluded
    ~10 trades per week            -- the cadence that makes cost small
    20 micros held at once         -- what the account can carry
    maximise average revenue       -- the objective INSIDE the cap

Ranking on revenue while filtering on drawdown is not the same as
ranking on Calmar, and the difference matters. Calmar rewards a cell
that earns $40 a week on a $200 drawdown; that cell is useless here. The
cap is the requirement and revenue is the score.

THREE LEVERS THAT ACTUALLY REDUCE DRAWDOWN, in the order they matter:

  1  EQUAL DOLLAR RISK PER MARKET. One HO contract carries about forty
     times the dollar risk of one YM, so an equal-CONTRACT book is a
     bet on heating oil wearing a diversification costume -- measured
     earlier as HO drawdown $40,697 against YM's few hundred. Weighting
     inversely to each market's own dollar volatility is worth more
     than any signal improvement.

  2  MORE MARKETS. Drawdown grows with sqrt(N) while revenue grows with
     N, but only to the extent the markets are independent. Earlier
     searches forced every market onto one shared clock and silently
     dropped five of them -- grains and crypto, the LEAST correlated
     things available, and therefore exactly the ones diversification
     needed most. Here each market is read on its own calendar and
     joined only for the rebalance, so all 23 survive.

  3  CONVICTION THRESHOLD. Trading only when the trend is strong
     relative to its own noise cuts time in the market. Less exposure
     is less drawdown, and it costs less in fees; what it costs in
     revenue is the thing being measured.

THE CONTROL. The identical book -- same markets, same sizes, same
turnover, same costs, same threshold -- with each position's DIRECTION
drawn at random. Volatility scaling, diversification and a threshold
all reduce drawdown ON THEIR OWN, so a low drawdown proves nothing by
itself. Only beating a coin flip pushed through the same machinery does.

Costs are the measured $1.99 a round turn. Nothing is judged at $0.85.

MDE is reported for every surviving configuration, because a cell that
earns less than the smallest effect its own sample could resolve is a
number, not a finding -- and that distinction is what four months of
"nothing found" was missing.
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
DROP = {"SI"}                       # permanently excluded
DD_CAP = float(os.environ.get("DD_CAP", "2000"))
COST = 1.99                         # measured from real fills
BUDGET = int(os.environ.get("BUDGET", "20"))
SPEC = {
    "NQ": 2.0, "ES": 5.0, "YM": 0.50, "RTY": 5.0, "GC": 10.0, "HG": 2500.0,
    "CL": 100.0, "NG": 2500.0, "HO": 42000.0, "RB": 42000.0, "ZB": 1000.0,
    "ZN": 1000.0, "ZF": 1000.0, "ZT": 2000.0, "6E": 12500.0, "6A": 10000.0,
    "6B": 6250.0, "6J": 6250000.0, "ZC": 10.0, "ZW": 10.0, "ZS": 10.0,
    "ETH": 0.10, "MBT": 0.10,
}
LOOKBACK_D = [5, 10, 20, 40, 60, 120]
HOLD_D = [5, 10, 20, 40]
THRESH = [0.0, 0.5, 1.0, 1.5]
VOLWIN_D = 60


def load_daily():
    """Each market on ITS OWN calendar, resampled to daily closes.

    Reading every market on one shared 5-minute clock forced a common
    trading session and dropped grains and crypto entirely -- the least
    correlated instruments available, and so the ones diversification
    needed most. A two-week hold has no use for 5-minute bars anyway.
    """
    out = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "polygon",
                                           "*_5min.csv"))):
        s = os.path.basename(p).replace("_5min.csv", "")
        if s in DROP or s not in SPEC:
            continue
        d = pd.read_csv(p, parse_dates=["ts"], usecols=["ts", "close"])
        day = d.set_index("ts")["close"].resample("1D").last()
        out[s] = day
    px = pd.DataFrame(out).sort_index()
    px = px.ffill(limit=3).dropna(how="all")
    keep = [c for c in px.columns if px[c].notna().sum() > 400]
    return px[keep]


def simulate(px, lb, hold, thresh, budget, cost, rng=None):
    syms = list(px.columns)
    pv = np.array([SPEC[s] for s in syms], dtype=float)
    V = px.values
    start = max(lb, VOLWIN_D) + hold
    idx = np.arange(start, len(px) - hold, hold)
    if len(idx) < 15:
        return None
    pnl, prev, exposure = [], np.zeros(len(syms)), []
    for t in idx:
        win = V[t - VOLWIN_D:t]
        # dollar move over one HOLD, per contract, from the trailing
        # window only -- never from the period being traded
        step = np.diff(win[::max(1, hold // 5)], axis=0) * pv
        sd = np.nanstd(step, axis=0) * math.sqrt(max(1, hold // 5))
        sig = (V[t] - V[t - lb]) / V[t - lb]
        # trend strength in units of its own noise, so the threshold
        # means the same thing in gold and in gas
        nz = np.nanstd(np.diff(win, axis=0) / win[:-1], axis=0) * math.sqrt(lb)
        z = np.divide(sig, nz, out=np.zeros_like(sig), where=nz > 1e-12)
        fwd = (V[t + hold] - V[t]) * pv
        ok = (np.isfinite(sd) & (sd > 1e-9) & np.isfinite(z)
              & np.isfinite(fwd) & (np.abs(z) >= thresh))
        pos = np.zeros(len(syms))
        if ok.sum() >= 3:
            raw = np.zeros(len(syms))
            raw[ok] = 1.0 / sd[ok]
            raw = raw / raw.sum() * budget
            n = np.floor(raw + 0.5)
            n[~ok] = 0.0
            d = (rng.choice([-1.0, 1.0], size=len(syms)) if rng is not None
                 else np.sign(z))
            pos = n * d
        g = float(np.nansum(pos * np.nan_to_num(fwd)))
        turn = float(np.nansum(np.abs(pos - prev)))
        pnl.append(g - turn * cost / 2.0)
        exposure.append(float(np.abs(pos).sum()))
        prev = pos
    pnl = np.array(pnl)
    if len(pnl) < 15:
        return None
    days = (px.index[-1] - px.index[0]).days
    weeks = days / 7.0
    eq = np.cumsum(pnl)
    dd = float((np.maximum.accumulate(eq) - eq).max())
    sd_ = float(pnl.std(ddof=1))
    contracts_per_reb = float(np.mean(exposure))
    return {
        "lookback_d": lb, "hold_d": hold, "thresh": thresh,
        "budget": budget, "rebalances": len(pnl),
        "trades_per_week": round(contracts_per_reb / (hold / 5.0), 1),
        "net_per_week": round(float(pnl.sum()) / weeks, 2),
        "net_per_fortnight": round(2 * float(pnl.sum()) / weeks, 2),
        "max_drawdown": round(dd, 2),
        "mde_per_week": round(3.0 * sd_ * math.sqrt(len(pnl)) / weeks, 2),
        "pct_positive": round(100.0 * float((pnl > 0).mean()), 1),
        "worst": round(float(pnl.min()), 2),
        "avg_contracts_held": round(contracts_per_reb, 1),
    }


def main():
    print(__doc__, flush=True)
    print("=" * 78, flush=True)
    px = load_daily()
    days = (px.index[-1] - px.index[0]).days
    print(f"{len(px.columns)} markets, {len(px)} daily bars, "
          f"{days/365:.1f} years: {', '.join(px.columns)}\n", flush=True)
    rng = np.random.default_rng(8080)

    rows, ctrl = [], []
    for lb, hold, th in itertools.product(LOOKBACK_D, HOLD_D, THRESH):
        if lb < hold:
            continue
        r = simulate(px, lb, hold, th, BUDGET, COST)
        if r:
            rows.append(r)
        c = simulate(px, lb, hold, th, BUDGET, COST, rng=rng)
        if c:
            ctrl.append(c)

    # THE CAP IS A FILTER, NOT A SCORE. Revenue ranks what survives it.
    ok = [r for r in rows if r["max_drawdown"] < DD_CAP]
    ok.sort(key=lambda r: -r["net_per_week"])
    cn = [c["net_per_week"] for c in ctrl if c["max_drawdown"] < DD_CAP]
    cn.sort()
    p95 = cn[int(0.95 * (len(cn) - 1))] if cn else 0.0

    print(f"{len(rows)} configurations, {len(ok)} respect the "
          f"${DD_CAP:,.0f} drawdown cap")
    print(f"RANDOM-SIGN CONTROL under the same cap: p95 = "
          f"${p95:,.0f}/week  <- the bar\n")
    print(f"{'look':>5} {'hold':>5} {'thr':>4} {'tr/wk':>6} {'$/wk':>8} "
          f"{'$/fortnight':>12} {'maxDD':>8} {'MDE $/wk':>9} {'%+':>5}")
    for r in ok[:15]:
        print(f"{r['lookback_d']:>4}d {r['hold_d']:>4}d {r['thresh']:>4.1f} "
              f"{r['trades_per_week']:>6.1f} {r['net_per_week']:>8,.0f} "
              f"{r['net_per_fortnight']:>12,.0f} "
              f"{r['max_drawdown']:>8,.0f} {r['mde_per_week']:>9,.0f} "
              f"{r['pct_positive']:>4.0f}%")

    win = [r for r in ok if r["net_per_week"] > max(p95, 0.0)
           and r["net_per_week"] > r["mde_per_week"]]
    print(f"\n{len(win)} configuration(s) clear the cap AND beat the "
          f"random-sign p95 AND exceed their own MDE")
    for w in win[:6]:
        print(f"   {w['lookback_d']}d look / {w['hold_d']}d hold / "
              f"thr {w['thresh']}: ${w['net_per_week']:,.0f}/wk "
              f"(${w['net_per_fortnight']:,.0f}/fortnight), "
              f"DD ${w['max_drawdown']:,.0f}, "
              f"{w['trades_per_week']:.1f} trades/wk")
    if not win:
        if ok:
            b = min(r["mde_per_week"] for r in ok)
            best = ok[0]
            print(f"   Nothing clears. Best under the cap earns "
                  f"${best['net_per_week']:,.0f}/wk against an MDE of "
                  f"${best['mde_per_week']:,.0f}.")
            print(f"   The most sensitive configuration under the cap "
                  f"could only have seen ${b:,.0f}/week.")
        else:
            print(f"   NO configuration respects a ${DD_CAP:,.0f} drawdown "
                  f"at {BUDGET} micros.")
    json.dump({"dd_cap": DD_CAP, "budget": BUDGET, "years": round(days/365, 2),
               "markets": list(px.columns), "control_p95": round(p95, 2),
               "under_cap": ok, "winners": win, "all": rows},
              open(os.path.join(ROOT, "research", "LOWDD.json"), "w"), indent=1)
    print("\nwrote research/LOWDD.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
