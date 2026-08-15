"""The level definition the LIVE strategy actually used.

The 14,400-cell search tested only close-to-close levels
(level = close - retr*(close[i]-close[i-w])). The deployed bot and the
user's original 2025 spec use a DIFFERENT level: a fib retracement of
the wick RANGE, with the impulse measured close-minus-open:

    net   = close[i] - open[i-w+1]
    level = high(window) - retr*(high-low)      (up impulse)
            low(window)  + retr*(high-low)      (down impulse)

Those are different prices, so none of the previous verdicts apply to
them. This runs the range anchor head-to-head with the close anchor,
on the user's original cell and the deployed cell, under the same
assumption-attack variants as DEEP_DIVE, all 8 NQ quarters.

Output: research/RANGE_ANCHOR.md
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse                  # noqa: E402
import causal_engine as ce   # noqa: E402

CELLS = {
    "ORIGINAL 2025 spec (5pt/4bar, .618, S6 T12)":
        dict(imp=5.0, w=4, retr=0.618, S=6.0, T=12.0, hold_s=600),
    "deployed cell (5pt/6bar, .618, S10 T20)":
        dict(imp=5.0, w=6, retr=0.618, S=10.0, T=20.0, hold_s=600),
}
VARIANTS = [
    ("baseline", dict()),
    ("touch entries+targets", dict(entry_touch=True, target_touch=True)),
    ("lockout=exit+60s (real bot)", dict(lockout="exit")),
    ("no lockout (multi-position)", dict(lockout="none")),
    ("membership comm $0.36", dict(comm=0.36)),
    ("CEILING: touch/touch/none/zero cost",
     dict(entry_touch=True, target_touch=True, lockout="none",
          comm=0.0, slip_on=False)),
]
BASE = dict(arch="limit", policy="first", tick=0.25, tv=2.0)


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    acc = {(cn, an, vn): [0.0, 0, 0]
           for cn in CELLS for an in ("close", "range")
           for vn, _ in VARIANTS}
    for q in cons:
        ts, px, _ = fuse.load_tape(meta[q]["path"])
        o = np.argsort(ts, kind="stable")
        ts, px = ts[o], px[o]
        bt, bo, bh, bl, bc, rth = ce.bars_ohlc(ts, px)
        mi = ce.MinuteIndex(ts, px, bt)
        for cname, cp in CELLS.items():
            for an in ("close", "range"):
                for vn, vp in VARIANTS:
                    cell = {**BASE, **cp, **vp, "anchor": an}
                    if an == "range":
                        cell.update(bo=bo, bh=bh, bl=bl)
                    tr = ce.run_cell(ts, px, bt, bc, rth, 0, len(bc),
                                     cell, mindex=mi)
                    a = acc[(cname, an, vn)]
                    a[0] += sum(t[4] for t in tr)
                    a[1] += len(tr)
                    a[2] += sum(1 for t in tr if t[4] > 0)
        del ts, px, bt, bo, bh, bl, bc, rth, mi
        import gc
        gc.collect()
        print(f"{q} done", flush=True)

    L = ["# The level definition the live strategy actually used", "",
         "`range` = fib retracement of the wick range with a "
         "close-minus-open impulse (what bot/pullback_strategy.py runs "
         "and what the 2025 spec described). `close` = close-to-close "
         "(what the 14,400-cell search tested). All 8 NQ quarters.", ""]
    for cname in CELLS:
        L += [f"## {cname}", "",
              "| variant | anchor | trades | win rate | $/trade | "
              "**total** |", "|---|---|---|---|---|---|"]
        print(f"\n=== {cname}", flush=True)
        for vn, _ in VARIANTS:
            for an in ("close", "range"):
                tot, n, wins = acc[(cname, an, vn)]
                per = tot / n if n else 0.0
                wr = wins / n if n else 0.0
                L.append(f"| {vn} | **{an}** | {n:,} | {wr:.1%} | "
                         f"${per:+.2f} | **${tot:+,.0f}** |")
                print(f"  {vn:34} {an:5} {n:6,}tr {wr:5.1%} "
                      f"${per:+6.2f}/tr ${tot:+10,.0f}", flush=True)
        L.append("")
    out = os.path.join(fuse.ROOT, "research", "RANGE_ANCHOR.md")
    open(out, "w").write("\n".join(L) + "\n")
    print("\nwrote", out, flush=True)


if __name__ == "__main__":
    main()
