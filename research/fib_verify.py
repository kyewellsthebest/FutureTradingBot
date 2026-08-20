"""Independent reproduction of the 15-minute Fib pullback on MNQ.

THE CLAIM, as handed over:

    15-min bars, momentum over 144 bars, impulse when |mom| > 3 x ATR,
    LIMIT entry at the 50% retracement, stop 2.5 x ATR, rr 1.5,
    trail 2.5 x ATR, ttl 12 bars, max hold 6 bars, one position at a time.

    ~5.6 trades/week, 50.6% win, PF 1.66, $198/week out of sample,
    $684 max drawdown on one micro, positive every year 2023-26.

WHY THIS IS WORTH THE COMPUTE RATHER THAN AN OPINION. 50.6% at rr 1.5
is +0.265R per trade, and chance at rr 1.5 is 40%, so the claim is
+10.6 percentage points of skill. That is the same size of claim as the
NQ breakout tested earlier today, which was real in NQ and vanished in
ES, YM and RTY. The only way to know which kind this is, is to build it
and look.

The handover says its own author could not reproduce it and that "every
mining number shrank when I tested it myself". That is worth taking
seriously: it is the single most common outcome when a strategy moves
between engines, and it usually means the original engine was
optimistic somewhere specific rather than wrong everywhere.

AMBIGUITIES IN THE SPEC, resolved explicitly because each one can move
the answer, and a reproduction that quietly picks one is not a
reproduction:

  ATR WINDOW is not given. Tested at 14 (the convention) and 144 (the
  momentum window), because "3 x ATR" means different things under each.

  FILL RULE for the limit. A limit at the 50% retracement is filled
  only if price actually TRADES there within the ttl. Assuming the fill
  because the level was calculated is the classic way a pullback
  backtest invents entries that never happened.

  SAME-BAR STOP AND TARGET is scored a LOSS. With OHLC the order inside
  a bar is unknowable, and this strategy's stop (2.5 ATR) and target
  (3.75 ATR) are close enough that ties are common.

  TRAIL vs MAX HOLD. Both are specified; the trail can only help while
  the position is open, and max hold 6 bars closes it regardless.

CONTROLS

  RANDOM ENTRY at the same times with the same brackets -- what this
  bracket geometry pays with no signal at all.
  SHUFFLED IMPULSE -- the signal times taken from a rotated series, so
  the setup fires as often but never where the impulse actually was.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PV = 2.0                      # MNQ $/point
COST = float(os.environ.get("COST", "1.99"))
LB = 144
K_IMPULSE = 3.0
PB = 0.5
SP_ATR = 2.5
RR = 1.5
TTL = 12
MAXHOLD = 6
THROUGH_TICKS = float(os.environ.get('THROUGH_TICKS', '0'))


def bars15():
    p = os.path.join(ROOT, "data", "polygon", "NQ_5min.csv")
    d = pd.read_csv(p, parse_dates=["ts"],
                    usecols=["ts", "open", "high", "low", "close"]
                    ).set_index("ts").sort_index()
    return d.resample("15min").agg({"open": "first", "high": "max",
                                    "low": "min", "close": "last"}).dropna()


def atr(d, win):
    pc = d["close"].shift(1)
    tr = np.maximum(d["high"] - d["low"],
                    np.maximum((d["high"] - pc).abs(),
                               (d["low"] - pc).abs()))
    return tr.rolling(win).mean()


def run(d, atr_win, mode="real", seed=0):
    o = d["open"].values; h = d["high"].values
    lo = d["low"].values; c = d["close"].values
    a = atr(d, atr_win).values
    n = len(d)
    mom = np.full(n, np.nan)
    mom[LB:] = c[LB:] - c[:-LB]
    rng = np.random.default_rng(seed)
    if mode == "shuffled":
        mom = np.roll(mom, len(mom) // 3)

    trades = []
    i = LB + 1
    while i < n - TTL - MAXHOLD - 1:
        if not np.isfinite(a[i]) or not np.isfinite(mom[i]) or a[i] <= 0:
            i += 1
            continue
        if abs(mom[i]) <= K_IMPULSE * a[i]:
            i += 1
            continue
        direction = 1 if mom[i] > 0 else -1
        if mode == "random":
            direction = int(rng.choice([-1, 1]))
        # 50% retracement of the impulse just measured
        limit = c[i] - direction * PB * abs(mom[i])
        stop_d = SP_ATR * a[i]
        targ_d = RR * stop_d
        # THE FILL MUST ACTUALLY HAPPEN. Walk the ttl window and only
        # enter if price trades through the limit.
        # FILL REALISM. Touching a limit is not being filled by it.
        # research/DEPTH.md measured resting MNQ orders filling only
        # 6.6% of the time within two minutes, because price leaves
        # before the queue is reached. A backtest that fills on a touch
        # collects exactly the cases where price kissed the level and
        # reversed -- which are the winners. THROUGH_TICKS requires the
        # market to trade past the limit before the fill is granted.
        thru = THROUGH_TICKS * 0.25
        filled = -1
        for j in range(i + 1, min(i + 1 + TTL, n)):
            if (direction > 0 and lo[j] <= limit - thru) or \
               (direction < 0 and h[j] >= limit + thru):
                filled = j
                break
        if filled < 0:
            i += 1
            continue
        entry = limit
        stop = entry - direction * stop_d
        targ = entry + direction * targ_d
        pnl, exit_i = None, None
        best = entry
        for j in range(filled, min(filled + MAXHOLD + 1, n)):
            # THE TRAIL MUST BE SET FROM BARS ALREADY CLOSED. An
            # earlier version updated `best` with THIS bar's high and
            # then tested this bar's low against the resulting trail,
            # which silently assumes the high printed before the low --
            # a look-ahead inside the bar, and it inflated every variant
            # including the controls.
            if direction > 0:
                trail = best - SP_ATR * a[i]
                hit_t = h[j] >= targ
                hit_s = lo[j] <= stop
                hit_tr = (lo[j] <= trail) and j > filled
                best = max(best, h[j])
            else:
                trail = best + SP_ATR * a[i]
                hit_t = lo[j] <= targ
                hit_s = h[j] >= stop
                hit_tr = (h[j] >= trail) and j > filled
                best = min(best, lo[j])
            if hit_s or (hit_t and hit_s):
                # TIE = LOSS. The order inside a bar is unknowable.
                pnl = -stop_d; exit_i = j; break
            if hit_t:
                pnl = targ_d; exit_i = j; break
            if hit_tr:
                pnl = direction * (trail - entry); exit_i = j; break
        if pnl is None:
            j = min(filled + MAXHOLD, n - 1)
            pnl = direction * (c[j] - entry)
            exit_i = j
        trades.append({"t": d.index[filled], "pnl": pnl * PV - COST,
                       "dir": direction})
        i = exit_i + 1          # ONE POSITION AT A TIME
    return pd.DataFrame(trades)


def report(tr, label, weeks):
    if len(tr) < 20:
        print(f"  {label:22} only {len(tr)} trades -- not enough")
        return None
    p = tr["pnl"].values
    wins, losses = p[p > 0], p[p <= 0]
    pf = (wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float("inf")
    eq = np.cumsum(p)
    dd = float((np.maximum.accumulate(eq) - eq).max())
    se = p.std(ddof=1) / math.sqrt(len(p))
    out = {"label": label, "trades": len(p),
           "per_week": round(len(p) / weeks, 2),
           "win_rate": round(100 * len(wins) / len(p), 1),
           "profit_factor": round(pf, 2),
           "per_trade": round(float(p.mean()), 2),
           "net_per_week": round(float(p.sum()) / weeks, 2),
           "t": round(float(p.mean() / se), 2),
           "max_drawdown": round(dd, 2),
           "total": round(float(p.sum()), 0)}
    print(f"  {label:22} {out['trades']:>5} trades {out['per_week']:>5.1f}/wk "
          f"win {out['win_rate']:>5.1f}%  PF {out['profit_factor']:>5.2f}  "
          f"${out['net_per_week']:>7,.0f}/wk  t {out['t']:>5.2f}  "
          f"DD ${out['max_drawdown']:>7,.0f}")
    return out


def main():
    print(__doc__)
    print("=" * 78)
    d = bars15()
    weeks = (d.index[-1] - d.index[0]).days / 7.0
    print(f"NQ 15-min: {len(d):,} bars, {weeks:.0f} weeks "
          f"({d.index[0].date()} to {d.index[-1].date()})\n")
    print("CLAIM:  ~5.6/wk, win 50.6%, PF 1.66, $198/wk OOS, DD $684\n")
    rows = []
    for aw in (14, 144):
        print(f"--- ATR window {aw} " + "-" * 46)
        r = report(run(d, aw, "real"), f"REAL atr{aw}", weeks)
        if r:
            r["atr_win"] = aw
            rows.append(r)
        report(run(d, aw, "random", seed=1), f"random-direction", weeks)
        report(run(d, aw, "shuffled"), f"shuffled-impulse", weeks)
        print()

    # year by year on the better of the two, as the claim asserts
    if rows:
        best = max(rows, key=lambda r: r["net_per_week"])
        tr = run(d, best["atr_win"], "real")
        if len(tr):
            print(f"YEAR BY YEAR (ATR {best['atr_win']}), claim says all "
                  f"positive:")
            tr["year"] = pd.DatetimeIndex(tr["t"]).year
            for y, g in tr.groupby("year"):
                wk = max((g["t"].iloc[-1] - g["t"].iloc[0]).days / 7.0, 1)
                print(f"    {y}  {len(g):>4} trades  "
                      f"win {100*float((g['pnl']>0).mean()):>5.1f}%  "
                      f"${g['pnl'].sum()/wk:>7,.0f}/wk  "
                      f"total ${g['pnl'].sum():>8,.0f}")
    json.dump(rows, open(os.path.join(ROOT, "research", "FIB_VERIFY.json"),
                         "w"), indent=1, default=str)
    print("\nwrote research/FIB_VERIFY.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
