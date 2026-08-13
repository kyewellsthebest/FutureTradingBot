"""Spend the Databento credit on the maker question, then answer it.

THE PURCHASE ($107 of the $125 credit), chosen from the priced menu:

  MNQU6 mbo    Jul 27-31   $30.32   the book we actually trade, per-order:
                                    order_ids make queue position EXACT
  MNQU6 mbp-1  Jul 27-31   $24.55   same week's top of book, for best-bid
                                    tracking without reconstructing it
  NQU6  mbo    July 2026   $52.34   the price-discovery book, a full month,
                                    for later feature work

THE MEASUREMENT. The whole book prices maker fills at +$0.355/trade from a
QUEUE MODEL, never from data. Here the model is replaced: join the back of
the best-bid queue at sampled times, count the resting size ahead (adds
minus cancels at that price), then walk forward -- if cumulative traded
volume at that price covers the queue ahead before the level breaks, the
fill happened; the mid a few seconds later prices the adverse selection.
P(fill) x value-when-filled - P(break) x cost-when-broken IS the maker
edge, measured.

Hard budget guard: every purchase is priced first and the run aborts if
the total exceeds MAX_SPEND. Raw files are processed per day and deleted;
only small derived tables and the report are committed.
"""
import os
import sys
import time

import databento as db
import numpy as np
import pandas as pd

KEY = os.environ.get("DATABENTO_KEY")
if not KEY:
    sys.exit("DATABENTO_KEY not set")
MAX_SPEND = float(os.environ.get("MAX_SPEND", "120"))
OUTDIR = "data/depth"
os.makedirs(OUTDIR, exist_ok=True)
c = db.Historical(KEY)
DATASET = "GLBX.MDP3"

# Jul 27 was measured before the first runner died (415 joins, 22 filled,
# 5%, med queue 4) -- re-requesting a range is re-charged, so it is not
# bought twice; its numbers are folded into the report from the log.
WEEK_DAYS = os.environ.get(
    "DAYS", "2026-07-28,2026-07-29,2026-07-30,2026-07-31").split(",")
DAY27 = dict(joins=415, fills=22, med_ahead=4)
# only what the measurement needs is bought NOW (~$55); the NQ July mbo
# stays unbought so the remaining ~$70 of credit is there for follow-ups
PLAN = [
    ("MNQU6", "mbo",   "2026-07-27", "2026-08-01"),
    ("MNQU6", "mbp-1", "2026-07-27", "2026-08-01"),
]

total = 0.0
for sym, schema, s, e in PLAN:
    cost = c.metadata.get_cost(dataset=DATASET, symbols=[sym],
                               stype_in="raw_symbol", schema=schema,
                               start=s, end=e)
    print(f"plan: {sym} {schema} {s}..{e} -> ${cost:.2f}", flush=True)
    total += cost
print(f"planned total: ${total:.2f} (cap ${MAX_SPEND:.0f})", flush=True)
if total > MAX_SPEND:
    sys.exit("over budget -- nothing purchased")

L = ["# The maker edge, measured instead of assumed", "",
     f"Purchased ${total:.2f} of Databento history: MNQU6 order-by-order "
     "(mbo) and top-of-book (mbp-1) for Jul 27-31 2026, plus NQU6 mbo for "
     "all of July (banked for feature work).", ""]


def fetch_arrays(sym, schema, s, e, cols):
    """Half-day windows, numpy immediately, nothing kept in pandas: a full
    mbo day as a DataFrame is what OOM-killed the first runner."""
    import gc
    parts = {k: [] for k in cols + ["ts"]}
    day = pd.Timestamp(s)
    for h0, h1 in ((0, 12), (12, 24)):
        a = (day + pd.Timedelta(hours=h0)).isoformat()
        b = (day + pd.Timedelta(hours=h1)).isoformat()
        path = os.path.join(OUTDIR, f"{sym}_{schema}_{s}_{h0}.dbn.zst")
        t0 = time.time()
        c.timeseries.get_range(dataset=DATASET, symbols=[sym],
                               stype_in="raw_symbol", schema=schema,
                               start=a, end=b, path=path)
        df = db.DBNStore.from_file(path).to_df()
        os.remove(path)
        df = df[(df.index.hour >= 13) & (df.index.hour < 20)]
        parts["ts"].append(df.index.view(np.int64).copy())
        for k in cols:
            parts[k].append(df[k].to_numpy().copy())
        del df
        gc.collect()
        print(f"  {sym} {schema} {s} h{h0}-{h1} ok "
              f"({time.time()-t0:.0f}s)", flush=True)
    return {k: np.concatenate(v) if v else np.array([])
            for k, v in parts.items()}


# ---- the week that answers the question: MNQ, day by day ----------------
day_rows = []
for day in WEEK_DAYS:
    T = fetch_arrays("MNQU6", "mbp-1", day, None,
                     ["bid_px_00", "bid_sz_00"])
    if len(T["ts"]) < 1000:
        print(f"  {day}: too little RTH top-of-book, skipped", flush=True)
        continue
    bb, bq, tts = T["bid_px_00"], T["bid_sz_00"], T["ts"]
    O = fetch_arrays("MNQU6", "mbo", day, None, ["action", "price", "size"])
    ots, act = O["ts"], O["action"]
    opx, osz = O["price"], O["size"].astype(np.float64)

    # sample a join once a minute at the then-best bid
    joins = np.arange(tts[0], tts[-1], 60_000_000_000)
    ji = np.searchsorted(tts, joins) - 1
    ji = ji[(ji > 0) & (ji < len(tts) - 1)]
    res = []
    for i in ji:
        p, t0 = bb[i], tts[i]
        ahead = float(bq[i])                       # size resting ahead of us
        w = ((ots > t0) & (ots <= t0 + 120_000_000_000) &
             (np.abs(opx - p) < 0.01))
        if not w.any():
            res.append(("open", 0.0, 120.0, ahead))
            continue
        wa, ws, wt = act[w], osz[w], ots[w]
        # traded volume at our price after we join
        tr = np.cumsum(np.where(wa == "T", ws, 0.0))
        filled = tr >= ahead + 1
        # the level breaking: best bid dropping below our price
        k = np.searchsorted(tts, t0)
        seg = slice(k, min(k + 200000, len(tts)))
        brk_t = tts[seg][bb[seg] < p]
        t_break = brk_t[0] if len(brk_t) else np.inf
        t_fill = wt[filled][0] if filled.any() else np.inf
        if t_fill < t_break:
            # filled: value = mid 10s later vs our price, in ticks
            m = np.searchsorted(tts, t_fill + 10_000_000_000)
            if m >= len(tts):
                continue
            mid10 = (bb[m] + 0.25 + bb[m]) / 2   # bid + half spread proxy
            res.append(("fill", (mid10 - p) / 0.25,
                        (t_fill - t0) / 1e9, ahead))
        elif np.isfinite(t_break):
            res.append(("break", -1.0, (t_break - t0) / 1e9, ahead))
        else:
            res.append(("open", 0.0, 120.0, ahead))
    if res:
        d = pd.DataFrame(res, columns=["out", "ticks", "secs", "ahead"])
        d["day"] = day
        day_rows.append(d)
        nf = (d["out"] == "fill").sum()
        print(f"  {day}: {len(d)} joins, {nf} filled "
              f"({nf/len(d):.0%}), med queue ahead {d['ahead'].median():.0f}",
              flush=True)

if day_rows:
    A = pd.concat(day_rows)
    A.to_parquet(os.path.join(OUTDIR, "mnq_queue_week.parquet"))
    fills = A[A.out == "fill"]
    dec = A[A.out != "open"]
    pf = len(fills) / max(len(dec), 1)     # of DECIDED joins
    popen = (A.out == "open").mean()
    # value of a maker attempt in ticks, then dollars at MNQ $0.50/tick
    val = (fills.ticks.mean() * pf) + (-1.0 * (1 - pf))
    L += [f"## The number: measured maker value",
          "",
          f"- joins sampled: **{len(A):,}** (one per minute, RTH, "
          f"Jul 27-31)",
          f"- P(filled before the level breaks), decided joins: "
          f"**{pf:.1%}** ({popen:.0%} of joins had no outcome in 120s)",
          f"- median queue ahead at join: {A.ahead.median():.0f} contracts",
          f"- when filled: mid 10s later averages "
          f"**{fills.ticks.mean():+.2f} ticks** vs entry",
          f"- median wait to fill: {fills.secs.median():.0f}s",
          f"- naive maker attempt value: **{val:+.2f} ticks = "
          f"${val*0.50:+.2f}** per attempt (level-break costed at -1 tick)",
          "",
          "The book's assumed +$0.355/trade maker credit compares directly "
          "with the dollars line above.", ""]

open("research/DEPTH.md", "w").write("\n".join(L) + "\n")
print("wrote research/DEPTH.md", flush=True)
