"""Trade-level replay of the discovered cell. Means are not equity curves.

The grammar found the behaviour; this plays it as an account would trade it:
every signal in chronological order, one position at a time, signals that fire
mid-trade are SKIPPED (no overlap), entry one price change after confirmation
(the bounce-proof entry), exit a fixed number of price changes later. Bin
edges come from the five training contracts only, exactly as the era test
built them, so the held-out era stays held out.

Output is the distribution the account actually lives through: per-trade win
rate and averages, MAE (worst moment inside a trade), per-DAY best/worst/
average win/loss/%positive, per-WEEK the same, max drawdown, longest losing
streak -- at two cost levels, the measured ~$1.75 and the user's $4.40.

Usage: python tradecells.py [F_HOLD]      (default 200 price changes)
"""
import os
import sys

import numpy as np
import pandas as pd

os.environ.setdefault("DELAY", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glob

import grammar  # noqa: E402  (compress/decompose/leg_table, DELAY read at import)

ROOT = os.environ.get("M2_REPO", "/home/user/FutureTradingBot")
RAW = os.path.join(ROOT, "data", "tick", "raw")
OUT = os.path.join(ROOT, "research", "TRADE_REPLAY.md")
R = int(os.environ.get("R", "4"))
F = int(sys.argv[1]) if len(sys.argv) > 1 else 200
USD_TICK = 0.50
COSTS = [1.75, 4.40]
TRAIN = set(os.environ.get("TRAIN_CONTRACTS",
                           "NQU4,NQZ4,NQH5,NQM5,NQU5").split(","))
# the discovered cell: dist top quintile, vel top tercile, retr top quintile,
# volume BOTTOM tercile -- both directions
CELL = dict(dist_b=4, vel_b=2, retr_b=4, vol_b=0)

LINES = []


def log(s=""):
    print(s, flush=True)
    LINES.append(s)


files = sorted(glob.glob(os.path.join(RAW, "NQ*.parquet")))
tapes, legs = {}, {}
for f in files:
    c = os.path.basename(f).replace(".parquet", "")
    import pyarrow.parquet as pq
    t = pq.read_table(f, columns=["ts", "price", "size"])
    price = t.column("price").to_numpy(zero_copy_only=False).astype(np.float64)
    size = t.column("size").to_numpy(zero_copy_only=False).astype(np.float64)
    ts = t.column("ts").to_numpy(zero_copy_only=False).astype(np.int64)
    del t
    o = np.argsort(ts, kind="stable")
    price, size, ts = price[o], size[o], ts[o]
    pc, vol, tsc = grammar.compress(price, size, ts)
    del price, size, ts
    d = grammar.leg_table(pc, vol, tsc, R)
    if d is None:
        continue
    keep = ["conf", "dir", "dist_n", "vel_n", "retr", "vol_n"]
    legs[c] = d[keep].copy()
    tapes[c] = (pc, tsc)
    del d
    print(f"  {c}: {len(legs[c]):,} legs", flush=True)

# bin edges from the TRAIN contracts only, pooled -- identical to the era test
pool = pd.concat([legs[c] for c in legs if c in TRAIN], ignore_index=True)
edges = {}
for col, nb in (("dist_n", 5), ("vel_n", 3), ("retr", 5), ("vol_n", 3)):
    v = pool[col].replace([np.inf, -np.inf], np.nan).dropna()
    edges[col] = np.quantile(v, np.linspace(0, 1, nb + 1)[1:-1])
del pool

trades = []
for c, d in legs.items():
    pc, tsc = tapes[c]
    m = np.ones(len(d), bool)
    for col, b in (("dist_n", CELL["dist_b"]), ("vel_n", CELL["vel_b"]),
                   ("retr", CELL["retr_b"]), ("vol_n", CELL["vol_b"])):
        m &= grammar.qbins(d[col].values, edges[col]) == b
    m &= np.isfinite(d[["dist_n", "vel_n", "retr", "vol_n"]].values).all(1)
    ev = d[m].sort_values("conf")
    last_exit = -1
    n = len(pc)
    for conf, dr in zip(ev.conf.values, ev["dir"].values):
        ent = conf + 1                       # DELAY=1, the bounce-proof entry
        if ent <= last_exit or ent + F + 1 >= n:
            continue                          # in a trade already, or tape end
        side = -int(dr)                       # continuation of the new leg
        e0 = pc[ent]
        window = (pc[ent + 1: ent + F + 1] - e0) * side
        pnl_ticks = float(window[-1])
        mae = float(window.min())             # worst moment inside the trade
        mfe = float(window.max())
        trades.append((tsc[ent], c, side, pnl_ticks, mae, mfe,
                       c not in TRAIN))
        last_exit = ent + F

T = pd.DataFrame(trades, columns=["ts", "contract", "side", "ticks",
                                  "mae", "mfe", "oos"])
T["t"] = pd.to_datetime(T.ts)
T = T.sort_values("t").reset_index(drop=True)
T["gross"] = T.ticks * USD_TICK

log(f"# Trade replay of the discovered cell -- R={R}, hold {F} price changes")
log()
log(f"{len(T):,} non-overlapping trades over "
    f"{T.t.dt.date.nunique()} trading days "
    f"({T.t.min().date()} to {T.t.max().date()}). Signals during an open "
    f"trade were skipped, entry one price change after confirmation, bins "
    f"from the five training contracts only.")
log()

for cost in COSTS:
    T[f"net"] = T.gross - cost
    for scope, sub in (("HELD-OUT ERA (Dec 2025 - Jun 2026, never trained on)",
                        T[T.oos]),
                       ("training era (mid-2024 - late-2025)", T[~T.oos])):
        if not len(sub):
            continue
        net = sub.net
        day = sub.groupby(sub.t.dt.date).net.sum()
        wk = sub.groupby(pd.Grouper(key="t", freq="W")).net.sum()
        wk = wk[wk != 0]
        eq = net.cumsum()
        dd = (eq - eq.cummax()).min()
        wins = net > 0
        streak, worst_streak = 0, 0
        for w in wins.values:
            streak = 0 if w else streak + 1
            worst_streak = max(worst_streak, streak)
        wd, ld = day[day > 0], day[day <= 0]
        ww, lw = wk[wk > 0], wk[wk <= 0]
        log(f"## {scope} -- cost ${cost:.2f}/trade")
        log()
        log(f"| metric | value |")
        log(f"|---|---|")
        log(f"| trades | {len(sub):,} ({len(sub)/max(day.size,1):.1f}/day) |")
        log(f"| win rate | {wins.mean()*100:.1f}% |")
        log(f"| avg winner / avg loser | ${net[wins].mean():+.2f} / "
            f"${net[~wins].mean():+.2f} |")
        log(f"| expectancy per trade | ${net.mean():+.2f} |")
        log(f"| avg MAE (worst moment in a trade) | "
            f"{sub.mae.mean():.1f} ticks (${sub.mae.mean()*USD_TICK:.2f}) |")
        log(f"| **average day** | **${day.mean():+.2f}** |")
        log(f"| positive days | {len(wd)}/{day.size} "
            f"({len(wd)/day.size*100:.0f}%) |")
        log(f"| average winning day / losing day | ${wd.mean():+.2f} / "
            f"${ld.mean():+.2f} |")
        log(f"| best day / WORST day | ${day.max():+.2f} / "
            f"**${day.min():+.2f}** |")
        log(f"| **average week** | **${wk.mean():+.2f}** |")
        log(f"| positive weeks | {len(ww)}/{wk.size} "
            f"({len(ww)/max(wk.size,1)*100:.0f}%) |")
        log(f"| avg winning week / losing week | ${ww.mean():+.2f} / "
            f"${lw.mean() if len(lw) else 0:+.2f} |")
        log(f"| best week / WORST week | ${wk.max():+.2f} / "
            f"**${wk.min():+.2f}** |")
        log(f"| max drawdown (equity, 1 micro) | ${dd:+.2f} |")
        log(f"| longest losing streak | {worst_streak} trades |")
        log()

log("Day boundaries are UTC dates; MAE is the lowest point inside the trade "
    "before exit. One micro contract throughout. Costs are round-turn, "
    "charged once per trade.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(LINES) + "\n")
print("\nwrote", OUT)
