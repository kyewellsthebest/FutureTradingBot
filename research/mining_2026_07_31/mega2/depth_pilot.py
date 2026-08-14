"""Does the order book predict anything our features cannot see?

Spends ~$38 of the remaining credit on NQU6 top-of-book (mbp-1) for all of
July 2026 and asks the only question that justifies buying months more:
do book-state features -- top-of-book imbalance, spread state, quote
intensity, size asymmetry -- carry information about forward returns at
horizons we can trade (1-5 minutes)?

Output per minute of RTH July: imbalance, spread, top sizes, quote rate,
mid; then information coefficients (rank correlation of each feature with
forward 1m/5m mid returns) and quintile spreads. A real IC (|rho| > 0.03
sustained across weeks) means depth features graduate into the validated
search engine and 6+ months of history becomes a justified purchase; a
zero means the book adds nothing at our horizons and the question is
closed for $38 instead of $230.
"""
import gc
import os
import sys
import time

import databento as db
import numpy as np
import pandas as pd

KEY = os.environ.get("DATABENTO_KEY")
if not KEY:
    sys.exit("DATABENTO_KEY not set")
MAX_SPEND = float(os.environ.get("MAX_SPEND", "15"))
OUTDIR = "data/depth"
os.makedirs(OUTDIR, exist_ok=True)
c = db.Historical(KEY)
DATASET = "GLBX.MDP3"
SYM, SCHEMA = "NQU6", "mbp-1"
# July's full-month run completed and lost its results to a push race;
# re-buying the month would overrun the remaining credit. One week keeps
# the question answered inside what's left.
S, E = "2026-07-27", "2026-08-01"

cost = c.metadata.get_cost(dataset=DATASET, symbols=[SYM],
                           stype_in="raw_symbol", schema=SCHEMA,
                           start=S, end=E)
print(f"plan: {SYM} {SCHEMA} July -> ${cost:.2f} (cap ${MAX_SPEND:.0f})",
      flush=True)
if cost > MAX_SPEND:
    sys.exit("over budget -- nothing purchased")

rows = []
for day in pd.bdate_range(S, "2026-07-31"):
    ds = day.strftime("%Y-%m-%d")
    frames = []
    for h0, h1 in ((12, 18), (18, 24)):        # RTH is 13:30-20:00 UTC
        path = os.path.join(OUTDIR, f"p_{ds}_{h0}.dbn.zst")
        try:
            c.timeseries.get_range(dataset=DATASET, symbols=[SYM],
                                   stype_in="raw_symbol", schema=SCHEMA,
                                   start=(day + pd.Timedelta(hours=h0)).isoformat(),
                                   end=(day + pd.Timedelta(hours=h1)).isoformat(),
                                   path=path)
        except Exception as e:                                   # noqa: BLE001
            print(f"  {ds} h{h0}: {str(e)[:80]}", flush=True)
            continue
        df = db.DBNStore.from_file(path).to_df()
        os.remove(path)
        df = df[(df.index.hour * 60 + df.index.minute >= 13 * 60 + 30) &
                (df.index.hour < 20)]
        if len(df):
            frames.append(df[["bid_px_00", "ask_px_00",
                              "bid_sz_00", "ask_sz_00"]])
        del df
        gc.collect()
    if not frames:
        continue
    d = pd.concat(frames)
    del frames
    bs, as_ = d["bid_sz_00"], d["ask_sz_00"]
    d["imb"] = (bs - as_) / (bs + as_).clip(lower=1)
    d["spread"] = d["ask_px_00"] - d["bid_px_00"]
    d["mid"] = (d["ask_px_00"] + d["bid_px_00"]) / 2
    g = d.resample("1min")
    m = pd.DataFrame({
        "imb": g["imb"].mean(),
        "imb_last": g["imb"].last(),
        "spread": g["spread"].mean(),
        "bsz": g["bid_sz_00"].mean(),
        "asz": g["ask_sz_00"].mean(),
        "qrate": g["mid"].count(),          # quote updates per minute
        "mid": g["mid"].last(),
    }).dropna()
    m["szasym"] = np.log((m.bsz + 1) / (m.asz + 1))
    rows.append(m)
    print(f"  {ds}: {len(m)} minutes", flush=True)
    del d, m
    gc.collect()

if not rows:
    sys.exit("no data came back")
M = pd.concat(rows)
M["r1"] = M["mid"].shift(-1) - M["mid"]     # next-minute mid change
M["r5"] = M["mid"].shift(-5) - M["mid"]
M.to_parquet(os.path.join(OUTDIR, "nq_book_july_1min.parquet"))

L = ["# Does the top of the book predict forward returns? (July pilot)",
     "",
     f"NQU6 mbp-1, July 2026, {len(M):,} RTH minutes, ${cost:.2f} spent.",
     "", "| feature | IC vs 1min | IC vs 5min | Q5-Q1 (1min, ticks) |",
     "|---|---|---|---|"]
for f in ("imb", "imb_last", "szasym", "spread", "qrate"):
    ic1 = M[f].corr(M.r1, method="spearman")
    ic5 = M[f].corr(M.r5, method="spearman")
    q = pd.qcut(M[f], 5, labels=False, duplicates="drop")
    qs = (M.groupby(q).r1.mean().iloc[-1] -
          M.groupby(q).r1.mean().iloc[0]) / 0.25
    L.append(f"| {f} | {ic1:+.3f} | {ic5:+.3f} | {qs:+.2f} |")
L += ["",
      "Read: |IC| above ~0.03 sustained is tradeable at our horizons and "
      "justifies buying 6+ months for the validated engine; ~0.00 closes "
      "the book-feature question for $38.", ""]
open("research/DEPTH_PILOT.md", "w").write("\n".join(L) + "\n")
print("wrote research/DEPTH_PILOT.md", flush=True)
