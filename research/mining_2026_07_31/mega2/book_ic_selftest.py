"""Can book_ic.py find an edge that is definitely there?

A harness that returns "no signal" is only worth believing if it has been
shown to say "signal" when one exists. This builds a synthetic 1-second
book tape with a KNOWN relationship planted in it, runs the real
book_ic.py code paths over it, and checks three things:

  1. the planted feature is detected, with the correct SIGN
  2. the unplanted features read near zero
  3. the shift floor -- the measured noise floor -- sits near zero, and
     the planted IC clears it by the 3x margin the real gate demands

It also plants the trap that would fool a naive harness: a stretch of
missing seconds. If forward returns are computed straight across the
hole, the jump shows up as a huge fake return and inflates everything.
The test asserts the gap does not leak.

Costs nothing, needs no data, and runs in seconds. Run it before
trusting a negative result from the real thing.

    python book_ic_selftest.py
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import book_ic  # noqa: E402

N = 400_000          # seconds of synthetic tape
PLANT_H = 30         # the horizon the edge is planted at
STRENGTH = 0.25      # fraction of the next move explained by imbalance


def synth(seed=5):
    rng = np.random.default_rng(seed)
    # imbalance: autocorrelated, like the real thing
    z = rng.standard_normal(N)
    imb = np.array(pd.Series(z).ewm(span=60).mean().values, dtype=float)
    imb /= max(np.std(imb), 1e-9)

    # price: random walk PLUS a drift proportional to imbalance, so the
    # next PLANT_H seconds move in the direction the book leans
    noise = rng.standard_normal(N) * 0.25
    drift = STRENGTH * 0.25 * imb / PLANT_H
    mid = np.cumsum(noise + drift) + 20000.0
    mid = np.round(mid * 4) / 4.0

    # turn the target imbalance into sizes that reproduce it exactly:
    # imb = (bid - ask)/(bid + ask), so pick a total and split it.
    tot = rng.integers(20, 400, N).astype(np.float64)
    frac = np.clip((np.tanh(imb) + 1) / 2, 0.02, 0.98)
    bid_sz = np.round(tot * frac)
    ask_sz = np.maximum(tot - bid_sz, 1.0)

    sec = np.arange(N, dtype=np.int64) + 1_700_000_000
    # spread must VARY or its rank correlation is undefined and the
    # "unplanted features read zero" check passes without testing
    # anything. One tick most of the time, two now and then.
    half = np.where(rng.random(N) < 0.15, 0.25, 0.125)
    A = pd.DataFrame({
        "sec": sec,
        "bid_px": (mid - half).astype(np.float32),
        "ask_px": (mid + half).astype(np.float32),
        "bid_sz": bid_sz.astype(np.float32),
        "ask_sz": ask_sz.astype(np.float32),
        "n_evt": rng.integers(1, 40, N).astype(np.int32),
        "n_trade": rng.integers(0, 8, N).astype(np.int32),
        "tv_buy": rng.random(N).astype(np.float32) * 10,
        "tv_sell": rng.random(N).astype(np.float32) * 10,
        "bid_depl": rng.random(N).astype(np.float32) * 5,
        "ask_depl": rng.random(N).astype(np.float32) * 5,
        "bid_add": rng.random(N).astype(np.float32) * 5,
        "ask_add": rng.random(N).astype(np.float32) * 5,
    })
    # THE TRAP: punch a 6-hour hole out of the middle, and make the price
    # jump 80 points across it. A harness that differences straight
    # through the gap will read that jump as a 30-second return.
    hole = (A.sec >= sec[N // 2]) & (A.sec < sec[N // 2] + 21_600)
    A.loc[~hole, "bid_px"] = A.loc[~hole, "bid_px"]
    after = A.sec >= sec[N // 2] + 21_600
    A.loc[after, "bid_px"] = A.loc[after, "bid_px"] + 80.0
    A.loc[after, "ask_px"] = A.loc[after, "ask_px"] + 80.0
    A = A[~hole].reset_index(drop=True)
    return A


def main():
    A = synth()
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_selftest_book_1s.parquet")
    A.to_parquet(path, index=False)
    try:
        B = book_ic.load(path)
        F, mid = book_ic.build(B)
        present = B["present"].values
        print(f"tape: {len(B):,} rows on the grid, "
              f"{present.mean():.1%} carrying an event "
              f"(a 6-hour hole was punched out)")

        ok = True
        for h in (5, PLANT_H, 300):
            y = book_ic.forward(mid, present, h)
            sig = float(np.nanstd(y))
            iv = book_ic.ic(F["imb"], y)
            fl = [book_ic.ic(F["imb"], np.roll(y, s))
                  for s in book_ic.SHIFTS]
            floor = float(np.nanstd(fl))
            print(f"\nh={h:4d}s  sigma={sig:6.2f}pt  "
                  f"imb IC={iv:+.4f}  shift floor={floor:.4f}  "
                  f"ratio={abs(iv)/max(floor,1e-9):5.1f}")
            for other in ("spread", "add_skew", "tt_press"):
                print(f"          {other:>10s} IC="
                      f"{book_ic.ic(F[other], y):+.4f}")

            if h == PLANT_H:
                # 1. planted edge found, correct sign, clears the gate
                if not (iv > 0.03 and abs(iv) > 3 * floor):
                    print("  FAIL: planted edge not detected at its own "
                          "horizon")
                    ok = False
                # 2. unrelated features stay near zero
                for other in ("spread", "add_skew", "tt_press"):
                    if abs(book_ic.ic(F[other], y)) > 0.02:
                        print(f"  FAIL: unplanted feature {other} reads "
                              f"non-zero")
                        ok = False
                # 3. the gap did not leak. An 80pt jump smuggled into a
                #    30s window would blow sigma far past a real one.
                if sig > 5.0:
                    print(f"  FAIL: sigma {sig:.2f}pt at {h}s implies the "
                          f"6-hour gap leaked into forward returns")
                    ok = False
            if floor > 0.02:
                print(f"  FAIL: shift floor {floor:.4f} is not near zero")
                ok = False

        print("\n" + ("PASS -- the harness finds a planted edge, ignores "
                      "unplanted features, and does not difference across "
                      "a feed hole." if ok else
                      "FAIL -- do not trust a negative result from "
                      "book_ic.py until this passes."))
        return 0 if ok else 1
    finally:
        if os.path.exists(path):
            os.remove(path)


if __name__ == "__main__":
    sys.exit(main())
