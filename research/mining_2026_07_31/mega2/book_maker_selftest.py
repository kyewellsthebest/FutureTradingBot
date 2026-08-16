"""Four hand-checkable cases for the maker queue model.

The fill model in book_maker.py decides whether the HFT lane is
buildable, so it does not get to be plausible -- it has to reproduce
answers that can be worked out on paper. Each case below has one
obviously correct outcome.

  1  queue of 10, one contract a second trades through
     -> fills after exactly 10 seconds
  2  queue of 500, same rate
     -> never fills inside the 120-second horizon
  3  the bid ticks DOWN every 3 seconds, queue of 10
     -> the level always leaves before the queue clears: no fills
  4  fill, then the market moves up a tick
     -> the mark reads positive

Case 3 is the one that caught a bad test the first time round. Dropping
the price ONCE looks like it should produce all breaks, but every join
after the drop rests at the NEW price, which never falls again, so those
fills are correct and the test was wrong. A departing level has to keep
departing.

    python book_maker_selftest.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import book_maker as bm  # noqa: E402

N = 600


def tape(bid_sz, tv_sell, bp):
    n = len(bp)
    return pd.DataFrame({
        "sec": np.arange(n, dtype=np.int64) + 1_700_000_000,
        "bid_px": bp.astype(np.float32),
        "ask_px": (bp + 0.25).astype(np.float32),
        "bid_sz": np.full(n, bid_sz, dtype=np.float32),
        "ask_sz": np.full(n, 50, dtype=np.float32),
        "n_evt": np.ones(n, np.int32), "n_trade": np.ones(n, np.int32),
        "tv_buy": np.zeros(n, np.float32),
        "tv_sell": np.full(n, tv_sell, dtype=np.float32),
        "bid_depl": np.zeros(n, np.float32),
        "ask_depl": np.zeros(n, np.float32),
        "bid_add": np.zeros(n, np.float32),
        "ask_add": np.zeros(n, np.float32)})


def go(name, bid_sz, tv_sell, bp):
    p = f"/tmp/_maker_{name}.parquet"
    tape(bid_sz, tv_sell, bp).to_parquet(p, index=False)
    try:
        r, _ = bm.run(p, name)
        return r
    finally:
        os.remove(p)


def main():
    ok = True
    flat = np.full(N, 100.0)

    r = go("t1", 10, 1.0, flat)
    w = np.median(r[30]["wait"]) if r[30]["wait"] else float("nan")
    print(f"1) queue=10 rate=1/s      -> {r[30]['fill']} fills, "
          f"median wait {w:.0f}s (expect 10)")
    ok &= w == 10

    r = go("t2", 500, 1.0, flat)
    print(f"2) queue=500 rate=1/s     -> {r[120]['fill']} fills, "
          f"{r[120]['open']} open (expect 0 fills)")
    ok &= r[120]["fill"] == 0

    down = 100.0 - 0.25 * (np.arange(N) // 3)
    r = go("t3", 10, 1.0, down)
    print(f"3) bid ticks down each 3s -> {r[30]['fill']} fills, "
          f"{r[30]['break']} breaks (expect 0 fills)")
    ok &= r[30]["fill"] == 0 and r[30]["break"] > 0

    up = np.concatenate([np.full(300, 100.0), np.full(N - 300, 100.25)])
    r = go("t4", 10, 1.0, up)
    m = r[30]["ticks"][60]
    print(f"4) +1 tick after fill     -> mean mark {np.mean(m):+.2f} tk "
          f"over {len(m)} fills (expect positive)")
    ok &= len(m) > 0 and np.mean(m) > 0

    print("\n" + ("PASS -- the queue model reproduces all four "
                  "hand-checkable answers." if ok else
                  "FAIL -- do not trust BOOK_MAKER.md until this passes."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
