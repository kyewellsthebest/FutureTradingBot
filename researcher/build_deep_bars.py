"""Precompute the deep tier so it survives to a deploy target.

THE PROBLEM. Tier 2 is 4.7 GB of raw NQ tick data under `data/tick/`,
which is gitignored -- correctly, it is far too large for a repo. But
Railway builds from the repo, so the deployed searcher would find zero
tick contracts and skip the entire deep tier.

Worse, it would skip it SILENTLY: `if cs:` around the tier-2 block means
no contracts simply means no message. The console would show a healthy
searcher working through its cycles while a third of its data was
missing. That is the exact failure shape this project keeps finding --
not a wrong number, an absent one, reported as normal.

THE FIX. Bars, not ticks. Everything tier 2 actually uses is
close/vol/n/absret at 15s, 60s and 300s. Resampling 25M trades down to
24k bars throws away nothing the searcher reads and shrinks the tier by
three orders of magnitude, so it fits in the repo and rides along to
every deploy.

    8 contracts x {15s, 60s, 300s}  ->  data/research_bars/

This is lossless with respect to the questions tier 2 asks. It is NOT
lossless in general -- anything needing trade-by-trade detail (queue
position, individual print size, sub-second timing) is gone, and such a
hypothesis belongs at tier 3 on book data anyway, where those columns
actually exist.

Run:  python -m researcher.build_deep_bars
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from researcher import data_tiers as DT                       # noqa: E402

OUT = os.path.join(DT.ROOT, "data", "research_bars")
RES = [15, 60, 300]


def main():
    os.makedirs(OUT, exist_ok=True)
    cs = DT.tier2_contracts()
    if not cs:
        print("no raw tick contracts under data/tick/raw -- nothing to do.")
        print("This script runs where the raw data lives; the OUTPUT is "
              "what gets committed.")
        return 1
    total = 0
    print(f"{len(cs)} contracts x {len(RES)} resolutions\n")
    for p in cs:
        cn = os.path.basename(p).replace(".parquet", "")
        for r in RES:
            dst = os.path.join(OUT, f"{cn}_{r}s.parquet")
            if os.path.exists(dst):
                print(f"  {cn} @{r:>3}s  exists, skipping")
                continue
            a = DT.tier2(p, bar_s=r)
            if a is None or len(a) < 500:
                print(f"  {cn} @{r:>3}s  too few bars, skipped")
                continue
            # float32 halves the file and is far finer than any price
            # increment these instruments trade in -- NQ ticks at 0.25
            # on a ~24,000 handle needs 6 significant figures; float32
            # gives 7.
            a = a.astype("float32")
            a.to_parquet(dst, compression="zstd")
            sz = os.path.getsize(dst)
            total += sz
            print(f"  {cn} @{r:>3}s  {len(a):>7,} bars  {sz/1e6:6.2f} MB")
    print(f"\ntotal {total/1e6:.1f} MB in {OUT}")
    print("Commit data/research_bars/ so the deep tier reaches Railway.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
