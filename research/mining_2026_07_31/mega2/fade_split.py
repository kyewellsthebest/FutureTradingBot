"""Is the range-anchored FADE edge real, or wrong-side-of-book fills?

The premise matrix showed the fade clearing breakeven only with the
range anchor at shallow retracements (0.236 -> 37.2%, 0.382 -> 31.4%,
0.618 -> 25.8%), while the close anchor showed no such gradient. The
range level is pinned near the wick HIGH, so it frequently sits ABOVE
the current price -- and the matrix's fill rule ("tape prints below
the level") is then satisfied by the very first tick, booking a SHORT
at a price the market has already left behind.

This splits every fade signal into the two executable cases and
prices each honestly:

  ABOVE  level is above the market at signal time. A sell limit CAN
         rest there. It fills only when the tape trades UP to it.
         Entry = the level. This is a legitimate resting limit.
  BELOW  level is below the market. A sell limit there would execute
         instantly at the higher bid, so the only way in is a market
         order when price touches. Entry = the triggering print.

If the "edge" lives in ABOVE-with-instant-fill accounting, it vanishes
once ABOVE requires an actual upward trade to the level.

Output: research/FADE_SPLIT.md
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuse  # noqa: E402

IMP = 5.0
S, T = 10.0, 20.0
TV, TICK, COMM = 2.0, 0.25, 1.24
HZ = 600 * 1_000_000_000
CFGS = [(6, 0.236), (4, 0.236), (6, 0.382), (6, 0.618)]


def main():
    meta = fuse.tape_meta()
    cons = [c for c in fuse.NQ_CONTRACTS if c in meta]
    acc = {(w, r, k): {"t": 0, "s": 0, "o": 0, "n": 0}
           for (w, r) in CFGS for k in ("ABOVE", "BELOW", "matrix")}
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

        def walk(f, entry, side, jend):
            seg = px[f:jend]
            sp, tp = entry - side * S, entry + side * T
            if side > 0:
                si = np.flatnonzero(seg <= sp)
                ti = np.flatnonzero(seg >= tp)
            else:
                si = np.flatnonzero(seg >= sp)
                ti = np.flatnonzero(seg <= tp)
            sa = si[0] if len(si) else 10**9
            ta = ti[0] if len(ti) else 10**9
            return "t" if ta < sa else ("s" if sa < 10**9 else "o")

        for (w, r) in CFGS:
            for i in range(w + 1, len(bc)):
                if not rth[i]:
                    continue
                move = bc[i] - bo[i - w + 1]
                if abs(move) < IMP:
                    continue
                hi_ = bh[i - w + 1:i + 1].max()
                lo_ = bl[i - w + 1:i + 1].min()
                rg = hi_ - lo_
                if rg <= 0:
                    continue
                up = move > 0
                lvl = float((hi_ - r * rg) if up else (lo_ + r * rg))
                bclose = bt[i] + 60_000_000_000
                j0 = np.searchsorted(ts, bclose)
                jend = np.searchsorted(ts, bclose + HZ)
                if j0 >= jend:
                    continue
                seg = px[j0:jend]
                p0 = float(px[j0])
                side = -1 if up else 1          # FADE
                # --- what the matrix did: approach from the impulse
                # side, instant fill at the level ---
                hit = np.flatnonzero(seg < lvl) if up else \
                    np.flatnonzero(seg > lvl)
                if len(hit):
                    a = acc[(w, r, "matrix")]
                    a[walk(j0 + hit[0], lvl, side, jend)] += 1
                    a["n"] += 1
                # --- honest split ---
                if (up and lvl > p0) or ((not up) and lvl < p0):
                    # level on the far side of the market: a limit CAN
                    # rest here; it fills only if the tape trades TO it
                    h2 = np.flatnonzero(seg >= lvl) if up else \
                        np.flatnonzero(seg <= lvl)
                    if len(h2):
                        a = acc[(w, r, "ABOVE")]
                        a[walk(j0 + h2[0], lvl, side, jend)] += 1
                        a["n"] += 1
                else:
                    # level already behind the market: market order at
                    # the touch, entry = the triggering print
                    if len(hit):
                        f = j0 + hit[0]
                        a = acc[(w, r, "BELOW")]
                        a[walk(f, float(px[f]), side, jend)] += 1
                        a["n"] += 1
        del ts, px, bo, bh, bl, bcs
        import gc
        gc.collect()
        print(f"{cn} done", flush=True)

    def ev(d):
        n = max(d["n"], 1)
        return (d["t"] * T * TV + d["s"] * (-(S + TICK) * TV)
                + d["o"] * (-TICK * TV)) / n - COMM

    be = ((S + TICK) * TV + COMM) / (T * TV + (S + TICK) * TV + COMM)
    L = ["# Is the range-anchored FADE edge real, or wrong-side fills?",
         "",
         f"NQ, 8 quarters, FADE direction, bracket {S:.0f}/{T:.0f}, "
         f"breakeven **{be:.1%}** target-first.", "",
         "- **matrix** = what the premise matrix measured (instant fill "
         "at the level when the tape prints past it)",
         "- **ABOVE** = level on the far side of the market: a resting "
         "limit is legitimate, and must be reached by an actual trade",
         "- **BELOW** = level already behind the market: market order, "
         "entry at the triggering print", "",
         "| w | retr | case | n | target first | EV/trade |",
         "|---|---|---|---|---|---|"]
    for (w, r) in CFGS:
        for k in ("matrix", "ABOVE", "BELOW"):
            d = acc[(w, r, k)]
            n = max(d["n"], 1)
            L.append(f"| {w} | {r} | {k} | {d['n']:,} | "
                     f"{d['t']/n:.2%} | ${ev(d):+.2f} |")
    L.append("")
    out = os.path.join(fuse.ROOT, "research", "FADE_SPLIT.md")
    open(out, "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
