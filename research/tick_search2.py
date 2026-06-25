"""Stage-2 refinement around the stage-1 winner (tight stop + big target,
INVERSE, low impulse). Explores lower impulse + shorter cooldown for more
trades/day, and the stop/target region around s6/t30.

Reuses the worker machinery from tick_search.
"""
from __future__ import annotations
import itertools, time
from concurrent.futures import ProcessPoolExecutor
import pandas as pd
from research import tick_search as ts1

def build_grid():
    imps    = [2.0, 3.0, 4.0]
    Ws      = [3, 4]
    pulls   = [0.118, 0.236, 0.382]
    stops   = [5.0, 6.0, 7.0, 8.0]
    tgts    = [24.0, 30.0, 36.0, 44.0]
    inverts = [True]
    cooldowns = [30, 60]
    max_holds = [600]
    max_waits = [300]
    min_legs  = [0.0]
    return list(itertools.product(imps, Ws, pulls, stops, tgts, inverts,
                                  cooldowns, max_holds, max_waits, min_legs))

def main():
    t0 = time.time()
    grid = build_grid()
    print(f"stage-2 grid: {len(grid)} configs", flush=True)
    ts1._init()
    results = []
    with ProcessPoolExecutor(max_workers=4, initializer=ts1._init) as ex:
        for i, r in enumerate(ex.map(ts1._eval, grid, chunksize=2)):
            if r: results.append(r)
            if (i+1) % 20 == 0:
                print(f"  {i+1}/{len(grid)}  {time.time()-t0:.0f}s", flush=True)
    df = pd.DataFrame(results).sort_values("net", ascending=False).reset_index(drop=True)
    df.to_csv("research/tick_search2_results.csv", index=False)
    cols = ["name","n","tr_day","wr","net","per_day","per_trade","maxDD",
            "train_per_day","test_per_day","test_wr"]
    pd.set_option("display.width", 240, "display.max_columns", 40)
    print(f"\nDONE {time.time()-t0:.0f}s")
    print("\nTOP 20 by net:")
    print(df.head(20)[cols].to_string(index=False))
    rob = df[(df.train_per_day>0)&(df.test_per_day>0)&(df.n>=300)].copy()
    rob["worst"] = rob[["train_per_day","test_per_day"]].min(axis=1)
    print(f"\nROBUST {len(rob)}; TOP 15 by worst-half $/day:")
    print(rob.sort_values("worst",ascending=False).head(15)[cols].to_string(index=False))
    print("\nHIGH-FREQUENCY robust (tr_day>=200), TOP 10 by worst-half:")
    print(rob[rob.tr_day>=200].sort_values("worst",ascending=False).head(10)[cols].to_string(index=False))

if __name__ == "__main__":
    main()
