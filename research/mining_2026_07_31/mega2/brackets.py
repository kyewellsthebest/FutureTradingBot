"""What is the REAL win rate of a +T / -S bracket on NQ? Nobody has measured it.

Every search in this repo used a time-based exit: enter, hold N bars, exit.
A bracket is a different object -- target and stop, first touch wins, exit is
path-dependent -- and the win rate is a real quantity rather than an artifact
of the holding period. The user's spec (45% at +12/-6, hundreds of trades a
day) is a bracket, and a bracket has never been tested here.

The premise deserves a direct measurement, not theory:

  * On a coin-flip walk, P(hit +12 before -6) = 6/(6+12) = 33.3%, and the
    expectancy is exactly zero before costs, whatever T and S are.
  * The user needs 45%.
  * So the entire question is: what does the REAL tape do? If NQ's brackets
    come in at 33.3%, the path carries nothing and no bracket will ever pay.
    If they come in at 35%, that is a genuine deviation from a random walk,
    and it is worth real money at this frequency.

This measures every (T, S) on the actual tick path by first touch -- no bar
approximation, no assumption about which came first, the real sequence of
prices. Entries are sampled evenly across the tape, which is the honest
"no-skill" baseline: whatever a bracket returns from a blind entry is what any
strategy using that bracket starts from before its signal does any work.

Both directions are run. Costs are charged once per round turn.

Reading it: the `edge vs chance` column is the whole point. It is the real win
rate minus S/(S+T), the coin-flip rate for that bracket shape. Positive and
consistent across the grid means the path has structure a bracket can harvest.
Zero across the grid means it does not, and that is a stronger statement than
any single backtest because it holds for EVERY target and stop at once.
"""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
CACHE = os.path.join(ROOT, "data", "tick", "cache")
OUT = os.path.join(ROOT, "research", "BRACKETS.md")
PT = 4                       # ticks per NQ point
USD_PT = 2.00
COST = 1.99
W = int(os.environ.get("W", "12000"))        # forward horizon, price changes
STEP = int(os.environ.get("STEP", "400"))    # sample an entry every STEP
CHUNK = int(os.environ.get("CHUNK", "4000"))
TARGETS = [4, 6, 8, 10, 12, 16, 20, 30]
STOPS = [2, 3, 4, 6, 8, 12, 20]
TRAIN = set("NQU4,NQZ4,NQH5,NQM5,NQU5".split(","))
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


def bracket_stats(pc, side):
    """First-touch outcome of every (T,S) for entries sampled across the tape.

    cummax/cummin of the forward window are computed ONCE and reused for the
    whole grid, which is what makes 56 brackets affordable on 18M prints.
    """
    n = len(pc)
    idx = np.arange(0, n - W - 1, STEP, dtype=np.int64)
    res = {(T, S): [0, 0, 0.0, 0] for T in TARGETS for S in STOPS}
    for c0 in range(0, len(idx), CHUNK):
        ii = idx[c0:c0 + CHUNK]
        # forward window as a strided view, then running extremes
        win = np.lib.stride_tricks.sliding_window_view(pc, W + 1)[ii]
        p0 = win[:, 0].astype(np.float64)
        fwd = win[:, 1:].astype(np.float64)
        cmax = np.maximum.accumulate(fwd, axis=1)
        cmin = np.minimum.accumulate(fwd, axis=1)
        last = fwd[:, -1]
        for T in TARGETS:
            for S in STOPS:
                up = p0 + side * T * PT
                dn = p0 - side * S * PT
                if side > 0:
                    hitT = cmax >= up[:, None]
                    hitS = cmin <= dn[:, None]
                else:
                    hitT = cmin <= up[:, None]
                    hitS = cmax >= dn[:, None]
                aT = np.where(hitT.any(1), hitT.argmax(1), W + 1)
                aS = np.where(hitS.any(1), hitS.argmax(1), W + 1)
                win_ = aT < aS
                lose = aS < aT
                neither = ~(win_ | lose)
                pnl = np.where(win_, T, np.where(lose, -S, 0.0))
                # unresolved inside the horizon: exit at the window's end
                if neither.any():
                    pnl[neither] = (side * (last[neither] - p0[neither])) / PT
                r = res[(T, S)]
                r[0] += int(win_.sum())
                r[1] += len(ii)
                r[2] += float(pnl.sum())
                r[3] += int(neither.sum())
        del win, fwd, cmax, cmin
    return res


tapes = {}
for p in sorted(glob.glob(os.path.join(CACHE, "NQ*_R4.npz"))):
    c = os.path.basename(p).split("_")[0]
    if c in TRAIN:
        continue                      # held-out contracts only
    tapes[c] = np.load(p, allow_pickle=False)["pc"].astype(np.int64)
    print(f"  {c}: {len(tapes[c]):,} price changes", flush=True)

log("# The real win rate of a bracket on NQ")
log()
log("Every previous search here used a time-based exit — enter, hold N bars, "
    "exit. A bracket is a different object: target and stop, first touch "
    "wins, and the win rate is a real quantity. It had never been measured.")
log()
log(f"Measured by first touch on the actual tick path across "
    f"{len(tapes)} held-out NQ contracts, "
    f"{sum(len(t) for t in tapes.values()):,} price changes. Entries sampled "
    f"every {STEP} price changes — the honest no-skill baseline, since "
    f"whatever a blind entry returns is where any strategy using that bracket "
    f"starts before its signal does any work.")
log()
log("**The column that matters is `edge vs chance`.** On a coin-flip walk a "
    "+T/-S bracket wins S/(S+T) of the time and returns exactly zero before "
    "costs, for every T and S. If the real tape beats that consistently "
    "across the grid, the price path carries structure a bracket can harvest. "
    "If it does not, no bracket will ever pay — and that is a much stronger "
    "statement than one backtest, because it covers every target and stop at "
    "once.")
log()

for side, name in ((1, "LONG"), (-1, "SHORT")):
    tot = {}
    for c, pc in tapes.items():
        r = bracket_stats(pc, side)
        for k, v in r.items():
            t = tot.setdefault(k, [0, 0, 0.0, 0])
            for i in range(4):
                t[i] += v[i]
        print(f"  {name} {c} done", flush=True)
    log(f"## {name} brackets")
    log()
    log("| target | stop | R:R | trades | win rate | chance rate | "
        "**edge vs chance** | $/trade gross | net of $1.99 |")
    log("|---|---|---|---|---|---|---|---|---|")
    rows = []
    for (T, S), (w, n, pnl, un) in sorted(tot.items()):
        if not n:
            continue
        wr = w / n
        ch = S / (S + T)
        g = pnl / n * USD_PT
        rows.append((wr - ch, T, S, n, wr, ch, g))
    for d, T, S, n, wr, ch, g in sorted(rows, key=lambda x: -x[0]):
        log(f"| {T} | {S} | {T/S:.1f}:1 | {n:,} | {wr*100:.2f}% | "
            f"{ch*100:.2f}% | **{d*100:+.2f} pp** | ${g:+.3f} | "
            f"${g - COST:+.2f} |")
    log()
    ds = np.array([r[0] for r in rows])
    log(f"Across all {len(rows)} brackets: mean edge over chance "
        f"**{ds.mean()*100:+.2f} percentage points**, "
        f"{int((ds > 0).sum())}/{len(ds)} positive "
        f"(chance would give {len(ds)/2:.0f}). Best gross "
        f"**${max(r[6] for r in rows):+.3f}** per trade against ${COST:.2f} "
        f"of cost.")
    log()

log("## What the user's spec needs, against what the tape gives")
log()
log("45% on a +12/-6 bracket. Chance on that shape is 33.3%, so the spec "
    "needs **+11.7 percentage points** of skill. The +12/-6 row above is the "
    "measured starting point from a blind entry; the gap between it and 45% "
    "is what an entry signal would have to supply.")
log()
log("---")
log("First touch on the real tick sequence, no bar approximation. Entries "
    "unresolved inside the forward horizon exit at the horizon. Held-out "
    "contracts only.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(L) + "\n")
print("\nwrote", OUT)
