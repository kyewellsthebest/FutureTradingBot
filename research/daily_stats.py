"""The full sheet, marked to market DAILY, at 2 minis of risk.

WHY DAILY AND NOT PER TRADE. A funded account has two kill switches,
not one: a trailing drawdown AND a maximum loss in a single day. Every
number in this project so far has been per trade or per week, which
says nothing about the second. A strategy holding a two-week position
can be perfectly fine on a trade basis and still breach a daily limit
on a bad Tuesday, and the account is gone before the trade resolves.

So the position is carried and marked to market every day, and the
daily series is what gets measured.

SIZE. "2 minis" is 20 micros of the same instrument, so the book is the
20-micro configuration -- the best one found at roughly ten trades a
week: a 4-week lookback, 2-week hold, sized inversely to each market's
own dollar volatility across 23 markets.

WHAT IS REPORTED, being exactly what was asked for:

    best day, best week
    average winning day, average losing day
    average win, average loss (per trade)
    % of days positive, % of weeks positive
    maximum drawdown
    worst single day  <- the funded-account killer

AND THE THING THAT HAS TO BE SAID ALONGSIDE THEM. This configuration
earns less per week than the smallest effect its own sample can
resolve. Every number below is measured honestly from the tape and is
still, statistically, indistinguishable from a coin flip run through
the same book. They describe what this rule DID across 4.2 years, not
what it will do. A plan that buys a funded account expecting these
numbers to repeat is betting on a result the data cannot support.

That is a separate question from whether the plan is reasonable -- a
cheap account with a capped downside and an uncapped upside can be a
sane bet even on a weak edge. But the odds should be read off the real
numbers, not off a backtest presented as a forecast.
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DROP = {"SI"}
COST = 1.99
BUDGET = int(os.environ.get("BUDGET", "20"))      # 20 micros = 2 minis
LOOKBACK_D = int(os.environ.get("LOOKBACK_D", "20"))   # 4 weeks
HOLD_D = int(os.environ.get("HOLD_D", "10"))           # 2 weeks
VOLWIN_D = 60
SPEC = {
    "NQ": 2.0, "ES": 5.0, "YM": 0.50, "RTY": 5.0, "GC": 10.0, "HG": 2500.0,
    "CL": 100.0, "NG": 2500.0, "HO": 42000.0, "RB": 42000.0, "ZB": 1000.0,
    "ZN": 1000.0, "ZF": 1000.0, "ZT": 2000.0, "6E": 12500.0, "6A": 10000.0,
    "6B": 6250.0, "6J": 6250000.0, "ZC": 10.0, "ZW": 10.0, "ZS": 10.0,
    "ETH": 0.10, "MBT": 0.10,
}


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


def run(px, rng=None):
    """Daily P&L series, plus the per-trade record."""
    syms = list(px.columns)
    pv = np.array([SPEC[s] for s in syms], dtype=float)
    V = px.values
    start = max(LOOKBACK_D, VOLWIN_D) + 1
    pos = np.zeros(len(syms))
    daily, trades, open_trades = [], [], {}
    for t in range(start, len(px) - 1):
        if (t - start) % HOLD_D == 0:
            win = V[t - VOLWIN_D:t]
            step = np.diff(win, axis=0) * pv * math.sqrt(HOLD_D)
            sd = np.nanstd(step, axis=0)
            sig = (V[t] - V[t - LOOKBACK_D]) / V[t - LOOKBACK_D]
            ok = np.isfinite(sd) & (sd > 1e-9) & np.isfinite(sig) \
                & np.isfinite(V[t])
            new = np.zeros(len(syms))
            if ok.sum() >= 3:
                raw = np.zeros(len(syms))
                raw[ok] = 1.0 / sd[ok]
                raw = raw / raw.sum() * BUDGET
                n = np.floor(raw + 0.5)
                n[~ok] = 0.0
                d = (rng.choice([-1.0, 1.0], size=len(syms)) if rng is not None
                     else np.sign(sig))
                new = n * np.nan_to_num(d)
            # book the trades that closed, open the ones that did not
            for i in range(len(syms)):
                if pos[i] != 0 and new[i] != pos[i] and i in open_trades:
                    e = open_trades.pop(i)
                    trades.append(pos[i] * (V[t][i] - e) * pv[i]
                                  - abs(pos[i]) * COST)
                if new[i] != 0 and (pos[i] != new[i] or i not in open_trades):
                    open_trades[i] = V[t][i]
            turn = float(np.nansum(np.abs(new - pos)))
            cost_today = turn * COST / 2.0
            pos = new
        else:
            cost_today = 0.0
        move = np.nan_to_num((V[t + 1] - V[t]) * pv)
        daily.append(float(np.nansum(pos * move)) - cost_today)
    return np.array(daily), np.array(trades), px.index[start:len(px) - 1]


def stats(daily, trades, idx, label):
    eq = np.cumsum(daily)
    dd = float((np.maximum.accumulate(eq) - eq).max())
    s = pd.Series(daily, index=idx)
    wk = s.resample("W").sum()
    wins, losses = daily[daily > 0], daily[daily < 0]
    tw, tl = trades[trades > 0], trades[trades < 0]
    years = (idx[-1] - idx[0]).days / 365
    return {
        "label": label,
        "years": round(years, 2),
        "trades": int(len(trades)),
        "trades_per_week": round(len(trades) / (len(idx) / 7.0), 1),
        "net_total": round(float(daily.sum()), 2),
        "net_per_week": round(float(daily.sum()) / (len(idx) / 7.0), 2),
        "best_day": round(float(daily.max()), 2),
        "worst_day": round(float(daily.min()), 2),
        "best_week": round(float(wk.max()), 2),
        "worst_week": round(float(wk.min()), 2),
        "avg_winning_day": round(float(wins.mean()), 2) if len(wins) else 0,
        "avg_losing_day": round(float(losses.mean()), 2) if len(losses) else 0,
        "pct_days_positive": round(100.0 * len(wins) / max(len(daily), 1), 1),
        "pct_weeks_positive": round(100.0 * float((wk > 0).mean()), 1),
        "avg_win_per_trade": round(float(tw.mean()), 2) if len(tw) else 0,
        "avg_loss_per_trade": round(float(tl.mean()), 2) if len(tl) else 0,
        "win_rate_pct": round(100.0 * len(tw) / max(len(trades), 1), 1),
        "max_drawdown": round(dd, 2),
        "worst_day_pct_of_maxdd": round(100.0 * abs(float(daily.min()))
                                        / max(dd, 1), 1),
    }


def main():
    print(__doc__, flush=True)
    print("=" * 78, flush=True)
    px = load_daily()
    # These are DAILY bars, so the constants are already in days --
    # multiplying by 5 printed a 100-day lookback for a 20-day rule.
    print(f"{len(px.columns)} markets, {LOOKBACK_D}-day lookback "
          f"(~{LOOKBACK_D//5} weeks), {HOLD_D}-day hold "
          f"(~{HOLD_D//5} weeks), {BUDGET} micros (= {BUDGET//10} minis)\n")
    d, tr, idx = run(px)
    real = stats(d, tr, idx, "REAL")
    rng = np.random.default_rng(4242)
    c, ctr, _ = run(px, rng=rng)
    ctrl = stats(c, ctr, idx, "coin flip")

    rows = [("trades", "trades", ""), ("trades per week", "trades_per_week", ""),
            ("", "", ""),
            ("BEST DAY", "best_day", "$"), ("WORST DAY", "worst_day", "$"),
            ("BEST WEEK", "best_week", "$"), ("worst week", "worst_week", "$"),
            ("", "", ""),
            ("avg WINNING day", "avg_winning_day", "$"),
            ("avg LOSING day", "avg_losing_day", "$"),
            ("avg win per trade", "avg_win_per_trade", "$"),
            ("avg loss per trade", "avg_loss_per_trade", "$"),
            ("", "", ""),
            ("% days positive", "pct_days_positive", "%"),
            ("% weeks positive", "pct_weeks_positive", "%"),
            ("win rate per trade", "win_rate_pct", "%"),
            ("", "", ""),
            ("MAX DRAWDOWN", "max_drawdown", "$"),
            ("worst day as % of maxDD", "worst_day_pct_of_maxdd", "%"),
            ("", "", ""),
            ("$/week", "net_per_week", "$"),
            ("total over period", "net_total", "$")]
    print(f"{'':28} {'REAL':>12} {'coin flip':>12}")
    for lbl, key, unit in rows:
        if not lbl:
            print()
            continue
        a, b = real[key], ctrl[key]
        fa = f"${a:,.0f}" if unit == "$" else (f"{a}%" if unit == "%" else f"{a}")
        fb = f"${b:,.0f}" if unit == "$" else (f"{b}%" if unit == "%" else f"{b}")
        print(f"{lbl:28} {fa:>12} {fb:>12}")
    print(f"\n  {real['years']} years of daily marks")
    json.dump({"real": real, "control": ctrl},
              open(os.path.join(ROOT, "research", "DAILY_STATS.json"), "w"),
              indent=1)
    print("  wrote research/DAILY_STATS.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
