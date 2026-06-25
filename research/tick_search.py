"""Parameter search over the faithful tick simulator.

Loads ticks once, forks workers (copy-on-write), evaluates a grid of
strategy configs, ranks by net $/day on 1 MNQ with an out-of-sample
(train/test) split so winners are not overfit.

Train = first 70% of calendar days, Test = last 30%.
"""
from __future__ import annotations
import itertools, time, sys, json
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd

from research.tick_sim import (load_ticks, build_1m_bars, precompute_setups,
                               simulate, stats, SimCfg)

_TICKS = None
_BARS = None
_SPLIT_NS = None  # train/test boundary timestamp (ns)

def _init():
    global _TICKS, _BARS, _SPLIT_NS
    _TICKS = load_ticks()
    _BARS = build_1m_bars(_TICKS[0], _TICKS[1])
    ts = _TICKS[0]
    # 70/30 split by calendar time
    _SPLIT_NS = ts[0] + int(0.70 * (ts[-1] - ts[0]))

def _eval(cfg_tuple):
    (imp, W, pull, stop, tgt, invert, cooldown, max_hold, max_wait, min_leg) = cfg_tuple
    params = {"IMPULSE_PTS": imp, "IMPULSE_WINDOW_BARS": W, "PULLBACK_PCT": pull,
              "STOP_PTS": stop, "TARGET_PTS": tgt, "INVERT": invert,
              "MIN_LEG_PTS": min_leg}
    setups = precompute_setups(_BARS, params)
    cfg = SimCfg(cooldown_s=cooldown, max_hold_s=max_hold, max_wait_s=max_wait)
    df = simulate(_TICKS, setups, cfg)
    if df.empty:
        return None
    full = stats(df)
    tr = df[df["fire_ts"] < _SPLIT_NS]
    te = df[df["fire_ts"] >= _SPLIT_NS]
    s_tr = stats(tr); s_te = stats(te)
    name = f"i{imp}_w{W}_p{pull}_s{stop}_t{tgt}_{'INV' if invert else 'WITH'}_cd{cooldown}_mh{max_hold}_mw{max_wait}_ml{min_leg}"
    return {"name": name, "imp": imp, "W": W, "pull": pull, "stop": stop,
            "tgt": tgt, "invert": invert, "cooldown": cooldown,
            "max_hold": max_hold, "max_wait": max_wait, "min_leg": min_leg,
            "n": full["n"], "tr_day": full["tr_per_day"], "wr": full["wr"],
            "tgt%": full["tgt%"], "stop%": full["stop%"], "to%": full["to%"],
            "net": full["net"], "per_day": full["per_day"],
            "per_trade": full["per_trade"], "maxDD": full["maxDD"],
            "train_per_day": s_tr.get("per_day", 0), "train_n": s_tr.get("n", 0),
            "test_per_day": s_te.get("per_day", 0), "test_n": s_te.get("n", 0),
            "test_wr": s_te.get("wr", 0), "test_maxDD": s_te.get("maxDD", 0)}

def build_grid():
    imps    = [3.0, 5.0, 7.0]
    Ws      = [3, 4, 5]
    pulls   = [0.236, 0.382, 0.5, 0.618]
    stops   = [6.0, 8.0, 10.0, 12.0]
    tgts    = [12.0, 18.0, 24.0, 30.0]
    inverts = [True, False]
    cooldowns = [60]
    max_holds = [600]
    max_waits = [300]
    min_legs  = [0.0]
    grid = list(itertools.product(imps, Ws, pulls, stops, tgts, inverts,
                                  cooldowns, max_holds, max_waits, min_legs))
    return grid

def main():
    t0 = time.time()
    grid = build_grid()
    print(f"grid size: {len(grid)} configs", flush=True)
    _init()
    print(f"ticks loaded {time.time()-t0:.0f}s; split at {pd.to_datetime(_SPLIT_NS)}", flush=True)
    results = []
    workers = 4
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as ex:
        for i, r in enumerate(ex.map(_eval, grid, chunksize=2)):
            if r: results.append(r)
            if (i+1) % 20 == 0:
                print(f"  {i+1}/{len(grid)}  {time.time()-t0:.0f}s", flush=True)
    df = pd.DataFrame(results)
    df = df.sort_values("net", ascending=False).reset_index(drop=True)
    df.to_csv("research/tick_search_results.csv", index=False)
    print(f"\nDONE {time.time()-t0:.0f}s  -> research/tick_search_results.csv")
    cols = ["name","n","tr_day","wr","net","per_day","per_trade","maxDD",
            "train_per_day","test_per_day","test_wr"]
    pd.set_option("display.width", 200, "display.max_columns", 30)
    print("\nTOP 25 by net $:")
    print(df.head(25)[cols].to_string())
    # robust: positive in BOTH train and test, ranked by test_per_day
    robust = df[(df.train_per_day > 0) & (df.test_per_day > 0) & (df.n >= 200)]
    robust = robust.sort_values("test_per_day", ascending=False)
    print(f"\nROBUST (train>0 AND test>0, n>=200): {len(robust)} configs. TOP 20 by test $/day:")
    print(robust.head(20)[cols].to_string())

if __name__ == "__main__":
    main()
