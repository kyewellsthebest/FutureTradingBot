"""Which market is even winnable? Cost measured in units of the market's own noise.

Every family tested so far has died the same death, and it is always the same
arithmetic: an edge worth $0.50-1.50 a trade against $1.75-2.00 of cost. The
leg grammar was real and still lost. Book imbalance was real and worth about
a seventh of the spread. Market making was real and negative after adverse
selection. None of those failed because the signal was fake. They failed
because the toll was bigger than the move.

That points at a question nobody asked before spending months searching:
IN WHICH MARKET IS THE TOLL SMALLEST RELATIVE TO WHAT THE MARKET DOES?

The comparison has to be scale-free, because a tick means something different
in every contract. So for each market, at each event horizon, this measures
the full distribution of |forward move| in dollars on one micro contract, and
asks where the all-in cost sits inside that distribution:

  * cost as a fraction of the AVERAGE absolute move -- the toll as a share of
    a typical trade's raw material
  * the PERCENTILE of moves that the cost exceeds -- "on this fraction of
    trades, the entire move is eaten before you are right or wrong"
  * the EDGE REQUIRED as a fraction of one standard deviation of the move --
    which is the honest difficulty rating, because that is the effect size a
    search must find

A market where cost is 60% of the average move is close to unwinnable no
matter how good the signal. A market where it is 5% will forgive a weak one.
That ratio, not the signal, is what decides whether the remaining effort has
anywhere to go -- and it is the number that says whether bond tick data
(ZB/ZN, tick values of $31.25 and $15.62) is worth acquiring.

A NOTE ON WHY THE CLOCK APPEARS HERE. The first version of this file used
event horizons, and it ranked GC as the most forgiving market on the board by
a factor of ten. That was an artifact of MY OWN measurement: GC's tape has
8.6M ticks where NQ has 184M, so fifty price changes in GC spans far more real
market movement than fifty in NQ. Event time runs at a different speed in
every market, which is exactly what makes it the right representation for
SEARCHING inside one market -- and the wrong one for COMPARING across markets.
So the horizons below are wall-clock, used only as a common ruler to put
fifteen markets on one axis. No bar in any search is ever built this way.

Tick density is printed alongside, because it is the thing that fooled the
first version and it also affects how a K-print bar in megatick compares
across markets.
"""
import glob
import os
import sys

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import megatick as mt  # noqa: E402  (market table, cost model, loader)

OUT = os.path.join(mt.ROOT, "research", "COST_RATIO.md")
HZ = [int(x) for x in os.environ.get("HZ", "60,300,1800,7200").split(",")]
HZLAB = {60: "1 min", 300: "5 min", 1800: "30 min", 7200: "2 h"}
MAXROWS = int(os.environ.get("MAXROWS", "8000000"))
L = []


def log(s=""):
    print(s, flush=True)
    L.append(s)


log("# Where is the toll smallest? Cost in units of each market's own noise")
log()
log("Every dead family died the same way: a real edge of $0.50-1.50 against "
    "$1.75-2.00 of cost. That is a toll problem, not a signal problem, and it "
    "is measured here directly. For each market, the distribution of "
    "|forward move| in dollars on one micro contract at each event horizon, "
    "and where the all-in cost sits inside it.")
log()
log("`cost / avg move` is the share of a typical trade's raw material eaten "
    "by the toll. `% eaten` is the fraction of trades whose ENTIRE move is "
    "smaller than the cost. `edge needed` is the effect size a search has to "
    "find, in standard deviations — that is the difficulty rating.")
log()

rows = []
for mk in mt.WANT:
    cfg = mt.MARKETS[mk]
    fs = sorted(glob.glob(os.path.join(mt.ROOT, cfg["dir"], cfg["glob"])))
    if not fs:
        log(f"- {mk}: no tick data")
        continue
    # the LARGEST file, not the middle one by name. Contract files are wildly
    # uneven -- GCH5 holds 22,805 rows where GC totals 8.6M -- and picking a
    # near-empty one made GC look like 161 ticks/day and the most forgiving
    # market on the board.
    fs = sorted(fs, key=lambda x: pq.ParquetFile(x).metadata.num_rows)
    pick = fs[-1]
    try:
        px, sz, sp, ts = mt.load_one(pick, cfg)
    except Exception as e:                                  # noqa: BLE001
        log(f"- {mk}: load failed ({type(e).__name__})")
        continue
    if len(px) > MAXROWS:
        px, ts = px[:MAXROWS], ts[:MAXROWS]
        sp = sp[:MAXROWS] if sp is not None else None
    chg = np.r_[True, px[1:] != px[:-1]]
    pc, pt = px[chg], ts[chg]
    span_days = max((ts[-1] - ts[0]) / 86400e9, 1e-9)
    dens = len(px) / span_days
    if cfg.get("fx"):
        spread_usd = float(np.median(sp[chg])) * cfg["usd_tick"] * 2.0
        cost = spread_usd
    else:
        cost = mt.COMM + mt.SLIP_TICKS * cfg["usd_tick"]
    for F in HZ:
        # index of the first print at least F seconds later -- the clock is a
        # ruler here, never a bar rule
        j = np.searchsorted(pt, pt + np.int64(F) * 1_000_000_000, side="left")
        keep = j < len(pc)
        if keep.sum() < 5000:
            continue
        mv = np.abs(pc[j[keep]] - pc[keep]) * cfg["usd_tick"]
        avg = float(mv.mean())
        sd = float(mv.std())
        eaten = float((mv < cost).mean() * 100)
        rows.append((mk, F, cost, avg, sd, eaten,
                     cost / max(avg, 1e-9), cost / max(sd, 1e-9), dens))
    del px, sz, sp, ts, pc, pt
    print(f"  {mk}: {os.path.basename(pick)}, {len(chg):,} rows, "
          f"{dens:,.0f} ticks/day", flush=True)

log("| market | ticks/day | window | all-in cost | avg abs move | "
    "**cost / avg move** | % of trades whose whole move is eaten | "
    "edge needed (sd) |")
log("|---|---|---|---|---|---|---|---|")
for mk, F, cost, avg, sd, eaten, ratio, sdr, dens in sorted(
        rows, key=lambda r: (r[1], r[6])):
    log(f"| {mk} | {dens:,.0f} | {HZLAB.get(F, str(F))} | ${cost:.2f} | "
        f"${avg:.2f} | **{ratio*100:.0f}%** | {eaten:.0f}% | {sdr:.2f} |")
log()

log("## The ranking that matters")
log()
log("Averaged across horizons, cheapest toll first:")
log()
log("| market | mean cost / avg move | verdict |")
log("|---|---|---|")
agg = {}
for mk, F, cost, avg, sd, eaten, ratio, sdr, dens in rows:
    agg.setdefault(mk, []).append(ratio)
for mk, v in sorted(agg.items(), key=lambda x: np.mean(x[1])):
    r = float(np.mean(v)) * 100
    verdict = ("forgiving — a weak signal can still pay" if r < 15 else
               "workable if the signal is good" if r < 35 else
               "hostile — needs a strong signal" if r < 60 else
               "close to unwinnable at this size")
    log(f"| {mk} | **{r:.0f}%** | {verdict} |")
log()
log("Read it as: to make money you must predict more than this share of a "
    "typical move, on average, forever. The leg-grammar cell predicted about "
    "$0.87 of NQ's move and lost, which is the same statement in dollars.")
log()
log("Not in this table because there is no tick data yet: **ZB and ZN**, "
    "whose tick values are $31.25 and $15.62 against the same $0.74 "
    "commission. That is the one structural way the ratio above gets "
    "dramatically smaller, and it is the strongest argument for acquiring "
    "bond tick data — see TODO_FOR_USER.md.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
open(OUT, "w").write("\n".join(L) + "\n")
print("\nwrote", OUT)
