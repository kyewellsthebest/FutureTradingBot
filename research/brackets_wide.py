"""Wide brackets: 1:2 or better, ~5 trades a week, across 23 markets.

THE TARGET, stated before anything runs so it cannot drift:

    reward:risk  >= 1:2        (risk 1 unit to make 2)
    win rate     >= 45%
    trades       ~5 per week
    cost         $1.99 a round turn, measured

At 1:2 the chance win rate is 33.3%, so 45% is +11.7 percentage points
of real skill and +0.35R per trade. For scale, BRACKETS.md measured 56
brackets on this tape and found a mean edge over chance of -0.01
points. This is a large ask, and saying so in advance is part of the
method rather than pessimism.

WHY THIS IS NOT A REPEAT. Every bracket tested in this project was 6 to
20 POINTS -- a few dollars on a micro, against $1.99 of cost, so the
toll ate 10-30% of the target before any question of skill. Wide
brackets sized to DAILY volatility put the target at 1-4x ATR, hundreds
of dollars, where the toll is nearer 1%. That region has never been
searched here, and today established that the toll is the binding
constraint everywhere else.

HOW THE SEARCH IS STRUCTURED, which is what makes it affordable.
Bracket outcomes depend only on (entry bar, stop distance, target
distance) -- NOT on why the trade was taken. So the outcome of every
bar is precomputed once per bracket geometry, and a "signal" becomes a
boolean selection over those precomputed outcomes. Evaluating a
hundred signals then costs almost nothing, and the expensive part runs
once instead of a hundred times.

Resolution is on 5-minute HIGH/LOW, so which side was touched first is
read from the path rather than assumed. A bar that trades through both
is scored a LOSS -- the pessimistic convention, because with only OHLC
the true order is unknowable and flattering that ambiguity is how
backtests come to disagree with brokers.

THE CONTROL, and it is not a shuffle. The honest baseline for a bracket
is the win rate of the SAME bracket entered at every bar regardless of
signal. That is what "no skill" pays given this market's drift and
volatility, and it is measured per market and per geometry rather than
assumed to be 1/3. A signal earns its keep only by beating its own
all-bar baseline.

DELIBERATELY NOT A BILLION CONFIGURATIONS. The significance bar rises
as sqrt(2 ln N): a billion configs demands about 7.5 sigma, and a 45%
win rate over 500 trades is 5.6 sigma. Searching a billion would
REJECT the very result being looked for. The grid below is sized so the
bar stays near 4.5 sigma, and the bar actually applied is printed with
the results.
"""
from __future__ import annotations

import glob
import itertools
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DROP = {"SI"}
COST = 1.99
HORIZON = int(os.environ.get("HORIZON", "576"))     # 48h of 5-min bars
ATR_WIN = 288                                        # ~1 day
ENTRY_EVERY = int(os.environ.get("ENTRY_EVERY", "12"))   # hourly candidates
ATR_MULTS = [0.5, 1.0, 2.0, 3.0]                     # stop = k x ATR
RRS = [2.0, 3.0]                                     # target = RR x stop
SPEC = {
    "NQ": 2.0, "ES": 5.0, "YM": 0.50, "RTY": 5.0, "GC": 10.0, "HG": 2500.0,
    "CL": 100.0, "NG": 2500.0, "HO": 42000.0, "RB": 42000.0, "ZB": 1000.0,
    "ZN": 1000.0, "ZF": 1000.0, "ZT": 2000.0, "6E": 12500.0, "6A": 10000.0,
    "6B": 6250.0, "6J": 6250000.0, "ZC": 10.0, "ZW": 10.0, "ZS": 10.0,
    "ETH": 0.10, "MBT": 0.10,
}


def load(sym):
    p = os.path.join(ROOT, "data", "polygon", f"{sym}_5min.csv")
    d = pd.read_csv(p, parse_dates=["ts"],
                    usecols=["ts", "open", "high", "low", "close"])
    return d.set_index("ts").sort_index()


def outcomes(d, mult, rr, direction):
    """Win/loss/timeout for a bracket entered at every candidate bar.

    Vectorised over entries: the forward window of highs and lows is
    materialised once and the first touch of each side is found by
    argmax, so the cost is one pass rather than a Python loop.
    """
    c = d["close"].values.astype(np.float64)
    hi = d["high"].values.astype(np.float64)
    lo = d["low"].values.astype(np.float64)
    tr = np.maximum(hi - lo, np.abs(np.diff(c, prepend=c[0])))
    atr = pd.Series(tr).rolling(ATR_WIN).mean().values
    n = len(c)
    last = n - HORIZON - 1
    ent = np.arange(ATR_WIN + 1, last, ENTRY_EVERY)
    if len(ent) < 200:
        return None
    a = atr[ent]
    ok = np.isfinite(a) & (a > 0)
    ent, a = ent[ok], a[ok]
    stop_d = mult * a
    targ_d = rr * stop_d
    px = c[ent]
    if direction > 0:
        tgt, stp = px + targ_d, px - stop_d
    else:
        tgt, stp = px - targ_d, px + stop_d

    H = sliding_window_view(hi, HORIZON)[ent + 1]
    L = sliding_window_view(lo, HORIZON)[ent + 1]
    if direction > 0:
        hit_t = H >= tgt[:, None]
        hit_s = L <= stp[:, None]
    else:
        hit_t = L <= tgt[:, None]
        hit_s = H >= stp[:, None]
    any_t, any_s = hit_t.any(1), hit_s.any(1)
    ft = np.where(any_t, hit_t.argmax(1), HORIZON + 1)
    fs = np.where(any_s, hit_s.argmax(1), HORIZON + 1)
    # SAME BAR = LOSS. With only OHLC the order inside a bar is
    # unknowable, and assuming the good side came first is exactly how
    # a backtest ends up disagreeing with a broker.
    win = any_t & (ft < fs)
    loss = any_s & (fs <= ft)
    timeout = ~win & ~loss
    return {"ent": ent, "win": win, "loss": loss, "timeout": timeout,
            "stop_d": stop_d, "targ_d": targ_d, "atr": a}


def signals(d, ent):
    """A library of entry conditions, evaluated at the candidate bars."""
    c = d["close"]
    hi, lo = d["high"], d["low"]
    out = {}
    r = c.pct_change()
    for L in (12, 48, 144, 288, 576):
        mom = c.pct_change(L).values[ent]
        z = (c.pct_change(L) / r.rolling(L).std() / math.sqrt(L)).values[ent]
        out[f"mom{L}_up"] = mom > 0
        out[f"mom{L}_dn"] = mom < 0
        out[f"mom{L}_z1"] = z > 1.0
        out[f"mom{L}_zm1"] = z < -1.0
        bo = (c >= hi.rolling(L).max().shift(1)).values[ent]
        bd = (c <= lo.rolling(L).min().shift(1)).values[ent]
        out[f"breakout{L}"] = bo
        out[f"breakdown{L}"] = bd
    v = r.rolling(288).std()
    vq = v.rolling(2016).rank(pct=True).values[ent]
    out["vol_low"] = vq < 0.33
    out["vol_high"] = vq > 0.67
    hour = pd.DatetimeIndex(d.index[ent]).hour
    out["rth"] = (hour >= 13) & (hour < 20)
    out["overnight"] = ~out["rth"]
    out["all"] = np.ones(len(ent), bool)
    return {k: np.nan_to_num(val).astype(bool) for k, val in out.items()}


def main():
    t0 = time.time()
    print(__doc__, flush=True)
    print("=" * 78, flush=True)
    syms = [os.path.basename(p).replace("_5min.csv", "")
            for p in sorted(glob.glob(os.path.join(ROOT, "data", "polygon",
                                                   "*_5min.csv")))]
    syms = [s for s in syms if s not in DROP and s in SPEC]
    rows, n_cfg = [], 0
    for si, sym in enumerate(syms):
        d = load(sym)
        pv = SPEC[sym]
        weeks = (d.index[-1] - d.index[0]).days / 7.0
        for mult, rr, dirn in itertools.product(ATR_MULTS, RRS, (1, -1)):
            o = outcomes(d, mult, rr, dirn)
            if o is None:
                continue
            sig = signals(d, o["ent"])
            base = sig["all"]
            nb = base.sum()
            base_wr = float(o["win"][base].sum()
                            / max((o["win"] | o["loss"])[base].sum(), 1))
            for name, m in sig.items():
                dec = m & (o["win"] | o["loss"])
                nd = int(dec.sum())
                if nd < 100:
                    continue
                n_cfg += 1
                w = int(o["win"][dec].sum())
                wr = w / nd
                # dollars: target and stop are in price, times $/point
                gross = (w * o["targ_d"][dec].mean()
                         - (nd - w) * o["stop_d"][dec].mean()) * pv
                net = gross - nd * COST
                tpw = nd / weeks
                se = math.sqrt(max(base_wr * (1 - base_wr), 1e-9) / nd)
                rows.append({
                    "market": sym, "atr_mult": mult, "rr": rr,
                    "dir": "long" if dirn > 0 else "short", "signal": name,
                    "trades": nd, "trades_per_week": round(tpw, 2),
                    "win_rate": round(100 * wr, 2),
                    "baseline_win_rate": round(100 * base_wr, 2),
                    "edge_pp": round(100 * (wr - base_wr), 2),
                    "sigma": round((wr - base_wr) / se, 2),
                    "net_total": round(net, 0),
                    "net_per_week": round(net / weeks, 2),
                    "avg_target_$": round(o["targ_d"][dec].mean() * pv, 0),
                    "avg_stop_$": round(o["stop_d"][dec].mean() * pv, 0),
                })
        print(f"  {sym:>4} done  [{si+1}/{len(syms)}, {n_cfg:,} configs, "
              f"{time.time()-t0:.0f}s]", flush=True)

    bar = max(3.0, math.sqrt(2 * math.log(max(n_cfg, 2))) + 0.8)
    print(f"\n{n_cfg:,} configurations -> significance bar {bar:.2f} sigma")
    print(f"(a billion would demand "
          f"{math.sqrt(2*math.log(1e9))+0.8:.2f} sigma and reject this)\n")

    want = [r for r in rows
            if r["win_rate"] >= 45.0 and r["rr"] >= 2.0
            and 1.0 <= r["trades_per_week"] <= 12.0
            and r["net_per_week"] > 0]
    want.sort(key=lambda r: -r["sigma"])
    print(f"{len(want)} configurations meet the BRIEF "
          f"(>=45% win, >=1:2, 1-12 trades/wk, profitable)\n")
    hdr = (f"{'mkt':>4} {'sig':>13} {'dir':>5} {'atr':>4} {'rr':>4} "
           f"{'trades':>7} {'/wk':>5} {'win%':>6} {'base%':>6} {'edge':>6} "
           f"{'sigma':>6} {'$/wk':>8}")
    print(hdr)
    for r in want[:20]:
        print(f"{r['market']:>4} {r['signal']:>13} {r['dir']:>5} "
              f"{r['atr_mult']:>4} {r['rr']:>4} {r['trades']:>7,} "
              f"{r['trades_per_week']:>5.1f} {r['win_rate']:>6.2f} "
              f"{r['baseline_win_rate']:>6.2f} {r['edge_pp']:>6.2f} "
              f"{r['sigma']:>6.2f} {r['net_per_week']:>8,.0f}")

    surv = [r for r in want if r["sigma"] >= bar]
    print(f"\n{len(surv)} of those also clear the {bar:.2f} sigma bar "
          f"for {n_cfg:,} configurations")
    for r in surv[:10]:
        print(f"   {r['market']} {r['signal']} {r['dir']} "
              f"atr={r['atr_mult']} rr={r['rr']}: {r['win_rate']}% win "
              f"vs {r['baseline_win_rate']}% baseline, {r['sigma']} sigma, "
              f"${r['net_per_week']:,.0f}/wk, {r['trades_per_week']:.1f}/wk")
    json.dump({"n_configs": n_cfg, "bar_sigma": round(bar, 2),
               "meet_brief": want[:200], "survivors": surv,
               "all_count": len(rows)},
              open(os.path.join(ROOT, "research", "BRACKETS_WIDE.json"), "w"),
              indent=1)
    print(f"\nwrote research/BRACKETS_WIDE.json  ({time.time()-t0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
