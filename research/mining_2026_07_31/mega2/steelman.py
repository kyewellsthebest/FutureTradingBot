"""STEELMAN: try to prove the strategy DOES work.

Every judgement call set to the most strategy-favourable value that is
still physically real, plus a correction of a genuine error in my own
harness:

  FIXED  separate expiry and hold. The spec says a setup expires after
         5 min unfilled, and once FILLED you hold 10 min FROM ENTRY.
         Earlier tests used one 10-min window covering both, so a late
         fill got only the remainder. That was unfair to the strategy.
  entry  fills on a TOUCH of the level (best case for a resting limit)
  target fills on a TOUCH (best case)
  stop   requires a print strictly THROUGH the level (best case --
         wick touches do not stop you out)
  costs  ZERO commission, ZERO slippage
  dirs   continuation AND fade
  levels close-to-close AND the live bot's fib-of-range
  depths 0.236 / 0.382 / 0.5 / 0.618, impulse windows 4 and 6

Executability is still enforced: a resting limit only fills if the
tape trades to its price from the correct side; where the level sits
on the wrong side of the market for the trade's direction, the entry
is a market order priced at the triggering print.

If every row is negative under zero costs and best-case fills, no
execution, broker or commission structure can rescue this family.

Output: research/STEELMAN.md
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

IMP = 5.0
S, T = 10.0, 20.0
TV = 2.0
EXPIRY_NS = 300 * 1_000_000_000     # 5 min to fill
HOLD_NS = 600 * 1_000_000_000       # 10 min from ENTRY
CFGS = [(w, r, d, a)
        for w in (4, 6)
        for r in (0.236, 0.382, 0.5, 0.618)
        for d in ("cont", "fade")
        for a in ("close", "range")]


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    acc = {c: {"t": 0, "s": 0, "o": 0, "n": 0} for c in CFGS}
    for cn in cons:
        ts, px, _ = fuse.load_tape(meta[cn]["path"])
        o_ = np.argsort(ts, kind="stable")
        ts, px = ts[o_], px[o_]
        idx = pd.to_datetime(ts)
        g = pd.Series(px, index=idx).resample("1min")
        bo = g.first().ffill().values
        bh = g.max().ffill().values
        bl = g.min().ffill().values
        bcs = g.last().ffill()
        bt = bcs.index.view(np.int64)
        bc = bcs.values
        rth = np.asarray((bcs.index.hour * 60 + bcs.index.minute
                          >= 13 * 60 + 30) & (bcs.index.hour < 20))

        for (w, r, d, a) in CFGS:
            cnt = acc[(w, r, d, a)]
            for i in range(w + 1, len(bc)):
                if not rth[i]:
                    continue
                if a == "range":
                    move = bc[i] - bo[i - w + 1]
                    hi_ = bh[i - w + 1:i + 1].max()
                    lo_ = bl[i - w + 1:i + 1].min()
                    rg = hi_ - lo_
                    if rg <= 0:
                        continue
                    lvl = float((hi_ - r * rg) if move > 0
                                else (lo_ + r * rg))
                else:
                    move = bc[i] - bc[i - w]
                    lvl = float(bc[i] - r * move)
                if abs(move) < IMP:
                    continue
                up = move > 0
                side = (1 if up else -1) * (1 if d == "cont" else -1)
                bclose = bt[i] + 60_000_000_000
                j0 = np.searchsorted(ts, bclose)
                jx = np.searchsorted(ts, bclose + EXPIRY_NS)
                if j0 >= jx:
                    continue
                seg = px[j0:jx]
                p0 = float(px[j0])
                if side > 0:                     # buying
                    if lvl <= p0:                # limit rests below
                        hit = np.flatnonzero(seg <= lvl)
                        at_level = True
                    else:                        # wrong side: market
                        hit = np.flatnonzero(seg >= lvl)
                        at_level = False
                else:                            # selling
                    if lvl >= p0:                # limit rests above
                        hit = np.flatnonzero(seg >= lvl)
                        at_level = True
                    else:
                        hit = np.flatnonzero(seg <= lvl)
                        at_level = False
                if not len(hit):
                    continue
                f = j0 + hit[0]
                entry = lvl if at_level else float(px[f])
                jend = np.searchsorted(ts, ts[f] + HOLD_NS)
                rest = px[f:jend]
                sp, tp = entry - side * S, entry + side * T
                if side > 0:
                    si = np.flatnonzero(rest < sp)     # STRICT stop
                    ti = np.flatnonzero(rest >= tp)    # touch target
                else:
                    si = np.flatnonzero(rest > sp)
                    ti = np.flatnonzero(rest <= tp)
                sa = si[0] if len(si) else 10**9
                ta = ti[0] if len(ti) else 10**9
                k = "t" if ta < sa else ("s" if sa < 10**9 else "o")
                cnt[k] += 1
                cnt["n"] += 1
        del ts, px, bo, bh, bl, bcs
        import gc
        gc.collect()
        print(f"{cn} done", flush=True)

    L = ["# STEELMAN: the strategy under best-case honest assumptions",
         "",
         "5-min setup expiry, **10-min hold from ENTRY** (earlier tests "
         "wrongly shared one 10-min window between waiting and "
         "holding), entries and targets fill on a TOUCH, stops require "
         "a print strictly THROUGH the level, and **zero commission, "
         "zero slippage**. Resting limits still require the tape to "
         "reach them from the correct side.", "",
         "| w | retr | dir | anchor | n | target first | stop | "
         "neither | **EV/trade (zero cost)** |", "|" + "---|" * 9]
    best = None
    for c in CFGS:
        d = acc[c]
        n = max(d["n"], 1)
        ev = (d["t"] * T * TV - d["s"] * S * TV) / n
        L.append(f"| {c[0]} | {c[1]} | {c[2]} | {c[3]} | {d['n']:,} | "
                 f"{d['t']/n:.2%} | {d['s']/n:.2%} | {d['o']/n:.2%} | "
                 f"**${ev:+.2f}** |")
        if best is None or ev > best[0]:
            best = (ev, c, d["t"] / n, d["n"])
    L += ["", f"Best: {best[1][2]} w={best[1][0]} retr={best[1][1]} "
          f"anchor={best[1][3]} -> **${best[0]:+.2f}/trade** at zero "
          f"cost ({best[2]:.2%} target-first, {best[3]:,} trades).",
          "", "A positive row here is a real candidate and gets the "
          "full validation. Every row negative means no cost structure "
          "or execution quality can make this family profitable.", ""]
    out = os.path.join(fuse.ROOT, "research", "STEELMAN.md")
    open(out, "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
