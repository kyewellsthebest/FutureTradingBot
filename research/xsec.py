"""Cross-sectional search across 23 markets at 30 minutes to 2 hours.

WHY THIS SHAPE, and it comes straight from the arithmetic rather than
from taste.

  BREADTH, because power demands it. The per-trade spread of outcomes
  is about 21 round trips, so the smallest edge that can ever be found
  is 5 x 21 / sqrt(n). At 60 trades a week over two years that is 1.33
  RT -- an edge worth $800 a week would be INVISIBLE. At 500 a week it
  is 0.46 RT. Breadth is not a preference here, it is the difference
  between a search that can see and one that cannot.

  LONG HOLDS, because cost demands it. At one minute the toll is 5.5%
  of NQ's average move; at two hours it is 0.5%. Every short-horizon
  search in this repo -- 26 billion configurations of it -- was run
  where the toll eats the edge by construction.

  500 TRADES A WEEK SPREAD ACROSS MARKETS, not crammed into one. 500 in
  NQ alone means two-minute holds, which is the dead zone. 500 across
  20 markets is 25 each, which at these horizons is exactly right.

WHAT IT TESTS. Cross-sectional rank effects: at each rebalance, score
every market on a lookback, go long the strongest and short the
weakest, hold, repeat. This is a documented anomaly class in equities
and futures, and -- checked against the 155 documents in research/ --
it has never been run here. Every prior search scored markets ONE AT A
TIME. A cross-sectional signal is invisible to that design no matter
how many configurations it tries, because the signal lives in the
comparison BETWEEN markets, not inside any of them.

Both signs are tested. Momentum (buy strength) and reversal (buy
weakness) are the same measurement with opposite sign, and deciding
which one to believe in advance would be the researcher choosing the
answer.

THE CONTROLS

  1  SHUFFLED. The same pipeline with the forward returns permuted
     ACROSS MARKETS within each timestamp -- which destroys the
     cross-sectional relationship while preserving each market's own
     volatility and the overall drift. That is the precise null: "the
     ranking carries no information", not "returns are random".

  2  DOLLAR-NEUTRAL BY CONSTRUCTION. Equal long and short legs, so the
     result cannot be the market going up. That artifact cost a whole
     run earlier today.

  3  POWER IS REPORTED WHETHER OR NOT ANYTHING IS FOUND. Every null
     result states the smallest edge it COULD have detected. The
     searcher's silence has been read as "there is nothing there" when
     it meant "nothing big enough for me to see", and those are
     different sentences.

SUCCESS CRITERION, fixed before the run:

    net > 0 at $0.85 all-in per round turn, AND the shuffled control
    at the same settings is not, AND |t| >= 3 on the per-trade mean,
    AND the edge exceeds the minimum detectable effect for its own
    trade count.
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
# SI is permanently excluded at the user's instruction.
DROP = {"SI"}
COSTS = [0.85, 1.99]
# how many of the complex must be open for a cross-section to exist
MIN_OPEN = int(os.environ.get("MIN_OPEN", "18"))
BAR_MIN = 5

# $/point for the smallest tradeable contract, and tick, from runner.py
SPEC = {
    "NQ": (2.0, 0.25, 0.10), "ES": (5.0, 0.25, 0.20), "YM": (0.50, 1.0, 0.20),
    "RTY": (5.0, 0.10, 0.20), "GC": (10.0, 0.10, 0.20),
    "HG": (2500.0, 0.0005, 0.20), "CL": (100.0, 0.01, 0.20),
    "NG": (2500.0, 0.001, 0.20), "HO": (42000.0, 0.0001, 0.30),
    "RB": (42000.0, 0.0001, 0.30), "ZB": (1000.0, 0.03125, 2.50),
    "ZN": (1000.0, 0.015625, 2.50), "ZF": (1000.0, 0.0078125, 2.50),
    "ZT": (2000.0, 0.00390625, 2.50), "6E": (12500.0, 0.0001, 0.20),
    "6A": (10000.0, 0.0001, 0.20), "6B": (6250.0, 0.0001, 0.20),
    "6J": (6250000.0, 0.000001, 0.20), "ZC": (10.0, 0.125, 0.20),
    "ZW": (10.0, 0.125, 0.20), "ZS": (10.0, 0.125, 0.20),
    "ETH": (0.10, 0.05, 0.20), "MBT": (0.10, 5.0, 0.20),
}

# Extended to where the arithmetic points. The toll is 5.5% of the move
# at one minute and 0.5% at two hours; at a DAY it is nearer 0.1%. The
# first sweep covered 30m-2h and found a clean null with power. Longer
# holds cost less and were never tested cross-sectionally at all.
LOOKBACKS = [int(x) for x in os.environ.get(
    "LOOKBACKS", "6,12,24,48,96,288,864").split(",")]   # 30m .. 3d
HOLDS = [int(x) for x in os.environ.get(
    "HOLDS", "6,12,24,72,288,864").split(",")]          # 30m .. 3d
LEGS = [3, 5]                          # markets per side


def load():
    """Every market on one clock, as a wide frame of closes."""
    out = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "polygon",
                                           "*_5min.csv"))):
        sym = os.path.basename(p).replace("_5min.csv", "")
        if sym in DROP or sym not in SPEC:
            continue
        d = pd.read_csv(p, parse_dates=["ts"], usecols=["ts", "close"])
        out[sym] = d.set_index("ts")["close"]
    px = pd.DataFrame(out).sort_index()
    # ALIGN ON THE HOURS WHEN THE COMPLEX IS ACTUALLY OPEN. A naive
    # outer join over 23 markets that keep different hours leaves every
    # column mostly empty -- measured coverage ran from 0.19 (soybeans)
    # to 0.93 (natural gas), so a "must be 80% present" filter deleted
    # 22 of 23 markets and left the search comparing NG to itself.
    #
    # A cross-sectional signal is a comparison BETWEEN markets at one
    # instant, so it is only defined when they are open together. Keep
    # the timestamps where most of the complex is trading, then judge
    # coverage on those rows rather than on the union.
    present = px.notna().sum(axis=1)
    px = px[present >= MIN_OPEN].ffill(limit=3)
    keep = [c for c in px.columns if px[c].notna().mean() > 0.90]
    dropped = sorted(set(px.columns) - set(keep))
    if dropped:
        print(f"  dropped for thin coverage even in common hours: "
              f"{', '.join(dropped)}")
    return px[keep].dropna(how="any")


def run_cell(px, lb, hold, leg, sign, costs, rng=None, shuffle=False):
    """One configuration. Returns per-trade dollar P&L, dollar-neutral."""
    r = px.pct_change(lb)
    fwd = px.shift(-hold) / px - 1.0
    # rebalance every `hold` bars -- trade at the signal's own cadence
    idx = np.arange(0, len(px) - hold, hold)
    sig = r.iloc[idx].values
    fw = fwd.iloc[idx].values
    if shuffle:
        # Destroy the CROSS-SECTIONAL link, keep each row's own returns.
        fw = np.array([rng.permutation(row) for row in fw])
    pv = np.array([SPEC[c][0] for c in px.columns], dtype=float)
    # dollars per contract for a 1% move, so legs are comparable across
    # markets whose point values differ by six orders of magnitude
    notional = px.iloc[idx].values * pv

    pnl, ntr = [], 0
    for i in range(len(sig)):
        s, f, nv = sig[i], fw[i], notional[i]
        ok = np.isfinite(s) & np.isfinite(f) & np.isfinite(nv) & (nv > 0)
        if ok.sum() < 2 * leg + 2:
            continue
        si, fi, nvi = s[ok], f[ok], nv[ok]
        order = np.argsort(si)
        short, long_ = order[:leg], order[-leg:]
        if sign < 0:
            short, long_ = long_, short
        # EQUAL DOLLARS PER LEG. Sizing by contract count would make
        # this a bet on whichever market has the biggest point value.
        target = 1000.0
        w = np.zeros(len(si))
        w[long_] = target / nvi[long_] / leg
        w[short] = -target / nvi[short] / leg
        gross = float(np.sum(w * fi * nvi))
        contracts = float(np.sum(np.abs(w)))
        pnl.append((gross, contracts))
        ntr += 2 * leg
    if len(pnl) < 100:
        return None
    g = np.array([p[0] for p in pnl])
    c = np.array([p[1] for p in pnl])
    weeks = (px.index[-1] - px.index[0]).total_seconds() / (7 * 86400)
    out = {"lb": lb, "hold": hold, "leg": leg,
           "sign": "momentum" if sign > 0 else "reversal",
           "rebalances": len(g), "trades": ntr,
           "trades_per_week": round(ntr / weeks, 1),
           "gross_per_reb": round(float(g.mean()), 4),
           "gross_per_week": round(float(g.sum()) / weeks, 2)}
    sd = float(g.std(ddof=1))
    out["t_gross"] = round(float(g.mean() / (sd / math.sqrt(len(g)))), 2)
    for cost in costs:
        net = g - c * cost
        out[f"net_per_week_at_{cost}"] = round(float(net.sum()) / weeks, 2)
        sdn = float(net.std(ddof=1))
        out[f"t_at_{cost}"] = round(
            float(net.mean() / (sdn / math.sqrt(len(net)))), 2)
        # THE THING THAT MUST ALWAYS BE REPORTED: what could not have
        # been seen. 3 sigma on the per-rebalance mean, in $/week.
        mde = 3.0 * sdn / math.sqrt(len(net))
        out[f"mde_per_week_at_{cost}"] = round(mde * len(net) / weeks, 2)
    return out


def main():
    print(__doc__, flush=True)
    print("=" * 74, flush=True)
    px = load()
    weeks = (px.index[-1] - px.index[0]).total_seconds() / (7 * 86400)
    print(f"{len(px.columns)} markets, {len(px):,} bars, {weeks:.0f} weeks: "
          f"{', '.join(px.columns)}\n", flush=True)

    rng = np.random.default_rng(4242)
    rows, nulls = [], []
    combos = list(itertools.product(LOOKBACKS, HOLDS, LEGS, (1, -1)))
    for k, (lb, hold, leg, sign) in enumerate(combos):
        r = run_cell(px, lb, hold, leg, sign, COSTS)
        if r:
            rows.append(r)
        n = run_cell(px, lb, hold, leg, sign, COSTS, rng=rng, shuffle=True)
        if n:
            nulls.append(n)
        if (k + 1) % 10 == 0:
            print(f"  {k+1}/{len(combos)} configurations", flush=True)

    key = "net_per_week_at_0.85"
    rows.sort(key=lambda r: r[key], reverse=True)
    nl = sorted(n[key] for n in nulls)
    p99 = nl[int(0.99 * (len(nl) - 1))] if nl else 0.0

    print(f"\n{len(rows)} configurations, {len(nulls)} shuffled controls")
    print(f"SHUFFLED p99 = ${p99:,.0f}/wk  <- the bar a real cell must clear\n")
    print(f"{'sign':>9} {'lb':>4} {'hold':>5} {'leg':>4} {'tr/wk':>7} "
          f"{'$/wk@0.85':>10} {'t':>6} {'MDE $/wk':>9} {'$/wk@1.99':>10}")
    for r in rows[:12]:
        print(f"{r['sign']:>9} {r['lb']:>4} {r['hold']:>5} {r['leg']:>4} "
              f"{r['trades_per_week']:>7.0f} "
              f"{r['net_per_week_at_0.85']:>10,.0f} "
              f"{r['t_at_0.85']:>6.2f} "
              f"{r['mde_per_week_at_0.85']:>9,.0f} "
              f"{r['net_per_week_at_1.99']:>10,.0f}")

    winners = [r for r in rows
               if r[key] > 0 and r[key] > p99 and abs(r["t_at_0.85"]) >= 3.0
               and r[key] > r["mde_per_week_at_0.85"]]
    print(f"\n{len(winners)} configuration(s) clear ALL FOUR hurdles "
          f"(positive, beat shuffled p99, |t|>=3, above own MDE)")
    for w in winners[:6]:
        print(f"   {w['sign']} lb={w['lb']} hold={w['hold']} leg={w['leg']}: "
              f"${w[key]:,.0f}/wk at $0.85, "
              f"${w['net_per_week_at_1.99']:,.0f}/wk at $1.99, "
              f"t={w['t_at_0.85']}, {w['trades_per_week']:.0f} trades/wk")
    if not winners:
        best_mde = (min(r["mde_per_week_at_0.85"] for r in rows)
                    if rows else float("nan"))
        print(f"\n   NOTHING FOUND -- and here is what that does NOT mean.")
        print(f"   The most sensitive configuration could only have seen an "
              f"edge of ${best_mde:,.0f}/week or larger.")
        print(f"   Anything smaller than that was never visible to this "
              f"search. Silence here is not absence.")
    p = os.path.join(ROOT, "research", "XSEC.json")
    json.dump({"weeks": round(weeks, 1), "markets": list(px.columns),
               "shuffled_p99": round(p99, 2), "rows": rows,
               "winners": winners}, open(p, "w"), indent=1)
    print(f"\nwrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
